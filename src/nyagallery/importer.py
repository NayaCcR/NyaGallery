"""Background executor for web import jobs (import_jobs table).

Supported sources:
- ``local_directory`` / ``nas``: files under a directory that must sit inside one of the
  configured ``[import] allowed_roots``. Symlinks are resolved and must stay inside the root.
- ``url_list``: direct image URLs fetched through the SSRF-guarded ``fetch_remote_image``.

Progress is checkpointed per item (cursor / succeeded / failed / failed_indices), so a paused or
interrupted job resumes where it stopped and ``retry_failed`` only re-runs failed items.
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from nyagallery.db import (
    AssetModel,
    ImportJobModel,
    create_transcode_job,
    create_upload_log,
    upsert_asset,
    upsert_user_asset,
)
from nyagallery.metadata import GalleryMetadata, make_asset_key, utc_now_iso
from nyagallery.remote_upload import RemoteImageError, fetch_remote_image
from nyagallery.storage import GalleryStorage, OriginalAlreadyExistsError, StorageError, sha256_bytes
from nyagallery.tags import TagCatalog, TagNotFoundError, source_tag_details_from_extra

LOGGER = logging.getLogger("nyagallery.importer")

MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".mp4", ".webm", ".mov"}
LOCAL_SOURCES = {"local_directory", "nas"}
SUPPORTED_SOURCES = LOCAL_SOURCES | {"url_list"}
MAX_ERRORS_KEPT = 50
MAX_URLS = 5000


class ImportConfigError(ValueError):
    """Raised for an import job whose source configuration is not allowed or invalid."""


@dataclass(frozen=True)
class ImportItem:
    index: int
    key: str
    location: str
    kind: str  # "file" | "url"


def resolve_local_root(directory: str, allowed_roots: Iterable[str]) -> Path:
    """Resolve ``directory`` and require it to be inside one of ``allowed_roots`` (after symlinks)."""
    if not directory or not str(directory).strip():
        raise ImportConfigError("source_config.path is required")
    roots = [Path(root).expanduser().resolve() for root in allowed_roots if str(root).strip()]
    if not roots:
        raise ImportConfigError("local imports are disabled: set [import] allowed_roots in nyagallery.toml")
    target = Path(str(directory).strip()).expanduser().resolve()
    for root in roots:
        if target == root or root in target.parents:
            if not target.is_dir():
                raise ImportConfigError(f"not a directory: {target}")
            return target
    raise ImportConfigError(f"path is outside the allowed import roots: {target}")


def validate_job_config(source_type: str, config: dict[str, object], allowed_roots: Iterable[str]) -> dict[str, object]:
    """Normalise and validate a job's source_config at creation time; raises ImportConfigError."""
    if source_type not in SUPPORTED_SOURCES:
        raise ImportConfigError(f"unsupported source type: {source_type}")
    normalized: dict[str, object] = {
        "visibility": "public" if config.get("visibility") == "public" else "private",
        "generate_cache": bool(config.get("generate_cache", True)),
        "skip_duplicates": bool(config.get("skip_duplicates", True)),
        "tags": [str(tag).strip() for tag in (config.get("tags") or []) if str(tag).strip()][:50] if isinstance(config.get("tags"), list) else [],
    }
    if source_type in LOCAL_SOURCES:
        root = resolve_local_root(str(config.get("path") or ""), allowed_roots)
        normalized["path"] = str(root)
        normalized["recursive"] = bool(config.get("recursive", True))
    else:
        raw = config.get("urls")
        urls = raw if isinstance(raw, list) else str(raw or "").split()
        cleaned = [str(url).strip() for url in urls if str(url).strip()]
        if not cleaned:
            raise ImportConfigError("source_config.urls is empty")
        if len(cleaned) > MAX_URLS:
            raise ImportConfigError(f"at most {MAX_URLS} URLs per job")
        for url in cleaned:
            if not url.startswith(("http://", "https://")):
                raise ImportConfigError(f"unsupported URL: {url[:120]}")
        normalized["urls"] = cleaned
    return normalized


