"""Read-only compatibility readers for historical metadata files."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterator

from nyagallery.asset import Asset
from nyagallery.metadata import GalleryMetadata


LEGACY_SCHEMA = "nyagallery.creator_metadata.v1"


@dataclass(frozen=True)
class LegacyDocument:
    path: Path
    schema: str
    assets: tuple[GalleryMetadata, ...]


class LegacyReader:
    """Parse v1 JSON without modifying or normalizing the source files."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def detect_schema(path: str | Path) -> str:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(document, dict) and document.get("schema") == LEGACY_SCHEMA:
            return LEGACY_SCHEMA
        if isinstance(document, dict) and isinstance(document.get("assets"), list):
            return LEGACY_SCHEMA
        if isinstance(document, dict) and {"source", "source_id", "file_sha256"}.issubset(document):
            return LEGACY_SCHEMA
        raise ValueError(f"unsupported metadata schema: {path}")

    def documents(self) -> Iterator[LegacyDocument]:
        paths = [self.path] if self.path.is_file() else sorted(self.path.glob("*.json"))
        for path in paths:
            if path.name.startswith("_"):
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            schema = self.detect_schema(path)
            raw_assets = document.get("assets") if isinstance(document, dict) else None
            if not isinstance(raw_assets, list):
                raw_assets = [document]
            assets = tuple(GalleryMetadata.from_dict(dict(item)) for item in raw_assets if isinstance(item, dict))
            yield LegacyDocument(path, schema, assets)

    def read(self) -> list[GalleryMetadata]:
        assets: dict[str, GalleryMetadata] = {}
        for document in self.documents():
            for metadata in document.assets:
                assets[metadata.asset_key] = metadata
        return [assets[key] for key in sorted(assets)]

    def read_assets(self) -> list[Asset]:
        return [Asset.from_metadata(metadata, external_refs=(
            {"system": "nyagallery_v1", "path": metadata.original_path},
        )) for metadata in self.read()]
