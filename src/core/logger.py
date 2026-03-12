"""
logger.py - Configuração centralizada de logging.

Fornece uma factory de loggers consistente para toda a aplicação.
Grava logs em arquivo rotativo e no console simultaneamente.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger() -> None:
    """Configura o logger raiz com handlers de console e arquivo."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Handler para console (INFO e acima)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # Handler para arquivo rotativo (DEBUG e acima)
    file_handler = RotatingFileHandler(
        filename=LOG_DIR / "linkedin_tracker.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # Handler de erros separado para facilitar diagnóstico
    error_handler = RotatingFileHandler(
        filename=LOG_DIR / "errors.log",
        maxBytes=2 * 1024 * 1024,  # 2 MB
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.addHandler(error_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger nomeado pronto para uso.

    Args:
        name: Nome do módulo/componente. Use __name__ para convenção padrão.

    Returns:
        Logger configurado e pronto para uso.
    """
    _configure_root_logger()
    return logging.getLogger(name)
