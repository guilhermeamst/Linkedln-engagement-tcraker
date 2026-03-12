"""
post_repository.py - Repositório de acesso a dados de posts.

Responsabilidade única: operações CRUD na tabela 'posts'.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.models.post import Post, PostORM

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #

class IPostRepository(ABC):
    """Interface abstrata para o repositório de posts."""

    @abstractmethod
    def salvar(self, post: Post) -> None:
        """Persiste um post. Atualiza se já existir (upsert)."""
        ...

    @abstractmethod
    def salvar_em_lote(self, posts: List[Post]) -> None:
        """Persiste uma lista de posts via upsert."""
        ...

    @abstractmethod
    def buscar_por_id(self, post_id: str) -> Optional[Post]:
        """Retorna um post pelo seu ID único do LinkedIn."""
        ...

    @abstractmethod
    def buscar_todos(self) -> List[Post]:
        """Retorna todos os posts cadastrados, do mais recente ao mais antigo."""
        ...

    @abstractmethod
    def post_existe(self, post_id: str) -> bool:
        """Verifica se um post já está cadastrado no banco."""
        ...

    @abstractmethod
    def contar_total(self) -> int:
        """Conta o total de posts no banco."""
        ...


# --------------------------------------------------------------------------- #
#  Implementação SQLite
# --------------------------------------------------------------------------- #

class PostRepository(IPostRepository):
    """Implementação concreta do repositório de posts."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def _valores(self, post: Post) -> dict:
        return {
            "post_id":           post.post_id,
            "url_post":          post.url_post,
            "data_post":         post.data_post,
            "total_likes":       post.total_likes,
            "total_comentarios": post.total_comentarios,
            "total_shares":      post.total_shares,
        }

    def salvar(self, post: Post) -> None:
        vals = self._valores(post)
        with self._db.get_session() as session:
            stmt = (
                sqlite_insert(PostORM)
                .values(**vals)
                .on_conflict_do_nothing(index_elements=["post_id"])
            )
            session.execute(stmt)
        logger.debug("Post salvo (ignorado se já existia): %s", post.post_id)

    def salvar_em_lote(self, posts: List[Post]) -> None:
        if not posts:
            return
        with self._db.get_session() as session:
            for post in posts:
                vals = self._valores(post)
                stmt = (
                    sqlite_insert(PostORM)
                    .values(**vals)
                    .on_conflict_do_nothing(index_elements=["post_id"])
                )
                session.execute(stmt)
        logger.info("%d posts processados em lote (ignorados se já existiam).", len(posts))

    def buscar_por_id(self, post_id: str) -> Optional[Post]:
        with self._db.get_session() as session:
            row = (
                session.query(PostORM)
                .filter(PostORM.post_id == post_id)
                .first()
            )
            return Post.from_orm(row) if row else None

    def buscar_todos(self) -> List[Post]:
        with self._db.get_session() as session:
            rows = session.query(PostORM).order_by(PostORM.data_post.desc()).all()
            return [Post.from_orm(row) for row in rows]

    def post_existe(self, post_id: str) -> bool:
        with self._db.get_session() as session:
            count = (
                session.query(PostORM)
                .filter(PostORM.post_id == post_id)
                .count()
            )
            return count > 0

    def contar_total(self) -> int:
        with self._db.get_session() as session:
            return session.query(func.count(PostORM.id)).scalar() or 0