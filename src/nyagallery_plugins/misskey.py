"""Official plugin: Misskey sync (moved out of nyagallery.app; URLs unchanged)."""

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
    get_misskey_token,
    list_misskey_logs,
    list_misskey_tokens,
    misskey_token_belongs_to_user,
    misskey_token_to_dict,
    rebuild_database,
    revoke_misskey_token,
    save_misskey_token,
    transcode_job_to_dict,
    update_misskey_token_label,
    upload_log_to_dict,
)
from nyagallery.metadata import (
    utc_now_iso,
)
from nyagallery.misskey import (
    MISSKEY_DEFAULT_HOST,
    MisskeyClient,
    MisskeyDownloader,
    MisskeyError,
    MisskeyNote,
    MisskeyNoteResult,
    MisskeyRateLimitError,
    MisskeyRequestOptions,
    MisskeySyncService,
    MisskeyUser,
    normalize_misskey_host,
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
    _set_synced_assets_public,
    _storage_strategy_items,
    _sync_asset_keys,
    _update_pixiv_log,
)


class MisskeyTokenCreate(BaseModel):
    token: str = Field(min_length=1, max_length=4000)
    label: str = ""
    host: str = "misskey.io"
    misskey_user: dict | None = None


class MisskeyTokenUpdate(BaseModel):
    label: str = ""


class MisskeySyncRequest(BaseModel):
    make_public: bool = True
    name_media_by_post_id: bool | None = None
    token: str | None = None
    misskey_token_id: int | None = None
    host: str | None = None
    proxy_url: str | None = None
    storage_strategy: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100_000)
    page_size: int = Field(default=100, ge=1, le=100)
    max_pages: int | None = Field(default=None, ge=1, le=10_000)
    include_replies: bool = True
    backfill: bool = True
    download_media: bool = True
    download_concurrency: int = Field(default=5, ge=1, le=16)
    request_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: int = Field(default=60, ge=1, le=3600)
    retry_max_seconds: int = Field(default=300, ge=1, le=7200)
    rebuild_db: bool = True
    generate_cache: bool = True
    dry_run: bool = False


def _resolve_misskey_request(
    request: MisskeySyncRequest,
    config: NyaGalleryConfig,
    storage: GalleryStorage,
    *,
    db: Session | None = None,
    principal: Principal | None = None,
    http_request: Request | None = None,
) -> MisskeySyncRequest:
    resolved = MisskeySyncRequest(**_model_dump(request))
    saved_host = ""
    if resolved.misskey_token_id is not None:
        if db is None or principal is None:
            raise MisskeyError("saved Misskey tokens cannot be used in this context")
        if not _is_admin_principal(principal) and not misskey_token_belongs_to_user(
            db, resolved.misskey_token_id, principal.user_id
        ):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            resolved.token, saved_host = get_misskey_token(
                db,
                resolved.misskey_token_id,
                record_usage=True,
                client_ip=client_ip(http_request, trust_proxy_headers=False) if http_request is not None else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
    resolved.token = (resolved.token or config.misskey.token or "").strip() or None
    if not resolved.token:
        raise MisskeyError("Misskey token is required; save one in the admin page or set [misskey].token")
    resolved.host = normalize_misskey_host(resolved.host or saved_host or config.misskey.host)
    if not resolved.proxy_url:
        resolved.proxy_url = network_proxy_for(config, "misskey") or None
    resolved.storage_strategy = storage.validate_storage_strategy(resolved.storage_strategy)
    if resolved.name_media_by_post_id is None:
        resolved.name_media_by_post_id = config.core.name_media_by_post_id
    return resolved


def _misskey_request_options(request: MisskeySyncRequest) -> MisskeyRequestOptions:
    return MisskeyRequestOptions(
        request_delay_seconds=request.request_delay_seconds,
        max_retries=request.max_retries,
        retry_base_seconds=request.retry_base_seconds,
        retry_max_seconds=request.retry_max_seconds,
        download_concurrency=request.download_concurrency,
        proxy_url=request.proxy_url or "",
    )


def _misskey_sync_components(request: MisskeySyncRequest) -> tuple[MisskeyClient, MisskeyDownloader]:
    options = _misskey_request_options(request)
    host = request.host or MISSKEY_DEFAULT_HOST
    client = MisskeyClient(token=request.token or "", host=host, options=options, proxy_url=request.proxy_url)
    downloader = MisskeyDownloader(host=host, options=options, proxy_url=request.proxy_url)
    return client, downloader


def _misskey_options_log(request: MisskeySyncRequest) -> dict[str, object]:
    return {
        "host": request.host,
        "limit": request.limit,
        "page_size": request.page_size,
        "max_pages": request.max_pages,
        "include_replies": request.include_replies,
        "backfill": request.backfill,
        "download_media": request.download_media,
        "download_concurrency": request.download_concurrency,
        "request_delay_seconds": request.request_delay_seconds,
        "storage_strategy": request.storage_strategy,
        "make_public": request.make_public,
        "rebuild_db": request.rebuild_db,
        "generate_cache": request.generate_cache,
        "proxy_configured": bool(request.proxy_url),
    }


def _misskey_user_preview(user: MisskeyUser) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "name": user.display_name,
        "handle": user.handle,
        "avatar_url": user.avatar_url,
        "notes_count": user.notes_count,
    }


