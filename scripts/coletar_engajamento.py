"""
coletar_engajamento.py - Ponto de entrada da coleta de engajamento.

Uso:
    python scripts/coletar_engajamento.py
    python scripts/coletar_engajamento.py --max-posts 50
    python scripts/coletar_engajamento.py --desde 2026-02-01
    python scripts/coletar_engajamento.py --mostrar-browser
    python scripts/coletar_engajamento.py --apenas-ranking
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import load_config
from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.pipeline.etl_pipeline import ETLPipeline
from src.repository.engagement_repository import EngagementRepository
from src.repository.post_repository import PostRepository
from src.repository.user_repository import UserRepository
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LinkedIn Engagement Tracker - Coletor de dados",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/coletar_engajamento.py
  python scripts/coletar_engajamento.py --max-posts 100
  python scripts/coletar_engajamento.py --desde 2026-02-01
  python scripts/coletar_engajamento.py --mostrar-browser
  python scripts/coletar_engajamento.py --apenas-ranking
  python scripts/coletar_engajamento.py --somente-salvos
        """,
    )
    parser.add_argument("--max-posts",       type=int,                default=None, metavar="N",          help="Número máximo de posts a processar")
    parser.add_argument("--desde",           type=date.fromisoformat, default=None, metavar="YYYY-MM-DD", help="Data de início da coleta")
    parser.add_argument("--mostrar-browser", action="store_true",     default=False,                      help="Exibe o browser durante a execução")
    parser.add_argument("--apenas-ranking",  action="store_true",     default=False,                      help="Exibe o ranking atual sem coletar")
    parser.add_argument("--somente-salvos",  action="store_true",     default=False,                      help="Reprocessa apenas posts já salvos no banco (ignora posts novos)")
    return parser.parse_args()


def _build_engagement_service(config) -> tuple[EngagementService, DatabaseManager]:
    db        = DatabaseManager(config.database.db_path)
    db.create_tables()
    eng_repo  = EngagementRepository(db)
    post_repo = PostRepository(db)
    user_repo = UserRepository(db)
    return EngagementService(eng_repo, post_repo, user_repo), db


def exibir_ranking_no_terminal(svc: EngagementService, rank_svc: RankingService) -> None:
    df_ranking = svc.get_ranking_dataframe()
    ranking    = rank_svc.calcular_ranking_from_df_agregado(df_ranking)

    if not ranking:
        print("\nNenhum dado de engajamento encontrado no banco.")
        return

    print("\n" + "=" * 72)
    print("  RANKING DE ENGAJAMENTO LINKEDIN".center(72))
    print("=" * 72)
    print(f"{'Pos':>4}  {'Usuário':<30} {'Pts':>6} {'React':>6} {'Coment':>7} {'Shares':>7}  Nível")
    print("-" * 72)

    for u in ranking[:20]:
        print(
            f"{u.posicao:>3}°  "
            f"{u.usuario[:28]:<30} "
            f"{u.pontos:>6} "
            f"{u.reactions:>6} "
            f"{u.comentarios:>7} "
            f"{u.shares:>7}  "
            f"{u.emoji_nivel} {u.nivel_engajamento}"
        )

    if len(ranking) > 20:
        print(f"\n  ... e mais {len(ranking) - 20} usuários.")

    print("=" * 72)

    stats = svc.obter_estatisticas_gerais()
    print(f"\n  Total de interações: {stats['total_interacoes']:,}")
    print(f"  Posts analisados:    {stats['total_posts']:,}")
    print(f"  Usuários únicos:     {stats['total_usuarios']:,}")
    print(f"  Pontos totais:       {stats['pontos_totais']:,}")
    print()


def main() -> None:
    args = parse_args()

    try:
        config = load_config()
    except EnvironmentError as e:
        print(f"\nERRO: {e}")
        print("Configure o arquivo .env na raiz do projeto (copie de .env.example).")
        sys.exit(1)

    # Aplica overrides dos argumentos
    if args.max_posts:
        config = replace(config, scraper=replace(config.scraper, max_posts=args.max_posts))
    if args.desde:
        config = replace(config, scraper=replace(config.scraper, data_inicio=args.desde))
    if args.mostrar_browser:
        config = replace(config, linkedin=replace(config.linkedin, headless=False))

    rank_svc = RankingService()

    # Modo apenas-ranking
    if args.apenas_ranking:
        svc, db = _build_engagement_service(config)
        try:
            exibir_ranking_no_terminal(svc, rank_svc)
        finally:
            db.dispose()
        sys.exit(0)

    # Executa pipeline
    try:
        pipeline = ETLPipeline.from_config(config)
        if args.somente_salvos:
            result = pipeline.executar_somente_posts_salvos()
        else:
            result = pipeline.executar()
    except Exception as e:
        logger.error("Falha ao inicializar pipeline: %s", e, exc_info=True)
        print(f"\nERRO: {e}")
        sys.exit(1)

    # Exibe ranking atualizado após coleta
    if result.posts_processados > 0:
        svc, db = _build_engagement_service(config)
        try:
            exibir_ranking_no_terminal(svc, rank_svc)
        finally:
            db.dispose()

    print(f"\nColeta concluída em {result.duracao_segundos:.1f}s.")
    print(f"Posts: {result.posts_processados} | Inseridos: {result.interacoes_inseridas} | Duplicatas: {result.duplicatas_ignoradas}")
    print("\nPara o dashboard: streamlit run src/dashboard/app.py")

    sys.exit(0 if result.sucesso else 1)


if __name__ == "__main__":
    main()