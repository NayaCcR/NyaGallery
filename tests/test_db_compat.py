from __future__ import annotations

import os

import pytest

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


@pytest.mark.skipif(not os.environ.get("NYAGALLERY_TEST_POSTGRES_URL"), reason="PostgreSQL URL not configured")
def test_postgres_key_path():
    engine = create_engine_for_url(os.environ["NYAGALLERY_TEST_POSTGRES_URL"])
    init_database(engine)
    engine.dispose()
