"""
coletar_post_unico.py - Coleta engajamento de um ou mais posts específicos.

Uso:
    python scripts/coletar_post_unico.py --post-id 7439626651308826624
    python scripts/coletar_post_unico.py --post-id 111 222 333
    python scripts/coletar_post_unico.py --url "https://www.linkedin.com/feed/update/urn:li:activity:7439626651308826624/"
    python scripts/coletar_post_unico.py --post-id 7439626651308826624 --mostrar-browser
    python scripts/coletar_post_unico.py --post-id 7439626651308826624 --forcar
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import load_config
from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.repository.engagement_repository import EngagementRepository
from src.repository.post_repository import PostRepository
from src.repository.user_repository import UserRepository
from src.scraper.linkedin_scraper import LinkedInScraper
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService

logger = get_logger(__name__)

# Regex para extrair o activity ID de uma URL ou string qualquer
_ACTIVITY_ID_RE = re.compile(r"activity[:\-](\d{10,})")


def extrair_post_id(valor: str) -> str:
    """Extrai o activity ID numérico de uma URL ou devolve o valor direto se já for um ID."""
    valor = valor.strip()
    if valor.isdigit():
        return valor
    m = _ACTIVITY_ID_RE.search(valor)
    if m:
        return m.group(1)
    raise ValueError(
        f"Não foi possível extrair o post ID de: {valor!r}\n"
        "Passe um ID numérico (ex.: 7439626651308826624) ou uma URL do LinkedIn "
        "contendo 'activity:XXXXXXXX' ou 'activity-XXXXXXXX'."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LinkedIn Engagement Tracker - Coleta de posts específicos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/coletar_post_unico.py --post-id 7439626651308826624
  python scripts/coletar_post_unico.py --post-id 111111111 222222222 333333333
  python scripts/coletar_post_unico.py --url "https://www.linkedin.com/feed/update/urn:li:activity:7439626651308826624/"
  python scripts/coletar_post_unico.py --post-id 7439626651308826624 --mostrar-browser
  python scripts/coletar_post_unico.py --post-id 7439626651308826624 --forcar
        """,
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--post-id",
        metavar="ID",
        nargs="+",
        help="Um ou mais IDs numéricos de posts (ex.: 111 222 333)",
    )
    grupo.add_argument(
        "--url",
        metavar="URL",
        nargs="+",
        help="Uma ou mais URLs de posts no LinkedIn",
    )
    parser.add_argument(
        "--mostrar-browser",
        action="store_true",
        default=False,
        help="Exibe o browser durante a execução (útil para depuração)",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        default=False,
        help="Reprocessa o post mesmo que já esteja no banco com os mesmos totais",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve todos os post IDs
    valores = args.post_id or args.url
    post_ids: list[str] = []
    for v in valores:
        try:
            post_ids.append(extrair_post_id(v))
        except ValueError as e:
            print(f"\nERRO: {e}")
            sys.exit(1)

    alvos = set(post_ids)
    print(f"\nPosts alvo ({len(post_ids)}): {', '.join(post_ids)}")

    # Carrega configuração
    try:
        config = load_config()
    except EnvironmentError as e:
        print(f"\nERRO: {e}")
        print("Configure o arquivo .env na raiz do projeto.")
        sys.exit(1)

    # Ajustes de config para coleta de post único:
    # - data_inicio/fim amplos para não filtrar o post por data
    # - max_posts mantido alto (o scraper incrementa o contador mesmo em posts pulados,
    #   então reduzir para 1 faria o loop parar no primeiro card ignorado)
    # - headless opcional
    config = replace(
        config,
        scraper=replace(
            config.scraper,
            data_inicio=date(2020, 1, 1),
            data_fim=date(2030, 12, 31),
        ),
        linkedin=replace(
            config.linkedin,
            headless=not args.mostrar_browser,
        ),
    )

    # Monta repositórios e serviço
    db        = DatabaseManager(config.database.db_path)
    db.create_tables()
    eng_repo  = EngagementRepository(db)
    post_repo = PostRepository(db)
    user_repo = UserRepository(db)
    svc       = EngagementService(eng_repo, post_repo, user_repo)
    rank_svc  = RankingService()

    pendentes = set(alvos)  # posts ainda não processados

    def deve_pular(pid: str, total_r: int, total_c: int, total_s: int) -> bool:
        """Pula todos os posts exceto os alvos. Se --forcar, reprocessa sempre."""
        if pid not in alvos:
            return True  # não é nenhum dos posts que queremos
        if pid not in pendentes:
            return True  # já foi processado nesta execução
        if args.forcar:
            return False  # forçar reprocessamento
        # Verifica se já está no banco com os mesmos totais
        post_db = post_repo.buscar_por_id(pid)
        if post_db is None:
            return False
        contagens      = svc.contar_interacoes_por_tipo(pid)
        reactions_db   = contagens.get("reaction", 0)
        comentarios_db = contagens.get("comentario", 0)
        shares_db      = contagens.get("share", 0)
        if reactions_db == total_r and comentarios_db == total_c and shares_db == total_s:
            print(f"\nPost {pid} já está atualizado no banco (reactions={total_r}, comentários={total_c}, shares={total_s}).")
            print("Use --forcar para reprocessar mesmo assim.")
            pendentes.discard(pid)
            return True
        return False

    encontrados: list[str] = []
    try:
        with LinkedInScraper(config.linkedin, config.scraper) as scraper:
            print("Realizando login no LinkedIn...")
            scraper.login()
            print("Login OK. Buscando posts na página de admin...")

            for post, engagements in scraper.coletar_posts(deve_pular=deve_pular):
                if post.post_id not in pendentes:
                    continue  # segurança extra

                encontrados.append(post.post_id)
                pendentes.discard(post.post_id)

                print(f"\nPost encontrado: {post.post_id}")
                print(f"  Data:         {post.data_post}")
                print(f"  URL:          {post.url_post}")
                print(f"  Reações:      {post.total_likes}")
                print(f"  Comentários:  {post.total_comentarios}")
                print(f"  Shares:       {post.total_shares}")
                print(f"  Interações coletadas: {len(engagements)}")

                res = svc.registrar_engajamentos_post(post, engagements)
                print(f"\n  Inseridos:   {res['inseridos']}")
                print(f"  Duplicatas:  {res['duplicatas']}")

                if not pendentes:
                    break  # todos os posts alvo foram processados

    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(1)
    except Exception as e:
        logger.error("Erro durante a coleta: %s", e, exc_info=True)
        print(f"\nERRO: {e}")
        sys.exit(1)
    finally:
        db.dispose()

    if pendentes:
        for pid in pendentes:
            print(
                f"\nPost {pid} não encontrado na página de admin.\n"
                "Verifique se o ID está correto e se o post ainda está publicado."
            )
        sys.exit(1)

    print("\nColeta concluída com sucesso.")
    sys.exit(0)


if __name__ == "__main__":
    main()
