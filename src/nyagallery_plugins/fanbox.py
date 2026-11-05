"""Official plugin: FANBOX sync (moved out of nyagallery.app; URLs unchanged)."""

from __future__ import annotations

import secrets
import threading
import time
from fastapi import (
    HTTPException,
    Query,
    Request,
)
from nyagallery.auth import (
    Principal,
    permissions_for_role,
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
    fanbox_session_belongs_to_user,
    fanbox_session_to_dict,
    get_fanbox_session,
    get_pixiv_cookie,
    list_fanbox_logs,
    list_fanbox_sessions,
    pixiv_cookie_belongs_to_user,
    rebuild_database,
    revoke_fanbox_session,
    save_fanbox_session,
    transcode_job_to_dict,
    update_fanbox_session_label,
    upload_log_to_dict,
)
from nyagallery.fanbox import (
    FanboxAuthError,
    FanboxClient,
    FanboxCreator,
    FanboxCredentials,
    FanboxDownloader,
    FanboxError,
    FanboxPost,
    FanboxPostResult,
    FanboxRateLimitError,
    FanboxRequestOptions,
    FanboxSyncService,
    exchange_pixiv_cookie_for_fanbox_session,
    normalize_creator_id,
)
from nyagallery.metadata import (
    utc_now_iso,
)
from nyagallery.security import (
    client_ip,
)
from nyagallery.storage import (
    GalleryStorage,
    StorageError,
)
from nyagallery.tags import (
    TagCatalog,
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

from nyagallery.plugin_host import PluginContext, PluginInfo
from nyagallery.plugins import PluginManifest
from nyagallery.app import (
    ApiPrincipal,
    DbSession,
    UploadPrincipal,
    ViewPrincipal,
    _asset_original_size,
    _commit_pixiv_log_update,
    _generate_cache_and_refresh_asset,
    _is_admin_principal,
    _model_dump,
    _require_self_or_admin,
    _save_catalog,
    _schedule_background_task,
    _storage_strategy_items,
    _sync_asset_keys,
    _update_pixiv_log,
)


class FanboxSessionCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=4000)
    label: str = ""
    source: str = "manual"
    fanbox_user: dict | None = None


class FanboxSessionUpdate(BaseModel):
    label: str = ""


class FanboxLoginRequest(BaseModel):
    """Derives a FANBOXSESSID from a Pixiv web session, since Fanbox will not accept the Pixiv cookie directly."""

    cookie: str | None = None
    pixiv_cookie_id: int | None = None
    label: str = ""
    headless: bool = True
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    save: bool = True


class FanboxSyncRequest(BaseModel):
    name_media_by_post_id: bool | None = None
    session_id: str | None = None
    fanbox_session_id: int | None = None
    targets: list[str] = Field(default_factory=list)
    proxy_url: str | None = None
    storage_strategy: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100_000)
    page_size: int = Field(default=10, ge=1, le=300)
    max_pages: int | None = Field(default=None, ge=1, le=10_000)
    backfill: bool = True
    download_media: bool = True
    download_files: bool = True
    download_concurrency: int = Field(default=3, ge=1, le=16)
    request_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: int = Field(default=60, ge=1, le=3600)
    retry_max_seconds: int = Field(default=300, ge=1, le=7200)
    rebuild_db: bool = True
    generate_cache: bool = True
    dry_run: bool = False


def _fanbox_batch_targets(targets: list[str]) -> list[str]:
    from nyagallery.fanbox import split_batch_input as fanbox_split

    collected: list[str] = []
    for entry in targets:
        collected.extend(fanbox_split(entry))
    return list(dict.fromkeys(collected))


def _fanbox_session_identity(session_id: str, config: NyaGalleryConfig) -> dict[str, object]:
    """Best-effort identity for a freshly derived session; a failure here must not fail the login."""
    try:
        client = FanboxClient(
            credentials=FanboxCredentials(session_id=session_id),
            options=FanboxRequestOptions(request_delay_seconds=0, max_retries=0),
            proxy_url=network_proxy_for(config, "fanbox"),
        )
        return client.verify_session()
    except FanboxError:
        return {}


