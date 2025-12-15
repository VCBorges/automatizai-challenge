import enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


_settings = None


class StorageBackend(enum.StrEnum):
    LOCAL = "local"


class Settings(BaseSettings):
    DEBUG: bool = True

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    POSTGRES_DRIVER: str = "postgresql+asyncpg"

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int

    OPENROUTER_API_KEY: str
    OPENROUTER_API_BASE_URL: str
    OPENROUTER_MODEL: str = "qwen/qwen3-4b-2507"
    OPENROUTER_TEMPERATURE: float = 0.0

    UVICORN_HOST: str = "0.0.0.0"
    UVICORN_PORT: int = 8000
    UVICORN_RELOAD: bool = False

    # Storage settings
    STORAGE_BACKEND: StorageBackend = StorageBackend.LOCAL
    STORAGE_LOCAL_PATH: Path = BASE_DIR / "static"

    # Langfuse settings
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    @property
    def POSTGRES_URL(self) -> str:
        return f"{self.POSTGRES_DRIVER}://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def LANGFUSE_ENABLED(self) -> bool:
        return (
            self.LANGFUSE_PUBLIC_KEY is not None
            and self.LANGFUSE_SECRET_KEY is not None
            and self.LANGFUSE_BASE_URL is not None
        )


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
