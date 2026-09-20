"""Stable, storage-independent asset contract used by import/export tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from nyagallery.metadata import GalleryMetadata


ASSET_SCHEMA = "nyagallery.asset.v1"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_id_for_sha256(value: str) -> str:
    digest = str(value or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[7:]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("asset SHA256 must be a 64-character hexadecimal digest")
    return f"sha256:{digest}"


@dataclass(frozen=True)
class AssetBlob:
    sha256: str
    size: int
    mime: str | None
    width: int | None
    height: int | None
    storage_key: str
    original_filename: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size": self.size,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "storage_key": self.storage_key,
            "original_filename": self.original_filename,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AssetBlob":
        return cls(
            sha256=str(value["sha256"]),
            size=max(0, int(value.get("size") or 0)),
            mime=str(value.get("mime") or "") or None,
            width=int(value["width"]) if value.get("width") is not None else None,
            height=int(value["height"]) if value.get("height") is not None else None,
            storage_key=str(value.get("storage_key") or ""),
            original_filename=str(value.get("original_filename") or ""),
        )


@dataclass(frozen=True)
class Asset:
    asset_id: str
    blob: AssetBlob
    metadata: dict[str, Any] = field(default_factory=dict)
    external_refs: tuple[dict[str, Any], ...] = ()
    created_at: str = ""
    schema: str = ASSET_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", asset_id_for_sha256(self.asset_id))
        if self.schema != ASSET_SCHEMA:
            raise ValueError(f"unsupported asset schema: {self.schema}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "asset_id": self.asset_id,
            "blob": self.blob.to_dict(),
            "metadata": dict(self.metadata),
            "external_refs": [dict(item) for item in self.external_refs],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Asset":
        if str(value.get("schema") or ASSET_SCHEMA) != ASSET_SCHEMA:
            raise ValueError(f"unsupported asset schema: {value.get('schema')}")
        return cls(
            asset_id=str(value["asset_id"]),
            blob=AssetBlob.from_dict(dict(value["blob"])),
            metadata=dict(value.get("metadata") or {}),
            external_refs=tuple(dict(item) for item in value.get("external_refs") or () if isinstance(item, dict)),
            created_at=str(value.get("created_at") or ""),
        )

    @classmethod
    def from_metadata(
        cls,
        metadata: GalleryMetadata,
        *,
        size: int | None = None,
        storage_key: str | None = None,
        external_refs: tuple[dict[str, Any], ...] = (),
    ) -> "Asset":
        return cls(
            asset_id=metadata.file_sha256,
            blob=AssetBlob(
                sha256=metadata.file_sha256,
                size=max(0, int(size or 0)),
                mime=metadata.mime_type,
                width=metadata.width,
                height=metadata.height,
                storage_key=storage_key or metadata.original_path,
                original_filename=metadata.original_filename,
            ),
            metadata=metadata.to_dict(),
            external_refs=external_refs,
            created_at=metadata.crawl_time or datetime.now(timezone.utc).isoformat(),
        )

    def verify_sha256(self, path: str | Path) -> bool:
        candidate = Path(path)
        return _sha256_path(candidate) == self.blob.sha256
