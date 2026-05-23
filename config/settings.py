"""
Application settings loaded from environment variables / .env file.

Usage:
    from config.settings import settings
    print(settings.postgres_url)
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    postgres_url: str = "postgresql://sspm:sspm_pass@localhost:5432/sspm"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    redis_url: str = "redis://localhost:6379/0"

    # ── Encryption ────────────────────────────────────────────────────────────
    encryption_key: str = ""  # Fernet key – MUST be set in production

    # ── GitHub connector ──────────────────────────────────────────────────────
    github_token: str = ""
    github_org: str = ""
    github_base_url: str = "https://api.github.com"  # override for GHE

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ── LLM Judge (DeepSeek AI) ───────────────────────────────────────────────
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # ── Ollama LLM ────────────────────────────────────────────────────────────
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2"
    ollama_enabled: bool = True

    # ── LLM timeouts ──────────────────────────────────────────────────────────
    llm_timeout_ollama: int = 60
    llm_timeout_deepseek: int = 30
    llm_fallback_to_template: bool = True

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Default requests/second for connectors that don't set their own limit
    default_rate_limit_rps: float = 5.0
    github_rate_limit_rps: float = 1.38  # 5000/hour ≈ 1.38/s

    # ── Scan behaviour ────────────────────────────────────────────────────────
    scan_timeout_seconds: int = 300
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0

    @field_validator("encryption_key")
    @classmethod
    def _check_encryption_key(cls, v: str) -> str:
        # Allow empty only in testing; validated at runtime when encrypting
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
