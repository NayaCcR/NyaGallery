from __future__ import annotations

import os
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

from nyagallery.db import (
    AssetModel,
    AssetTagModel,
    asset_to_dict,
    create_engine_for_url,
    init_database,
    make_session_factory,
    search_asset_dicts,
    search_assets,
)
from nyagallery.asset import Asset, AssetBlob
from nyagallery.importers import LskyProImporter, copy_assets_read_only
from nyagallery.tags import TagCatalog


def test_sqlite_engine_enables_safe_write_defaults(tmp_path):
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'gallery.db'}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1
    engine.dispose()


def test_core_search_matches_orm_mapping(tmp_path):
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'gallery.db'}")
    init_database(engine)
    catalog = TagCatalog.default()
    catalog.add_tag("general:fixture")
    session = make_session_factory(engine)()
    asset = AssetModel(
        asset_key="fixture",
        source="upload",
        source_id="fixture",
        file_sha256="0" * 64,
        original_filename="fixture.jpg",
        original_path="original/fixture.jpg",
        title="Fixture",
        extra={"description": "core"},
    )
    asset.tags = [AssetTagModel(asset_key="fixture", tag="general:fixture")]
    session.add(asset)
    session.commit()
    orm = [asset_to_dict(item, catalog) for item in search_assets(session, catalog, "", limit=10)]
    core = search_asset_dicts(session, catalog, "", limit=10)
    assert core == orm
    session.close()
    engine.dispose()


def test_acl_filter_keeps_legacy_assets_and_hides_private_assets(tmp_path):
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'gallery.db'}")
    init_database(engine)
    catalog = TagCatalog.default()
    session = make_session_factory(engine)()
    session.add_all([
        AssetModel(asset_key="legacy", source="fixture", source_id="legacy", file_sha256="1" * 64, original_filename="legacy.jpg", original_path="original/legacy.jpg"),
        AssetModel(asset_key="private", source="fixture", source_id="private", file_sha256="2" * 64, original_filename="private.jpg", original_path="original/private.jpg", uploader_user_id=42),
    ])
    session.commit()
    assert [row["asset_key"] for row in search_asset_dicts(session, catalog, "", user_id=None)] == ["legacy"]
    assert [row["asset_key"] for row in search_asset_dicts(session, catalog, "", user_id=7)] == ["legacy"]
    assert [row["asset_key"] for row in search_asset_dicts(session, catalog, "", user_id=42)] == ["legacy", "private"]
    assert [row.asset_key for row in search_assets(session, catalog, "", user_id=7)] == ["legacy"]
    assert [row.asset_key for row in search_assets(session, catalog, "", user_id=42)] == ["legacy", "private"]
    session.close()
    engine.dispose()


def test_import_copy_uses_content_addressed_destination_keys(tmp_path):
    source_root = tmp_path / "source"
    first = source_root / "first"
    second = source_root / "second"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    first_file = first / "same.jpg"
    second_file = second / "same.jpg"
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")

    def asset(path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return Asset(
            asset_id=digest,
            blob=AssetBlob(
                sha256=digest,
                size=path.stat().st_size,
                mime="image/jpeg",
                width=None,
                height=None,
                storage_key=path.relative_to(source_root).as_posix(),
                original_filename=path.name,
            ),
            metadata={"source": "fixture", "source_id": digest, "original_filename": path.name, "original_path": ""},
        )

    destination = tmp_path / "destination"
    report = copy_assets_read_only(
        [asset(first_file), asset(second_file)],
        source_root=source_root,
        destination_root=destination,
        storage_prefix="original",
    )
    assert report.failures == []
    assert report.copied == 2
    assert len({item.blob.storage_key for item in report.assets}) == 2
    assert all((destination / Path(item.blob.storage_key).name).exists() for item in report.assets)


def test_lsky_importer_reads_through_sqlalchemy_core(tmp_path):
    source_db = tmp_path / "lsky.sqlite"
    upload = tmp_path / "uploads" / "images"
    upload.mkdir(parents=True)
    image = upload / "one.jpg"
    image.write_bytes(b"lsky-fixture")
    engine = create_engine_for_url(f"sqlite:///{source_db}")
    metadata = MetaData()
    images = Table(
        "images", metadata,
        Column("id", Integer, primary_key=True),
        Column("path", String),
        Column("mimetype", String),
        Column("name", String),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(images.insert().values(id=1, path="images/one.jpg", mimetype="image/jpeg", name="one"))
    engine.dispose()
    assets = LskyProImporter().read_source(source_db, {"upload_root": tmp_path / "uploads"})
    assert len(assets) == 1
    assert assets[0].external_refs[0]["system"] == "lsky"


@pytest.mark.skipif(not os.environ.get("NYAGALLERY_TEST_POSTGRES_URL"), reason="PostgreSQL URL not configured")
def test_postgres_key_path():
    engine = create_engine_for_url(os.environ["NYAGALLERY_TEST_POSTGRES_URL"])
    init_database(engine)
    engine.dispose()
