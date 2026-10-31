from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    delivery_url: str


class StorageInterface(Protocol):
    name: str

    def put(self, key: str, data: bytes | BinaryIO) -> StoredObject:
        ...

    def open(self, key: str) -> BinaryIO:
        ...

    def delete(self, key: str) -> None:
        ...

    def delivery_url(self, key: str) -> str:
        ...


class LocalStorageBackend:
    name = "local"

    def __init__(self, root: str | Path, *, base_url: str = "/media") -> None:
        self.root = Path(root).resolve()
        self.base_url = base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("storage key escapes root")
        return path

    def put(self, key: str, data: bytes | BinaryIO) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
            size = len(data)
        else:
            size = 0
            with path.open("wb") as output:
                while chunk := data.read(1024 * 1024):
                    output.write(chunk)
                    size += len(chunk)
        return StoredObject(key=key, size=size, delivery_url=self.delivery_url(key))

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delivery_url(self, key: str) -> str:
        return f"{self.base_url}/{key.lstrip('/')}"
