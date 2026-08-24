"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_PORT = 8011
DEFAULT_API_BASE_URL = f"http://127.0.0.1:{DEFAULT_API_PORT}"


class Settings(BaseSettings):
    """Runtime settings. Secret values are masked by Pydantic in logs and reprs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    copilot_runtime_mode: Literal["portable", "local", "live"] = "portable"
    log_level: str = "INFO"
    api_port: int = DEFAULT_API_PORT
    ui_port: int = 8501
    copilot_api_url: AnyHttpUrl | None = None
    copilot_public_api_url: AnyHttpUrl | None = None

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_reranker_model: str = "gpt-5-mini"
    openai_reranker_version: str = "configured"
    reranker_failure_policy: Literal["fail_closed", "heuristic_fallback"] = "fail_closed"
    reranker_timeout_seconds: float = Field(default=4.0, ge=1.0, le=4.0)
    reranker_max_candidates: int = Field(default=20, ge=1, le=20)
    reranker_max_text_chars: int = Field(default=1200, ge=200, le=2000)

    agent_max_model_calls: int = Field(default=8, ge=1, le=32)
    agent_max_tool_calls: int = Field(default=6, ge=1, le=24)
    agent_max_seconds: float = Field(default=60.0, gt=0, le=300)
    agent_model_request_timeout_seconds: float = Field(default=28.0, gt=0, le=300)
    agent_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"
    agent_max_cost_usd: float = Field(default=0.25, gt=0)
    agent_input_cost_per_1k_tokens: float = Field(default=0.00025, gt=0)
    agent_output_cost_per_1k_tokens: float = Field(default=0.002, gt=0)

    mem0_api_key: SecretStr | None = None

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: AnyHttpUrl = "http://localhost:3000"
    langfuse_debug: bool = False

    database_url: PostgresDsn = "postgresql://civil_copilot:change-me@localhost:55432/civil_copilot"
    qdrant_url: AnyHttpUrl = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("change-me")

    @property
    def api_base_url(self) -> str:
        """Return the application-to-API service URL without a trailing slash."""

        if self.copilot_api_url:
            return str(self.copilot_api_url).rstrip("/")
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def public_api_base_url(self) -> str:
        """Return the browser-facing API URL used by clickable citations."""

        if self.copilot_public_api_url:
            return str(self.copilot_public_api_url).rstrip("/")
        return f"http://127.0.0.1:{self.api_port}"


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings object per process."""

    return Settings()
