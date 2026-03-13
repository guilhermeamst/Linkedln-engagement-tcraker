"""
engagement_repository.py - Repositório de acesso a dados de engajamento.

Responsabilidade única: operações CRUD na tabela 'engagement'.
Toda a lógica de negócio fica nas camadas superiores (services).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Dict, List

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.models.engagement import Engagement, EngagementORM

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #

class IEngagementRepository(ABC):

    @abstractmethod
    def salvar(self, engagement: Engagement) -> None: ...

    @abstractmethod
    def salvar_em_lote(self, engagements: List[Engagement]) -> int: ...

    @abstractmethod
    def buscar_todos(self) -> List[Engagement]: ...

    @abstractmethod
    def buscar_por_post(self, post_id: str) -> List[Engagement]: ...

    @abstractmethod
    def buscar_por_usuario(self, usuario_id: str) -> List[Engagement]: ...

    @abstractmethod
    def buscar_por_periodo(self, inicio: date, fim: date) -> List[Engagement]: ...

    @abstractmethod
    def contar_total(self) -> int: ...

    @abstractmethod
    def get_ranking_dataframe(self) -> pd.DataFrame: ...

    @abstractmethod
    def get_engajamento_por_tipo_dataframe(self) -> pd.DataFrame: ...

    @abstractmethod
    def get_evolucao_temporal_dataframe(self) -> pd.DataFrame: ...

    @abstractmethod
    def get_engajamento_por_post_dataframe(self) -> pd.DataFrame: ...

    @abstractmethod
    def contar_por_post_e_tipo(self, post_id: str) -> Dict[str, int]: ...


# --------------------------------------------------------------------------- #
#  Implementação SQLite
# --------------------------------------------------------------------------- #

class EngagementRepository(IEngagementRepository):

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def salvar(self, engagement: Engagement) -> None:
        with self._db.get_session() as session:
            stmt = (
                sqlite_insert(EngagementORM)
                .values(
                    usuario=engagement.usuario,
                    usuario_id=engagement.usuario_id,
                    tipo=engagement.tipo.value,
                    post_id=engagement.post_id,
                    data_interacao=engagement.data_interacao,
                )
                .on_conflict_do_nothing(index_elements=["usuario_id", "tipo", "post_id"])
            )
            session.execute(stmt)
        logger.debug("Engajamento salvo: %s | %s | %s", engagement.usuario, engagement.tipo.value, engagement.post_id)

    def salvar_em_lote(self, engagements: List[Engagement]) -> int:
        if not engagements:
            return 0

        registros = [
            {
                "usuario":        e.usuario,
                "usuario_id":     e.usuario_id,
                "tipo":           e.tipo.value,
                "post_id":        e.post_id,
                "data_interacao": e.data_interacao,
            }
            for e in engagements
        ]

        with self._db.get_session() as session:
            # total_changes() é a única forma confiável de contar inserções reais
            # no SQLite com ON CONFLICT DO NOTHING (result.rowcount não é confiável).
            antes = session.execute(text("SELECT total_changes()")).scalar() or 0
            stmt = (
                sqlite_insert(EngagementORM)
                .values(registros)
                .on_conflict_do_nothing(index_elements=["usuario_id", "tipo", "post_id"])
            )
            session.execute(stmt)
            depois = session.execute(text("SELECT total_changes()")).scalar() or 0

        inseridos = depois - antes
        logger.info("Lote: %d enviados, %d inseridos.", len(engagements), inseridos)
        return inseridos

    def buscar_todos(self) -> List[Engagement]:
        with self._db.get_session() as session:
            rows = session.query(EngagementORM).all()
            return [Engagement.from_orm(row) for row in rows]

    def buscar_por_post(self, post_id: str) -> List[Engagement]:
        with self._db.get_session() as session:
            rows = session.query(EngagementORM).filter(EngagementORM.post_id == post_id).all()
            return [Engagement.from_orm(row) for row in rows]

    def buscar_por_usuario(self, usuario_id: str) -> List[Engagement]:
        with self._db.get_session() as session:
            rows = session.query(EngagementORM).filter(EngagementORM.usuario_id == usuario_id).all()
            return [Engagement.from_orm(row) for row in rows]

    def buscar_por_periodo(self, inicio: date, fim: date) -> List[Engagement]:
        with self._db.get_session() as session:
            rows = (
                session.query(EngagementORM)
                .filter(
                    EngagementORM.data_interacao >= inicio,
                    EngagementORM.data_interacao <= fim,
                )
                .all()
            )
            return [Engagement.from_orm(row) for row in rows]

    def contar_total(self) -> int:
        with self._db.get_session() as session:
            return session.query(func.count(EngagementORM.id)).scalar() or 0

    def contar_por_post_e_tipo(self, post_id: str) -> Dict[str, int]:
        """Retorna {tipo: contagem} para as interações salvas de um post."""
        sql = text("""
            SELECT tipo, COUNT(*) AS quantidade
            FROM engagement
            WHERE post_id = :post_id
            GROUP BY tipo
        """)
        with self._db.get_session() as session:
            result = session.execute(sql, {"post_id": post_id})
            rows = result.fetchall()
        return {row[0]: row[1] for row in rows}

    def get_ranking_dataframe(self) -> pd.DataFrame:
        """Ranking de usuários por pontos (reaction=1, comentario=2, share=2)."""
        sql = text("""
            SELECT
                usuario,
                usuario_id,
                SUM(
                    CASE
                        WHEN tipo = 'reaction'   THEN 1
                        WHEN tipo = 'comentario' THEN 2
                        WHEN tipo = 'share'      THEN 2
                        ELSE 0
                    END
                ) AS pontos,
                SUM(CASE WHEN tipo = 'reaction'   THEN 1 ELSE 0 END) AS reactions,
                SUM(CASE WHEN tipo = 'comentario' THEN 1 ELSE 0 END) AS comentarios,
                SUM(CASE WHEN tipo = 'share'      THEN 1 ELSE 0 END) AS shares,
                COUNT(*) AS total_interacoes
            FROM engagement
            GROUP BY usuario, usuario_id
            ORDER BY pontos DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql)
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_engajamento_por_tipo_dataframe(self) -> pd.DataFrame:
        """Contagem agregada por tipo de interação."""
        sql = text("""
            SELECT tipo, COUNT(*) AS quantidade
            FROM engagement
            GROUP BY tipo
            ORDER BY quantidade DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql)
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_evolucao_temporal_dataframe(self) -> pd.DataFrame:
        """Evolução de engajamento por data para gráfico de linha."""
        sql = text("""
            SELECT
                data_interacao,
                tipo,
                COUNT(*) AS quantidade
            FROM engagement
            WHERE data_interacao IS NOT NULL
            GROUP BY data_interacao, tipo
            ORDER BY data_interacao ASC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql)
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_engajamento_por_post_dataframe(self) -> pd.DataFrame:
        """Engajamento agrupado por post com pontuação ponderada."""
        sql = text("""
            SELECT
                e.post_id,
                p.data_post,
                p.url_post,
                SUM(CASE WHEN e.tipo = 'reaction'   THEN 1 ELSE 0 END) AS reactions,
                SUM(CASE WHEN e.tipo = 'comentario' THEN 1 ELSE 0 END) AS comentarios,
                SUM(CASE WHEN e.tipo = 'share'      THEN 1 ELSE 0 END) AS shares,
                COUNT(*) AS total_interacoes,
                SUM(
                    CASE
                        WHEN e.tipo = 'reaction'   THEN 1
                        WHEN e.tipo = 'comentario' THEN 2
                        WHEN e.tipo = 'share'      THEN 2
                        ELSE 0
                    END
                ) AS pontos
            FROM engagement e
            LEFT JOIN posts p ON e.post_id = p.post_id
            GROUP BY e.post_id
            ORDER BY pontos DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql)
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    # ------------------------------------------------------------------ #
    #  Consultas filtradas por período
    # ------------------------------------------------------------------ #

    def get_ranking_dataframe_por_periodo(self, inicio: date, fim: date) -> pd.DataFrame:
        sql = text("""
            SELECT
                e.usuario, e.usuario_id,
                SUM(CASE WHEN e.tipo='reaction' THEN 1 WHEN e.tipo='comentario' THEN 2 WHEN e.tipo='share' THEN 2 ELSE 0 END) AS pontos,
                SUM(CASE WHEN e.tipo='reaction'   THEN 1 ELSE 0 END) AS reactions,
                SUM(CASE WHEN e.tipo='comentario' THEN 1 ELSE 0 END) AS comentarios,
                SUM(CASE WHEN e.tipo='share'      THEN 1 ELSE 0 END) AS shares,
                COUNT(*) AS total_interacoes
            FROM engagement e
            JOIN posts p ON e.post_id = p.post_id
            WHERE p.data_post >= :inicio AND p.data_post <= :fim
            GROUP BY e.usuario, e.usuario_id
            ORDER BY pontos DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql, {"inicio": inicio, "fim": fim})
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_engajamento_por_tipo_dataframe_por_periodo(self, inicio: date, fim: date) -> pd.DataFrame:
        sql = text("""
            SELECT e.tipo, COUNT(*) AS quantidade
            FROM engagement e
            JOIN posts p ON e.post_id = p.post_id
            WHERE p.data_post >= :inicio AND p.data_post <= :fim
            GROUP BY e.tipo
            ORDER BY quantidade DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql, {"inicio": inicio, "fim": fim})
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_evolucao_temporal_dataframe_por_periodo(self, inicio: date, fim: date) -> pd.DataFrame:
        sql = text("""
            SELECT p.data_post AS data_interacao, e.tipo, COUNT(*) AS quantidade
            FROM engagement e
            JOIN posts p ON e.post_id = p.post_id
            WHERE p.data_post IS NOT NULL AND p.data_post >= :inicio AND p.data_post <= :fim
            GROUP BY p.data_post, e.tipo
            ORDER BY p.data_post ASC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql, {"inicio": inicio, "fim": fim})
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)

    def get_engajamento_por_post_dataframe_por_periodo(self, inicio: date, fim: date) -> pd.DataFrame:
        sql = text("""
            SELECT
                e.post_id, p.data_post, p.url_post,
                SUM(CASE WHEN e.tipo='reaction'   THEN 1 ELSE 0 END) AS reactions,
                SUM(CASE WHEN e.tipo='comentario' THEN 1 ELSE 0 END) AS comentarios,
                SUM(CASE WHEN e.tipo='share'      THEN 1 ELSE 0 END) AS shares,
                COUNT(*) AS total_interacoes,
                SUM(CASE WHEN e.tipo='reaction' THEN 1 WHEN e.tipo='comentario' THEN 2 WHEN e.tipo='share' THEN 2 ELSE 0 END) AS pontos
            FROM engagement e
            LEFT JOIN posts p ON e.post_id = p.post_id
            WHERE p.data_post >= :inicio AND p.data_post <= :fim
            GROUP BY e.post_id
            ORDER BY pontos DESC
        """)
        with self._db.get_session() as session:
            result = session.execute(sql, {"inicio": inicio, "fim": fim})
            rows = result.fetchall()
            columns = list(result.keys())
        return pd.DataFrame(rows, columns=columns)