def _resolve_fanbox_request(
    request: FanboxSyncRequest,
    config: NyaGalleryConfig,
    storage: GalleryStorage,
    *,
    db: Session | None = None,
    principal: Principal | None = None,
    http_request: Request | None = None,
) -> FanboxSyncRequest:
    resolved = FanboxSyncRequest(**_model_dump(request))
    if resolved.fanbox_session_id is not None:
        if db is None or principal is None:
            raise FanboxError("saved Fanbox sessions cannot be used in this context")
        if not _is_admin_principal(principal) and not fanbox_session_belongs_to_user(
            db, resolved.fanbox_session_id, principal.user_id
        ):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            resolved.session_id = get_fanbox_session(
                db,
                resolved.fanbox_session_id,
                record_usage=True,
                client_ip=client_ip(http_request, trust_proxy_headers=False) if http_request is not None else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
    resolved.session_id = (resolved.session_id or config.fanbox.session_id or "").strip() or None
    if not resolved.proxy_url:
        resolved.proxy_url = network_proxy_for(config, "fanbox") or None
    resolved.storage_strategy = storage.validate_storage_strategy(resolved.storage_strategy)
    if resolved.name_media_by_post_id is None:
        resolved.name_media_by_post_id = config.core.name_media_by_post_id
    return resolved


def _fanbox_request_options(request: FanboxSyncRequest) -> FanboxRequestOptions:
    return FanboxRequestOptions(
        request_delay_seconds=request.request_delay_seconds,
        max_retries=request.max_retries,
        retry_base_seconds=request.retry_base_seconds,
        retry_max_seconds=request.retry_max_seconds,
        download_concurrency=request.download_concurrency,
        proxy_url=request.proxy_url or "",
    )


def _fanbox_sync_components(request: FanboxSyncRequest) -> tuple[FanboxClient, FanboxDownloader]:
    options = _fanbox_request_options(request)
    credentials = FanboxCredentials(session_id=request.session_id or "")
    client = FanboxClient(credentials=credentials, options=options, proxy_url=request.proxy_url)
    downloader = FanboxDownloader(credentials=credentials, options=options, proxy_url=request.proxy_url)
    return client, downloader


def _fanbox_options_log(request: FanboxSyncRequest) -> dict[str, object]:
    return {
        "limit": request.limit,
        "page_size": request.page_size,
        "max_pages": request.max_pages,
        "backfill": request.backfill,
        "download_media": request.download_media,
        "download_files": request.download_files,
        "download_concurrency": request.download_concurrency,
        "request_delay_seconds": request.request_delay_seconds,
        "storage_strategy": request.storage_strategy,
        "rebuild_db": request.rebuild_db,
        "generate_cache": request.generate_cache,
        "session_configured": bool(request.session_id),
        "proxy_configured": bool(request.proxy_url),
    }


def _fanbox_creator_preview(creator: FanboxCreator) -> dict[str, object]:
    return {
        "creator_id": creator.creator_id,
        "user_id": creator.user_id,
        "name": creator.display_name,
        "icon_url": creator.icon_url,
        "has_adult_content": creator.has_adult_content,
        "is_supported": creator.is_supported,
    }


def _fanbox_post_preview(post: FanboxPost) -> dict[str, object]:
    return {
        "post_id": post.post_id,
        "title": post.title[:120],
        "post_type": post.post_type,
        "published_at": post.published_at,
        "fee_required": post.fee_required,
        "locked": post.is_locked,
        "file_count": len(post.files),
        "tags": list(post.tags),
        "url": post.url,
    }


def _create_fanbox_log(
    db: Session,
    *,
    principal: Principal,
    target: str,
    status: str,
    message: str,
    extra: dict[str, object] | None = None,
) -> UploadLogModel:
    return create_upload_log(
        db,
        asset_key=None,
        uploader_user_id=principal.user_id,
        uploader_username=principal.username,
        original_filename=f"fanbox:{target}",
        file_size=None,
        mime_type=None,
        event="fanbox_sync",
        status=status,
        message=message,
        extra={"target": target, **(extra or {})},
    )


def _fanbox_rate_limit_error(
    db: Session,
    exc: FanboxRateLimitError,
    *,
    principal: Principal,
    target: str,
    request: FanboxSyncRequest,
) -> HTTPException:
    retry_after = exc.retry_after_seconds or request.retry_base_seconds
    _create_fanbox_log(
        db, principal=principal, target=target, status="error",
        message="fanbox rate limited", extra={"retry_after_seconds": retry_after},
    )
    db.commit()
    return HTTPException(
        status_code=429,
        detail=f"Fanbox rate limited; retry after {retry_after} seconds",
        headers={"Retry-After": str(retry_after)},
    )


def _queue_fanbox_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    *,
    session_factory: sessionmaker[Session],
    db: Session,
    principal: Principal,
    target: str,
    request: FanboxSyncRequest,
    targets: list[str] | None = None,
) -> dict[str, object]:
    if not request.session_id:
        raise FanboxAuthError(
            "a Fanbox session is required: post bodies are gated behind FANBOXSESSID. "
            "Save a session in the admin Fanbox panel, set [fanbox].session_id, or pass fanbox_session_id."
        )
    job_id = secrets.token_urlsafe(9).rstrip("=")
    log = _create_fanbox_log(
        db, principal=principal, target=target, status="queued", message="fanbox sync queued",
        extra={
            "sync_job_id": job_id, "stage": "queued", "progress": 0,
            "last_update_at": utc_now_iso(), "options": _fanbox_options_log(request),
        },
    )
    db.commit()
    thread = threading.Thread(
        target=_run_fanbox_sync_job,
        args=(storage, catalog, session_factory, principal, target, request, log.id, job_id, targets),
        daemon=True,
    )
    thread.start()
    return {
        "status": "queued", "sync_job_id": job_id, "message": "fanbox sync queued",
        "sync": [], "posts": [], "media": [], "jobs": [], "rebuild": None, "failures": [],
    }


