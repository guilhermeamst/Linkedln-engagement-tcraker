"""
etl_pipeline.py - Orquestrador do fluxo de coleta e persistência.

Responsabilidade: executar o loop completo de ETL (Extract → Transform → Load).
  - Extract: LinkedInScraper.coletar_posts() — gera (Post, List[Engagement])
  - Transform: regras já aplicadas no scraper e nos modelos
  - Load: EngagementService.registrar_engajamentos_post()

Não conhece argumentos de linha de comando, sys.exit nem UI.
Recebe todas as dependências por injeção.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.core.config import AppConfig
from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.repository.engagement_repository import EngagementRepository
from src.repository.post_repository import PostRepository
from src.repository.user_repository import UserRepository
from src.scraper.linkedin_scraper import LinkedInScraper
from src.services.analytics_service import AnalyticsService
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Value Object de resultado
# --------------------------------------------------------------------------- #

@dataclass
class PipelineResult:
    """Resumo imutável da execução do pipeline."""
    posts_processados: int   = 0
    interacoes_inseridas: int = 0
    duplicatas_ignoradas: int = 0
    duracao_segundos: float  = 0.0
    erro: Optional[str]      = None
    iniciado_em: datetime    = field(default_factory=datetime.now)

    @property
    def sucesso(self) -> bool:
        return self.erro is None

    def __str__(self) -> str:
        status = "OK" if self.sucesso else f"ERRO: {self.erro}"
        return (
            f"Pipeline [{status}] | "
            f"Posts: {self.posts_processados} | "
            f"Inseridos: {self.interacoes_inseridas} | "
            f"Duplicatas: {self.duplicatas_ignoradas} | "
            f"Duração: {self.duracao_segundos:.1f}s"
        )


# --------------------------------------------------------------------------- #
#  Pipeline principal
# --------------------------------------------------------------------------- #

class ETLPipeline:
    """
    Orquestra o fluxo Extract → Transform → Load do LinkedIn Engagement Tracker.

    Uso:
        pipeline = ETLPipeline.from_config(config)
        result = pipeline.executar()
    """

    def __init__(
        self,
        config: AppConfig,
        db: DatabaseManager,
        post_repo: PostRepository,
        engagement_service: EngagementService,
        analytics_service: AnalyticsService,
    ) -> None:
        self._config = config
        self._db = db
        self._post_repo = post_repo
        self._engagement_service = engagement_service
        self._analytics_service = analytics_service

    @classmethod
    def from_config(cls, config: AppConfig) -> "ETLPipeline":
        """
        Factory: constrói o pipeline completo a partir de AppConfig.
        Inicializa banco, repositórios e serviços internamente.
        """
        db = DatabaseManager(config.database.db_path)
        db.create_tables()

        engagement_repo = EngagementRepository(db)
        post_repo       = PostRepository(db)
        user_repo       = UserRepository(db)

        engagement_service = EngagementService(engagement_repo, post_repo, user_repo)
        ranking_service    = RankingService()
        analytics_service  = AnalyticsService(engagement_service, ranking_service)

        return cls(config, db, post_repo, engagement_service, analytics_service)

    # ------------------------------------------------------------------ #
    #  Execução
    # ------------------------------------------------------------------ #

    def executar(self) -> PipelineResult:
        """
        Executa o pipeline completo de coleta.

        Returns:
            PipelineResult com os totais da execução.
        """
        result = PipelineResult()
        inicio = time.time()

        logger.info("=" * 60)
        logger.info("PIPELINE ETL INICIADO — %s", result.iniciado_em.isoformat())
        logger.info("Desde: %s | Max posts: %d", self._config.scraper.data_inicio, self._config.scraper.max_posts)
        logger.info("=" * 60)

        try:
            with LinkedInScraper(self._config.linkedin, self._config.scraper) as scraper:
                logger.info("Realizando login no LinkedIn...")
                scraper.login()
                logger.info("Login bem-sucedido. Iniciando coleta...")

                for post, engagements in scraper.coletar_posts(deve_pular=self._verificar_skip):
                    try:
                        res = self._engagement_service.registrar_engajamentos_post(post, engagements)
                        result.posts_processados     += 1
                        result.interacoes_inseridas  += res["inseridos"]
                        result.duplicatas_ignoradas  += res["duplicatas"]

                        logger.info(
                            "[Post %d] %s | interações: %d | inseridos: %d | dups: %d",
                            result.posts_processados,
                            post.post_id,
                            len(engagements),
                            res["inseridos"],
                            res["duplicatas"],
                        )
                    except Exception as exc:
                        logger.error("Falha ao persistir post %s: %s", post.post_id, exc, exc_info=True)

        except KeyboardInterrupt:
            logger.info("Coleta interrompida pelo usuário (Ctrl+C).")
            result.erro = "Interrompido pelo usuário"
        except Exception as exc:
            logger.error("Erro fatal no pipeline: %s", exc, exc_info=True)
            result.erro = str(exc)
        finally:
            result.duracao_segundos = time.time() - inicio
            self._db.dispose()

        self._log_resumo(result)
        return result

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _verificar_skip(self, post_id: str, total_r: int, total_c: int, total_s: int) -> bool:
        """
        Retorna True (pular) se o post já está no banco E o número de interações
        reais salvas na tabela engagement coincide com os totais do LinkedIn.
        Retorna False (processar) se o post é novo ou se algum total divergiu.
        """
        post_db = self._post_repo.buscar_por_id(post_id)
        if post_db is None:
            return False  # post novo — deve processar

        contagens = self._engagement_service.contar_interacoes_por_tipo(post_id)
        reactions_db   = contagens.get("reaction", 0)
        comentarios_db = contagens.get("comentario", 0)
        shares_db      = contagens.get("share", 0)

        return reactions_db == total_r and comentarios_db == total_c and shares_db == total_s

    def _pular_se_nao_salvo(self, post_id: str, total_r: int, total_c: int, total_s: int) -> bool:
        """
        Retorna True (pular) se o post NÃO está no banco.
        Usado por executar_somente_posts_salvos() para reprocessar apenas posts existentes.
        """
        return not self._post_repo.post_existe(post_id)

    # ------------------------------------------------------------------ #
    #  Modo: reprocessar apenas posts já no banco
    # ------------------------------------------------------------------ #

    def executar_somente_posts_salvos(self) -> PipelineResult:
        """
        Roda o scraper mas processa APENAS os posts que já existem no banco.
        Posts novos encontrados no LinkedIn são ignorados.
        Útil para atualizar engajamentos de posts já cadastrados sem ampliar o escopo.
        """
        result = PipelineResult()
        inicio = time.time()

        posts_salvos = {p.post_id for p in self._post_repo.buscar_todos()}
        logger.info("=" * 60)
        logger.info("PIPELINE (somente posts salvos) INICIADO — %s", result.iniciado_em.isoformat())
        logger.info("Posts no banco: %d", len(posts_salvos))
        logger.info("=" * 60)

        try:
            with LinkedInScraper(self._config.linkedin, self._config.scraper) as scraper:
                logger.info("Realizando login no LinkedIn...")
                scraper.login()
                logger.info("Login bem-sucedido. Iniciando coleta limitada ao banco...")

                for post, engagements in scraper.coletar_posts(deve_pular=self._pular_se_nao_salvo):
                    try:
                        res = self._engagement_service.registrar_engajamentos_post(post, engagements)
                        result.posts_processados     += 1
                        result.interacoes_inseridas  += res["inseridos"]
                        result.duplicatas_ignoradas  += res["duplicatas"]

                        logger.info(
                            "[Post %d] %s | inseridos: %d | dups: %d",
                            result.posts_processados,
                            post.post_id,
                            res["inseridos"],
                            res["duplicatas"],
                        )
                    except Exception as exc:
                        logger.error("Falha ao persistir post %s: %s", post.post_id, exc, exc_info=True)

        except KeyboardInterrupt:
            logger.info("Coleta interrompida pelo usuário (Ctrl+C).")
            result.erro = "Interrompido pelo usuário"
        except Exception as exc:
            logger.error("Erro fatal no pipeline: %s", exc, exc_info=True)
            result.erro = str(exc)
        finally:
            result.duracao_segundos = time.time() - inicio
            self._db.dispose()

        self._log_resumo(result)
        return result

    def _log_resumo(self, result: PipelineResult) -> None:
        logger.info("=" * 60)
        logger.info("PIPELINE CONCLUÍDO")
        logger.info("Posts processados:     %d", result.posts_processados)
        logger.info("Interações inseridas:  %d", result.interacoes_inseridas)
        logger.info("Duplicatas ignoradas:  %d", result.duplicatas_ignoradas)
        logger.info("Duração:               %.1fs", result.duracao_segundos)
        if result.erro:
            logger.warning("Status: %s", result.erro)
        logger.info("=" * 60)

    @property
    def analytics(self) -> AnalyticsService:
        """Acesso ao serviço de analytics após a execução."""
        return self._analytics_service