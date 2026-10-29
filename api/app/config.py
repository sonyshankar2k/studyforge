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


settings = Settings()
