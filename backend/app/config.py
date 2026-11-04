"""Application settings, loaded from environment variables prefixed with ``HAKOBU_``."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAKOBU_", env_file=".env", extra="ignore")

    # Storage / limits
    data_dir: Path = Path("/tmp/hakobu")
    max_upload_mb: int = 200
    file_ttl_seconds: int = 3600
    cleanup_interval_seconds: int = 300
    max_archive_expanded_mb: int = 2048
    max_archive_entries: int = 10_000

    # Infrastructure
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "conversions"
    job_timeout_seconds: int = 900
    # Run jobs inline (tests / single-process dev without a worker).
    sync_jobs: bool = False

    # Subprocess guards
    subprocess_timeout_seconds: int = 600
    subprocess_memory_mb: int = 4096

    # LibreOffice warm instances (unoserver). Ports are base_port, base_port+1, ...
    unoserver_host: str = "127.0.0.1"
    unoserver_base_port: int = 2003
    unoserver_instances: int = 0  # 0 = no warm instance; fall back to one-shot soffice

    # FFmpeg hardware acceleration: "auto" probes once, "off" disables.
    ffmpeg_hwaccel: str = "auto"

    # HTTP
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_minute: int = 120

    worker_concurrency: int = Field(default_factory=lambda: os.cpu_count() or 2)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
