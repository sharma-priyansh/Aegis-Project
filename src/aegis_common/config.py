"""Centralised, environment-driven configuration.

All services share one Settings object so connection strings and tuning knobs are
defined once. Values come from environment variables (12-factor) with sane local
defaults that match docker-compose.yml.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEGIS_", env_file=".env", extra="ignore")

    # --- Service identity (set per-service via env) ---
    service_name: str = Field(default="aegis-service")
    environment: str = Field(default="local")
    log_level: str = Field(default="INFO")

    # --- Postgres ---
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- Kafka ---
    kafka_bootstrap: str = Field(default="localhost:9092")
    kafka_client_id: str = Field(default="aegis")

    # --- OpenTelemetry ---
    otel_endpoint: str = Field(default="http://localhost:4317")
    otel_enabled: bool = Field(default=True)

    # --- Qdrant (Phase 2) ---
    qdrant_url: str = Field(default="http://localhost:6333")

    # --- Ollama (Phase 3, ADR-010) ---
    ollama_url: str = Field(default="http://localhost:11434")
    llm_model: str = Field(default="qwen2.5:7b-instruct")
    embedding_model: str = Field(default="nomic-embed-text")

    # --- Detection / correlation tuning (ADR-018) ---
    correlation_window_seconds: int = Field(default=120)
    dedup_window_seconds: int = Field(default=300)

    # --- Agent safety budgets (ADR-017) ---
    max_diagnose_iterations: int = Field(default=4)
    incident_wallclock_budget_seconds: int = Field(default=600)
    incident_token_budget: int = Field(default=120_000)


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton settings."""
    return Settings()
