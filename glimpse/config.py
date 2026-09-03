"""Runtime configuration.

Every setting can be provided as an environment variable prefixed with ``GLIMPSE_``
(e.g. ``GLIMPSE_RUNNER=lambda``) or in a ``.env`` file in the working directory.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

RunnerKind = Literal["docker", "lambda", "unsafe-local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GLIMPSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- server ---------------------------------------------------------------
    runner: RunnerKind = "docker"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    # NoDecode: env values are plain comma-separated strings, not JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    trust_proxy: bool = False
    """Use ``X-Forwarded-For`` for the client address (only behind a trusted proxy)."""
    api_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """If non-empty, ``POST /v1/execute`` requires ``Authorization: Bearer <key>``."""
    rate_limit: str | None = "30/minute"
    """Per-client limit for ``POST /v1/execute`` as ``<count>/<second|minute|hour>``."""
    global_rate_limit: str | None = None
    """Limit for ``POST /v1/execute`` across *all* clients; protects a public instance."""
    client_ip_header: str | None = None
    """Header carrying the real client IP behind a proxy (e.g. ``CF-Connecting-IP``).
    Only used when ``trust_proxy`` is set; falls back to the first ``X-Forwarded-For`` entry."""

    # --- request limits -------------------------------------------------------
    max_code_bytes: int = 64 * 1024
    max_stdin_bytes: int = 64 * 1024
    max_output_bytes: int = 64 * 1024
    default_timeout_s: float = 10.0
    max_timeout_s: float = 30.0

    # --- docker runner --------------------------------------------------------
    sandbox_image: str = "glimpse-sandbox"
    sandbox_pool_size: int = 2
    sandbox_max_concurrency: int = 4
    sandbox_memory_mb: int = 512
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128
    sandbox_tmpfs_mb: int = 64
    sandbox_user: str = "sandbox"
    sandbox_acquire_timeout_s: float = 5.0

    # --- lambda runner --------------------------------------------------------
    lambda_function_name: str | None = None
    aws_region: str | None = None

    @field_validator("cors_origins", "api_keys", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("rate_limit", "global_rate_limit", "client_ip_header", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() in {"", "none", "off", "0"}:
            return None
        return value

    def clamp_timeout(self, requested: float | None) -> float:
        if requested is None:
            return self.default_timeout_s
        return max(1.0, min(float(requested), self.max_timeout_s))


def get_settings() -> Settings:
    return Settings()