def _run_fanbox_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    session_factory: sessionmaker[Session],
    principal: Principal,
    target: str,
    request: FanboxSyncRequest,
    log_id: int,
    job_id: str,
    targets: list[str] | None = None,
) -> None:
    started_at = time.monotonic()
    options = _fanbox_options_log(request)

    def update(status: str, message: str, extra: dict[str, object] | None = None) -> None:
        payload = {
            "sync_job_id": job_id,
            "last_update_at": utc_now_iso(),
            "duration_seconds": round(time.monotonic() - started_at, 1),
            **(extra or {}),
        }
        _commit_pixiv_log_update(
            session_factory, log_id, status=status, message=message,
            extra={key: value for key, value in payload.items() if value is not None},
        )

    def progress(event: dict[str, object]) -> None:
        update("running", str(event.get("message") or "fanbox sync running"), dict(event))

    try:
        update("running", "fetching fanbox posts", {"stage": "fetching_posts", "progress": 0, "options": options})
        client, downloader = _fanbox_sync_components(request)
        service = FanboxSyncService(
            storage,
            client=client,
            downloader=downloader,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
            storage_strategy_name=request.storage_strategy,
            download_media=request.download_media,
            download_files=request.download_files,
            download_concurrency=request.download_concurrency,
            name_media_by_post_id=bool(request.name_media_by_post_id),
            progress=progress,
        )
        if targets:
            batch = service.sync_posts(targets)
            results, failures = list(batch.results), list(batch.failures)
        else:
            results = service.sync_creator(
                target,
                limit=request.limit,
                backfill=request.backfill,
                page_size=request.page_size,
                max_pages=request.max_pages,
            )
            failures = []
        with session_factory() as session:
            _fanbox_sync_finish(
                storage, session, catalog, results,
                failures=failures, session_factory=session_factory, principal=principal,
                request=request, log_id=log_id,
                extra={"sync_job_id": job_id, "duration_seconds": round(time.monotonic() - started_at, 1)},
            )
    except FanboxRateLimitError as exc:
        retry_after = exc.retry_after_seconds or request.retry_base_seconds
        update("error", "fanbox rate limited", {"stage": "error", "retry_after_seconds": retry_after, "options": options})
    except Exception as exc:  # noqa: BLE001 - background job must record any failure
        update("error", str(exc), {"stage": "error", "options": options})


