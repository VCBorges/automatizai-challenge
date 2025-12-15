"""
Dependency injection for services.
"""

from functools import lru_cache

from src.core.settings import StorageBackend, get_settings
from src.core.storage.backends import FileStorage, LocalFileStorage

settings = get_settings()


@lru_cache
def get_storage() -> FileStorage:
    match settings.STORAGE_BACKEND:
        case StorageBackend.LOCAL:
            return LocalFileStorage(base_path=settings.STORAGE_LOCAL_PATH)

        case _:
            raise ValueError(f"Unsupported storage backend: {settings.STORAGE_BACKEND}")


__all__ = [
    "get_storage",
]
