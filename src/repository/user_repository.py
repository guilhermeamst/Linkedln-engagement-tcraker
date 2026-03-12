"""
user_repository.py - Repositório de acesso a dados de usuários.

Responsabilidade única: operações CRUD na tabela 'users'.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.models.user import User, UserORM

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #

class IUserRepository(ABC):

    @abstractmethod
    def salvar(self, user: User) -> None: ...

    @abstractmethod
    def salvar_em_lote(self, users: List[User]) -> None: ...

    @abstractmethod
    def buscar_por_id(self, usuario_id: str) -> Optional[User]: ...

    @abstractmethod
    def buscar_por_nome(self, nome: str) -> Optional[User]: ...

    @abstractmethod
    def buscar_todos(self) -> List[User]: ...

    @abstractmethod
    def contar_total(self) -> int: ...


# --------------------------------------------------------------------------- #
#  Implementação SQLite
# --------------------------------------------------------------------------- #

class UserRepository(IUserRepository):

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def salvar(self, user: User) -> None:
        """Upsert: insere ou atualiza o nome se o usuario_id já existir."""
        with self._db.get_session() as session:
            stmt = (
                sqlite_insert(UserORM)
                .values(usuario_id=user.usuario_id, nome=user.nome)
                .on_conflict_do_update(
                    index_elements=["usuario_id"],
                    set_={"nome": user.nome},
                )
            )
            session.execute(stmt)
        logger.debug("User salvo: %s (%s)", user.nome, user.usuario_id)

    def salvar_em_lote(self, users: List[User]) -> None:
        if not users:
            return
        with self._db.get_session() as session:
            for user in users:
                stmt = (
                    sqlite_insert(UserORM)
                    .values(usuario_id=user.usuario_id, nome=user.nome)
                    .on_conflict_do_update(
                        index_elements=["usuario_id"],
                        set_={"nome": user.nome},
                    )
                )
                session.execute(stmt)
        logger.info("%d users salvos/atualizados.", len(users))

    def buscar_por_id(self, usuario_id: str) -> Optional[User]:
        with self._db.get_session() as session:
            row = session.query(UserORM).filter(UserORM.usuario_id == usuario_id).first()
            return User.from_orm(row) if row else None

    def buscar_por_nome(self, nome: str) -> Optional[User]:
        """Busca um usuário pelo nome exato (case-insensitive, ignora espaços)."""
        nome_norm = nome.strip().lower()
        with self._db.get_session() as session:
            row = (
                session.query(UserORM)
                .filter(func.lower(func.trim(UserORM.nome)) == nome_norm)
                .first()
            )
            return User.from_orm(row) if row else None

    def buscar_todos(self) -> List[User]:
        with self._db.get_session() as session:
            rows = session.query(UserORM).order_by(UserORM.nome).all()
            return [User.from_orm(row) for row in rows]

    def contar_total(self) -> int:
        with self._db.get_session() as session:
            return session.query(func.count(UserORM.usuario_id)).scalar() or 0