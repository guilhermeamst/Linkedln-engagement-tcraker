"""
database.py - Engine SQLAlchemy e gerenciamento de sessões SQLite.

Padrão Unit of Work via context manager.
Dependency Inversion: repositórios recebem DatabaseManager por injeção.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.logger import get_logger
from src.models.engagement import Base
from src.models.post import PostORM          # noqa: F401 — registra tabela no metadata
from src.models.user import UserORM          # noqa: F401 — registra tabela no metadata

logger = get_logger(__name__)


def _configure_sqlite(dbapi_connection, connection_record) -> None:  # type: ignore
    """Ativa WAL mode e foreign keys no SQLite para melhor performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class DatabaseManager:
    """
    Gerencia o ciclo de vida da conexão com o SQLite.
    Instanciar uma única vez e distribuir por injeção de dependência.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._engine: Engine = self._build_engine()
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        logger.info("DatabaseManager inicializado. DB: %s", db_path)

    def _build_engine(self) -> Engine:
        engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        event.listen(engine, "connect", _configure_sqlite)
        return engine

    def create_tables(self) -> None:
        """Cria todas as tabelas se não existirem. Idempotente."""
        Base.metadata.create_all(bind=self._engine)
        logger.info("Tabelas verificadas/criadas: %s", list(Base.metadata.tables.keys()))

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Fornece sessão transacional com commit/rollback automático.

        Uso:
            with db.get_session() as session:
                session.add(obj)
        """
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("Rollback executado: %s", exc, exc_info=True)
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Libera o pool de conexões. Chamar ao encerrar a aplicação."""
        self._engine.dispose()
        logger.info("Pool de conexões liberado.")