def _misskey_note_preview(note: MisskeyNote) -> dict[str, object]:
    return {
        "note_id": note.note_id,
        "created_at": note.created_at,
        "text": note.text[:200],
        "cw": note.cw,
        "file_count": len(note.files),
        "url": note.url,
        "tags": list(note.tags),
    }


def _create_misskey_log(
    db: Session,
    *,
    principal: Principal,
    target: str,
    host: str,
    status: str,
    message: str,
    extra: dict[str, object] | None = None,
) -> UploadLogModel:
    return create_upload_log(
        db,
        asset_key=None,
        uploader_user_id=principal.user_id,
        uploader_username=principal.username,
        original_filename=f"misskey:{target}",
        file_size=None,
        mime_type=None,
        event="misskey_sync",
        status=status,
        message=message,
        extra={"target": target, "host": host, **(extra or {})},
    )


def _queue_misskey_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    *,
    session_factory: sessionmaker[Session],
    db: Session,
    principal: Principal,
    target: str,
    request: MisskeySyncRequest,
) -> dict[str, object]:
    job_id = secrets.token_urlsafe(9).rstrip("=")
    log = _create_misskey_log(
        db,
        principal=principal,
        target=target,
        host=request.host or "",
        status="queued",
        message="misskey sync queued",
        extra={
            "sync_job_id": job_id,
            "stage": "queued",
            "progress": 0,
            "last_update_at": utc_now_iso(),
            "options": _misskey_options_log(request),
        },
    )
    db.commit()
    thread = threading.Thread(
        target=_run_misskey_sync_job,
        args=(storage, catalog, session_factory, principal, target, request, log.id, job_id),
        daemon=True,
    )
    thread.start()
    return {
        "status": "queued",
        "sync_job_id": job_id,
        "message": "misskey sync queued",
        "sync": [],
        "posts": [],
        "media": [],
        "jobs": [],
        "rebuild": None,
    }


def _run_misskey_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    session_factory: sessionmaker[Session],
    principal: Principal,
    target: str,
    request: MisskeySyncRequest,
    log_id: int,
    job_id: str,
) -> None:
    started_at = time.monotonic()
    options = _misskey_options_log(request)

    def update(status: str, message: str, extra: dict[str, object] | None = None) -> None:
        payload = {
            "sync_job_id": job_id,
            "last_update_at": utc_now_iso(),
            "duration_seconds": round(time.monotonic() - started_at, 1),
            **(extra or {}),
        }
        _commit_pixiv_log_update(
            session_factory,
            log_id,
            status=status,
            message=message,
            extra={key: value for key, value in payload.items() if value is not None},
        )

    def progress(event: dict[str, object]) -> None:
        update("running", str(event.get("message") or "misskey sync running"), dict(event))

    try:
        update("running", "fetching misskey notes", {"stage": "fetching_notes", "progress": 0, "options": options})
        client, downloader = _misskey_sync_components(request)
        service = MisskeySyncService(
            storage,
            client=client,
            downloader=downloader,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
            storage_strategy_name=request.storage_strategy,
            download_media=request.download_media,
            download_concurrency=request.download_concurrency,
            name_media_by_post_id=bool(request.name_media_by_post_id),
            progress=progress,
        )
        results = service.sync_user(
            target,
            limit=request.limit,
            backfill=request.backfill,
            include_replies=request.include_replies,
            page_size=request.page_size,
            max_pages=request.max_pages,
        )
        with session_factory() as session:
            _misskey_sync_finish(
                storage,
                session,
                catalog,
                results,
                session_factory=session_factory,
                principal=principal,
                request=request,
                log_id=log_id,
                extra={
                    "sync_job_id": job_id,
                    "duration_seconds": round(time.monotonic() - started_at, 1),
                },
            )
    except MisskeyRateLimitError as exc:
        retry_after = exc.retry_after_seconds or request.retry_base_seconds
        update(
            "error",
            "misskey rate limited",
            {"stage": "error", "retry_after_seconds": retry_after, "options": options},
        )
    except Exception as exc:  # noqa: BLE001 - background job must record any failure
        update("error", str(exc), {"stage": "error", "options": options})


