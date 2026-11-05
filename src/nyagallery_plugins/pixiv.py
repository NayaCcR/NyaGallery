"""Official plugin: Pixiv sync (moved out of nyagallery.app; URLs unchanged)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import secrets
import threading
import time
import zipfile
from dataclasses import (
    replace,
)
from fastapi import (
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import (
    StreamingResponse,
)
from nyagallery.auth import (
    Principal,
)
from nyagallery.config import (
    NyaGalleryConfig,
    network_proxy_for,
)
from nyagallery.db import (
    AssetModel,
    TranscodeJobModel,
    UploadLogModel,
    attach_sync_log_assets,
    create_transcode_job,
    create_upload_log,
    get_pixiv_cookie,
    get_pixiv_refresh_token,
    list_pixiv_cookies,
    list_pixiv_logs,
    list_pixiv_tokens,
    pixiv_cookie_belongs_to_user,
    pixiv_cookie_to_dict,
    pixiv_token_belongs_to_user,
    pixiv_token_to_dict,
    rebuild_database,
    revoke_pixiv_cookie,
    revoke_pixiv_token,
    save_pixiv_cookie,
    save_pixiv_token,
    transcode_job_to_dict,
    update_pixiv_cookie_label,
    update_pixiv_token_label,
    upload_log_to_dict,
)
from nyagallery.metadata import (
    utc_now_iso,
)
from nyagallery.pixiv import (
    HTTPPixivDownloader,
    PixivCookieClient,
    PixivOAuthError,
    PixivPyClient,
    PixivRateLimitError,
    PixivRequestOptions,
    PixivSyncService,
    create_pixiv_oauth_start,
    exchange_pixiv_oauth_code,
    get_pixiv_refresh_token_with_browser_worker,
    get_pixiv_refresh_token_with_cookie_worker,
)
from nyagallery.secret_crypto import (
    SecretEncryptionError,
    secret_encryption_enabled,
)
from nyagallery.security import (
    client_ip,
)
from nyagallery.storage import (
    GalleryStorage,
)
from nyagallery.tags import (
    TagCatalog,
)
from pathlib import (
    Path,
)
from pydantic import (
    BaseModel,
    Field,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)
from typing import (
    Annotated,
)
from urllib.parse import (
    quote,
    unquote,
    urlparse,
)

from nyagallery.plugin_host import PluginContext, PluginInfo
from nyagallery.plugins import PluginManifest
from nyagallery.app import (
    AdminPrincipal,
    ApiPrincipal,
    AppState,
    DbSession,
    UploadPrincipal,
    _asset_original_size,
    _clip_log_text,
    _commit_pixiv_log_update,
    _generate_cache_and_refresh_asset,
    _is_admin_principal,
    _model_dump,
    _require_self_or_admin,
    _save_catalog,
    _schedule_background_task,
    _set_synced_assets_public,
    _storage_strategy_items,
    _sync_asset_keys,
    _update_pixiv_log,
)


class PixivTokenCreate(BaseModel):
    refresh_token: str = Field(min_length=1)
    label: str = ""
    pixiv_user: dict | None = None


class PixivTokenUpdate(BaseModel):
    label: str = ""


class PixivCookieCreate(BaseModel):
    cookie: str = Field(min_length=1, max_length=50_000)
    label: str = ""
    pixiv_user: dict | None = None


class PixivCookieUpdate(BaseModel):
    label: str = ""


class PixivSyncRequest(BaseModel):
    auth_mode: str = "public"
    refresh_token: str | None = None
    pixiv_token_id: int | None = None
    cookie: str | None = None
    pixiv_cookie_id: int | None = None
    proxy_url: str | None = None
    storage_strategy: str | None = None
    public_first: bool = True
    make_public: bool = True
    rebuild_db: bool = True
    generate_cache: bool = False
    limit: int | None = Field(default=None, ge=1, le=500)
    request_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: int = Field(default=60, ge=1, le=3600)
    retry_max_seconds: int = Field(default=300, ge=1, le=7200)
    concurrency: int = Field(default=1, ge=1, le=3)
    dry_run: bool = False
    restrict: str = "public"


PIXIV_PREVIEW_LIMIT = 30


class PixivPreviewRequest(BaseModel):
    pids: list[str] = Field(min_length=1, max_length=200)
    options: PixivSyncRequest = Field(default_factory=PixivSyncRequest)


class PixivOAuthStartRequest(BaseModel):
    state: str | None = None
    callback_url: str | None = None


class PixivOAuthExchangeRequest(BaseModel):
    code: str | None = None
    callback_url: str | None = None
    code_verifier: str
    state: str | None = None


class PixivOAuthBrowserLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)
    timeout_seconds: int = Field(default=180, ge=30, le=600)


class PixivOAuthVisibleLoginRequest(BaseModel):
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    timeout_seconds: int = Field(default=600, ge=60, le=1800)


class PixivSessionExchangeRequest(BaseModel):
    cookie: str = Field(min_length=1, max_length=50_000)
    username: str | None = Field(default=None, max_length=80)
    label: str = ""
    save: bool = True
    return_token: bool = True
    headless: bool = True
    timeout_seconds: int = Field(default=180, ge=30, le=600)


def _run_visible_pixiv_login_session(
    state: AppState,
    session_id: str,
    username: str | None,
    password: str | None,
    timeout_seconds: int,
    proxy_url: str | None,
) -> None:
    try:
        token = get_pixiv_refresh_token_with_browser_worker(
            headless=False,
            username=username,
            password=password,
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
        )
        update = {
            "status": "success",
            "message": "Pixiv refresh token acquired",
            "refresh_token": token.refresh_token,
            "expires_in": token.expires_in,
            "user": token.user,
            "error": None,
        }
    except PixivOAuthError as exc:
        update = {
            "status": "error",
            "message": "Pixiv visible browser login failed",
            "error": str(exc),
        }
    except Exception as exc:
        update = {
            "status": "error",
            "message": "Pixiv visible browser login failed",
            "error": str(exc),
        }
    update["updated_at"] = time.time()
    with state.pixiv_login_lock:
        session = state.pixiv_login_sessions.get(session_id)
        if session is not None:
            session.update(update)


def _pixiv_login_session_public(session: dict[str, object]) -> dict[str, object]:
    return {
        "id": session.get("id"),
        "status": session.get("status"),
        "message": session.get("message"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "expires_at": session.get("expires_at"),
        "refresh_token": session.get("refresh_token") if session.get("status") == "success" else None,
        "expires_in": session.get("expires_in") if session.get("status") == "success" else None,
        "user": session.get("user") if session.get("status") == "success" else None,
        "error": session.get("error") if session.get("status") == "error" else None,
    }


def _prune_pixiv_login_sessions(sessions: dict[str, dict[str, object]]) -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, session in sessions.items()
        if float(session.get("expires_at") or 0) < now
    ]
    for session_id in expired:
        sessions.pop(session_id, None)


def _queue_pixiv_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    *,
    session_factory: sessionmaker[Session],
    db: Session,
    principal: Principal,
    target: str,
    kind: str,
    request: PixivSyncRequest,
    mode: str,
) -> dict[str, object]:
    job_id = secrets.token_urlsafe(9).rstrip("=")
    request_copy = PixivSyncRequest(**_model_dump(request))
    request_copy.storage_strategy = storage.validate_storage_strategy(request_copy.storage_strategy)
    log = _create_pixiv_log(
        db,
        principal=principal,
        target=target,
        mode=mode,
        status="queued",
        message="pixiv sync queued",
        extra={
            "sync_job_id": job_id,
            "kind": kind,
            "stage": "queued",
            "progress": 0,
            "last_update_at": utc_now_iso(),
            "options": _pixiv_options_log(request_copy),
        },
    )
    db.commit()
    thread = threading.Thread(
        target=_run_pixiv_sync_job,
        args=(storage, catalog, session_factory, principal, target, kind, request_copy, mode, log.id, job_id),
        daemon=True,
    )
    thread.start()
    return {
        "status": "queued",
        "sync_job_id": job_id,
        "message": "pixiv sync queued",
        "sync": [],
        "media": [],
        "jobs": [],
        "rebuild": None,
    }


def _run_pixiv_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    session_factory: sessionmaker[Session],
    principal: Principal,
    target: str,
    kind: str,
    request: PixivSyncRequest,
    mode: str,
    log_id: int,
    job_id: str,
) -> None:
    started_at = time.monotonic()
    options = _pixiv_options_log(request)
    cumulative_results = 0
    current_result_base = 0
    artworks_done = 0
    current_artwork_index: int | None = None

    def update(status: str, message: str, extra: dict[str, object] | None = None) -> None:
        payload = {
            "sync_job_id": job_id,
            "kind": kind,
            "stage": extra.get("stage") if extra else None,
            "last_update_at": utc_now_iso(),
            "duration_seconds": round(time.monotonic() - started_at, 1),
            **(extra or {}),
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        _commit_pixiv_log_update(session_factory, log_id, status=status, message=message, extra=payload)

    def progress(event: dict[str, object]) -> None:
        nonlocal cumulative_results
        payload = dict(event)
        local_count = _optional_number(payload.get("sync_count"))
        if local_count is not None:
            payload["sync_count"] = current_result_base + int(local_count)
            cumulative_results = max(cumulative_results, current_result_base + int(local_count))
        elif cumulative_results:
            payload["sync_count"] = cumulative_results
        if current_artwork_index is not None:
            payload["current_artwork_index"] = current_artwork_index
        if artworks_done:
            payload["artworks_done"] = artworks_done
        message = str(payload.get("message") or "pixiv sync running")
        update("running", message, _normalize_pixiv_progress_payload(payload))

    try:
        update("running", "fetching pixiv metadata", {"stage": "fetching_metadata", "progress": 0, "options": options})
        client, downloader = _pixiv_sync_components(request)
        service = PixivSyncService(
            storage,
            client=client,
            downloader=downloader,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
            storage_strategy_name=request.storage_strategy,
            progress=progress,
        )
        results = []
        if kind == "pid":
            artwork = client.get_illust(target)
            update(
                "running",
                "pixiv metadata fetched",
                {
                    "stage": "metadata_fetched",
                    "pixiv_id": artwork.pixiv_id,
                    "title": artwork.title,
                    "artist_name": artwork.artist_name,
                    "page_count": len(artwork.pages),
                    "progress": 0,
                },
            )
            current_result_base = 0
            results.extend(service.sync_artwork(artwork))
            cumulative_results = len(results)
        elif kind == "bookmarks":
            restrict = request.restrict or "public"
            update("running", "fetching pixiv bookmarks", {"stage": "fetching_user_bookmarks", "progress": 0})
            for index, artwork in enumerate(client.iter_user_bookmarks(target, restrict=restrict)):
                if request.limit is not None and index >= request.limit:
                    break
                current_artwork_index = index + 1
                current_result_base = len(results)
                update(
                    "running",
                    "pixiv artwork queued",
                    {
                        "stage": "artwork_queued",
                        "current_artwork_index": current_artwork_index,
                        "pixiv_id": artwork.pixiv_id,
                        "title": artwork.title,
                        "artist_name": artwork.artist_name,
                        "page_count": len(artwork.pages),
                        "sync_count": len(results),
                        "progress": 0,
                    },
                )
                results.extend(service.sync_artwork(artwork))
                artworks_done = index + 1
                cumulative_results = len(results)
                update(
                    "running",
                    "pixiv artwork completed",
                    {
                        "stage": "artwork_done",
                        "artworks_done": artworks_done,
                        "current_artwork_index": current_artwork_index,
                        "pixiv_id": artwork.pixiv_id,
                        "title": artwork.title,
                        "sync_count": len(results),
                        "progress": 100,
                    },
                )
        else:
            update("running", "fetching pixiv user artworks", {"stage": "fetching_user_artworks", "progress": 0})
            for index, artwork in enumerate(client.iter_user_illusts(target)):
                if request.limit is not None and index >= request.limit:
                    break
                current_artwork_index = index + 1
                current_result_base = len(results)
                update(
                    "running",
                    "pixiv artwork queued",
                    {
                        "stage": "artwork_queued",
                        "current_artwork_index": current_artwork_index,
                        "pixiv_id": artwork.pixiv_id,
                        "title": artwork.title,
                        "artist_name": artwork.artist_name,
                        "page_count": len(artwork.pages),
                        "sync_count": len(results),
                        "progress": 0,
                    },
                )
                results.extend(service.sync_artwork(artwork))
                artworks_done = index + 1
                cumulative_results = len(results)
                update(
                    "running",
                    "pixiv artwork completed",
                    {
                        "stage": "artwork_done",
                        "artworks_done": artworks_done,
                        "current_artwork_index": current_artwork_index,
                        "pixiv_id": artwork.pixiv_id,
                        "title": artwork.title,
                        "sync_count": len(results),
                        "progress": 100,
                    },
                )
        with session_factory() as session:
            _pixiv_sync_response(
                storage,
                session,
                catalog,
                results,
                rebuild_db=request.rebuild_db,
                generate_cache=request.generate_cache,
                background_tasks=None,
                session_factory=session_factory,
                principal=principal,
                target=target,
                mode=mode,
                options=options,
                log_id=log_id,
                progress_extra={
                    "sync_job_id": job_id,
                    "kind": kind,
                    "duration_seconds": round(time.monotonic() - started_at, 1),
                    "artworks_done": artworks_done or (1 if kind == "pid" and results else 0),
                },
            )
    except PixivRateLimitError as exc:
        retry_after = exc.retry_after_seconds or request.retry_base_seconds
        update(
            "error",
            "pixiv rate limited",
            {
                "stage": "rate_limited",
                "retry_after_seconds": retry_after,
                "error": str(exc),
                "sync_count": cumulative_results,
            },
        )
    except Exception as exc:
        update(
            "error",
            _clip_log_text(str(exc) or exc.__class__.__name__),
            {
                "stage": "error",
                "error": _clip_log_text(str(exc) or exc.__class__.__name__, 1000),
                "sync_count": cumulative_results,
            },
        )


def _normalize_pixiv_progress_payload(payload: dict[str, object]) -> dict[str, object]:
    data = dict(payload)
    if "progress" in data:
        progress = _optional_number(data.get("progress"))
        if progress is None:
            data.pop("progress", None)
        else:
            data["progress"] = _bounded_progress(progress)
    return data


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_progress(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


def _pixiv_sync_response(
    storage: GalleryStorage,
    db: Session,
    catalog: TagCatalog,
    results,
    *,
    rebuild_db: bool,
    generate_cache: bool,
    background_tasks: BackgroundTasks | None,
    session_factory: sessionmaker[Session],
    principal: Principal,
    target: str,
    mode: str,
    options: dict[str, object],
    log_id: int | None = None,
    progress_extra: dict[str, object] | None = None,
) -> dict[str, object]:
    media_items = []
    make_public = bool(options.get("make_public", True))
    rebuild_result = rebuild_database(db, storage, catalog) if rebuild_db or generate_cache or make_public else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
    _set_synced_assets_public(db, (result.asset_key for result in results), principal, make_public)
    jobs = []
    cache_tasks: list[tuple[GalleryStorage, sessionmaker[Session], TagCatalog, str, str]] = []
    if generate_cache:
        for result in results:
            if result.status == "skipped":
                continue
            asset = db.get(AssetModel, result.asset_key)
            if asset is None:
                continue
            existing = db.scalar(
                select(TranscodeJobModel)
                .where(
                    TranscodeJobModel.asset_key == asset.asset_key,
                    TranscodeJobModel.status.in_(("queued", "running")),
                )
                .order_by(TranscodeJobModel.id.desc())
            )
            if existing:
                jobs.append(transcode_job_to_dict(existing))
                continue
            job = create_transcode_job(db, asset, source="pixiv", file_size=_asset_original_size(storage, asset))
            create_upload_log(
                db,
                asset_key=asset.asset_key,
                uploader_user_id=principal.user_id,
                uploader_username=principal.username,
                original_filename=asset.original_filename,
                file_size=_asset_original_size(storage, asset),
                mime_type=asset.mime_type,
                event="transcode_request",
                status="queued",
                message=f"requested by {principal.username}",
                extra={"job_id": job.job_id, "source": "pixiv"},
            )
            jobs.append(transcode_job_to_dict(job))
            cache_tasks.append((storage, session_factory, catalog, asset.asset_key, job.job_id))
        db.commit()
        for task_args in cache_tasks:
            _schedule_background_task(background_tasks, _generate_cache_and_refresh_asset, *task_args)
    final_extra = {
        "sync_count": len(results),
        "asset_keys": _sync_asset_keys(result.asset_key for result in results),
        "queued_transcode_jobs": len([job for job in jobs if job]),
        "rebuild": rebuild_result.__dict__ if rebuild_result else None,
        "options": options,
        "stage": "done",
        "progress": 100,
        "last_update_at": utc_now_iso(),
        **(progress_extra or {}),
    }
    if log_id is None:
        _create_pixiv_log(
            db,
            principal=principal,
            target=target,
            mode=mode,
            status="success",
            message="pixiv sync completed",
            extra=final_extra,
        )
    else:
        _update_pixiv_log(db, log_id, status="success", message="pixiv sync completed", extra=final_extra)
    db.commit()
    return {
        "sync": [result.__dict__ for result in results],
        "media": media_items,
        "jobs": jobs,
        "rebuild": rebuild_result.__dict__ if rebuild_result else None,
    }


class _PublicFirstPixivClient:
    def __init__(self, public_client, private_client_factory) -> None:
        self.public_client = public_client
        self.private_client_factory = private_client_factory
        self._private_client = None

    def _private(self):
        if self._private_client is None:
            self._private_client = self.private_client_factory()
        return self._private_client

    def get_illust(self, pixiv_id: str):
        try:
            return self.public_client.get_illust(pixiv_id)
        except PixivRateLimitError:
            raise
        except Exception:
            return self._private().get_illust(pixiv_id)

    def iter_user_illusts(self, user_id: str):
        yielded = 0
        try:
            for artwork in self.public_client.iter_user_illusts(user_id):
                yielded += 1
                yield artwork
        except PixivRateLimitError:
            raise
        except Exception:
            if yielded:
                raise
            yield from self._private().iter_user_illusts(user_id)

    def iter_user_bookmarks(self, user_id: str, restrict: str = "public"):
        for pixiv_id in self._private().iter_user_bookmark_ids(user_id, restrict=restrict):
            try:
                yield self.get_illust(pixiv_id)
            except RuntimeError:
                continue

    def iter_user_bookmark_ids(self, user_id: str, restrict: str = "public"):
        yield from self._private().iter_user_bookmark_ids(user_id, restrict=restrict)


class _PublicFirstDownloader:
    def __init__(self, public_downloader, private_downloader_factory) -> None:
        self.public_downloader = public_downloader
        self.private_downloader_factory = private_downloader_factory
        self._private_downloader = None

    def _private(self):
        if self._private_downloader is None:
            self._private_downloader = self.private_downloader_factory()
        return self._private_downloader

    def download(self, url: str) -> bytes:
        try:
            return self.public_downloader.download(url)
        except PixivRateLimitError:
            raise
        except Exception:
            return self._private().download(url)


def _pixiv_sync_components(request: PixivSyncRequest):
    mode = _normalize_pixiv_auth_mode(request.auth_mode)
    options = _pixiv_request_options(request)
    if _pixiv_public_first_enabled(request, mode):
        public_client, public_downloader = _pixiv_public_components(options)
        private_components = None

        def private():
            nonlocal private_components
            if private_components is None:
                private_components = _pixiv_private_components(mode, request, options)
            return private_components

        return (
            _PublicFirstPixivClient(public_client, lambda: private()[0]),
            _PublicFirstDownloader(public_downloader, lambda: private()[1]),
        )
    if mode == "public":
        return _pixiv_public_components(options)
    return _pixiv_private_components(mode, request, options)


def _pixiv_public_components(options: PixivRequestOptions):
    client = PixivCookieClient("", options=options)
    downloader = HTTPPixivDownloader(options=options)
    return client, downloader


def _pixiv_private_components(mode: str, request: PixivSyncRequest, options: PixivRequestOptions):
    if mode in {"oauth", "refresh_token"}:
        client = PixivPyClient.from_refresh_token(request.refresh_token, options=options)
        downloader = HTTPPixivDownloader(options=options)
        return client, downloader
    if mode == "cookie":
        client = PixivCookieClient(request.cookie or "", options=options)
        downloader = HTTPPixivDownloader(cookie=request.cookie or "", options=options)
        return client, downloader
    if mode == "local_import":
        raise RuntimeError("local Pixiv import is not available from this sync endpoint yet")
    raise RuntimeError(f"unsupported Pixiv auth mode: {request.auth_mode}")


def _apply_pixiv_proxy_config(request: PixivSyncRequest, config: NyaGalleryConfig) -> None:
    if not (request.proxy_url or "").strip():
        request.proxy_url = network_proxy_for(config, "pixiv")


def _pixiv_public_first_enabled(request: PixivSyncRequest, mode: str) -> bool:
    if not request.public_first:
        return False
    if mode in {"oauth", "refresh_token"}:
        return bool(request.refresh_token or os.environ.get("PIXIV_REFRESH_TOKEN"))
    if mode == "cookie":
        return bool(request.cookie)
    return False


def _resolve_saved_pixiv_token(
    request: PixivSyncRequest,
    db: Session,
    principal: Principal,
    http_request: Request,
) -> None:
    if request.pixiv_token_id is None:
        return
    if not _is_admin_principal(principal) and not pixiv_token_belongs_to_user(db, request.pixiv_token_id, principal.user_id):
        raise HTTPException(status_code=403, detail="permission denied")
    try:
        request.refresh_token = get_pixiv_refresh_token(
            db,
            request.pixiv_token_id,
            record_usage=True,
            client_ip=client_ip(http_request, trust_proxy_headers=False),
        )
    except SecretEncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()


def _resolve_saved_pixiv_cookie(
    request: PixivSyncRequest,
    db: Session,
    principal: Principal,
    http_request: Request,
) -> None:
    if request.pixiv_cookie_id is None:
        return
    if not _is_admin_principal(principal) and not pixiv_cookie_belongs_to_user(db, request.pixiv_cookie_id, principal.user_id):
        raise HTTPException(status_code=403, detail="permission denied")
    try:
        request.cookie = get_pixiv_cookie(
            db,
            request.pixiv_cookie_id,
            record_usage=True,
            client_ip=client_ip(http_request, trust_proxy_headers=False),
        )
    except SecretEncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()


def _normalize_pixiv_auth_mode(value: str | None) -> str:
    normalized = str(value or "public").strip().casefold().replace("-", "_")
    aliases = {
        "public": "public",
        "guest": "public",
        "anonymous": "public",
        "anon": "public",
        "none": "public",
        "no_auth": "public",
        "oauth_local": "oauth",
        "local_oauth": "oauth",
        "browser_oauth": "oauth",
        "token": "refresh_token",
        "refresh": "refresh_token",
        "refresh_token": "refresh_token",
        "oauth": "oauth",
        "oauth_manual": "oauth",
        "manual_oauth": "oauth",
        "cookie": "cookie",
        "browser_cookie": "cookie",
        "local": "local_import",
        "local_import": "local_import",
    }
    return aliases.get(normalized, normalized)


def _pixiv_request_options(request: PixivSyncRequest) -> PixivRequestOptions:
    return PixivRequestOptions(
        request_delay_seconds=request.request_delay_seconds,
        max_retries=request.max_retries,
        retry_base_seconds=request.retry_base_seconds,
        retry_max_seconds=max(request.retry_base_seconds, request.retry_max_seconds),
        proxy_url=(request.proxy_url or "").strip(),
    )


def _pixiv_options_log(request: PixivSyncRequest) -> dict[str, object]:
    mode = _normalize_pixiv_auth_mode(request.auth_mode)
    return {
        "auth_mode": mode,
        "has_refresh_token": bool(request.refresh_token),
        "pixiv_token_id": request.pixiv_token_id,
        "has_cookie": bool(request.cookie),
        "pixiv_cookie_id": request.pixiv_cookie_id,
        "storage_strategy": request.storage_strategy,
        "public_first": request.public_first,
        "make_public": request.make_public,
        "limit": request.limit,
        "rebuild_db": request.rebuild_db,
        "generate_cache": request.generate_cache,
        "request_delay_seconds": request.request_delay_seconds,
        "max_retries": request.max_retries,
        "retry_base_seconds": request.retry_base_seconds,
        "retry_max_seconds": request.retry_max_seconds,
        "concurrency": request.concurrency,
        "proxy_enabled": bool((request.proxy_url or "").strip()),
        "dry_run": request.dry_run,
    }


def _pixiv_artwork_preview(artwork) -> dict[str, object]:
    return {
        "pixiv_id": artwork.pixiv_id,
        "title": artwork.title,
        "artist_id": artwork.artist_id,
        "artist_name": artwork.artist_name,
        "page_count": len(artwork.pages),
        "tags": list(artwork.tags),
        "source_type": artwork.source_type,
        "age_rating": artwork.age_rating,
        "is_ai_generated": artwork.is_ai_generated,
        "artwork_date": artwork.artwork_date,
        "pixiv_upload_date": artwork.pixiv_upload_date,
        "thumbnail_url": f"/api/sync/pixiv/thumb?url={quote(artwork.pages[0].original_url, safe='')}" if artwork.pages else None,
    }


_PIXIV_ORIGINAL_RE = re.compile(r"^/img-original/img/(?P<date>(?:\d+/){6})(?P<name>\d+(?:-[0-9a-f]{8,64})?_p\d+)(?:_ugoira0)?\.(?:jpg|jpeg|png|gif)$")


_PIXIV_MASTER_RE = re.compile(r"^/(?:c/[0-9x_]+/)?img-master/img/(?:\d+/){6}\d+(?:-[0-9a-f]{8,64})?_p\d+(?:_master1200|_square1200)\.jpg$")


def _pixiv_thumb_url(raw: str) -> str | None:
    """Map an i.pximg.net original/master URL to the 540px master JPEG; reject anything else."""
    try:
        parsed = urlparse(unquote(raw))
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != "i.pximg.net" or parsed.username or parsed.port or parsed.query:
        return None
    original = _PIXIV_ORIGINAL_RE.match(parsed.path)
    if original:
        return f"https://i.pximg.net/c/540x540_70/img-master/img/{original.group('date')}{original.group('name')}_master1200.jpg"
    if _PIXIV_MASTER_RE.match(parsed.path):
        return f"https://i.pximg.net{parsed.path}"
    return None


def _create_pixiv_log(
    db: Session,
    *,
    principal: Principal,
    target: str,
    mode: str,
    status: str,
    message: str,
    extra: dict[str, object] | None = None,
) -> UploadLogModel:
    return create_upload_log(
        db,
        asset_key=None,
        uploader_user_id=principal.user_id,
        uploader_username=principal.username,
        original_filename=f"pixiv:{target}",
        file_size=None,
        mime_type=None,
        event="pixiv_sync",
        status=status,
        message=message,
        extra={"target": target, "auth_mode": mode, **(extra or {})},
    )


def _pixiv_extension_zip_response() -> StreamingResponse:
    extension_dir = Path(__file__).resolve().parents[2] / "pixiv-login-extension"
    if not extension_dir.exists():
        raise HTTPException(status_code=404, detail="Pixiv login extension files not found")

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extension_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(extension_dir)
            if any(part.startswith(".") for part in relative.parts):
                continue
            archive.write(path, f"pixiv-login-extension/{relative.as_posix()}")
    payload.seek(0)

    headers = {"Content-Disposition": 'attachment; filename="pixiv-login-extension.zip"'}
    return StreamingResponse(payload, media_type="application/zip", headers=headers)


class PixivPlugin:
    manifest = PluginManifest("official.pixiv", "1.0.0", ("adapter",), permissions=('routes', 'events', 'read_assets', 'write_assets', 'network', 'credentials', 'read_config'))
    info = PluginInfo(title='Pixiv', description='Pixiv artwork / user / bookmark sync, OAuth / token / cookie credentials, preview and sync logs.', official=True, provides_sections=('pixiv',))

    def setup(self, ctx: PluginContext) -> None:
        state = ctx.app_state
        app = ctx._host.app  # official plugins share the app object (lifespan / state access)
        router = ctx.router()
        storage = state.storage
        catalog = state.catalog
        session_factory = state.session_factory

        @router.get("/api/sync/pixiv/logs")
        def api_pixiv_logs(
            db: DbSession,
            principal: ApiPrincipal,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> dict[str, object]:
            logs = list_pixiv_logs(
                db,
                user_id=principal.user_id,
                is_admin=_is_admin_principal(principal),
                limit=limit,
                offset=offset,
            )
            assets = {
                asset.asset_key: asset
                for asset in db.scalars(
                    select(AssetModel).where(
                        AssetModel.asset_key.in_([log.asset_key for log in logs if log.asset_key])
                    )
                )
            } if logs else {}
            return {
                "items": attach_sync_log_assets(
                    db,
                    storage,
                    logs,
                    [upload_log_to_dict(log, storage=storage, asset=assets.get(log.asset_key or "")) for log in logs],
                ),
                "limit": limit,
                "offset": offset,
            }

        @router.get("/api/sync/pixiv/config")
        def api_pixiv_config(request: Request, _principal: UploadPrincipal) -> dict[str, object]:
            state_config: NyaGalleryConfig = request.app.state.nyagallery.config
            configured_token = bool(state_config.pixiv.refresh_token)
            env_token = bool(os.environ.get("PIXIV_REFRESH_TOKEN"))
            browser_login_available = importlib.util.find_spec("gppt") is not None
            cookie_session_exchange_available = importlib.util.find_spec("playwright") is not None
            return {
                "has_env_refresh_token": configured_token or env_token,
                "token_source": "config" if configured_token else "environment" if env_token else "request",
                "supports_user_sync": True,
                "supports_generate_cache": True,
                "supports_browser_oauth_login": browser_login_available,
                "supports_cookie_session_exchange": cookie_session_exchange_available,
                "storage_strategies": _storage_strategy_items(storage),
                "default_storage_strategy": storage.default_storage_strategy(),
                "secret_encryption_enabled": secret_encryption_enabled(state_config.security.secret_key),
                "proxy_enabled": bool(network_proxy_for(state_config, "pixiv")),
                "auth_modes": ["public", "oauth_local", "refresh_token", "cookie", "oauth_manual", "local_import"],
                "default_request_delay_seconds": state_config.pixiv.default_request_delay_seconds,
                "max_concurrency": state_config.pixiv.max_concurrency,
                "oauth_note": "Public Pixiv artwork/user crawling does not require login. Use OAuth only for account-scoped sources such as bookmarks or private context.",
                "browser_oauth_note": "Server-side browser login requires the optional pixiv-login dependency and sends Pixiv credentials only to this NyaGallery backend for the current request.",
                "manual_oauth_note": "Manual callback/code exchange is kept as a fallback because Pixiv web redirects may get stuck on post-redirect pages.",
                "rate_limit_note": "Public crawling is preferred for public artwork/user sources. Logged-in crawling may trigger Pixiv 429 more easily; keep concurrency at 1 and use delay/backoff when using OAuth/Cookie.",
            }

        @router.get("/api/sync/pixiv/extension/download")
        def api_pixiv_extension_download(_principal: UploadPrincipal) -> StreamingResponse:
            return _pixiv_extension_zip_response()

        @router.post("/api/sync/pixiv/oauth/start")
        def api_pixiv_oauth_start(_principal: AdminPrincipal, request: PixivOAuthStartRequest | None = None) -> dict[str, object]:
            start = create_pixiv_oauth_start(
                state=request.state if request else None,
                callback_url=request.callback_url if request else None,
            )
            return {
                "authorization_url": start.authorization_url,
                "code_verifier": start.code_verifier,
                "code_challenge": start.code_challenge,
                "state": start.state,
                "callback_url": start.callback_url,
            }

        @router.post("/api/sync/pixiv/oauth/exchange")
        def api_pixiv_oauth_exchange(
            request: PixivOAuthExchangeRequest,
            http_request: Request,
            _principal: AdminPrincipal,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            proxy_url = network_proxy_for(state_config, "pixiv")
            try:
                token = exchange_pixiv_oauth_code(
                    code=request.code,
                    callback_url=request.callback_url,
                    code_verifier=request.code_verifier,
                    state=request.state,
                    proxy_url=proxy_url,
                )
            except (PixivOAuthError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {
                "refresh_token": token.refresh_token,
                "expires_in": token.expires_in,
                "user": token.user,
            }

        @router.post("/api/sync/pixiv/oauth/browser-login")
        def api_pixiv_oauth_browser_login(
            request: PixivOAuthBrowserLoginRequest,
            http_request: Request,
            _principal: AdminPrincipal,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            proxy_url = network_proxy_for(state_config, "pixiv")
            try:
                token = get_pixiv_refresh_token_with_browser_worker(
                    headless=True,
                    username=request.username,
                    password=request.password,
                    timeout_seconds=request.timeout_seconds,
                    proxy_url=proxy_url,
                )
            except PixivOAuthError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {
                "refresh_token": token.refresh_token,
                "expires_in": token.expires_in,
                "user": token.user,
            }

        @router.post("/api/sync/pixiv/oauth/visible/start")
        def api_pixiv_oauth_visible_start(request: PixivOAuthVisibleLoginRequest | None, _principal: AdminPrincipal) -> dict[str, object]:
            session_id = secrets.token_urlsafe(18)
            now = time.time()
            payload = request or PixivOAuthVisibleLoginRequest()
            session = {
                "id": session_id,
                "status": "running",
                "message": "visible Pixiv browser login started",
                "created_at": now,
                "updated_at": now,
                "expires_at": now + payload.timeout_seconds + 300,
                "refresh_token": None,
                "expires_in": None,
                "user": None,
                "error": None,
            }
            with app.state.nyagallery.pixiv_login_lock:
                _prune_pixiv_login_sessions(app.state.nyagallery.pixiv_login_sessions)
                app.state.nyagallery.pixiv_login_sessions[session_id] = session

            thread = threading.Thread(
                target=_run_visible_pixiv_login_session,
                args=(
                    app.state.nyagallery,
                    session_id,
                    (payload.username or "").strip() or None,
                    payload.password or None,
                    payload.timeout_seconds,
                    network_proxy_for(app.state.nyagallery.config, "pixiv"),
                ),
                daemon=True,
            )
            thread.start()
            return _pixiv_login_session_public(session)

        @router.get("/api/sync/pixiv/oauth/visible/{session_id}")
        def api_pixiv_oauth_visible_status(session_id: str, _principal: AdminPrincipal) -> dict[str, object]:
            with app.state.nyagallery.pixiv_login_lock:
                _prune_pixiv_login_sessions(app.state.nyagallery.pixiv_login_sessions)
                session = app.state.nyagallery.pixiv_login_sessions.get(session_id)
                if session is None:
                    raise HTTPException(status_code=404, detail="Pixiv login session not found")
                return _pixiv_login_session_public(session)

        @router.post("/api/sync/pixiv/session/exchange")
        @router.post("/api/pixiv/session/exchange")
        def api_pixiv_session_exchange(
            request: PixivSessionExchangeRequest,
            http_request: Request,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            proxy_url = network_proxy_for(state_config, "pixiv")
            try:
                token = get_pixiv_refresh_token_with_cookie_worker(
                    cookie=request.cookie,
                    headless=request.headless,
                    timeout_seconds=request.timeout_seconds,
                    proxy_url=proxy_url,
                )
            except PixivOAuthError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            saved_token = None
            if request.save:
                target_username = (request.username or principal.username).strip()
                if not target_username or target_username == "bootstrap-admin":
                    raise HTTPException(status_code=400, detail="username is required to save Pixiv token")
                _require_self_or_admin(target_username, principal)
                try:
                    saved_token = save_pixiv_token(
                        db,
                        target_username,
                        token.refresh_token,
                        label=request.label,
                        pixiv_user=token.user,
                        created_by_user_id=principal.user_id,
                        created_by_username=principal.username,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=404 if "user not found" in str(exc) else 400, detail=str(exc)) from exc

            return {
                "refresh_token": token.refresh_token if request.return_token else None,
                "expires_in": token.expires_in,
                "user": token.user,
                "saved_token": pixiv_token_to_dict(saved_token) if saved_token is not None else None,
                "auth_mode": "refresh_token",
                "source": "pixiv_cookie_oauth",
            }

        @router.post("/api/sync/pixiv/preview")
        def api_sync_pixiv_preview(
            payload: PixivPreviewRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            """Fetch Pixiv artwork metadata without downloading or writing anything (no log row either)."""
            request = payload.options
            pids = list(dict.fromkeys(pid.strip() for pid in payload.pids if pid.strip().isdigit()))[:PIXIV_PREVIEW_LIMIT]
            if not pids:
                raise HTTPException(status_code=422, detail="no valid pixiv ids")
            try:
                _apply_pixiv_proxy_config(request, http_request.app.state.nyagallery.config)
                _resolve_saved_pixiv_token(request, db, principal, http_request)
                _resolve_saved_pixiv_cookie(request, db, principal, http_request)
                client, _downloader = _pixiv_sync_components(request)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            existing = {
                row[0]
                for row in db.execute(
                    select(AssetModel.source_id).where(AssetModel.source == "pixiv", AssetModel.source_id.in_(pids)).distinct()
                )
            }
            items: list[dict[str, object]] = []
            for pid in pids:
                try:
                    artwork = client.get_illust(pid)
                except PixivRateLimitError as exc:
                    items.append({"pixiv_id": pid, "error": f"rate limited; retry after {exc.retry_after_seconds or request.retry_base_seconds}s"})
                    break
                except Exception as exc:  # one bad id must not hide the others
                    items.append({"pixiv_id": pid, "error": _clip_log_text(str(exc) or exc.__class__.__name__, 300)})
                    continue
                preview = _pixiv_artwork_preview(artwork)
                preview["already_archived"] = pid in existing
                items.append(preview)
                if request.request_delay_seconds:
                    time.sleep(min(request.request_delay_seconds, 5.0))
            return {"items": items}

        @router.get("/api/sync/pixiv/thumb")
        def api_sync_pixiv_thumb(url: str, _principal: UploadPrincipal, http_request: Request) -> Response:
            """Referer-bearing proxy for preview thumbnails. Only i.pximg.net is allowed (no open proxy)."""
            thumb_url = _pixiv_thumb_url(url)
            if thumb_url is None:
                raise HTTPException(status_code=400, detail="unsupported thumbnail url")
            request = PixivSyncRequest()
            _apply_pixiv_proxy_config(request, http_request.app.state.nyagallery.config)
            options = _pixiv_request_options(request)
            try:
                content = HTTPPixivDownloader(options=replace(options, max_retries=0, request_delay_seconds=0)).download(thumb_url)
            except Exception as exc:
                raise HTTPException(status_code=502, detail="thumbnail fetch failed") from exc
            if len(content) > 4 * 1024 * 1024:
                raise HTTPException(status_code=502, detail="thumbnail too large")
            media_type = "image/png" if thumb_url.endswith(".png") else "image/jpeg"
            return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})

        @router.post("/api/sync/pixiv/{pid}")
        def api_sync_pixiv_pid(
            pid: str,
            request: PixivSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            mode = _normalize_pixiv_auth_mode(request.auth_mode)
            try:
                _apply_pixiv_proxy_config(request, http_request.app.state.nyagallery.config)
                _resolve_saved_pixiv_token(request, db, principal, http_request)
                _resolve_saved_pixiv_cookie(request, db, principal, http_request)
                if request.dry_run:
                    client, _downloader = _pixiv_sync_components(request)
                    artwork = client.get_illust(pid)
                    _create_pixiv_log(
                        db,
                        principal=principal,
                        target=pid,
                        mode=mode,
                        status="success",
                        message="dry run completed",
                        extra={"artworks": [_pixiv_artwork_preview(artwork)], "options": _pixiv_options_log(request)},
                    )
                    db.commit()
                    return {"sync": [], "media": [], "rebuild": None, "jobs": [], "preview": [_pixiv_artwork_preview(artwork)]}
                return _queue_pixiv_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=pid,
                    kind="pid",
                    request=request,
                    mode=mode,
                )
            except PixivRateLimitError as exc:
                retry_after = exc.retry_after_seconds or request.retry_base_seconds
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=pid,
                    mode=mode,
                    status="error",
                    message="pixiv rate limited",
                    extra={"retry_after_seconds": retry_after, "options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail=f"Pixiv rate limited; retry after {retry_after} seconds",
                    headers={"Retry-After": str(retry_after)},
                ) from exc
            except RuntimeError as exc:
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=pid,
                    mode=mode,
                    status="error",
                    message=str(exc),
                    extra={"options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/sync/pixiv/user/{uid}")
        def api_sync_pixiv_user(
            uid: str,
            request: PixivSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            mode = _normalize_pixiv_auth_mode(request.auth_mode)
            try:
                _apply_pixiv_proxy_config(request, http_request.app.state.nyagallery.config)
                _resolve_saved_pixiv_token(request, db, principal, http_request)
                _resolve_saved_pixiv_cookie(request, db, principal, http_request)
                if request.dry_run:
                    client, _downloader = _pixiv_sync_components(request)
                    artworks = []
                    for index, artwork in enumerate(client.iter_user_illusts(uid)):
                        if request.limit is not None and index >= request.limit:
                            break
                        artworks.append(_pixiv_artwork_preview(artwork))
                    _create_pixiv_log(
                        db,
                        principal=principal,
                        target=uid,
                        mode=mode,
                        status="success",
                        message="dry run completed",
                        extra={"artworks": artworks, "options": _pixiv_options_log(request)},
                    )
                    db.commit()
                    return {"sync": [], "media": [], "rebuild": None, "jobs": [], "preview": artworks}
                return _queue_pixiv_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=uid,
                    kind="user",
                    request=request,
                    mode=mode,
                )
            except PixivRateLimitError as exc:
                retry_after = exc.retry_after_seconds or request.retry_base_seconds
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=uid,
                    mode=mode,
                    status="error",
                    message="pixiv rate limited",
                    extra={"retry_after_seconds": retry_after, "options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail=f"Pixiv rate limited; retry after {retry_after} seconds",
                    headers={"Retry-After": str(retry_after)},
                ) from exc
            except RuntimeError as exc:
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=uid,
                    mode=mode,
                    status="error",
                    message=str(exc),
                    extra={"options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/sync/pixiv/bookmarks/{uid}")
        def api_sync_pixiv_bookmarks(
            uid: str,
            request: PixivSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            mode = _normalize_pixiv_auth_mode(request.auth_mode)
            restrict = request.restrict or "public"
            try:
                _apply_pixiv_proxy_config(request, http_request.app.state.nyagallery.config)
                _resolve_saved_pixiv_token(request, db, principal, http_request)
                _resolve_saved_pixiv_cookie(request, db, principal, http_request)
                if request.dry_run:
                    client, _downloader = _pixiv_sync_components(request)
                    artworks = []
                    for index, artwork in enumerate(client.iter_user_bookmarks(uid, restrict=restrict)):
                        if request.limit is not None and index >= request.limit:
                            break
                        artworks.append(_pixiv_artwork_preview(artwork))
                    _create_pixiv_log(
                        db,
                        principal=principal,
                        target=uid,
                        mode=mode,
                        status="success",
                        message="dry run completed",
                        extra={"artworks": artworks, "options": _pixiv_options_log(request)},
                    )
                    db.commit()
                    return {"sync": [], "media": [], "rebuild": None, "jobs": [], "preview": artworks}
                return _queue_pixiv_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=uid,
                    kind="bookmarks",
                    request=request,
                    mode=mode,
                )
            except PixivRateLimitError as exc:
                retry_after = exc.retry_after_seconds or request.retry_base_seconds
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=uid,
                    mode=mode,
                    status="error",
                    message="pixiv rate limited",
                    extra={"retry_after_seconds": retry_after, "options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail=f"Pixiv rate limited; retry after {retry_after} seconds",
                    headers={"Retry-After": str(retry_after)},
                ) from exc
            except RuntimeError as exc:
                _create_pixiv_log(
                    db,
                    principal=principal,
                    target=uid,
                    mode=mode,
                    status="error",
                    message=str(exc),
                    extra={"options": _pixiv_options_log(request)},
                )
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/users/{username}/pixiv-token")
        def api_save_user_pixiv_token(
            username: str,
            request: PixivTokenCreate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                token = save_pixiv_token(
                    db,
                    username,
                    request.refresh_token,
                    label=request.label,
                    pixiv_user=request.pixiv_user,
                    created_by_user_id=principal.user_id,
                    created_by_username=principal.username,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404 if "user not found" in str(exc) else 400, detail=str(exc)) from exc
            return pixiv_token_to_dict(token)

        @router.get("/api/users/{username}/pixiv-tokens")
        def api_user_pixiv_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                tokens = list_pixiv_tokens(db, username)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"items": [pixiv_token_to_dict(token) for token in tokens]}

        @router.post("/api/users/{username}/pixiv-cookie")
        def api_save_user_pixiv_cookie(
            username: str,
            request: PixivCookieCreate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                cookie = save_pixiv_cookie(
                    db,
                    username,
                    request.cookie,
                    label=request.label,
                    pixiv_user=request.pixiv_user,
                    created_by_user_id=principal.user_id,
                    created_by_username=principal.username,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404 if "user not found" in str(exc) else 400, detail=str(exc)) from exc
            return pixiv_cookie_to_dict(cookie)

        @router.get("/api/users/{username}/pixiv-cookies")
        def api_user_pixiv_cookies(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                cookies = list_pixiv_cookies(db, username)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"items": [pixiv_cookie_to_dict(cookie) for cookie in cookies]}

        @router.patch("/api/pixiv-cookies/{cookie_id}")
        def api_update_pixiv_cookie_label(
            cookie_id: int,
            request: PixivCookieUpdate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            if not _is_admin_principal(principal) and not pixiv_cookie_belongs_to_user(db, cookie_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                cookie = update_pixiv_cookie_label(db, cookie_id, request.label)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return pixiv_cookie_to_dict(cookie)

        @router.delete("/api/pixiv-cookies/{cookie_id}")
        def api_revoke_pixiv_cookie(cookie_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            if not _is_admin_principal(principal) and not pixiv_cookie_belongs_to_user(db, cookie_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                cookie = revoke_pixiv_cookie(db, cookie_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return pixiv_cookie_to_dict(cookie)

        @router.patch("/api/pixiv-tokens/{token_id}")
        def api_update_pixiv_token_label(
            token_id: int,
            request: PixivTokenUpdate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            if not _is_admin_principal(principal) and not pixiv_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = update_pixiv_token_label(db, token_id, request.label)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return pixiv_token_to_dict(token)

        @router.delete("/api/pixiv-tokens/{token_id}")
        def api_revoke_pixiv_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            if not _is_admin_principal(principal) and not pixiv_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = revoke_pixiv_token(db, token_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return pixiv_token_to_dict(token)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = PixivPlugin()
