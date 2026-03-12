"""
post.py - Entidade de domínio e ORM para posts do LinkedIn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, Date, DateTime, Integer, String, func

from src.models.engagement import Base


class PostORM(Base):
    """Mapeamento ORM da tabela 'posts'."""

    __tablename__ = "posts"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    post_id          = Column(String(100), unique=True, nullable=False, index=True)
    url_post         = Column(String(500), nullable=False)
    data_post        = Column(Date,        nullable=True)
    total_likes      = Column(Integer,     nullable=False, default=0)
    total_comentarios = Column(Integer,    nullable=False, default=0)
    total_shares     = Column(Integer,     nullable=False, default=0)
    data_coleta      = Column(DateTime,    nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<PostORM(post_id='{self.post_id}', data_post='{self.data_post}')>"


@dataclass
class Post:
    """
    Entidade de domínio pura representando um post da empresa.
    Sem dependência de ORM.
    """
    post_id:           str
    url_post:          str
    data_post:         Optional[date] = None
    total_likes:       int = 0
    total_comentarios: int = 0
    total_shares:      int = 0
    id:                Optional[int] = None

    @property
    def total_interacoes(self) -> int:
        return self.total_likes + self.total_comentarios + self.total_shares

    @property
    def pontuacao(self) -> int:
        """Pontuação ponderada: reaction×1, comentario×2, share×2."""
        return (
            self.total_likes * 1
            + self.total_comentarios * 2
            + self.total_shares * 2
        )

    @classmethod
    def from_orm(cls, orm: PostORM) -> "Post":
        return cls(
            id=orm.id,
            post_id=orm.post_id,
            url_post=orm.url_post,
            data_post=orm.data_post,
            total_likes=orm.total_likes or 0,
            total_comentarios=orm.total_comentarios or 0,
            total_shares=orm.total_shares or 0,
        )

    def to_orm(self) -> PostORM:
        return PostORM(
            id=self.id,
            post_id=self.post_id,
            url_post=self.url_post,
            data_post=self.data_post,
            total_likes=self.total_likes,
            total_comentarios=self.total_comentarios,
            total_shares=self.total_shares,
        )