def _misskey_sync_finish(
    storage: GalleryStorage,
    db: Session,
    catalog: TagCatalog,
    results: list[MisskeyNoteResult],
    *,
    session_factory: sessionmaker[Session],
    principal: Principal,
    request: MisskeySyncRequest,
    log_id: int,
    extra: dict[str, object],
) -> None:
    assets = [asset for result in results for asset in result.assets]
    rebuild_result = rebuild_database(db, storage, catalog) if request.rebuild_db or request.generate_cache or request.make_public else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
    _set_synced_assets_public(db, (asset.asset_key for asset in assets), principal, request.make_public)
    jobs: list[dict[str, object] | None] = []
    cache_tasks: list[tuple[GalleryStorage, sessionmaker[Session], TagCatalog, str, str]] = []
    if request.generate_cache:
        for asset_result in assets:
            if asset_result.status == "skipped":
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
            job = create_transcode_job(db, asset, source="misskey", file_size=_asset_original_size(storage, asset))
            jobs.append(transcode_job_to_dict(job))
            cache_tasks.append((storage, session_factory, catalog, asset.asset_key, job.job_id))
        db.commit()
        for task_args in cache_tasks:
            _schedule_background_task(None, _generate_cache_and_refresh_asset, *task_args)
    _update_pixiv_log(
        db,
        log_id,
        status="success",
        message="misskey sync completed",
        extra={
            "stage": "done",
            "progress": 100,
            "sync_count": len(results),
            "post_count": len(results),
            "asset_count": len(assets),
            "downloaded_assets": len([item for item in assets if item.status == "downloaded"]),
            "skipped_assets": len([item for item in assets if item.status == "skipped"]),
            "duplicate_assets": len([item for item in assets if item.status == "duplicate"]),
            "asset_keys": _sync_asset_keys(item.asset_key for item in assets),
            "queued_transcode_jobs": len([job for job in jobs if job]),
            "rebuild": rebuild_result.__dict__ if rebuild_result else None,
            "options": _misskey_options_log(request),
            "last_update_at": utc_now_iso(),
            **extra,
        },
    )
    db.commit()


