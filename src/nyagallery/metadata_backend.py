"""Pluggable metadata truth sources with explicit, one-way conversion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from nyagallery.asset import Asset
from nyagallery.db import AssetModel, upsert_asset
from nyagallery.metadata import GalleryMetadata
from nyagallery.storage import GalleryStorage
from nyagallery.tags import TagCatalog


class MetadataBackend(ABC):
    mode: str

    @abstractmethod
    def iter_assets(self) -> Iterable[Asset]:
        raise NotImplementedError

    @abstractmethod
    def export(self, destination: Path) -> dict[str, object]:
        raise NotImplementedError


class FileMetadataBackend(MetadataBackend):
    mode = "file"

    def __init__(self, storage: GalleryStorage) -> None:
        self.storage = storage

    def iter_assets(self) -> Iterable[Asset]:
        for metadata in self.storage.iter_metadata():
            yield Asset.from_metadata(metadata, size=self.storage.file_size(metadata.original_path))

    def export(self, destination: Path) -> dict[str, object]:
        return _export_assets(self.iter_assets(), self.mode, destination)


def _export_assets(assets: Iterable[Asset], mode: str, destination: Path) -> dict[str, object]:
    destination.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for asset in assets:
        path = destination / f"{asset.asset_id.removeprefix('sha256:')}.json"
        path.write_text(json.dumps(asset.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(path.name)
    return {"mode": mode, "assets": len(files), "files": files}


class DatabaseMetadataBackend(MetadataBackend):
    mode = "database"

    def __init__(self, session: Session, storage: GalleryStorage) -> None:
        self.session = session
        self.storage = storage

    def iter_assets(self) -> Iterable[Asset]:
        for row in self.session.scalars(select(AssetModel)):
            metadata = GalleryMetadata(
                source=row.source,
                source_id=row.source_id,
                title=row.title or "",
                artist_id=row.artist_id or "",
                artist_name=row.artist_name or "",
                original_url=row.original_url or "",
                crawl_time=row.crawl_time or "",
                file_sha256=row.file_sha256,
                original_filename=row.original_filename,
                original_path=row.original_path,
                pixiv_tags=tuple(row.pixiv_tags or ()),
                canonical_tags=tuple(row.canonical_tags or ()),
                page_index=row.page_index,
                width=row.width,
                height=row.height,
                mime_type=row.mime_type,
                artwork_date=row.artwork_date,
                pixiv_upload_date=row.pixiv_upload_date,
                source_type=row.source_type,
                age_rating=row.age_rating,
                is_ai_generated=row.is_ai_generated,
                is_animated=row.is_animated,
                uploader_user_id=row.uploader_user_id,
                uploader_username=row.uploader_username,
                deletion_status=row.deletion_status,
                deleted_at=row.deleted_at,
                deleted_by_user_id=row.deleted_by_user_id,
                deleted_by_username=row.deleted_by_username,
                extra=dict(row.extra or {}),
            )
            yield Asset.from_metadata(metadata, size=self.storage.file_size(row.original_path))

    def export(self, destination: Path) -> dict[str, object]:
        # Export is a sidecar backup only; it never becomes a second write target.
        return _export_assets(self.iter_assets(), self.mode, destination)


def metadata_backend(mode: str, *, storage: GalleryStorage, session: Session | None = None) -> MetadataBackend:
    normalized = str(mode or "file").strip().casefold()
    if normalized == "file":
        return FileMetadataBackend(storage)
    if normalized == "database" and session is not None:
        return DatabaseMetadataBackend(session, storage)
    if normalized == "database":
        raise ValueError("database metadata backend requires a database session")
    raise ValueError(f"unsupported metadata backend: {mode}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert_metadata_backend(
    *,
    source: MetadataBackend,
    destination: Path,
    backup_root: Path,
    confirm: bool = False,
) -> dict[str, object]:
    """Export a source backend into a verified sidecar directory.

    The operation is deliberately read-only until ``confirm`` is true. A
    backup copy is made before writing destination files and each output is
    verified by SHA256, allowing callers to roll back by removing the output.
    """
    if not confirm:
        return {"status": "dry_run", "source": source.mode, "destination": destination.as_posix()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / "metadata-backup"
    if destination.exists():
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(destination, backup)
    with tempfile.TemporaryDirectory(prefix="nyagallery-convert-", dir=str(destination.parent)) as temp:
        temp_path = Path(temp)
        result = source.export(temp_path)
        checksums = {path.name: _sha256_file(path) for path in temp_path.glob("*.json")}
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(temp_path, destination)
        destination_checksums = {path.name: _sha256_file(path) for path in destination.glob("*.json")}
        if destination_checksums != checksums:
            raise IOError("metadata conversion checksum verification failed")
    result["status"] = "converted"
    result["sha256"] = checksums
    result["verified_files"] = len(checksums)
    result["backup"] = backup.as_posix() if backup.exists() else None
    return result


def import_assets_to_database(
    assets: Iterable[Asset],
    *,
    session: Session,
    storage: GalleryStorage,
    catalog: TagCatalog,
) -> dict[str, object]:
    """Make the database the sole primary by importing a file-sidecar export."""
    count = 0
    for asset in assets:
        data = dict(asset.metadata)
        data.setdefault("source", "import")
        data.setdefault("source_id", asset.asset_id.removeprefix("sha256:"))
        data.setdefault("title", asset.blob.original_filename)
        data.setdefault("artist_id", "")
        data.setdefault("artist_name", "")
        data.setdefault("original_url", "")
        data.setdefault("crawl_time", asset.created_at)
        data["file_sha256"] = asset.blob.sha256
        data["original_filename"] = asset.blob.original_filename
        data["original_path"] = asset.blob.storage_key
        data.setdefault("mime_type", asset.blob.mime)
        data.setdefault("width", asset.blob.width)
        data.setdefault("height", asset.blob.height)
        metadata = GalleryMetadata.from_dict(data)
        tags = tuple(str(tag) for tag in data.get("canonical_tags") or data.get("tags") or ())
        upsert_asset(session, storage, metadata, tags)
        count += 1
    session.commit()
    return {"mode": "database", "assets": count}


def convert_file_to_database(
    *,
    source: FileMetadataBackend,
    session: Session,
    storage: GalleryStorage,
    catalog: TagCatalog,
    backup_root: Path,
    confirm: bool = False,
) -> dict[str, object]:
    """Promote file metadata to the database after a verified, transactional import."""
    assets = list(source.iter_assets())
    if not confirm:
        return {"status": "dry_run", "source": source.mode, "destination": "database", "assets": len(assets)}

    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / "database-sidecar"
    if backup.exists():
        shutil.rmtree(backup)
    _export_assets(DatabaseMetadataBackend(session, storage).iter_assets(), "database", backup)

    verified = 0
    try:
        for asset in assets:
            original = storage.resolve_relative_path(asset.blob.storage_key)
            if not asset.verify_sha256(original):
                raise ValueError(f"sha256 mismatch: {original}")
            verified += 1
        import_assets_to_database(assets, session=session, storage=storage, catalog=catalog)
    except Exception:
        session.rollback()
        raise
    return {
        "status": "converted",
        "source": source.mode,
        "destination": "database",
        "assets": len(assets),
        "verified": verified,
        "backup": backup.as_posix(),
    }
