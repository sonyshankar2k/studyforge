"""App settings, read from environment variables (or a .env file).

Pydantic Settings validates them at startup, so a typo in an env var fails fast
instead of causing a confusing error later.
"""

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


settings = Settings()
