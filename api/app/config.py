"""App settings, read from environment variables (or a .env file).

Pydantic Settings validates them at startup, so a typo in an env var fails fast
instead of causing a confusing error later.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studyforge:studyforge@localhost:5432/studyforge"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:4200"]
    seed_demo_data: bool = True

    # JWT settings. The default secret is for local development ONLY:
    # set JWT_SECRET to a long random value anywhere real (e.g. `openssl rand -hex 32`).
    jwt_secret: str = "dev-only-change-me-0123456789abcdef0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # ---- Protocol digitization (Week 2) ----
    # Where uploaded protocol files are stored. (Week 4 swaps this for S3.)
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10

    # "auto" uses Claude when ANTHROPIC_API_KEY is set, otherwise the rule-based parser.
    extractor: Literal["auto", "claude", "rules"] = "auto"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5-5"
    claude_timeout_seconds: float = 120

    # Background job retries (transient failures only, e.g. rate limits or timeouts).
    job_max_tries: int = 3
    job_retry_base_seconds: int = 5
    # Pause between stages so progress is visible in the demo. 0 in tests.
    job_stage_delay_seconds: float = 0.6


settings = Settings()