def list_items(source_type: str, config: dict[str, object], allowed_roots: Iterable[str]) -> list[ImportItem]:
    if source_type in LOCAL_SOURCES:
        root = resolve_local_root(str(config.get("path") or ""), allowed_roots)
        walker = root.rglob("*") if config.get("recursive", True) else root.glob("*")
        items: list[ImportItem] = []
        for path in sorted(walker):
            if not path.is_file() or path.suffix.casefold() not in MEDIA_SUFFIXES:
                continue
            resolved = path.resolve()
            if root not in resolved.parents:  # symlink escaping the root
                continue
            items.append(ImportItem(len(items), path.relative_to(root).as_posix(), str(resolved), "file"))
        return items
    urls = config.get("urls") or []
    return [ImportItem(index, f"url-{index}", str(url), "url") for index, url in enumerate(urls)]


class ImportRunner:
    """One worker thread per process; jobs run one at a time in creation order."""

    def __init__(
        self,
        *,
        storage: GalleryStorage,
        session_factory: sessionmaker[Session],
        catalog: TagCatalog,
        allowed_roots: Callable[[], Iterable[str]],
        max_file_bytes: Callable[[], int],
        save_catalog: Callable[[], None],
        schedule_transcode: Callable[[str, str], None],
        emit: Callable[[str, dict[str, object]], None],
    ) -> None:
        self.storage = storage
        self.session_factory = session_factory
        self.catalog = catalog
        self.allowed_roots = allowed_roots
        self.max_file_bytes = max_file_bytes
        self.save_catalog = save_catalog
        self.schedule_transcode = schedule_transcode
        self.emit = emit
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle ----------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        with self.session_factory() as db:
            # Jobs left "running" by a previous process resume from their checkpoint.
            for row in db.scalars(select(ImportJobModel).where(ImportJobModel.status == "running")):
                row.status = "queued"
            db.commit()
        self._thread = threading.Thread(target=self._loop, name="nyagallery-import", daemon=True)
        self._thread.start()
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def notify(self) -> None:
        self._wake.set()

    # ---- worker -------------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=30)
            self._wake.clear()
            while not self._stop.is_set():
                job_id = self._claim_next()
                if job_id is None:
                    break
                try:
                    self._run(job_id)
                except Exception as exc:  # never let one job kill the worker
                    LOGGER.exception("import job %s crashed", job_id)
                    self._finish(job_id, "failed", error=f"worker error: {type(exc).__name__}: {exc}")

    def _claim_next(self) -> str | None:
        with self.session_factory() as db:
            row = db.scalar(select(ImportJobModel).where(ImportJobModel.status == "queued").order_by(ImportJobModel.id))
            if row is None:
                return None
            row.status = "running"
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            return row.job_id

    def _run(self, job_id: str) -> None:
        with self.session_factory() as db:
            row = db.scalar(select(ImportJobModel).where(ImportJobModel.job_id == job_id))
            if row is None:
                return
            config = dict(row.source_config or {})
            source_type = row.source_type
            owner_id = row.owner_user_id
            retry_only = list(config.pop("_retry_indices", []) or [])
            if retry_only:
                row.source_config = config  # consume the retry marker
                db.commit()
        try:
            items = list_items(source_type, config, self.allowed_roots())
        except (ImportConfigError, OSError) as exc:
            self._finish(job_id, "failed", error=str(exc))
            return
        owner = self._owner(owner_id)
        with self.session_factory() as db:
            row = db.scalar(select(ImportJobModel).where(ImportJobModel.job_id == job_id))
            row.total = len(items)
            if retry_only:
                row.failed = max(0, int(row.failed or 0) - len(retry_only))
                row.failed_indices = [index for index in (row.failed_indices or []) if index not in set(retry_only)]
            db.commit()
            start = 0 if retry_only else int(row.cursor or 0)
        queue = [items[i] for i in retry_only if 0 <= i < len(items)] if retry_only else items[start:]
        for item in queue:
            if self._stop.is_set() or self._status(job_id) != "running":
                return  # paused or shutting down; checkpoint already persisted
            ok, error = self._ingest(item, config, owner)
            with self.session_factory() as db:
                row = db.scalar(select(ImportJobModel).where(ImportJobModel.job_id == job_id))
                if not retry_only:
                    row.cursor = item.index + 1
                if ok:
                    row.succeeded = int(row.succeeded or 0) + 1
                else:
                    row.failed = int(row.failed or 0) + 1
                    row.failed_indices = sorted(set(row.failed_indices or []) | {item.index})
                    errors = list(row.errors or [])
                    errors.append(f"{item.key}: {error}"[:300])
                    row.errors = errors[-MAX_ERRORS_KEPT:]
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
        self.save_catalog()
        with self.session_factory() as db:
            row = db.scalar(select(ImportJobModel).where(ImportJobModel.job_id == job_id))
            if row.status == "running":
                row.cursor = row.total
                row.status = "failed" if row.failed and not row.succeeded else "succeeded"
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
            final = {"job_id": job_id, "status": row.status, "succeeded": row.succeeded, "failed": row.failed}
        self.emit("import.finished", final)

    def _status(self, job_id: str) -> str | None:
        with self.session_factory() as db:
            return db.scalar(select(ImportJobModel.status).where(ImportJobModel.job_id == job_id))

    def _finish(self, job_id: str, status: str, *, error: str | None = None) -> None:
        with self.session_factory() as db:
            row = db.scalar(select(ImportJobModel).where(ImportJobModel.job_id == job_id))
            if row is None:
                return
            row.status = status
            if error:
                row.errors = (list(row.errors or []) + [error[:300]])[-MAX_ERRORS_KEPT:]
            row.updated_at = datetime.now(timezone.utc)
            db.commit()

    def _owner(self, owner_id: int | None) -> tuple[int | None, str]:
        from nyagallery.db import UserModel

        if owner_id is None:
            return None, "import"
        with self.session_factory() as db:
            user = db.get(UserModel, owner_id)
            return owner_id, (user.username if user else "import")

    # ---- one item -----------------------------------------------------------------------
    def _read(self, item: ImportItem) -> tuple[bytes, str, str | None]:
        limit = max(1, int(self.max_file_bytes()))
        if item.kind == "file":
            path = Path(item.location)
            size = path.stat().st_size
            if size > limit:
                raise ValueError(f"file is larger than the import limit ({size} > {limit} bytes)")
            content = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0]
            return content, path.name, mime
        remote = fetch_remote_image(item.location, limit)
        return remote.content, remote.filename, remote.content_type

    def _ingest(self, item: ImportItem, config: dict[str, object], owner: tuple[int | None, str]) -> tuple[bool, str]:
        owner_id, owner_name = owner
        try:
            content, filename, mime = self._read(item)
        except (OSError, ValueError, RemoteImageError) as exc:
            return False, str(getattr(exc, "detail", None) or exc)[:200]
        sniffed = sniff_media_type(content)
        if sniffed is None:
            return False, "not a supported image or video (content check failed)"
        mime = sniffed
        digest = sha256_bytes(content)
        with self.session_factory() as db:
            existing = db.scalar(select(AssetModel).where(AssetModel.file_sha256 == digest))
            if existing is not None and config.get("skip_duplicates", True):
                return True, ""
        asset_key = make_asset_key("import", digest[:16])
        safe_name = Path(filename).name[:200] or f"{digest[:16]}.bin"
        try:
            stored = self.storage.write_original(asset_key, safe_name, content, content_type=mime)
        except OriginalAlreadyExistsError:
            return True, ""
        except StorageError as exc:
            return False, str(exc)[:200]
        from nyagallery.media import probe_media_size

        try:
            width, height = probe_media_size(stored.path, mime_type=mime)
        except Exception:
            width, height = None, None
        requested = _known_tags(self.catalog, config.get("tags") or [])
        metadata = GalleryMetadata(
            source="import",
            source_id=digest[:16],
            title=Path(safe_name).stem,
            artist_id="",
            artist_name="",
            original_url=item.location if item.kind == "url" else "",
            crawl_time=utc_now_iso(),
            file_sha256=stored.sha256,
            original_filename=Path(safe_name).stem,
            original_path=stored.relative_path,
            pixiv_tags=(),
            canonical_tags=requested,
            mime_type=mime,
            width=width,
            height=height,
            extra={"import_source": item.kind, "import_key": item.key},
            uploader_user_id=owner_id,
            uploader_username=owner_name,
        )
        try:
            self.storage.write_metadata(metadata)
        except Exception:
            metadata = self.storage.read_metadata(asset_key)
        tags = self.catalog.canonicalize_tags(
            pixiv_tags=metadata.pixiv_tags,
            source_tag_details=source_tag_details_from_extra(metadata.extra),
            canonical_tags=metadata.canonical_tags,
            source=metadata.source,
            artist_name=metadata.artist_name,
            uploader_username=metadata.uploader_username,
            width=metadata.width,
            height=metadata.height,
            artwork_date=metadata.artwork_date,
            source_type=metadata.source_type,
            age_rating=metadata.age_rating,
            is_ai_generated=metadata.is_ai_generated,
            is_animated=metadata.is_animated,
            mime_type=metadata.mime_type,
        )
        job_id = None
        with self.session_factory() as db:
            duplicate_of = db.scalar(select(AssetModel.asset_key).where(AssetModel.file_sha256 == digest, AssetModel.asset_key != asset_key))
            asset = upsert_asset(db, self.storage, metadata, tags, duplicate_of=duplicate_of)
            if owner_id is not None:
                upsert_user_asset(db, user_id=owner_id, asset_key=asset.asset_key, visibility=str(config.get("visibility") or "private"))
            if config.get("generate_cache", True):
                job_id = create_transcode_job(db, asset, source="import", file_size=stored.size).job_id
            create_upload_log(
                db,
                asset_key=asset.asset_key,
                uploader_user_id=owner_id,
                uploader_username=owner_name,
                original_filename=safe_name,
                file_size=stored.size,
                mime_type=mime,
                event="import",
                status="success",
                message="imported",
                extra={"import_key": item.key, "transcode_job_id": job_id, "duplicate_of": duplicate_of},
            )
            db.commit()
        if job_id:
            self.schedule_transcode(asset_key, job_id)
        self.emit("asset.created", {"asset_key": asset_key, "source": "import", "uploader_user_id": owner_id, "duplicate_of": duplicate_of})
        return True, ""


