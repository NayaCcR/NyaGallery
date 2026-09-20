"""Read-only source adapters for image-host migrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, inspect, select

from nyagallery.asset import Asset, AssetBlob
from nyagallery.compat import LegacyReader
from nyagallery.storage import sha256_file


@dataclass
class ImportReport:
    source: str
    assets: list[Asset] = field(default_factory=list)
    copied: int = 0
    skipped: int = 0
    failures: list[str] = field(default_factory=list)
    verified: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "assets": len(self.assets),
            "copied": self.copied,
            "skipped": self.skipped,
            "verified": self.verified,
            "failures": list(self.failures),
        }


class Importer(ABC):
    @abstractmethod
    def detect_source(self, path: Path) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_source(self, path: Path, config: dict[str, Any]) -> list[Asset]:
        raise NotImplementedError

    def convert_to_asset(self, record: dict[str, Any]) -> Asset:
        return Asset.from_dict(record)

    def import_source(self, source: str, config: dict[str, Any]) -> ImportReport:
        path = Path(source)
        assets = self.read_source(path, config)
        return ImportReport(source=self.detect_source(path), assets=assets)

    def verify_sha256(self, assets: list[Asset], *, root: Path | None = None) -> ImportReport:
        report = ImportReport(source=self.__class__.__name__, assets=assets)
        for asset in assets:
            path = Path(asset.blob.storage_key)
            if root is not None and not path.is_absolute():
                path = root / path
            try:
                if asset.verify_sha256(path):
                    report.verified += 1
                else:
                    report.failures.append(f"sha256 mismatch: {path}")
            except OSError as exc:
                report.failures.append(f"cannot verify {path}: {exc}")
        return report


class NyaGalleryV1Importer(Importer):
    name = "nyagallery_v1"

    def detect_source(self, path: Path) -> str:
        LegacyReader.detect_schema(path)
        return self.name

    def read_source(self, path: Path, config: dict[str, Any]) -> list[Asset]:
        return LegacyReader(path).read_assets()


class LskyProImporter(Importer):
    name = "lsky_pro"

    def detect_source(self, path: Path) -> str:
        if path.suffix.casefold() not in {".db", ".sqlite", ".sqlite3"}:
            raise ValueError("Lsky Pro importer expects a SQLite database")
        engine = create_engine(f"sqlite:///{path.resolve().as_posix()}", future=True)
        try:
            if "images" not in inspect(engine).get_table_names():
                raise ValueError("Lsky Pro database has no images table")
        finally:
            engine.dispose()
        return self.name

    def read_source(self, path: Path, config: dict[str, Any]) -> list[Asset]:
        self.detect_source(path)
        upload_root = Path(config.get("upload_root") or path.parent)
        assets: list[Asset] = []
        engine = create_engine(f"sqlite:///{path.resolve().as_posix()}", future=True)
        metadata = MetaData()
        try:
            images = metadata.tables.get("images")
            if images is None:
                images = Table("images", metadata, autoload_with=engine)
            order_column = images.c.id if "id" in images.c else next(iter(images.c))
            with engine.connect() as connection:
                rows = connection.execute(select(images).order_by(order_column)).mappings().all()
        finally:
            engine.dispose()
        for row in rows:
            record = dict(row)
            relative = str(record.get("path") or record.get("pathname") or record.get("key") or "")
            candidate = upload_root / relative
            if not candidate.exists():
                continue
            digest = sha256_file(candidate)
            source_id = str(record.get("id") or digest)
            asset = Asset(
                asset_id=digest,
                blob=AssetBlob(
                    sha256=digest,
                    size=candidate.stat().st_size,
                    mime=record.get("mimetype") or record.get("mime_type"),
                    width=record.get("width"),
                    height=record.get("height"),
                    storage_key=relative,
                    original_filename=candidate.name,
                ),
                metadata={
                    "source": "lsky",
                    "source_id": source_id,
                    "title": str(record.get("name") or candidate.stem),
                    "tags": [],
                    "external_refs": {"system": "lsky", "id": source_id, "path": relative, "url": record.get("url")},
                },
                external_refs=({"system": "lsky", "id": source_id, "path": relative, "url": record.get("url")},),
            )
            assets.append(asset)
        return assets


def copy_assets_read_only(assets: list[Asset], *, source_root: Path, destination_root: Path, hardlink: bool = False) -> ImportReport:
    report = ImportReport(source="copy", assets=assets)
    destination_root.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        source = Path(asset.blob.storage_key)
        if not source.is_absolute():
            source = source_root / source
        destination = destination_root / Path(asset.blob.storage_key).name
        try:
            if not asset.verify_sha256(source):
                report.failures.append(f"sha256 mismatch: {source}")
                continue
            if destination.exists():
                if not asset.verify_sha256(destination):
                    report.failures.append(f"refusing immutable overwrite: {destination}")
                    continue
                report.skipped += 1
            elif hardlink:
                destination.hardlink_to(source)
                report.copied += 1
            else:
                shutil.copy2(source, destination)
                report.copied += 1
            report.verified += 1
        except OSError as exc:
            report.failures.append(f"copy failed for {source}: {exc}")
    return report
