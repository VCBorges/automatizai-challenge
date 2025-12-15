import abc
import hashlib
from pathlib import Path

from pydantic import BaseModel


class StoredFileInfo(BaseModel):
    object_key: str
    size_bytes: int
    checksum_sha256: str


class FileStorage(abc.ABC):
    @abc.abstractmethod
    async def save(
        self,
        content: bytes,
        object_key: str,
    ) -> StoredFileInfo: ...

    @abc.abstractmethod
    async def load(self, object_key: str) -> bytes: ...

    @abc.abstractmethod
    async def delete(self, object_key: str) -> bool: ...

    @abc.abstractmethod
    async def exists(self, object_key: str) -> bool: ...

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()


class LocalFileStorage(FileStorage):
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, object_key: str) -> Path:
        return self.base_path / object_key

    async def save(self, content: bytes, object_key: str) -> StoredFileInfo:
        full_path = self._get_full_path(object_key)

        full_path.parent.mkdir(parents=True, exist_ok=True)

        full_path.write_bytes(content)

        return StoredFileInfo(
            object_key=object_key,
            size_bytes=len(content),
            checksum_sha256=self.compute_checksum(content),
        )

    async def load(self, object_key: str) -> bytes:
        full_path = self._get_full_path(object_key)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {object_key}")

        return full_path.read_bytes()

    async def delete(self, object_key: str) -> bool:
        full_path = self._get_full_path(object_key)

        if not full_path.exists():
            return False

        full_path.unlink()
        return True

    async def exists(self, object_key: str) -> bool:
        full_path = self._get_full_path(object_key)
        return full_path.exists()

    def get_absolute_path(self, object_key: str) -> Path:
        return self._get_full_path(object_key).resolve()