def _fanbox_sync_finish(
    storage: GalleryStorage,
    db: Session,
    catalog: TagCatalog,
    results: list[FanboxPostResult],
    *,
    failures: list,
    session_factory: sessionmaker[Session],
    principal: Principal,
    request: FanboxSyncRequest,
    log_id: int,
    extra: dict[str, object],
) -> None:
    assets = [asset for result in results for asset in result.assets]
    rebuild_result = rebuild_database(db, storage, catalog) if request.rebuild_db or request.generate_cache else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
    jobs: list[dict[str, object] | None] = []
    cache_tasks: list[tuple[GalleryStorage, sessionmaker[Session], TagCatalog, str, str]] = []
    if request.generate_cache:
        for asset_result in assets:
            if asset_result.status == "skipped" or asset_result.kind != "image":
                continue
            asset = db.get(AssetModel, asset_result.asset_key)
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
            job = create_transcode_job(db, asset, source="fanbox", file_size=_asset_original_size(storage, asset))
            jobs.append(transcode_job_to_dict(job))
            cache_tasks.append((storage, session_factory, catalog, asset.asset_key, job.job_id))
        db.commit()
        for task_args in cache_tasks:
            _schedule_background_task(None, _generate_cache_and_refresh_asset, *task_args)
    _update_pixiv_log(
        db, log_id, status="success", message="fanbox sync completed",
        extra={
            "stage": "done", "progress": 100,
            "sync_count": len(results), "post_count": len(results),
            "locked_posts": len([item for item in results if item.locked]),
            "asset_count": len(assets),
            "downloaded_assets": len([item for item in assets if item.status == "downloaded"]),
            "skipped_assets": len([item for item in assets if item.status == "skipped"]),
            "duplicate_assets": len([item for item in assets if item.status == "duplicate"]),
            "file_assets": len([item for item in assets if item.kind != "image"]),
            "asset_keys": _sync_asset_keys(item.asset_key for item in assets),
            "queued_transcode_jobs": len([job for job in jobs if job]),
            "failure_count": len(failures),
            "failures": [failure.to_dict() for failure in failures][:50],
            "rebuild": rebuild_result.__dict__ if rebuild_result else None,
            "options": _fanbox_options_log(request),
            "last_update_at": utc_now_iso(),
            **extra,
        },
    )
    db.commit()