_SIGNATURES: tuple[tuple[bytes, int, str], ...] = (
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"GIF87a", 0, "image/gif"),
    (b"GIF89a", 0, "image/gif"),
    (b"BM", 0, "image/bmp"),
    (b"II*\x00", 0, "image/tiff"),
    (b"MM\x00*", 0, "image/tiff"),
    (b"\x1aE\xdf\xa3", 0, "video/webm"),
)


def sniff_media_type(content: bytes) -> str | None:
    """Media type from the file's magic bytes, or None if it is not a supported image/video."""
    head = content[:32]
    for magic, offset, mime in _SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        if brand in {b"heic", b"heix", b"hevc", b"mif1", b"msf1"}:
            return "image/heic"
        if brand in {b"qt  "}:
            return "video/quicktime"
        return "video/mp4"
    return None


def _known_tags(catalog: TagCatalog, names: Iterable[str]) -> tuple[str, ...]:
    """Canonical names of the requested tags that exist; unknown tags are skipped, not created."""
    known: list[str] = []
    for name in names:
        try:
            known.append(catalog.require(str(name)).name)
        except TagNotFoundError:
            continue
    return tuple(dict.fromkeys(known))


def retry_failed(db: Session, row: ImportJobModel) -> None:
    """Mark only the failed items of a finished job for re-run."""
    failed = list(row.failed_indices or [])
    if not failed:
        raise ImportConfigError("no failed items to retry")
    config = dict(row.source_config or {})
    config["_retry_indices"] = failed
    row.source_config = config
    row.status = "queued"


__all__ = ["ImportConfigError", "ImportRunner", "SUPPORTED_SOURCES", "resolve_local_root", "retry_failed", "validate_job_config", "replace"]
