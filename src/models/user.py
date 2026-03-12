"""
user.py - Entidade de domínio e ORM para usuários que engajaram nos posts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Column, DateTime, String, func

from src.models.engagement import Base


class UserORM(Base):
    """Mapeamento ORM da tabela 'users'."""

    __tablename__ = "users"

    usuario_id  = Column(String(64),  primary_key=True)
    nome        = Column(String(255), nullable=False)
    data_coleta = Column(DateTime,    nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<UserORM(usuario_id='{self.usuario_id}', nome='{self.nome}')>"


@dataclass
class User:
    """
    Entidade de domínio pura representando um usuário do LinkedIn.
    """
    usuario_id: str
    nome:       str

    @classmethod
    def from_orm(cls, orm: UserORM) -> "User":
        return cls(usuario_id=orm.usuario_id, nome=orm.nome)

    def to_orm(self) -> UserORM:
        return UserORM(usuario_id=self.usuario_id, nome=self.nome)