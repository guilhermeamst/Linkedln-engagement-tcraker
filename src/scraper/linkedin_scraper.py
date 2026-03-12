"""
linkedin_scraper.py - Robô de coleta de dados do LinkedIn.

Estratégia: navega até a página de admin de posts da empresa e coleta
reações, comentários e compartilhamentos via modais / expansão inline
— sem sair da página.

URL alvo: https://www.linkedin.com/company/{ID}/admin/page-posts/published/
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import date, datetime
from typing import Callable, Generator, List, Optional, Tuple

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.core.config import LinkedInConfig, ScraperConfig
from src.core.logger import get_logger
from src.models.engagement import Engagement, TipoInteracao
from src.models.post import Post

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Seletores CSS — centralizados para fácil manutenção
# --------------------------------------------------------------------------- #

class _Selectors:
    # Login
    EMAIL_INPUT    = 'input[name="session_key"]'
    PASSWORD_INPUT = 'input[name="session_password"]'
    LOGIN_BUTTON   = 'button[type="submit"]'

    # Cards de post na página de admin.
    # Usa ^= (começa com) para evitar pegar elementos aninhados (comentários,
    # reshares internos) que também têm data-urn contendo "activity".
    POST_CARD = (
        "div[data-urn^='urn:li:activity:'], "
        "li[data-urn^='urn:li:activity:'], "
        "div[data-urn^='urn:li:ugcPost:'], "
        "li[data-urn^='urn:li:ugcPost:']"
    )

    # Botão de reações (contagem clicável na área de social counts)
    REACTIONS_BUTTON = (
        "button.social-details-social-counts__reactions-count, "
        "button[aria-label*='reação'], "
        "button[aria-label*='reaction'], "
        "li.social-details-social-counts__reactions button, "
        "span.social-counts-reactions__count-value button, "
        "button.social-counts-reactions__count-value"
    )

    # Modal genérico (reações e shares)
    REACTIONS_MODAL = (
        "div.artdeco-modal__content, "
        "div[class*='artdeco-modal__content']"
    )

    # Itens dentro do modal de reações
    REACTION_ITEM = (
        "li.social-details-reactors-tab-body-list-item, "
        "li.reacted-list__reaction-item, "
        "li[class*='reactor'], "
        "li[class*='reacted']"
    )

    # Nome do usuário no item de reação
    REACTION_USER_NAME = (
        "span.artdeco-entity-lockup__title, "
        "span[class*='entity-lockup__title']"
    )

    # Aba "Todos" no modal de reações
    # Playwright aceita :has-text() para match por conteúdo de texto
    REACTIONS_ALL_TAB = (
        "button[aria-label*='Todos'], "
        "button[aria-label*='All reactions'], "
        "button[role='tab']:has-text('Todos'), "
        "button[role='tab']:has-text('All'), "
        "li[data-tab='ALL'] button, "
        "div[role='tab']:has-text('Todos'), "
        "div[role='tab']:has-text('All')"
    )

    # Botão que EXPANDE os comentários (count clicável na área de social counts)
    COMMENT_COUNT_BUTTON = (
        "li.social-details-social-counts__comments button, "
        "button[aria-label*='comentário'], "
        "button[aria-label*='comment'], "
        "a[class*='social-counts__num-comments'], "
        "button.social-details-social-counts__num-comments"
    )

    # Botão de ação "Comentar" na action bar (abre a seção de comentários)
    COMMENT_ACTION_BUTTON = (
        "button[aria-label='Comentar'], "
        "button[aria-label='Comment'], "
        "button.comment-button, "
        "li.comment-button button"
    )

    # Itens de comentário após expansão
    COMMENT_ITEM = (
        "article.comments-comment-item, "
        "div.comments-comment-item, "
        "article[class*='comment-item'], "
        "li[class*='comment-item'], "
        "[class*='comments-comment-item'], "
        "li[data-comment-id], "
        "div[data-comment-id]"
    )

    # Nome do comentarista
    COMMENTER_NAME = (
        "span.comments-post-meta__name-text, "
        "span[class*='post-meta__name'], "
        "span[class*='commenter-name']"
    )

    # "Carregar mais comentários"
    LOAD_MORE_COMMENTS = (
        "button.comments-comments-list__load-more-comments-button, "
        "button[class*='load-more-comments'], "
        "button[aria-label*='mais comentário'], "
        "button[aria-label*='more comment']"
    )

    # Botão de compartilhamentos / reposts (count clicável)
    SHARES_BUTTON = (
        "li.social-details-social-counts__reshares button, "
        "button[aria-label*='repost'], "
        "button[aria-label*='compartilhamento'], "
        "button[class*='reshares'], "
        "button[aria-label*='Repost']"
    )

    # Fechar modal
    MODAL_CLOSE = (
        "button[aria-label='Descartar'], "
        "button[aria-label='Dismiss'], "
        "button[aria-label='Fechar'], "
        "button[aria-label='Close'], "
        "button.artdeco-modal__dismiss"
    )


# --------------------------------------------------------------------------- #
#  Funções utilitárias
# --------------------------------------------------------------------------- #

# Nome da empresa — comentários dela nos próprios posts são ignorados
_EMPRESA_EXCLUIR = "armco do brasil"


def _gerar_hash_usuario(profile_url: str) -> str:
    clean = profile_url.split("?")[0].rstrip("/")
    return hashlib.md5(clean.encode()).hexdigest()[:16]


def _limpar_nome(texto: str) -> str:
    PARASITAS = [
        r"ver perfil", r"view profile", r"out of network",
        r"seguir", r"follow", r"connect", r"conectar",
        r"mensagem", r"message", r"•\s*\d+[a-z]+", r"\d+[a-z]+\s*\+",
    ]
    linhas = [l.strip() for l in texto.split("\n")]
    limpas = [
        l for l in linhas
        if l and not any(re.search(p, l, re.IGNORECASE) for p in PARASITAS)
    ]
    return limpas[0] if limpas else texto.strip()


def _extrair_post_id_da_urn(urn: str) -> Optional[str]:
    """Extrai o ID numérico de uma URN LinkedIn: 'urn:li:activity:123' → '123'."""
    m = re.search(r"activity[:\-](\d+)", urn)
    if m:
        return m.group(1)
    m = re.search(r"ugcPost[:\-](\d+)", urn)
    if m:
        return m.group(1)
    digits = re.findall(r"\d{10,}", urn)
    return digits[-1] if digits else None


def _parse_data_relativa(texto: str) -> Optional[date]:
    from datetime import timedelta
    hoje = date.today()
    texto = texto.lower().strip()

    padroes = [
        (r"(\d+)\s*(segundo|minuto|hora)",  lambda n: hoje),
        (r"(\d+)\s*(dia|dias)",              lambda n: hoje - timedelta(days=int(n))),
        (r"(\d+)\s*(semana|semanas)",        lambda n: hoje - timedelta(weeks=int(n))),
        (r"(\d+)\s*(m[eê]s|meses)",         lambda n: hoje - timedelta(days=int(n) * 30)),
        (r"(\d+)\s*(ano|anos)",              lambda n: hoje - timedelta(days=int(n) * 365)),
    ]
    for padrao, conv in padroes:
        m = re.search(padrao, texto)
        if m:
            return conv(m.group(1))

    meses = {
        "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
        "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
        "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    try:
        m = re.search(r"(\d{1,2})\s+de\s+(\w+)\.?\s+de\s+(\d{4})", texto)
        if m:
            dia, mes_str, ano = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            mes = meses.get(mes_str[:3]) or meses.get(mes_str)
            if mes:
                return date(ano, mes, dia)

        m = re.search(r"(\w+)\.?\s+de\s+(\d{4})", texto)
        if m:
            mes_str, ano = m.group(1).lower(), int(m.group(2))
            mes = meses.get(mes_str[:3]) or meses.get(mes_str)
            if mes:
                return date(ano, mes, 1)

        m = re.search(r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})", texto)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except (ValueError, KeyError):
        pass

    return None


def _extrair_numero(texto: str) -> int:
    """Extrai o primeiro número inteiro de uma string. Retorna 0 se não achar."""
    m = re.search(r"(\d[\d\.,]*)", texto)
    if not m:
        return 0
    return int(re.sub(r"[^\d]", "", m.group(1)) or "0")


def _coletar_links_de_perfil(container, hrefs_vistos: set) -> List[Tuple[str, str]]:
    """
    Coleta todos os links de perfil (/in/ e /company/) dentro de um container,
    ignorando hrefs já vistos. Retorna lista de (href, nome).
    """
    resultados = []
    # Perfis pessoais e páginas de empresa
    for seletor in ["a[href*='/in/']", "a[href*='/company/']"]:
        try:
            for link in container.locator(seletor).all():
                try:
                    href = (link.get_attribute("href") or "").split("?")[0].rstrip("/")
                    if not href or href in hrefs_vistos:
                        continue
                    nome = _limpar_nome(link.inner_text())
                    if not nome:
                        continue
                    hrefs_vistos.add(href)
                    resultados.append((href, nome))
                except Exception:
                    continue
        except Exception:
            continue
    return resultados


# --------------------------------------------------------------------------- #
#  Scraper principal
# --------------------------------------------------------------------------- #

class LinkedInScraper:
    """
    Coleta engajamentos dos posts da empresa diretamente na página de admin.
    Não navega para URLs individuais dos posts — tudo via modais / expansão inline.
    """

    def __init__(self, linkedin_config: LinkedInConfig, scraper_config: ScraperConfig) -> None:
        self._cfg = linkedin_config
        self._scraper_cfg = scraper_config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ------------------------------------------------------------------ #
    #  Gerenciamento de contexto
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "LinkedInScraper":
        self._iniciar_browser()
        return self

    def __exit__(self, *_) -> None:
        self._encerrar_browser()

    def _iniciar_browser(self) -> None:
        logger.info("Iniciando browser Playwright...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._cfg.headless,
            slow_mo=self._cfg.slow_mo_ms,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
        """)
        self._page = self._context.new_page()
        logger.info("Browser iniciado.")

    def _encerrar_browser(self) -> None:
        try:
            if self._page:    self._page.close()
            if self._context: self._context.close()
            if self._browser: self._browser.close()
            if self._playwright: self._playwright.stop()
            logger.info("Browser encerrado.")
        except Exception as e:
            logger.error("Erro ao encerrar browser: %s", e)

    # ------------------------------------------------------------------ #
    #  Login
    # ------------------------------------------------------------------ #

    def login(self) -> bool:
        assert self._page is not None
        logger.info("Iniciando login no LinkedIn...")

        for tentativa in range(1, self._scraper_cfg.retry_attempts + 1):
            try:
                self._page.goto("https://www.linkedin.com/login", wait_until="networkidle")
                self._aguardar_aleatoriamente(1.0, 2.0)
                self._page.fill(_Selectors.EMAIL_INPUT, self._cfg.email)
                self._aguardar_aleatoriamente(0.3, 0.8)
                self._page.fill(_Selectors.PASSWORD_INPUT, self._cfg.password)
                self._aguardar_aleatoriamente(0.5, 1.0)
                self._page.click(_Selectors.LOGIN_BUTTON)

                try:
                    self._page.wait_for_url(
                        lambda url: "linkedin.com/login" not in url,
                        timeout=self._scraper_cfg.wait_timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    pass

                self._page.wait_for_load_state("domcontentloaded", timeout=15000)
                self._aguardar_aleatoriamente(2.0, 3.0)
                url = self._page.url

                if "checkpoint" in url or "challenge" in url:
                    if not self._cfg.headless:
                        logger.info("Desafio detectado. Complete manualmente (60s)...")
                        time.sleep(60)
                        url = self._page.url
                    else:
                        raise RuntimeError("Desafio de segurança. Use --mostrar-browser.")

                if any(t in url for t in ("feed", "mynetwork", "home", "jobs", "notifications", "messaging", "in/")):
                    logger.info("Login bem-sucedido. URL: %s", url)
                    return True

                if "login" in url:
                    raise RuntimeError("Permaneceu na página de login. Verifique as credenciais.")

                logger.warning("URL inesperada após login: %s — assumindo sucesso.", url)
                return True

            except PlaywrightTimeoutError:
                logger.warning("Timeout no login (tentativa %d/%d).", tentativa, self._scraper_cfg.retry_attempts)
                if tentativa == self._scraper_cfg.retry_attempts:
                    raise RuntimeError("Timeout ao fazer login.")
                time.sleep(5 * tentativa)

        raise RuntimeError("Falha ao fazer login.")

    # ------------------------------------------------------------------ #
    #  Coleta de Posts (loop principal)
    # ------------------------------------------------------------------ #

    def coletar_posts(
        self,
        deve_pular: Optional[Callable[[str, int, int, int], bool]] = None,
    ) -> Generator[Tuple[Post, List[Engagement]], None, None]:
        """
        Fica na página de admin de posts e coleta engajamentos via modais.
        Não navega para URLs individuais de posts.

        Args:
            deve_pular: callable opcional (post_id, total_r, total_c, total_s → bool).
                        Se retornar True, o post é ignorado (já processado e sem
                        mudanças de contagem).
        """
        assert self._page is not None

        m = re.search(r"/company/([^/]+)", self._cfg.company_page_url)
        company_id = m.group(1) if m else None

        if company_id:
            url_admin = f"https://www.linkedin.com/company/{company_id}/admin/page-posts/published/"
        else:
            base = re.sub(r"/posts/.*", "", self._cfg.company_page_url.rstrip("/"))
            url_admin = base + "/posts/"

        logger.info("Acessando página de admin: %s", url_admin)
        self._page.goto(url_admin, wait_until="domcontentloaded")
        self._aguardar_aleatoriamente(4.0, 6.0)

        urns_processados: set = set()
        total_processados  = 0
        scroll_sem_novos   = 0
        posts_fora_periodo = 0

        while total_processados < self._scraper_cfg.max_posts:

            proximo_card = None
            proximo_urn  = None

            try:
                cards = self._page.locator(_Selectors.POST_CARD).all()
                for card in cards:
                    try:
                        urn = (
                            card.get_attribute("data-urn") or
                            card.get_attribute("data-id") or ""
                        )
                        if urn and urn not in urns_processados:
                            proximo_card = card
                            proximo_urn  = urn
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug("Erro ao listar cards: %s", e)

            if not proximo_card or not proximo_urn:
                scroll_sem_novos += 1
                if scroll_sem_novos >= 3:
                    logger.info("3 scrolls sem novos posts. Fim do feed.")
                    break
                logger.debug("Sem novos cards visíveis. Rolando... (%d/3)", scroll_sem_novos)
                self._scroll_para_mais_posts()
                self._aguardar_aleatoriamente(
                    self._scraper_cfg.delay_between_pages_s * 1.5,
                    self._scraper_cfg.delay_between_pages_s * 3.0,
                )
                continue

            scroll_sem_novos = 0
            urns_processados.add(proximo_urn)

            post_id  = _extrair_post_id_da_urn(proximo_urn) or hashlib.md5(proximo_urn.encode()).hexdigest()[:16]
            act_id   = _extrair_post_id_da_urn(proximo_urn)
            url_post = (
                f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/"
                if act_id else
                f"https://www.linkedin.com/feed/update/{proximo_urn}/"
            )

            data_post = self._extrair_data_do_card(proximo_card)

            if data_post and data_post < self._scraper_cfg.data_inicio:
                posts_fora_periodo += 1
                logger.info(
                    "Post %s em %s — anterior a %s (%d/3).",
                    post_id, data_post, self._scraper_cfg.data_inicio, posts_fora_periodo,
                )
                if posts_fora_periodo >= 3:
                    logger.info("3 posts fora do período. Encerrando.")
                    break
                total_processados += 1
                continue
            else:
                if data_post is not None:
                    posts_fora_periodo = 0

            # Lê totais exibidos no card (mais precisos que contar nomes coletados,
            # pois alguns perfis privados não aparecem no modal)
            total_reactions, total_comments, total_shares = self._extrair_totais_do_card(proximo_card)

            # Pula post se já está no banco E os totais não mudaram
            if deve_pular and deve_pular(post_id, total_reactions, total_comments, total_shares):
                logger.info(
                    "[skip] Post %s — já no banco com mesmos totais (r=%d c=%d s=%d). Pulando.",
                    post_id, total_reactions, total_comments, total_shares,
                )
                total_processados += 1
                continue

            post = Post(
                post_id=post_id,
                url_post=url_post,
                data_post=data_post,
                total_likes=total_reactions,
                total_comentarios=total_comments,
                total_shares=total_shares,
            )

            logger.info(
                "[%d/%d] Post %s (%s) — r:%d c:%d s:%d",
                total_processados + 1, self._scraper_cfg.max_posts,
                post_id, data_post or "?",
                total_reactions, total_comments, total_shares,
            )

            try:
                engagements = self._coletar_engajamentos_do_card(post, proximo_card)
            except Exception as exc:
                logger.error("Erro ao coletar engajamentos do post %s: %s", post_id, exc, exc_info=True)
                engagements = []

            total_processados += 1
            yield post, engagements

            self._aguardar_aleatoriamente(
                self._scraper_cfg.delay_between_posts_s,
                self._scraper_cfg.delay_between_posts_s * 1.5,
            )

        logger.info("Coleta finalizada. Total: %d posts.", total_processados)

    # ------------------------------------------------------------------ #
    #  Coleta de engajamentos — dentro do card, via modais
    # ------------------------------------------------------------------ #

    def _coletar_engajamentos_do_card(self, post: Post, card) -> List[Engagement]:
        """Coleta reações, comentários e shares de um card sem sair da página."""
        reactions: List[Engagement] = []
        comments:  List[Engagement] = []
        shares:    List[Engagement] = []

        try:
            reactions = self._coletar_reacoes_do_card(post, card)
        except Exception as e:
            logger.warning("Falha reações %s: %s", post.post_id, e)

        try:
            comments = self._coletar_comentarios_do_card(post, card)
        except Exception as e:
            logger.warning("Falha comentários %s: %s", post.post_id, e)

        try:
            shares = self._coletar_shares_do_card(post, card)
        except Exception as e:
            logger.warning("Falha shares %s: %s", post.post_id, e)

        logger.info(
            "  → Salvos: %d reações | %d comentários | %d compartilhamentos",
            len(reactions), len(comments), len(shares),
        )
        return reactions + comments + shares

    def _coletar_reacoes_do_card(self, post: Post, card) -> List[Engagement]:
        assert self._page is not None
        engagements: List[Engagement] = []

        # Tenta o botão dentro do card, depois na página
        btn = card.locator(_Selectors.REACTIONS_BUTTON)
        if btn.count() == 0:
            btn = self._page.locator(_Selectors.REACTIONS_BUTTON)
        if btn.count() == 0:
            logger.debug("Botão de reações não encontrado no post %s.", post.post_id)
            return engagements

        try:
            btn.first.scroll_into_view_if_needed()
            btn.first.click()
            self._aguardar_aleatoriamente(1.5, 2.5)
        except Exception as e:
            logger.debug("Falha ao clicar no botão de reações: %s", e)
            return engagements

        # Aguarda modal abrir e estabilizar
        modal_loc = self._page.locator(_Selectors.REACTIONS_MODAL)
        try:
            modal_loc.first.wait_for(state="visible", timeout=8000)
            # Aguarda o conteúdo do modal carregar (itens de lista aparecendo)
            self._aguardar_aleatoriamente(1.5, 2.0)
        except PlaywrightTimeoutError:
            logger.warning("Modal de reações não abriu para o post %s.", post.post_id)
            self._fechar_modal()
            return engagements

        # Clica na aba "Todos" com até 3 tentativas
        _aba_clicada = False
        for _tentativa in range(3):
            try:
                aba = self._page.locator(_Selectors.REACTIONS_ALL_TAB)
                if aba.count() > 0:
                    aba.first.scroll_into_view_if_needed()
                    aba.first.click()
                    self._aguardar_aleatoriamente(1.2, 1.8)
                    _aba_clicada = True
                    logger.debug("Aba 'Todos' clicada (tentativa %d).", _tentativa + 1)
                    break
            except Exception as _e:
                logger.debug("Falha ao clicar aba 'Todos' (tentativa %d): %s", _tentativa + 1, _e)
                time.sleep(0.8)

        if not _aba_clicada:
            logger.debug("Aba 'Todos' não encontrada para post %s — continuando com conteúdo atual.", post.post_id)

        modal = modal_loc.first
        hrefs: set = set()
        scroll_sem_novos = 0
        # Aumenta tolerância: LinkedIn carrega em lotes — até 6 scrolls sem novos antes de parar
        MAX_SCROLL_SEM_NOVOS = 6

        while scroll_sem_novos < MAX_SCROLL_SEM_NOVOS:
            novos = 0
            itens = self._page.locator(_Selectors.REACTION_ITEM).all()

            if itens:
                for item in itens:
                    try:
                        pares = _coletar_links_de_perfil(item, hrefs)
                        for href, nome in pares:
                            # Tenta pegar nome mais específico do span de título
                            try:
                                nome_el = item.locator(_Selectors.REACTION_USER_NAME).first
                                if nome_el.count() > 0:
                                    nome_span = _limpar_nome(nome_el.inner_text())
                                    if nome_span:
                                        nome = nome_span
                            except Exception:
                                pass
                            novos += 1
                            engagements.append(Engagement(
                                usuario=nome,
                                usuario_id=_gerar_hash_usuario(href),
                                tipo=TipoInteracao.LIKE,
                                post_id=post.post_id,
                                data_interacao=post.data_post,
                            ))
                    except Exception:
                        continue
            else:
                # Fallback: qualquer link de perfil dentro do modal
                pares = _coletar_links_de_perfil(modal, hrefs)
                for href, nome in pares:
                    novos += 1
                    engagements.append(Engagement(
                        usuario=nome,
                        usuario_id=_gerar_hash_usuario(href),
                        tipo=TipoInteracao.LIKE,
                        post_id=post.post_id,
                        data_interacao=post.data_post,
                    ))

            scroll_sem_novos = 0 if novos > 0 else scroll_sem_novos + 1

            # Rola o modal para carregar mais itens e aguarda o LinkedIn renderizar
            try:
                modal.evaluate("el => el.scrollTop += 500")
            except Exception:
                self._page.evaluate("window.scrollBy(0, 500)")
            # Espera um pouco mais longa para o LinkedIn carregar o próximo lote
            time.sleep(1.2)

        logger.debug("Post %s: %d reações coletadas no modal.", post.post_id, len(engagements))
        self._fechar_modal()
        return engagements

    def _coletar_comentarios_do_card(self, post: Post, card) -> List[Engagement]:
        assert self._page is not None
        engagements: List[Engagement] = []
        hrefs: set = set()

        # Snapshot COMPLETO de todos os links no card ANTES de expandir comentários.
        # Serve para excluir autor do post e menções no corpo do texto (diff approach).
        try:
            _snap = card.evaluate("""el => Array.from(
                el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')
            ).map(a => a.href.split('?')[0].replace(/\\/$/, ''))""")
            pre_hrefs: set = set(_snap)
        except Exception:
            pre_hrefs: set = set()

        # ------------------------------------------------------------------ #
        # PASSO 0: Comentários já estão visíveis? Coleta direto sem clicar.
        # ------------------------------------------------------------------ #
        if card.locator(_Selectors.COMMENT_ITEM).count() > 0:
            logger.debug("Post %s: comentários já visíveis no card.", post.post_id)
            # pre_hrefs já inclui comentaristas (expansão ativa) —
            # reduz para apenas os primeiros 3 links (header/autor do post).
            try:
                _h = card.evaluate("""el => Array.from(
                    el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')
                ).slice(0, 3).map(a => a.href.split('?')[0].replace(/\\/$/, ''))""")
                pre_hrefs = set(_h)
            except Exception:
                pre_hrefs = set()
            resultado = self._coletar_comentarios_inline(post, card, hrefs, engagements, pre_hrefs)
            self._fechar_comentarios_do_card(card)
            return resultado

        # ------------------------------------------------------------------ #
        # PASSO 1: Clicar no botão de contagem de comentários.
        #
        # Nota: no admin page o botão pode mostrar só um número sem o texto
        # "comentário", então usamos JavaScript para identificar o 2º item
        # da área de social counts (ordem: reações | comentários | shares).
        # ------------------------------------------------------------------ #
        expandido = False
        card.scroll_into_view_if_needed()

        # 1a. CSS selectors específicos
        for sel in [_Selectors.COMMENT_COUNT_BUTTON, _Selectors.COMMENT_ACTION_BUTTON]:
            try:
                btn = card.locator(sel)
                if btn.count() > 0:
                    btn.first.scroll_into_view_if_needed()
                    btn.first.click()
                    time.sleep(1.8)
                    expandido = True
                    logger.debug("Post %s: clicou comentários via CSS '%s'.", post.post_id, sel[:40])
                    break
            except Exception:
                continue

        # 1b. JavaScript — estratégia em 3 camadas:
        #     i.  Busca por texto/aria-label contendo "comentário"/"comment"
        #     ii. 2º item interativo da área de social-counts (posição fixa)
        #     iii. Qualquer elemento com aria-label numérico + "comment" em inglês
        if not expandido:
            try:
                resultado = card.evaluate("""el => {
                    // Área de social counts (reactions | comments | shares)
                    const countsArea = el.querySelector(
                        '.social-details-social-counts, [class*="social-counts"], ' +
                        '[class*="social-activity"], [class*="social-proof"]'
                    );
                    const searchIn = countsArea || el;

                    // i. Busca por texto ou aria-label contendo "comentário"/"comment"
                    const all = searchIn.querySelectorAll(
                        'button, a, li, span[role="button"], div[role="button"]'
                    );
                    for (const item of all) {
                        const txt  = (item.textContent  || '').trim();
                        const lbl  = (item.getAttribute('aria-label') || '').trim();
                        const combined = txt + ' ' + lbl;
                        if (
                            /comentário|comentarios|comment/i.test(combined) &&
                            !/reação|reaction|curtir|repost|share|compartilh/i.test(combined)
                        ) {
                            // Só clica se é curto (não é texto do post)
                            if (combined.length < 80) {
                                item.click();
                                return 'text:' + combined.slice(0, 40);
                            }
                        }
                    }

                    // ii. 2º item interativo da área de social counts
                    if (countsArea) {
                        const btns = Array.from(
                            countsArea.querySelectorAll('button, a[role="button"], li')
                        ).filter(b => b.offsetParent !== null); // visíveis
                        if (btns.length >= 2) {
                            btns[1].click();
                            return 'pos2:' + (btns[1].textContent || '').trim().slice(0, 30);
                        }
                    }

                    return null;
                }""")
                if resultado:
                    time.sleep(1.8)
                    expandido = True
                    logger.debug("Post %s: clicou comentários via JS (%s).", post.post_id, resultado[:40])
            except Exception as _e:
                logger.debug("Post %s: JS de comentários falhou: %s", post.post_id, _e)

        if not expandido:
            logger.debug("Post %s: nenhum botão de comentários encontrado.", post.post_id)

        # ------------------------------------------------------------------ #
        # PASSO 2: Verifica se abriu modal
        # ------------------------------------------------------------------ #
        modal_loc = self._page.locator(_Selectors.REACTIONS_MODAL)
        try:
            modal_loc.first.wait_for(state="visible", timeout=3000)
            modal = modal_loc.first
            scroll_sem_novos = 0

            while scroll_sem_novos < 5:
                novos = 0
                # Coleta comment items do modal (filtro de replies + fallback)
                try:
                    hrefs_list = list(hrefs)
                    resultados = modal.evaluate("""(args) => {
                        const seen = args.seen;
                        const results = [];
                        const COMMENT_SELS = [
                            'article.comments-comment-item',
                            'div.comments-comment-item',
                            '[class*="comments-comment-item"]',
                            'li[data-comment-id]',
                            'div[data-comment-id]',
                            'article[class*="comment-item"]',
                            'li[class*="comment-item"]',
                        ];
                        let items = [];
                        for (const sel of COMMENT_SELS) {
                            items = Array.from(el.querySelectorAll(sel));
                            if (items.length > 0) break;
                        }
                        if (items.length === 0) {
                            const links = el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
                            for (const link of links) {
                                const href = link.href.split('?')[0].replace(/\\/$/, '');
                                if (!href || seen.includes(href)) continue;
                                let name = link.textContent.trim().split('\\n')[0].trim();
                                if (name && name.length > 1 && name.length < 120) {
                                    seen.push(href); results.push({ href, name });
                                }
                            }
                            return results;
                        }
                        for (const item of items) {
                            let isReply = false;
                            let p = item.parentElement;
                            while (p && p !== el) {
                                if (/repl/i.test(p.className || '')) { isReply = true; break; }
                                p = p.parentElement;
                            }
                            if (isReply) continue;
                            const links = item.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
                            for (const link of links) {
                                const href = link.href.split('?')[0].replace(/\\/$/, '');
                                if (!href || seen.includes(href)) continue;
                                const nameEl = item.querySelector(
                                    '[class*="post-meta__name"], [class*="commenter-name"], ' +
                                    '[class*="entity-lockup__title"], [class*="actor__name"]'
                                );
                                let name = nameEl ? nameEl.textContent.trim() : link.textContent.trim();
                                name = name.split('\\n')[0].trim();
                                if (!name || name.length < 2 || name.length >= 120) continue;
                                const textEl = item.querySelector(
                                    '[class*="comment__text"], [class*="main-content"], ' +
                                    '[class*="inline-show-more-text"], [class*="comment-text"]'
                                );
                                const text = (textEl ? textEl.textContent.trim() : '').slice(0, 200);
                                seen.push(href); results.push({ href, name, text }); break;
                            }
                        }
                        return results;
                    }""", {"seen": hrefs_list})
                    for r in (resultados or []):
                        href = r.get("href", "")
                        nome = _limpar_nome(r.get("name", ""))
                        if not href or not nome or href in hrefs:
                            continue
                        if nome.strip().lower().startswith(_EMPRESA_EXCLUIR):
                            continue
                        hrefs.add(href)
                        novos += 1
                        engagements.append(Engagement(
                            usuario=nome,
                            usuario_id=_gerar_hash_usuario(href),
                            tipo=TipoInteracao.COMENTARIO,
                            post_id=post.post_id,
                            data_interacao=post.data_post,
                        ))
                        logger.debug(
                            "Post: %s\n  %s | %s\n  %s",
                            post.post_id, nome, str(post.data_post or "?"),
                            (r.get("text") or "")[:150],
                        )
                except Exception as _e:
                    logger.debug("Coleta modal comentários: %s", _e)

                # Carrega mais comentários no modal
                load_more = modal.locator(_Selectors.LOAD_MORE_COMMENTS)
                if load_more.count() > 0:
                    try:
                        if load_more.first.is_visible(timeout=1000):
                            load_more.first.click()
                            time.sleep(1.5)
                            novos += 1
                    except Exception:
                        pass

                scroll_sem_novos = 0 if novos > 0 else scroll_sem_novos + 1
                try:
                    modal.evaluate("el => el.scrollTop += 500")
                except Exception:
                    pass
                time.sleep(1.0)

            self._fechar_modal()
            return engagements

        except PlaywrightTimeoutError:
            pass  # Não abriu modal — tenta coleta inline abaixo

        # ------------------------------------------------------------------ #
        # PASSO 3: Comentários expandiram inline abaixo do card
        # ------------------------------------------------------------------ #
        # Rola a página até o final do card para que a seção de comentários
        # (que pode estar em um elemento irmão no DOM) fique visível.
        try:
            card_box = card.bounding_box()
            if card_box:
                self._page.evaluate(
                    f"window.scrollTo(0, {int(card_box['y'] + card_box['height'] - 100)})"
                )
            time.sleep(1.2)
        except Exception:
            pass

        resultado = self._coletar_comentarios_inline(post, card, hrefs, engagements, pre_hrefs)

        # Fecha a seção de comentários para não contaminar o próximo post.
        self._fechar_comentarios_do_card(card)

        return resultado

    def _fechar_comentarios_do_card(self, card) -> None:
        """
        Tenta colapsar a seção de comentários do card atual clicando
        novamente no botão de comentários (toggle). Se falhar, ignora —
        o escopo JS já garante que a coleta do próximo post ficará isolada.
        """
        try:
            card.evaluate("""el => {
                // Tenta clicar no botão de comentários para colapsar
                const sels = [
                    'li.social-details-social-counts__comments button',
                    'button[aria-label*="comentário"]',
                    'button[aria-label*="comment"]',
                    'button.comment-button',
                    'li.comment-button button',
                ];
                for (const sel of sels) {
                    try {
                        const btn = el.querySelector(sel);
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return;
                        }
                    } catch(e) {}
                }
                // Também tenta nos irmãos até o próximo post
                const parent = el.parentElement;
                if (!parent) return;
                const siblings = Array.from(parent.children);
                const idx = siblings.indexOf(el);
                const URN_RE = /^urn:li:(activity|ugcPost):/;
                for (let i = idx + 1; i < siblings.length && i <= idx + 5; i++) {
                    if (URN_RE.test(siblings[i].getAttribute('data-urn') || '')) break;
                    for (const sel of sels) {
                        try {
                            const btn = siblings[i].querySelector(sel);
                            if (btn && btn.offsetParent !== null) {
                                btn.click();
                                return;
                            }
                        } catch(e) {}
                    }
                }
            }""")
            time.sleep(0.5)
        except Exception:
            pass

    def _coletar_links_via_js_no_container(
        self,
        container,
        hrefs: set,
        engagements: List[Engagement],
        post: Post,
        tipo: TipoInteracao,
        container_js: str = "el",
    ) -> int:
        """
        Usa JavaScript para coletar links de perfil (/in/ e /company/)
        dentro de um container Playwright, independente de classes CSS.
        Para comentários: filtra respostas (replies) e o perfil da empresa.
        Retorna o número de novos engagements adicionados.
        """
        is_comentario = (tipo == TipoInteracao.COMENTARIO)
        try:
            hrefs_list = list(hrefs)
            resultados = container.evaluate(
                """(el, args) => {
                    const seen          = args.seen;
                    const filterReplies = args.filterReplies;

                    const COMMENT_SELS = [
                        'article.comments-comment-item',
                        'div.comments-comment-item',
                        'article[class*="comment-item"]',
                        'li[class*="comment-item"]',
                        '[class*="comments-comment-item"]',
                        '[class*="comments-comment"][class*="item"]',
                        'li[data-comment-id]',
                        'div[data-comment-id]',
                    ];

                    const results = [];

                    if (filterReplies) {
                        const URN_RE = /^urn:li:(activity|ugcPost):/;

                        // Monta a "zona de comentários": o card + irmãos seguintes
                        // até o próximo card de post, para não cruzar posts.
                        const zones = [];
                        const cardParent = el.parentElement;
                        if (cardParent) {
                            const siblings = Array.from(cardParent.children);
                            const myIdx = siblings.indexOf(el);
                            for (let i = myIdx; i < siblings.length && i <= myIdx + 15; i++) {
                                const sib = siblings[i];
                                if (i > myIdx && URN_RE.test(sib.getAttribute('data-urn') || '')) break;
                                zones.push(sib);
                            }
                        }
                        if (zones.length === 0) zones.push(el);

                        // Procura o container da lista de comentários em cada zona.
                        let listContainer = null;
                        for (const zone of zones) {
                            // Tentativa 1: classe CSS conhecida
                            const byClass =
                                zone.querySelector('[class*="comments-comments-list"]') ||
                                zone.querySelector('[class*="comment-list"]');
                            if (byClass) { listContainer = byClass; break; }

                            // Tentativa 2: rótulo "Mais relevantes" / "Most relevant"
                            // como âncora — usa closest() e depois sobe até um
                            // container específico de comentários (não o body inteiro).
                            const allEls = Array.from(
                                zone.querySelectorAll('button, span, div, li, p')
                            );
                            for (const candidate of allEls) {
                                const txt = (candidate.textContent || '').trim();
                                if (
                                    txt.length < 40 &&
                                    /mais relevantes?|most relevant|recentes?|recent/i.test(txt)
                                ) {
                                    // Tenta closest() com classes conhecidas de container de comentários
                                    let found = candidate.closest(
                                        '[class*="comments-comments-list"], ' +
                                        '[class*="comment-list"], ' +
                                        '[class*="comments-list"], ' +
                                        '[class*="social-comments"]'
                                    );
                                    if (!found) {
                                        // Sobe na árvore, mas só aceita container com classe "comment"
                                        let anc = candidate.parentElement;
                                        for (let depth = 0; depth < 10 && anc; depth++) {
                                            const cls = (anc.className || '').toLowerCase();
                                            const hasLinks = anc.querySelectorAll('a[href*="/in/"]').length > 0;
                                            const hasCommentClass = /comment/.test(cls);
                                            if (hasLinks && (hasCommentClass || depth >= 3)) {
                                                found = anc;
                                                break;
                                            }
                                            anc = anc.parentElement;
                                        }
                                    }
                                    // Também tenta: o pai do "Mais relevantes" tem irmãos com links /in/?
                                    if (!found) {
                                        const parentEl = candidate.parentElement;
                                        if (parentEl) {
                                            const siblingLinks = Array.from(
                                                parentEl.querySelectorAll('a[href*="/in/"]')
                                            );
                                            if (siblingLinks.length > 0) found = parentEl;
                                        }
                                    }
                                    if (found) { listContainer = found; break; }
                                }
                            }
                            if (listContainer) break;

                            // Tentativa 3: irmão (não o card) contém comment-item
                            if (zone !== el &&
                                    zone.querySelectorAll('[class*="comment-item"]').length > 0) {
                                listContainer = zone;
                                break;
                            }

                            // Tentativa 4: qualquer div/section com classe contendo
                            // "comment" que tenha links /in/ dentro da zona
                            const commentDivs = Array.from(
                                zone.querySelectorAll('div, ul, section, ol')
                            ).filter(d => {
                                const cls = (d.className || '').toLowerCase();
                                return /comment/.test(cls) &&
                                    d.querySelectorAll('a[href*="/in/"]').length > 0;
                            });
                            if (commentDivs.length > 0) {
                                // Pega o mais específico (menor que contém links)
                                commentDivs.sort((a, b) =>
                                    a.querySelectorAll('a[href*="/in/"]').length -
                                    b.querySelectorAll('a[href*="/in/"]').length
                                );
                                listContainer = commentDivs[0];
                                break;
                            }
                        }

                        // Tenta itens de comentário de nível superior dentro do container
                        let topLevel = [];
                        if (listContainer) {
                            let allItems = [];
                            for (const sel of COMMENT_SELS) {
                                allItems = Array.from(listContainer.querySelectorAll(sel));
                                if (allItems.length > 0) break;
                            }

                            function isReply(item) {
                                let ancestor = item.parentElement;
                                while (ancestor && ancestor !== listContainer) {
                                    const cls = (ancestor.className || '').toLowerCase();
                                    if (/repl/i.test(cls)) return true;
                                    for (const sel of COMMENT_SELS) {
                                        try { if (ancestor.matches(sel)) return true; }
                                        catch(e) {}
                                    }
                                    ancestor = ancestor.parentElement;
                                }
                                return false;
                            }

                            topLevel = allItems.filter(item => !isReply(item));

                            for (const item of topLevel) {
                                const links = item.querySelectorAll(
                                    'a[href*="/in/"], a[href*="/company/"]'
                                );
                                for (const link of links) {
                                    const href = link.href.split('?')[0].replace(/\\/$/, '');
                                    if (!href || seen.includes(href)) continue;
                                    seen.push(href);
                                    const nameEl = item.querySelector(
                                        '[class*="post-meta__name"], [class*="commenter-name"], ' +
                                        '[class*="entity-lockup__title"], [class*="actor__name"]'
                                    );
                                    let name = nameEl
                                        ? nameEl.textContent.trim()
                                        : link.textContent.trim();
                                    name = name.split('\\n')[0].trim();
                                    if (name && name.length > 1 && name.length < 120) {
                                        results.push({href, name});
                                        break; // Um autor por item de comentário
                                    }
                                }
                            }
                        }

                        // Fallback A: container encontrado mas sem COMMENT_SELS
                        // → coleta todos os links /in/ do container diretamente
                        if (topLevel.length === 0 && listContainer) {
                            const links = listContainer.querySelectorAll(
                                'a[href*="/in/"], a[href*="/company/"]'
                            );
                            for (const link of links) {
                                const href = link.href.split('?')[0].replace(/\\/$/, '');
                                if (!href || seen.includes(href)) continue;
                                seen.push(href);
                                let name = link.textContent.trim().split('\\n')[0].trim();
                                if (name && name.length > 1 && name.length < 120) {
                                    results.push({href, name});
                                }
                            }
                        }

                        // Fallback B: nenhum container encontrado
                        // → varre irmãos (exclui o card para não pegar autor do post)
                        if (topLevel.length === 0 && !listContainer) {
                            const cardLinks = new Set(
                                Array.from(
                                    el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')
                                ).map(a => a.href.split('?')[0].replace(/\\/$/, ''))
                            );
                            for (const zone of zones) {
                                if (zone === el) continue;
                                const links = zone.querySelectorAll(
                                    'a[href*="/in/"], a[href*="/company/"]'
                                );
                                for (const link of links) {
                                    const href = link.href.split('?')[0].replace(/\\/$/, '');
                                    if (!href || seen.includes(href) || cardLinks.has(href)) continue;
                                    seen.push(href);
                                    let name = link.textContent.trim().split('\\n')[0].trim();
                                    if (name && name.length > 1 && name.length < 120) {
                                        results.push({href, name});
                                    }
                                }
                            }
                        }

                    } else {
                        // Modo genérico (reactions / shares)
                        let items = [];
                        for (const sel of COMMENT_SELS) {
                            const found = el.querySelectorAll(sel);
                            if (found.length > 0) { items = Array.from(found); break; }
                        }
                        if (items.length === 0) items = [el];

                        for (const item of items) {
                            const links = item.querySelectorAll(
                                'a[href*="/in/"], a[href*="/company/"]'
                            );
                            for (const link of links) {
                                const href = link.href.split('?')[0].replace(/\\/$/, '');
                                if (!href || seen.includes(href)) continue;
                                seen.push(href);
                                const nameEl = item.querySelector(
                                    '[class*="post-meta__name"], [class*="commenter-name"], ' +
                                    '[class*="entity-lockup__title"], [class*="actor__name"]'
                                );
                                let name = nameEl
                                    ? nameEl.textContent.trim()
                                    : link.textContent.trim();
                                name = name.split('\\n')[0].trim();
                                if (name && name.length > 1 && name.length < 120) {
                                    results.push({href, name});
                                }
                            }
                        }
                    }

                    return results;
                }""",
                {"seen": hrefs_list, "filterReplies": is_comentario},
            )

            novos = 0
            for r in (resultados or []):
                href = r.get("href", "")
                nome = _limpar_nome(r.get("name", ""))
                if not href or not nome or href in hrefs:
                    continue
                if is_comentario and nome.strip().lower().startswith(_EMPRESA_EXCLUIR):
                    logger.debug("Ignorando comentário da empresa: %s", nome)
                    continue
                hrefs.add(href)
                novos += 1
                engagements.append(Engagement(
                    usuario=nome,
                    usuario_id=_gerar_hash_usuario(href),
                    tipo=tipo,
                    post_id=post.post_id,
                    data_interacao=post.data_post,
                ))
            return novos

        except Exception as _e:
            logger.debug("_coletar_links_via_js_no_container falhou: %s", _e)
            return 0

    def _coletar_comentarios_inline(
        self,
        post: Post,
        card,
        hrefs: set,
        engagements: List[Engagement],
        pre_hrefs: Optional[set] = None,
    ) -> List[Engagement]:
        """
        Coleta comentários expandidos inline.

        Abordagem robusta sem dependência de classes CSS do LinkedIn:
          - Coleta TODOS os links /in/ na zona do post (card + irmãos até próximo data-urn)
          - Exclui links presentes antes da expansão (pre_hrefs: autor, menções no texto)
          - Exclui links já coletados (hrefs)
        Repete em loop tentando "Carregar mais" a cada ciclo.
        """
        assert self._page is not None
        if pre_hrefs is None:
            pre_hrefs = set()
        sem_novos = 0

        while sem_novos < 4:
            novos = 0

            try:
                hrefs_list = list(hrefs)
                pre_list   = list(pre_hrefs)
                resultados = self._page.evaluate(
                    """(args) => {
                        const postId  = args.postId;
                        const seen    = args.seen;
                        const preH    = new Set(args.preHrefs);
                        const EMPRESA = args.empresa;
                        const URN_RE  = /^urn:li:(activity|ugcPost):/;

                        // ── Localiza o card ────────────────────────────────────
                        const cardEl = (
                            document.querySelector('[data-urn^="urn:li:activity:' + postId + '"]') ||
                            document.querySelector('[data-urn^="urn:li:ugcPost:' + postId + '"]') ||
                            document.querySelector('[data-id*="' + postId + '"]')
                        );

                        // ── Constrói zona: card + irmãos até próximo data-urn ──
                        const zoneEls = [];
                        if (cardEl) {
                            const parent = cardEl.parentElement;
                            if (parent) {
                                const siblings = Array.from(parent.children);
                                const myIdx = siblings.indexOf(cardEl);
                                zoneEls.push(cardEl);
                                for (let i = myIdx + 1; i < siblings.length; i++) {
                                    if (URN_RE.test(siblings[i].getAttribute('data-urn') || '')) break;
                                    zoneEls.push(siblings[i]);
                                }
                            } else {
                                zoneEls.push(cardEl);
                            }
                        }
                        if (zoneEls.length === 0) return [];

                        // ── Coleta todos os links na zona ──────────────────────
                        const allLinks = [];
                        for (const z of zoneEls) {
                            allLinks.push(
                                ...Array.from(z.querySelectorAll('a[href*="/in/"], a[href*="/company/"]'))
                            );
                        }

                        // ── Filtra: apenas links novos (não estavam antes da expansão) ──
                        const results = [];
                        for (const link of allLinks) {
                            const href = link.href.split('?')[0].replace(/\\/$/, '');
                            if (!href) continue;
                            if (preH.has(href)) continue;        // link pré-expansão (autor/menção)
                            if (seen.includes(href)) continue;   // já coletado
                            let name = link.textContent.trim().split('\\n')[0].trim();
                            if (!name || name.length < 2 || name.length >= 120) continue;
                            if (name.toLowerCase().startsWith(EMPRESA)) continue;

                            seen.push(href);

                            // Tenta extrair texto do comentário subindo na árvore
                            let text = '';
                            let p = link.parentElement;
                            for (let d = 0; d < 8 && p; d++, p = p.parentElement) {
                                const textEl = p.querySelector(
                                    '[class*="comment__text"], [class*="main-content"], ' +
                                    '[class*="inline-show-more-text"], [class*="comment-text"]'
                                );
                                if (textEl) { text = textEl.textContent.trim().slice(0, 200); break; }
                            }
                            results.push({ href, name, text });
                        }
                        return results;
                    }""",
                    {"postId": post.post_id, "seen": hrefs_list, "preHrefs": pre_list, "empresa": _EMPRESA_EXCLUIR},
                )
                for r in (resultados or []):
                    href = r.get("href", "")
                    nome = _limpar_nome(r.get("name", ""))
                    if not href or not nome or href in hrefs:
                        continue
                    hrefs.add(href)
                    novos += 1
                    engagements.append(Engagement(
                        usuario=nome,
                        usuario_id=_gerar_hash_usuario(href),
                        tipo=TipoInteracao.COMENTARIO,
                        post_id=post.post_id,
                        data_interacao=post.data_post,
                    ))
                    logger.debug(
                        "Post: %s\n  %s | %s\n  %s",
                        post.post_id, nome, str(post.data_post or "?"),
                        (r.get("text") or "")[:150],
                    )
            except Exception as _e:
                logger.debug("Busca inline de comentários falhou: %s", _e)

            # ── "Carregar mais" — card + irmãos até o próximo data-urn ────────
            try:
                carregou_mais = card.evaluate("""el => {
                    const LOAD_MORE_SELS = [
                        'button[class*="load-more-comments"]',
                        'button[aria-label*="mais comentário"]',
                        'button[aria-label*="more comment"]',
                        'button[aria-label*="Load more comments"]',
                        'button[class*="comments-load-more"]',
                    ];
                    function tryClick(root) {
                        for (const sel of LOAD_MORE_SELS) {
                            try {
                                const btn = root.querySelector(sel);
                                if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                            } catch(e) {}
                        }
                        return false;
                    }
                    if (tryClick(el)) return true;
                    const parent = el.parentElement;
                    if (!parent) return false;
                    const siblings = Array.from(parent.children);
                    const idx = siblings.indexOf(el);
                    const URN_RE = /^urn:li:(activity|ugcPost):/;
                    for (let i = idx + 1; i < siblings.length && i <= idx + 15; i++) {
                        if (URN_RE.test(siblings[i].getAttribute('data-urn') || '')) break;
                        if (tryClick(siblings[i])) return true;
                    }
                    return false;
                }""")
                if carregou_mais:
                    time.sleep(1.5)
                    novos += 1
            except Exception:
                pass

            sem_novos = 0 if novos > 0 else sem_novos + 1
            time.sleep(0.8)

        return engagements

    def _coletar_shares_do_card(self, post: Post, card) -> List[Engagement]:
        assert self._page is not None
        engagements: List[Engagement] = []
        hrefs: set = set()

        # Localiza o botão de share count no card ou na página
        btn = card.locator(_Selectors.SHARES_BUTTON)
        if btn.count() == 0:
            btn = self._page.locator(_Selectors.SHARES_BUTTON)
        if btn.count() == 0:
            logger.debug("Botão de shares não encontrado no post %s.", post.post_id)
            return engagements

        try:
            btn.first.scroll_into_view_if_needed()
            btn.first.click()
            self._aguardar_aleatoriamente(4.0, 6.0)  # aguarda carregamento inicial da lista
        except Exception as e:
            logger.debug("Falha ao clicar no botão de shares: %s", e)
            return engagements

        # Cenário A: abriu modal (estilo artdeco)
        modal_loc = self._page.locator(_Selectors.REACTIONS_MODAL)
        if modal_loc.count() > 0:
            try:
                modal_loc.first.wait_for(state="visible", timeout=8000)
                modal = modal_loc.first
                altura_anterior = -1
                sem_crescimento = 0
                MAX_SEM_CRESCIMENTO = 3  # para após 3 rodadas sem novo conteúdo

                while sem_crescimento < MAX_SEM_CRESCIMENTO:
                    # Rola até o fim absoluto do modal
                    try:
                        altura_atual = modal.evaluate(
                            "el => { el.scrollTop = el.scrollHeight; return el.scrollHeight; }"
                        )
                    except Exception:
                        altura_atual = altura_anterior

                    # Aguarda o LinkedIn carregar mais itens após o scroll
                    time.sleep(5.0)

                    # Rola até o fim novamente para revelar os itens recém-carregados
                    try:
                        nova_altura = modal.evaluate(
                            "el => { el.scrollTop = el.scrollHeight; return el.scrollHeight; }"
                        )
                    except Exception:
                        nova_altura = altura_atual

                    # Coleta todos os usuários visíveis (incluindo os novos)
                    pares = _coletar_links_de_perfil(modal, hrefs)
                    for href, nome in pares:
                        engagements.append(Engagement(
                            usuario=nome,
                            usuario_id=_gerar_hash_usuario(href),
                            tipo=TipoInteracao.SHARE,
                            post_id=post.post_id,
                            data_interacao=post.data_post,
                        ))

                    if nova_altura <= altura_anterior:
                        sem_crescimento += 1
                    else:
                        sem_crescimento = 0

                    logger.debug(
                        "Post %s shares: %d coletados | altura %d → %d | paradas: %d/%d",
                        post.post_id, len(engagements),
                        altura_anterior, nova_altura,
                        sem_crescimento, MAX_SEM_CRESCIMENTO,
                    )
                    altura_anterior = nova_altura

                self._fechar_modal()
                return engagements

            except PlaywrightTimeoutError:
                pass

        # Cenário B: não abriu modal — lista inline de reposts apareceu na página
        # Aguarda carregamento da lista inline
        time.sleep(5.0)
        pares = _coletar_links_de_perfil(self._page, hrefs)
        for href, nome in pares:
            engagements.append(Engagement(
                usuario=nome,
                usuario_id=_gerar_hash_usuario(href),
                tipo=TipoInteracao.SHARE,
                post_id=post.post_id,
                data_interacao=post.data_post,
            ))

        # Fecha qualquer modal/overlay aberto
        self._fechar_modal()
        return engagements

    # ------------------------------------------------------------------ #
    #  Utilitários
    # ------------------------------------------------------------------ #

    def _extrair_totais_do_card(self, card) -> Tuple[int, int, int]:
        """
        Lê os totais exibidos no card (reactions, comments, shares).
        Mais preciso que contar nomes coletados, pois perfis privados não
        aparecem nos modais mas são contados no total.
        """
        reactions = comments = shares = 0
        try:
            texto = card.inner_text()
        except Exception:
            return reactions, comments, shares

        # Padrões pt-BR e en-US
        for padrao, campo in [
            (r"(\d[\d\.,]*)\s*(?:reações?|reactions?|curtidas?)", "r"),
            (r"(\d[\d\.,]*)\s*(?:comentários?|comments?)",         "c"),
            (r"(\d[\d\.,]*)\s*(?:compartilhamentos?|reposts?|shares?)", "s"),
        ]:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                val = int(re.sub(r"[^\d]", "", m.group(1)) or "0")
                if campo == "r":
                    reactions = val
                elif campo == "c":
                    comments = val
                elif campo == "s":
                    shares = val

        # Fallback via aria-label dos botões
        if reactions == 0:
            try:
                btn = card.locator(_Selectors.REACTIONS_BUTTON).first
                if btn.count() > 0:
                    label = btn.get_attribute("aria-label") or btn.inner_text()
                    reactions = _extrair_numero(label)
            except Exception:
                pass

        logger.debug("Totais do card: reactions=%d, comments=%d, shares=%d", reactions, comments, shares)
        return reactions, comments, shares

    def _extrair_data_do_card(self, card) -> Optional[date]:
        """Extrai a data de publicação diretamente do card, sem navegar."""
        try:
            # Prioridade 1: time[datetime]
            time_el = card.locator("time[datetime]")
            if time_el.count() > 0:
                dt = time_el.first.get_attribute("datetime") or ""
                if dt:
                    try:
                        return datetime.fromisoformat(dt[:10]).date()
                    except ValueError:
                        pass

            # Prioridade 2: seletores de timestamp
            for sel in [
                "span[class*='actor__sub-description']",
                "span[class*='subline-level']",
                "span[class*='update-v2-social-activity']",
                "span[class*='posted-time']",
                "a[class*='actor__sub-description-link'] span",
            ]:
                el = card.locator(sel).first
                if el.count() > 0:
                    try:
                        texto = el.inner_text().strip()
                        if " - " in texto:
                            texto = texto.split(" - ")[-1].strip()
                        r = _parse_data_relativa(texto)
                        if r:
                            return r
                    except Exception:
                        continue

            # Prioridade 3: texto completo do card
            texto_card = card.inner_text()
            m = re.search(r"De .+? - (.+?)(?:\n|$)", texto_card)
            if m:
                return _parse_data_relativa(m.group(1).strip())

        except Exception:
            pass
        return None

    def _fechar_modal(self) -> None:
        """Fecha o modal aberto via botão de fechar ou Escape."""
        try:
            close = self._page.locator(_Selectors.MODAL_CLOSE)
            if close.count() > 0 and close.first.is_visible(timeout=1000):
                close.first.click()
            else:
                self._page.keyboard.press("Escape")
        except Exception:
            try:
                self._page.keyboard.press("Escape")
            except Exception:
                pass
        self._aguardar_aleatoriamente(0.5, 1.0)

    def _scroll_para_mais_posts(self) -> None:
        assert self._page is not None
        try:
            for sel in ["div.scaffold-finite-scroll__content", "main"]:
                el = self._page.locator(sel).first
                if el.count() > 0:
                    try:
                        el.evaluate("e => e.scrollTop += e.scrollHeight")
                        break
                    except Exception:
                        continue
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3.5)
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2.0)
        except Exception as e:
            logger.debug("Erro no scroll: %s", e)

    def _aguardar_aleatoriamente(self, minimo: float, maximo: float) -> None:
        time.sleep(random.uniform(minimo, maximo))
