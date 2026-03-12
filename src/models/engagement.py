"""
engagement.py - Entidade de domínio e ORM para interações de usuários em posts.

Interações suportadas: reaction (todos os tipos), comentario, share.
Pontuação: reaction=1, comentario=2, share=2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base SQLAlchemy compartilhada por todos os modelos ORM."""
    pass


class TipoInteracao(str, Enum):
    """
    Tipos de interação coletados do LinkedIn.
    Valor string usado diretamente no banco de dados.
    """
    LIKE    = "reaction"    # Todas as reações (curtir, amei, apoio, etc.)
    COMENTARIO = "comentario"
    SHARE   = "share"

    @property
    def pontos(self) -> int:
        _mapa = {
            TipoInteracao.LIKE:       1,
            TipoInteracao.COMENTARIO: 2,
            TipoInteracao.SHARE:      2,
        }
        return _mapa[self]


class EngagementORM(Base):
    """Mapeamento ORM da tabela 'engagement'."""

    __tablename__ = "engagement"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    usuario        = Column(String(255), nullable=False)
    usuario_id     = Column(String(64),  nullable=False, index=True)
    tipo           = Column(String(20),  nullable=False)
    post_id        = Column(String(100), nullable=False, index=True)
    data_interacao = Column(Date,        nullable=True)
    data_coleta    = Column(DateTime,    nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("usuario_id", "tipo", "post_id", name="uq_engagement"),
    )

    def __repr__(self) -> str:
        return (
            f"<EngagementORM(usuario='{self.usuario}', "
            f"tipo='{self.tipo}', post_id='{self.post_id}')>"
        )


@dataclass
class Engagement:
    """
    Entidade de domínio pura — sem dependência de ORM.
    Representa uma interação de um usuário em um post.
    """
    usuario:        str
    usuario_id:     str
    tipo:           TipoInteracao
    post_id:        str
    data_interacao: Optional[date] = None
    id:             Optional[int]  = None

    @property
    def pontos(self) -> int:
        return self.tipo.pontos

    @classmethod
    def from_orm(cls, orm: EngagementORM) -> "Engagement":
        return cls(
            id=orm.id,
            usuario=orm.usuario,
            usuario_id=orm.usuario_id,
            tipo=TipoInteracao(orm.tipo),
            post_id=orm.post_id,
            data_interacao=orm.data_interacao,
        )

    def to_orm(self) -> EngagementORM:
        return EngagementORM(
            id=self.id,
            usuario=self.usuario,
            usuario_id=self.usuario_id,
            tipo=self.tipo.value,
            post_id=self.post_id,
            data_interacao=self.data_interacao,
        )