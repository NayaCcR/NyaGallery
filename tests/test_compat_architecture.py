from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from nyagallery.asset import Asset, AssetBlob
from nyagallery.compat import LegacyReader
from nyagallery.cli import main
from nyagallery.db import AssetModel, create_engine_for_url, init_database, make_session_factory
from nyagallery.metadata_backend import FileMetadataBackend, convert_file_to_database, convert_metadata_backend
from nyagallery.storage import GalleryStorage
from nyagallery.tags import TagCatalog
from nyagallery.virtual_folders import VirtualFolder, VirtualFolderCatalog


def _legacy_payload(filename: str, digest: str) -> dict[str, object]:
    return {
        "schema": "nyagallery.creator_metadata.v1",
        "assets": [{
            "source": "fixture",
            "source_id": "1",
            "title": "Fixture",
            "artist_id": "",
            "artist_name": "",
            "original_url": "",
            "crawl_time": "2026-01-01T00:00:00Z",
            "file_sha256": digest,
            "original_filename": filename,
            "original_path": f"original/{filename}",
        }],
    }


def test_legacy_reader_and_asset_roundtrip(tmp_path: Path):
    original = tmp_path / "original.jpg"
    original.write_bytes(b"fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_legacy_payload(original.name, digest)), encoding="utf-8")
    assets = LegacyReader(metadata).read_assets()
    assert len(assets) == 1
    assert assets[0].asset_id == f"sha256:{digest}"
    assert Asset.from_dict(assets[0].to_dict()) == assets[0]


def test_file_backend_convert_has_backup_and_checksums(tmp_path: Path):
    storage = GalleryStorage(tmp_path / "storage")
    storage.ensure()
    original = storage.original_dir / "fixture.jpg"
    original.write_bytes(b"fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    from nyagallery.metadata import GalleryMetadata

    storage.write_metadata(GalleryMetadata(
        source="fixture", source_id="1", title="Fixture", artist_id="", artist_name="",
        original_url="", crawl_time="", file_sha256=digest, original_filename="fixture.jpg",
        original_path="original/fixture.jpg",
    ))
    destination = tmp_path / "sidecar"
    result = convert_metadata_backend(
        source=FileMetadataBackend(storage),
        destination=destination,
        backup_root=tmp_path / "backup",
        confirm=True,
    )
    assert result["status"] == "converted"
    assert result["sha256"]


def test_virtual_folders_are_saved_queries(tmp_path: Path):
    catalog = VirtualFolderCatalog(tmp_path / "folders.json")
    catalog.put(VirtualFolder("Wallpapers", "tag:type/static", "collection"))
    catalog.save()
    loaded = VirtualFolderCatalog(tmp_path / "folders.json")
    loaded.load()
    assert loaded.get("Wallpapers").query == "tag:type/static"


def test_file_to_database_conversion_verifies_and_imports(tmp_path: Path):
    storage = GalleryStorage(tmp_path / "storage")
    storage.ensure()
    original = storage.original_dir / "fixture.jpg"
    original.write_bytes(b"fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    from nyagallery.metadata import GalleryMetadata

    storage.write_metadata(GalleryMetadata(
        source="fixture", source_id="1", title="Fixture", artist_id="", artist_name="",
        original_url="", crawl_time="", file_sha256=digest, original_filename="fixture.jpg",
        original_path="original/fixture.jpg",
    ))
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'gallery.db'}")
    init_database(engine)
    with make_session_factory(engine)() as session:
        result = convert_file_to_database(
            source=FileMetadataBackend(storage), session=session, storage=storage,
            catalog=TagCatalog.default(), backup_root=tmp_path / "backup", confirm=True,
        )
        assert result["verified"] == 1
    engine.dispose()


def test_import_cli_writes_storage_relative_asset_records(tmp_path: Path):
    source_root = tmp_path / "source"
    (source_root / "original").mkdir(parents=True)
    original = source_root / "original" / "fixture.jpg"
    original.write_bytes(b"fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    metadata = source_root / "export.json"
    metadata.write_text(json.dumps(_legacy_payload("fixture.jpg", digest)), encoding="utf-8")
    output = tmp_path / "imported"

    assert main([
        "--storage", str(tmp_path / "unused-storage"),
        "import", str(metadata),
        "--source-type", "nyagallery_v1",
        "--source-root", str(source_root),
        "--output", str(output),
        "--confirm",
    ]) == 0

    imported_storage = GalleryStorage(output)
    imported = imported_storage.iter_metadata()
    assert len(imported) == 1
    assert imported[0].original_path.startswith("original/")
    assert imported_storage.resolve_relative_path(imported[0].original_path).read_bytes() == b"fixture"


def test_import_cli_database_target_switches_primary_mode(tmp_path: Path):
    source_root = tmp_path / "source"
    (source_root / "original").mkdir(parents=True)
    original = source_root / "original" / "fixture.jpg"
    original.write_bytes(b"fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    metadata = source_root / "export.json"
    metadata.write_text(json.dumps(_legacy_payload("fixture.jpg", digest)), encoding="utf-8")
    storage_root = tmp_path / "storage"
    config_path = tmp_path / "nyagallery.toml"
    config_path.write_text("[core]\n", encoding="utf-8")

    assert main([
        "--config", str(config_path),
        "--storage", str(storage_root),
        "--database-url", f"sqlite:///{storage_root / 'nyagallery.db'}",
        "import", str(metadata),
        "--source-type", "nyagallery_v1",
        "--source-root", str(source_root),
        "--target", "database",
        "--confirm",
    ]) == 0

    engine = create_engine_for_url(f"sqlite:///{storage_root / 'nyagallery.db'}")
    with make_session_factory(engine)() as session:
        assert session.scalar(select(AssetModel.asset_key)) == "fixture_1"
    engine.dispose()
    assert "metadata_mode = \"database\"" in config_path.read_text(encoding="utf-8")
