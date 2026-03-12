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

# Carrega o .env a partir da raiz do projeto (usado localmente)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

def _get(key: str, default: str | None = None) -> str | None:
    """Lê de st.secrets (Streamlit Cloud) ou variável de ambiente (local)."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


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


def _require(key: str) -> str:
    """Lê uma variável obrigatória de st.secrets ou .env; lança erro se ausente."""
    value = _get(key)
    if not value:
        raise EnvironmentError(
            f"Variável obrigatória não definida: '{key}'. "
            f"Configure no arquivo .env (local) ou em Secrets (Streamlit Cloud)."
        )
    return value


def load_config() -> AppConfig:
    """
    Constrói e retorna a configuração completa da aplicação.
    Deve ser chamada uma única vez na inicialização.
    """
    db_path = BASE_DIR / _get("DB_PATH", "linkedin_engagement.db")

    linkedin = LinkedInConfig(
        email=_require("LINKEDIN_EMAIL"),
        password=_require("LINKEDIN_PASSWORD"),
        company_page_url=_require("LINKEDIN_COMPANY_URL"),
        headless=_get("BROWSER_HEADLESS", "true").lower() == "true",
        slow_mo_ms=int(_get("BROWSER_SLOW_MO_MS", "50")),
    )

    database = DatabaseConfig(db_path=db_path)

    scraper = ScraperConfig(
        data_inicio=date.fromisoformat(_get("SCRAPER_DATA_INICIO", "2026-01-01")),
        max_posts=int(_get("SCRAPER_MAX_POSTS", "500")),
        wait_timeout_ms=int(_get("SCRAPER_WAIT_TIMEOUT_MS", "30000")),
        retry_attempts=int(_get("SCRAPER_RETRY_ATTEMPTS", "3")),
        delay_between_posts_s=float(_get("SCRAPER_DELAY_POSTS_S", "2.0")),
        delay_between_pages_s=float(_get("SCRAPER_DELAY_PAGES_S", "1.5")),
    )

    return AppConfig(linkedin=linkedin, database=database, scraper=scraper)