class FanboxPlugin:
    manifest = PluginManifest("official.fanbox", "1.0.0", ("adapter",), permissions=('routes', 'events', 'read_assets', 'write_assets', 'network', 'credentials', 'read_config'))
    info = PluginInfo(title='FANBOX', description='FANBOX creator / post sync including attachments; sessions can be exchanged from a Pixiv cookie.', official=True, provides_sections=('fanbox',))

    def setup(self, ctx: PluginContext) -> None:
        state = ctx.app_state
        app = ctx._host.app  # official plugins share the app object (lifespan / state access)
        router = ctx.router()
        storage = state.storage
        catalog = state.catalog
        session_factory = state.session_factory

        @router.get("/api/sync/fanbox/config")
        def api_fanbox_config(request: Request, _principal: UploadPrincipal) -> dict[str, object]:
            state_config: NyaGalleryConfig = request.app.state.nyagallery.config
            return {
                "session_configured": bool(state_config.fanbox.session_id),
                "default_request_delay_seconds": state_config.fanbox.default_request_delay_seconds,
                "page_size": state_config.fanbox.page_size,
                "download_concurrency": state_config.fanbox.download_concurrency,
                "download_files": state_config.fanbox.download_files,
                "proxy_configured": bool(network_proxy_for(state_config, "fanbox")),
                "supports_pixiv_cookie_login": True,
                "storage_strategies": _storage_strategy_items(storage),
                "default_storage_strategy": storage.default_storage_strategy(),
                "note": (
                    "Post images and attachments are archived as regular gallery assets; title, body, tags and "
                    "like/comment counts become a post. Fanbox does not accept a Pixiv cookie directly, but a saved "
                    "Pixiv session can be exchanged for a FANBOXSESSID. Post bodies always require that session."
                ),
            }

        @router.get("/api/sync/fanbox/logs")
        def api_fanbox_logs(
            db: DbSession,
            principal: ViewPrincipal,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> dict[str, object]:
            logs = list_fanbox_logs(
                db,
                user_id=principal.user_id,
                is_admin="admin" in permissions_for_role(principal.role),
                limit=limit,
                offset=offset,
            )
            return {"items": attach_sync_log_assets(db, storage, logs, [upload_log_to_dict(log) for log in logs]), "limit": limit, "offset": offset}

        @router.post("/api/sync/fanbox/login")
        def api_fanbox_login(
            request: FanboxLoginRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            """Completes the Fanbox login chain from a Pixiv cookie and optionally stores the resulting session."""
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            cookie = (request.cookie or "").strip()
            if request.pixiv_cookie_id is not None:
                if not _is_admin_principal(principal) and not pixiv_cookie_belongs_to_user(
                    db, request.pixiv_cookie_id, principal.user_id
                ):
                    raise HTTPException(status_code=403, detail="permission denied")
                try:
                    cookie = get_pixiv_cookie(
                        db,
                        request.pixiv_cookie_id,
                        record_usage=True,
                        client_ip=client_ip(http_request, trust_proxy_headers=False),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                db.commit()
            cookie = cookie or (state_config.pixiv.cookie or "").strip()
            if not cookie:
                raise HTTPException(status_code=400, detail="a Pixiv session cookie is required to derive a Fanbox session")
            try:
                session_id = exchange_pixiv_cookie_for_fanbox_session(
                    cookie,
                    headless=request.headless,
                    timeout_seconds=request.timeout_seconds,
                    proxy_url=network_proxy_for(state_config, "fanbox") or network_proxy_for(state_config, "pixiv"),
                )
            except FanboxAuthError as exc:
                _create_fanbox_log(db, principal=principal, target="login", status="error", message=str(exc))
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            identity = _fanbox_session_identity(session_id, state_config)
            saved = None
            if request.save and principal.username:
                saved = save_fanbox_session(
                    db,
                    principal.username,
                    session_id,
                    label=request.label,
                    source="pixiv_cookie",
                    fanbox_user=identity,
                    created_by_user_id=principal.user_id,
                    created_by_username=principal.username,
                )
            _create_fanbox_log(
                db,
                principal=principal,
                target="login",
                status="success",
                message="fanbox session derived from pixiv cookie",
                extra={"saved": bool(saved), "identity": identity or None},
            )
            db.commit()
            return {
                "session_id": session_id if not request.save else "",
                "saved": fanbox_session_to_dict(saved) if saved is not None else None,
                "identity": identity,
            }

        @router.post("/api/sync/fanbox/creator/{creator_id}")
        def api_sync_fanbox_creator(
            creator_id: str,
            request: FanboxSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            handle = normalize_creator_id(creator_id)
            if not handle:
                raise HTTPException(status_code=400, detail="a valid Fanbox creator id is required")
            try:
                resolved = _resolve_fanbox_request(request, state_config, storage, db=db, principal=principal, http_request=http_request)
                if resolved.dry_run:
                    client, _downloader = _fanbox_sync_components(resolved)
                    creator = client.get_creator(handle)
                    posts = [
                        _fanbox_post_preview(post)
                        for post in client.iter_creator_posts(
                            handle, limit=resolved.limit or 20, page_size=resolved.page_size, max_pages=resolved.max_pages
                        )
                    ]
                    _create_fanbox_log(
                        db,
                        principal=principal,
                        target=handle,
                        status="success",
                        message="dry run completed",
                        extra={"posts": posts, "creator": _fanbox_creator_preview(creator), "options": _fanbox_options_log(resolved)},
                    )
                    db.commit()
                    return {
                        "sync": [], "posts": [], "media": [], "rebuild": None, "jobs": [],
                        "preview": posts, "creator": _fanbox_creator_preview(creator), "failures": [],
                    }
                return _queue_fanbox_sync_job(
                    storage, catalog, session_factory=session_factory, db=db,
                    principal=principal, target=handle, request=resolved,
                )
            except FanboxRateLimitError as exc:
                raise _fanbox_rate_limit_error(db, exc, principal=principal, target=handle, request=request)
            except (FanboxError, StorageError) as exc:
                _create_fanbox_log(db, principal=principal, target=handle, status="error", message=str(exc))
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/sync/fanbox/posts")
        def api_sync_fanbox_posts(
            request: FanboxSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            targets = _fanbox_batch_targets(request.targets)
            if not targets:
                raise HTTPException(status_code=400, detail="at least one Fanbox post URL or id is required")
            label = f"{len(targets)} posts"
            try:
                resolved = _resolve_fanbox_request(request, state_config, storage, db=db, principal=principal, http_request=http_request)
                if resolved.dry_run:
                    client, _downloader = _fanbox_sync_components(resolved)
                    previews = [_fanbox_post_preview(client.get_post(target)) for target in targets]
                    _create_fanbox_log(
                        db, principal=principal, target=label, status="success",
                        message="dry run completed",
                        extra={"posts": previews, "options": _fanbox_options_log(resolved)},
                    )
                    db.commit()
                    return {"sync": [], "posts": [], "media": [], "rebuild": None, "jobs": [], "preview": previews, "failures": []}
                return _queue_fanbox_sync_job(
                    storage, catalog, session_factory=session_factory, db=db,
                    principal=principal, target=label, request=resolved, targets=targets,
                )
            except FanboxRateLimitError as exc:
                raise _fanbox_rate_limit_error(db, exc, principal=principal, target=label, request=request)
            except (FanboxError, StorageError) as exc:
                _create_fanbox_log(db, principal=principal, target=label, status="error", message=str(exc))
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/users/{username}/fanbox-session")
        def api_save_user_fanbox_session(
            username: str,
            request: FanboxSessionCreate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                row = save_fanbox_session(
                    db, username, request.session_id,
                    label=request.label, source=request.source, fanbox_user=request.fanbox_user,
                    created_by_user_id=principal.user_id, created_by_username=principal.username,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return fanbox_session_to_dict(row)

        @router.get("/api/users/{username}/fanbox-sessions")
        def api_user_fanbox_sessions(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                rows = list_fanbox_sessions(db, username)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"items": [fanbox_session_to_dict(row) for row in rows]}

        @router.patch("/api/fanbox-sessions/{session_row_id}")
        def api_update_fanbox_session_label(
            session_row_id: int,
            request: FanboxSessionUpdate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            if not _is_admin_principal(principal) and not fanbox_session_belongs_to_user(db, session_row_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                row = update_fanbox_session_label(db, session_row_id, request.label)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return fanbox_session_to_dict(row)

        @router.delete("/api/fanbox-sessions/{session_row_id}")
        def api_revoke_fanbox_session(session_row_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            if not _is_admin_principal(principal) and not fanbox_session_belongs_to_user(db, session_row_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                row = revoke_fanbox_session(db, session_row_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return fanbox_session_to_dict(row)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = FanboxPlugin()