class MisskeyPlugin:
    manifest = PluginManifest("official.misskey", "1.0.0", ("adapter",), permissions=('routes', 'events', 'read_assets', 'write_assets', 'network', 'credentials', 'read_config'))
    info = PluginInfo(title='Misskey', description='Misskey user sync (media to the gallery, notes to posts) with saved access tokens.', official=True, provides_sections=('misskey',))

    def setup(self, ctx: PluginContext) -> None:
        state = ctx.app_state
        app = ctx._host.app  # official plugins share the app object (lifespan / state access)
        router = ctx.router()
        storage = state.storage
        catalog = state.catalog
        session_factory = state.session_factory

        @router.get("/api/sync/misskey/config")
        def api_misskey_config(request: Request, _principal: UploadPrincipal) -> dict[str, object]:
            state_config: NyaGalleryConfig = request.app.state.nyagallery.config
            return {
                "host": normalize_misskey_host(state_config.misskey.host),
                "token_configured": bool(state_config.misskey.token),
                "default_request_delay_seconds": state_config.misskey.default_request_delay_seconds,
                "page_size": state_config.misskey.page_size,
                "download_concurrency": state_config.misskey.download_concurrency,
                "proxy_configured": bool(network_proxy_for(state_config, "misskey")),
                "storage_strategies": _storage_strategy_items(storage),
                "default_storage_strategy": storage.default_storage_strategy(),
                "note": "Media is archived as regular gallery assets; note text is stored as posts and shown on the posts page.",
            }

        @router.get("/api/sync/misskey/logs")
        def api_misskey_logs(
            db: DbSession,
            principal: ViewPrincipal,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> dict[str, object]:
            logs = list_misskey_logs(
                db,
                user_id=principal.user_id,
                is_admin="admin" in permissions_for_role(principal.role),
                limit=limit,
                offset=offset,
            )
            return {
                "items": attach_sync_log_assets(db, storage, logs, [upload_log_to_dict(log) for log in logs]),
                "limit": limit,
                "offset": offset,
            }

        @router.post("/api/sync/misskey/user/{username}")
        def api_sync_misskey_user(
            username: str,
            request: MisskeySyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            try:
                resolved = _resolve_misskey_request(
                    request,
                    state_config,
                    storage,
                    db=db,
                    principal=principal,
                    http_request=http_request,
                )
                if resolved.dry_run:
                    client, _downloader = _misskey_sync_components(resolved)
                    user = client.get_user(username)
                    notes = []
                    for note in client.iter_user_notes(
                        user.user_id,
                        limit=resolved.limit or 20,
                        include_replies=resolved.include_replies,
                        page_size=resolved.page_size,
                        max_pages=resolved.max_pages,
                    ):
                        notes.append(_misskey_note_preview(note))
                    _create_misskey_log(
                        db,
                        principal=principal,
                        target=username,
                        host=resolved.host or "",
                        status="success",
                        message="dry run completed",
                        extra={"notes": notes, "user": _misskey_user_preview(user), "options": _misskey_options_log(resolved)},
                    )
                    db.commit()
                    return {
                        "sync": [],
                        "posts": [],
                        "media": [],
                        "rebuild": None,
                        "jobs": [],
                        "preview": notes,
                        "user": _misskey_user_preview(user),
                    }
                return _queue_misskey_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=username,
                    request=resolved,
                )
            except MisskeyRateLimitError as exc:
                retry_after = exc.retry_after_seconds or request.retry_base_seconds
                _create_misskey_log(
                    db,
                    principal=principal,
                    target=username,
                    host=request.host or state_config.misskey.host,
                    status="error",
                    message="misskey rate limited",
                    extra={"retry_after_seconds": retry_after},
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail=f"Misskey rate limited; retry after {retry_after} seconds",
                    headers={"Retry-After": str(retry_after)},
                ) from exc
            except (MisskeyError, StorageError) as exc:
                _create_misskey_log(
                    db,
                    principal=principal,
                    target=username,
                    host=request.host or state_config.misskey.host,
                    status="error",
                    message=str(exc),
                )
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/users/{username}/misskey-token")
        def api_save_user_misskey_token(
            username: str,
            request: MisskeyTokenCreate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                token = save_misskey_token(
                    db,
                    username,
                    request.token,
                    label=request.label,
                    host=normalize_misskey_host(request.host),
                    misskey_user=request.misskey_user,
                    created_by_user_id=principal.user_id,
                    created_by_username=principal.username,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404 if "user not found" in str(exc) else 400, detail=str(exc)) from exc
            return misskey_token_to_dict(token)

        @router.get("/api/users/{username}/misskey-tokens")
        def api_user_misskey_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                tokens = list_misskey_tokens(db, username)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"items": [misskey_token_to_dict(token) for token in tokens]}

        @router.patch("/api/misskey-tokens/{token_id}")
        def api_update_misskey_token_label(
            token_id: int,
            request: MisskeyTokenUpdate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            if not _is_admin_principal(principal) and not misskey_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = update_misskey_token_label(db, token_id, request.label)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return misskey_token_to_dict(token)

        @router.delete("/api/misskey-tokens/{token_id}")
        def api_revoke_misskey_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            if not _is_admin_principal(principal) and not misskey_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = revoke_misskey_token(db, token_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return misskey_token_to_dict(token)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = MisskeyPlugin()
