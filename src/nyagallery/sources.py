"""Portable Source abstraction for import pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceItem:
    key: str
    location: str
    kind: str
    size: int | None = None


class Source(Protocol):
    name: str

    def iter_items(self) -> Iterable[SourceItem]:
        ...


class LocalDirectorySource:
    name = "local_directory"

    def __init__(self, root: str | Path, *, suffixes: set[str] | None = None) -> None:
        self.root = Path(root).resolve()
        self.suffixes = {suffix.casefold() for suffix in suffixes} if suffixes else None

    def iter_items(self) -> Iterable[SourceItem]:
        if not self.root.is_dir():
            raise FileNotFoundError(self.root)
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if self.suffixes is not None and path.suffix.casefold() not in self.suffixes:
                continue
            relative = path.relative_to(self.root).as_posix()
            yield SourceItem(key=relative, location=str(path), kind="file", size=path.stat().st_size)


class UrlListSource:
    name = "url_list"

    def __init__(self, urls: Iterable[str]) -> None:
        self.urls = tuple(self._validate(url) for url in urls if url.strip())

    def iter_items(self) -> Iterable[SourceItem]:
        for index, url in enumerate(self.urls):
            yield SourceItem(key=f"url-{index}", location=url, kind="url")

    @staticmethod
    def _validate(url: str) -> str:
        normalized = url.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"unsupported source URL: {url}")
        return normalized
