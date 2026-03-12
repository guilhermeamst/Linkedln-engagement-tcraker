"""
config.py - Configurações centrais da aplicação.

Carrega variáveis de ambiente e expõe configurações tipadas para toda a aplicação.
Segue o princípio de Single Responsibility: este módulo é o único responsável
por gerenciar configuração.
"""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Carrega o .env a partir da raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


@dataclass(frozen=True)
class LinkedInConfig:
    """Configurações de acesso ao LinkedIn."""
    email: str
    password: str
    company_page_url: str
    headless: bool
    slow_mo_ms: int


@dataclass(frozen=True)
class DatabaseConfig:
    """Configurações do banco de dados SQLite."""
    db_path: Path


@dataclass(frozen=True)
class ScraperConfig:
    """Configurações de comportamento do scraper."""
    data_inicio: date
    max_posts: int
    wait_timeout_ms: int
    retry_attempts: int
    delay_between_posts_s: float
    delay_between_pages_s: float


@dataclass(frozen=True)
class AppConfig:
    """Configuração raiz que agrega todas as sub-configurações."""
    linkedin: LinkedInConfig
    database: DatabaseConfig
    scraper: ScraperConfig


def _require_env(key: str) -> str:
    """Lê uma variável de ambiente obrigatória; lança erro se ausente."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Variável de ambiente obrigatória não definida: '{key}'. "
            f"Verifique o arquivo .env na raiz do projeto."
        )
    return value


def load_config() -> AppConfig:
    """
    Constrói e retorna a configuração completa da aplicação.
    Deve ser chamada uma única vez na inicialização.
    """
    db_path = BASE_DIR / os.getenv("DB_PATH", "linkedin_engagement.db")

    linkedin = LinkedInConfig(
        email=_require_env("LINKEDIN_EMAIL"),
        password=_require_env("LINKEDIN_PASSWORD"),
        company_page_url=_require_env("LINKEDIN_COMPANY_URL"),
        headless=os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
        slow_mo_ms=int(os.getenv("BROWSER_SLOW_MO_MS", "50")),
    )

    database = DatabaseConfig(db_path=db_path)

    scraper = ScraperConfig(
        data_inicio=date.fromisoformat(os.getenv("SCRAPER_DATA_INICIO", "2026-01-01")),
        max_posts=int(os.getenv("SCRAPER_MAX_POSTS", "500")),
        wait_timeout_ms=int(os.getenv("SCRAPER_WAIT_TIMEOUT_MS", "30000")),
        retry_attempts=int(os.getenv("SCRAPER_RETRY_ATTEMPTS", "3")),
        delay_between_posts_s=float(os.getenv("SCRAPER_DELAY_POSTS_S", "2.0")),
        delay_between_pages_s=float(os.getenv("SCRAPER_DELAY_PAGES_S", "1.5")),
    )

    return AppConfig(linkedin=linkedin, database=database, scraper=scraper)
