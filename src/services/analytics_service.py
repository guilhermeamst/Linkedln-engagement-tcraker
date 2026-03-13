"""
analytics_service.py - Serviço de analytics para o dashboard executivo.

Agrega e formata os dados prontos para consumo pelo Streamlit,
encapsulando toda a lógica de apresentação de métricas.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

import pandas as pd

from src.core.logger import get_logger
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService, UsuarioRanking

logger = get_logger(__name__)


class AnalyticsService:
    """
    Fachada de analytics: combina EngagementService e RankingService
    para fornecer dados prontos ao dashboard.
    """

    def __init__(
        self,
        engagement_service: EngagementService,
        ranking_service: RankingService,
    ) -> None:
        self._eng = engagement_service
        self._rank = ranking_service

    def obter_kpis(self) -> Dict[str, int]:
        """
        Retorna os KPIs principais para os cards do dashboard.

        Keys: total_interacoes, total_posts, total_usuarios,
              total_reactions, total_comentarios, total_shares, pontos_totais.
        """
        return self._eng.obter_estatisticas_gerais()

    def obter_ranking_completo(self) -> List[UsuarioRanking]:
        """Ranking completo de usuários por pontuação."""
        df = self._eng.get_ranking_dataframe()
        return self._rank.calcular_ranking_from_df_agregado(df)

    def obter_ranking_dataframe(self) -> pd.DataFrame:
        """DataFrame formatado do ranking para exibição em tabela."""
        ranking = self.obter_ranking_completo()
        return self._rank.ranking_para_dataframe(ranking)

    def obter_top3(self) -> List[UsuarioRanking]:
        """Top 3 usuários para destaque no dashboard."""
        return self._rank.obter_top_n(self.obter_ranking_completo(), n=3)

    def obter_evolucao_temporal(self) -> pd.DataFrame:
        """
        DataFrame com evolução de engajamento por data e tipo.
        Colunas: data_interacao, tipo, quantidade.
        """
        return self._eng.get_evolucao_temporal_dataframe()

    def obter_distribuicao_tipos(self) -> pd.DataFrame:
        """
        DataFrame com distribuição de interações por tipo.
        Colunas: tipo, quantidade.
        """
        return self._eng.get_engajamento_por_tipo_dataframe()

    def obter_posts_por_engajamento(self) -> pd.DataFrame:
        """
        DataFrame de posts ordenados por pontuação.
        Colunas: post_id, data_post, url_post, reactions, comentarios,
                 shares, total_interacoes, pontos.
        """
        return self._eng.get_engajamento_por_post_dataframe()

    def obter_dados_filtrados(self, inicio: date, fim: date) -> Dict:
        """Retorna todos os dados do dashboard filtrados pelo período informado."""
        raw = self._eng.get_dados_filtrados_por_periodo(inicio, fim)

        df_tipos  = raw["df_tipos"]
        df_posts  = raw["df_posts"]
        ranking   = self._rank.calcular_ranking_from_df_agregado(raw["df_ranking"])

        reactions = comentarios = shares = 0
        if not df_tipos.empty:
            for _, row in df_tipos.iterrows():
                if row["tipo"] == "reaction":   reactions   = int(row["quantidade"])
                elif row["tipo"] == "comentario": comentarios = int(row["quantidade"])
                elif row["tipo"] == "share":    shares      = int(row["quantidade"])

        kpis = {
            "total_interacoes":   reactions + comentarios + shares,
            "total_posts":        len(df_posts),
            "total_usuarios":     len(ranking),
            "total_reactions":    reactions,
            "total_comentarios":  comentarios,
            "total_shares":       shares,
            "pontos_totais":      reactions + comentarios * 2 + shares * 2,
        }

        niveis: Dict[str, int] = {}
        for r in ranking:
            niveis[r.nivel_engajamento] = niveis.get(r.nivel_engajamento, 0) + 1
        ordem = ["Embaixador", "Entusiasta", "Colaborador", "Iniciante"]
        rows_nv = [{"Nível": n, "Usuários": niveis.get(n, 0)} for n in ordem if n in niveis]

        return {
            "kpis":     kpis,
            "ranking":  ranking,
            "df_tipos": df_tipos,
            "df_temp":  raw["df_temp"],
            "df_posts": df_posts,
            "niveis":   pd.DataFrame(rows_nv) if rows_nv else pd.DataFrame(columns=["Nível", "Usuários"]),
        }

    def obter_resumo_por_nivel(self) -> pd.DataFrame:
        """
        Agrupa o ranking por nível de engajamento.
        Retorna contagem de usuários por nível.
        """
        ranking = self.obter_ranking_completo()
        if not ranking:
            return pd.DataFrame(columns=["Nível", "Usuários"])

        niveis: Dict[str, int] = {}
        for r in ranking:
            niveis[r.nivel_engajamento] = niveis.get(r.nivel_engajamento, 0) + 1

        ordem = ["Embaixador", "Entusiasta", "Colaborador", "Iniciante"]
        rows = [{"Nível": n, "Usuários": niveis.get(n, 0)} for n in ordem if n in niveis]
        return pd.DataFrame(rows)