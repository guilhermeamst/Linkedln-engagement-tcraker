"""
ranking_service.py - Serviço de cálculo e geração de rankings.

Responsabilidade única: aplicar regras de pontuação e gerar rankings.
Desacoplado do banco de dados: recebe DataFrames como entrada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from src.core.logger import get_logger
from src.models.engagement import TipoInteracao

logger = get_logger(__name__)

# Pontuação por tipo de interação — fonte única da verdade
PONTUACAO: Dict[str, int] = {
    TipoInteracao.LIKE.value:       1,   # reaction
    TipoInteracao.COMENTARIO.value: 2,
    TipoInteracao.SHARE.value:      2,
}


@dataclass(frozen=True)
class UsuarioRanking:
    """Value Object representando a posição de um usuário no ranking."""
    posicao:          int
    usuario:          str
    usuario_id:       str
    pontos:           int
    reactions:        int
    comentarios:      int
    shares:           int
    total_interacoes: int

    @property
    def nivel_engajamento(self) -> str:
        if self.pontos >= 30:
            return "Embaixador"
        elif self.pontos >= 15:
            return "Entusiasta"
        elif self.pontos >= 5:
            return "Colaborador"
        else:
            return "Iniciante"

    @property
    def emoji_nivel(self) -> str:
        return {
            "Embaixador":  "★",
            "Entusiasta":  "◆",
            "Colaborador": "●",
            "Iniciante":   "○",
        }.get(self.nivel_engajamento, "○")


class RankingService:
    """
    Calcula e formata o ranking de usuários.
    Não acessa banco de dados diretamente.
    """

    def calcular_ranking(self, df_engajamento: pd.DataFrame) -> List[UsuarioRanking]:
        """
        Calcula ranking a partir de DataFrame com registros individuais.
        Colunas esperadas: usuario, usuario_id, tipo.
        """
        if df_engajamento.empty:
            logger.warning("DataFrame de engajamento vazio. Ranking não calculado.")
            return []

        df = df_engajamento.copy()
        df["pontos_unitarios"] = df["tipo"].map(PONTUACAO).fillna(0).astype(int)

        agg = (
            df.groupby(["usuario", "usuario_id"])
            .agg(
                pontos=("pontos_unitarios", "sum"),
                reactions=("tipo", lambda x: (x == TipoInteracao.LIKE.value).sum()),
                comentarios=("tipo", lambda x: (x == TipoInteracao.COMENTARIO.value).sum()),
                shares=("tipo", lambda x: (x == TipoInteracao.SHARE.value).sum()),
                total_interacoes=("tipo", "count"),
            )
            .reset_index()
            .sort_values("pontos", ascending=False)
            .reset_index(drop=True)
        )

        ranking: List[UsuarioRanking] = []
        for idx, row in agg.iterrows():
            ranking.append(
                UsuarioRanking(
                    posicao=int(idx) + 1,
                    usuario=str(row["usuario"]),
                    usuario_id=str(row["usuario_id"]),
                    pontos=int(row["pontos"]),
                    reactions=int(row["reactions"]),
                    comentarios=int(row["comentarios"]),
                    shares=int(row["shares"]),
                    total_interacoes=int(row["total_interacoes"]),
                )
            )

        logger.info("Ranking calculado: %d usuários.", len(ranking))
        return ranking

    def calcular_ranking_from_df_agregado(self, df_agregado: pd.DataFrame) -> List[UsuarioRanking]:
        """
        Constrói ranking a partir de DataFrame já agregado retornado pelo repositório.
        Colunas esperadas: usuario, usuario_id, pontos, reactions, comentarios, shares, total_interacoes.
        """
        if df_agregado.empty:
            return []

        ranking: List[UsuarioRanking] = []
        for idx, row in df_agregado.reset_index(drop=True).iterrows():
            ranking.append(
                UsuarioRanking(
                    posicao=int(idx) + 1,
                    usuario=str(row["usuario"]),
                    usuario_id=str(row["usuario_id"]),
                    pontos=int(row["pontos"]),
                    reactions=int(row.get("reactions", row.get("likes", 0))),
                    comentarios=int(row.get("comentarios", 0)),
                    shares=int(row.get("shares", 0)),
                    total_interacoes=int(row.get("total_interacoes", 0)),
                )
            )

        return ranking

    def obter_top_n(self, ranking: List[UsuarioRanking], n: int = 3) -> List[UsuarioRanking]:
        return ranking[:n]

    def ranking_para_dataframe(self, ranking: List[UsuarioRanking]) -> pd.DataFrame:
        """Converte ranking para DataFrame formatado para exibição no dashboard."""
        if not ranking:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                "Posição":           f"{r.posicao}°",
                "Usuário":           r.usuario,
                "Pontos":            r.pontos,
                "Reactions":         r.reactions,
                "Comentários":       r.comentarios,
                "Shares":            r.shares,
                "Total Interações":  r.total_interacoes,
                "Nível":             f"{r.emoji_nivel} {r.nivel_engajamento}",
            }
            for r in ranking
        ])

    def calcular_pontuacao_usuario(self, reactions: int, comentarios: int, shares: int) -> int:
        return (
            reactions   * PONTUACAO[TipoInteracao.LIKE.value]
            + comentarios * PONTUACAO[TipoInteracao.COMENTARIO.value]
            + shares      * PONTUACAO[TipoInteracao.SHARE.value]
        )