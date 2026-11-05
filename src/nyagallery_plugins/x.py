"""Official plugin: X sync (moved out of nyagallery.app; URLs unchanged)."""

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
    load_config,
    network_proxy_for,
)
from nyagallery.db import (
    AssetModel,
    TranscodeJobModel,
    UploadLogModel,
    attach_sync_log_assets,
    create_transcode_job,
    create_upload_log,
    get_x_token,
    list_x_logs,
    list_x_tokens,
    rebuild_database,
    revoke_x_token,
    save_x_token,
    transcode_job_to_dict,
    update_x_token_label,
    upload_log_to_dict,
    x_token_belongs_to_user,
    x_token_to_dict,
)
from nyagallery.media import (
    MediaGenerator,
    media_limits_from_config,
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
from nyagallery.x import (
    XClient,
    XCredentials,
    XDownloader,
    XError,
    XGraphqlOperations,
    XRateLimitError,
    XRequestOptions,
    XSyncService,
    XTweet,
    XTweetResult,
    XUser,
    X_DEFAULT_HOST,
    normalize_screen_name,
    split_batch_input,
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


class XTokenCreate(BaseModel):
    token: str = Field(min_length=1, max_length=4000)
    ct0: str = ""
    label: str = ""
    host: str = "x.com"
    x_user: dict | None = None


class XTokenUpdate(BaseModel):
    label: str = ""


class XSyncRequest(BaseModel):
    make_public: bool = True
    name_media_by_post_id: bool | None = None
    auth_token: str | None = None
    ct0: str | None = None
    x_token_id: int | None = None
    targets: list[str] = Field(default_factory=list)
    proxy_url: str | None = None
    storage_strategy: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100_000)
    page_size: int = Field(default=20, ge=1, le=100)
    max_pages: int | None = Field(default=None, ge=1, le=10_000)
    include_replies: bool = True
    media_only: bool = False
    backfill: bool = True
    download_media: bool = True
    download_concurrency: int = Field(default=4, ge=1, le=16)
    request_delay_seconds: float = Field(default=2.0, ge=0, le=60)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: int = Field(default=60, ge=1, le=3600)
    retry_max_seconds: int = Field(default=300, ge=1, le=7200)
    rebuild_db: bool = True
    generate_cache: bool = True
    dry_run: bool = False


def _x_batch_targets(targets: list[str]) -> list[str]:
    """Accepts either a JSON list or one pasted blob of links, matching the batch endpoint of the resolver."""
    collected: list[str] = []
    for entry in targets:
        collected.extend(split_batch_input(entry))
    return list(dict.fromkeys(collected))


def _resolve_x_request(
    request: XSyncRequest,
    config: NyaGalleryConfig,
    storage: GalleryStorage,
    *,
    db: Session | None = None,
    principal: Principal | None = None,
    http_request: Request | None = None,
    require_session: bool = False,
) -> XSyncRequest:
    resolved = XSyncRequest(**_model_dump(request))
    if resolved.x_token_id is not None:
        if db is None or principal is None:
            raise XError("saved X sessions cannot be used in this context")
        if not _is_admin_principal(principal) and not x_token_belongs_to_user(db, resolved.x_token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            resolved.auth_token, saved_ct0, _host = get_x_token(
                db,
                resolved.x_token_id,
                record_usage=True,
                client_ip=client_ip(http_request, trust_proxy_headers=False) if http_request is not None else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        resolved.ct0 = resolved.ct0 or saved_ct0 or None
        db.commit()
    resolved.auth_token = (resolved.auth_token or config.x.auth_token or "").strip() or None
    resolved.ct0 = (resolved.ct0 or config.x.ct0 or "").strip() or None
    if require_session and not (resolved.auth_token and resolved.ct0):
        raise XError(
            "an X session is required to walk a timeline; save an auth_token/ct0 pair in the admin page "
            "or set [x].auth_token and [x].ct0"
        )
    if not resolved.proxy_url:
        resolved.proxy_url = network_proxy_for(config, "x") or None
    resolved.storage_strategy = storage.validate_storage_strategy(resolved.storage_strategy)
    if resolved.name_media_by_post_id is None:
        resolved.name_media_by_post_id = config.core.name_media_by_post_id
    return resolved


def _x_request_options(request: XSyncRequest) -> XRequestOptions:
    return XRequestOptions(
        request_delay_seconds=request.request_delay_seconds,
        max_retries=request.max_retries,
        retry_base_seconds=request.retry_base_seconds,
        retry_max_seconds=request.retry_max_seconds,
        download_concurrency=request.download_concurrency,
        proxy_url=request.proxy_url or "",
    )


def _x_sync_components(request: XSyncRequest, config: NyaGalleryConfig) -> tuple[XClient, XDownloader]:
    options = _x_request_options(request)
    client = XClient(
        credentials=XCredentials(auth_token=request.auth_token or "", ct0=request.ct0 or ""),
        options=options,
        operations=XGraphqlOperations(
            tweet_detail=config.x.tweet_detail_query_id,
            user_by_screen_name=config.x.user_by_screen_name_query_id,
            user_tweets=config.x.user_tweets_query_id,
            user_media=config.x.user_media_query_id,
        ),
        proxy_url=request.proxy_url,
    )
    return client, XDownloader(options=options, proxy_url=request.proxy_url)


def _x_options_log(request: XSyncRequest) -> dict[str, object]:
    return {
        "limit": request.limit,
        "page_size": request.page_size,
        "max_pages": request.max_pages,
        "include_replies": request.include_replies,
        "media_only": request.media_only,
        "backfill": request.backfill,
        "download_media": request.download_media,
        "download_concurrency": request.download_concurrency,
        "request_delay_seconds": request.request_delay_seconds,
        "storage_strategy": request.storage_strategy,
        "make_public": request.make_public,
        "rebuild_db": request.rebuild_db,
        "generate_cache": request.generate_cache,
        "session_configured": bool(request.auth_token and request.ct0),
        "proxy_configured": bool(request.proxy_url),
    }


def _x_user_preview(user: XUser) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "screen_name": user.screen_name,
        "name": user.display_name,
        "handle": user.handle,
        "avatar_url": user.avatar_url,
        "tweets_count": user.statuses_count,
        "media_count": user.media_count,
        "is_protected": user.is_protected,
    }


def _x_tweet_preview(tweet: XTweet) -> dict[str, object]:
    return {
        "tweet_id": tweet.tweet_id,
        "created_at": tweet.created_at,
        "text": tweet.text[:200],
        "screen_name": tweet.user.screen_name,
        "media_count": len(tweet.media),
        "media_types": sorted({media.media_type for media in tweet.media}),
        "url": tweet.url,
        "tags": list(tweet.tags),
        "metrics": dict(tweet.metrics),
    }


def _create_x_log(
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
        original_filename=f"x:{target}",
        file_size=None,
        mime_type=None,
        event="x_sync",
        status=status,
        message=message,
        extra={"target": target, "host": X_DEFAULT_HOST, **(extra or {})},
    )


def _x_rate_limit_error(
    db: Session,
    exc: XRateLimitError,
    *,
    principal: Principal,
    target: str,
    request: XSyncRequest,
) -> HTTPException:
    retry_after = exc.retry_after_seconds or request.retry_base_seconds
    _create_x_log(
        db,
        principal=principal,
        target=target,
        status="error",
        message="x rate limited",
        extra={"retry_after_seconds": retry_after},
    )
    db.commit()
    return HTTPException(
        status_code=429,
        detail=f"X rate limited; retry after {retry_after} seconds",
        headers={"Retry-After": str(retry_after)},
    )


def _queue_x_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    *,
    session_factory: sessionmaker[Session],
    db: Session,
    principal: Principal,
    target: str,
    request: XSyncRequest,
    targets: list[str] | None = None,
) -> dict[str, object]:
    job_id = secrets.token_urlsafe(9).rstrip("=")
    log = _create_x_log(
        db,
        principal=principal,
        target=target,
        status="queued",
        message="x sync queued",
        extra={
            "sync_job_id": job_id,
            "stage": "queued",
            "progress": 0,
            "last_update_at": utc_now_iso(),
            "options": _x_options_log(request),
        },
    )
    db.commit()
    thread = threading.Thread(
        target=_run_x_sync_job,
        args=(storage, catalog, session_factory, principal, target, request, log.id, job_id, targets),
        daemon=True,
    )
    thread.start()
    return {
        "status": "queued",
        "sync_job_id": job_id,
        "message": "x sync queued",
        "sync": [],
        "posts": [],
        "media": [],
        "jobs": [],
        "rebuild": None,
        "failures": [],
    }


def _run_x_sync_job(
    storage: GalleryStorage,
    catalog: TagCatalog,
    session_factory: sessionmaker[Session],
    principal: Principal,
    target: str,
    request: XSyncRequest,
    log_id: int,
    job_id: str,
    targets: list[str] | None = None,
) -> None:
    started_at = time.monotonic()
    options = _x_options_log(request)

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
        update("running", str(event.get("message") or "x sync running"), dict(event))

    try:
        update("running", "fetching x posts", {"stage": "fetching_posts", "progress": 0, "options": options})
        config: NyaGalleryConfig = load_config()
        client, downloader = _x_sync_components(request, config)
        media_limits = media_limits_from_config(config.media)
        generator = MediaGenerator(storage, limits=media_limits)
        service = XSyncService(
            storage,
            client=client,
            downloader=downloader,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
            storage_strategy_name=request.storage_strategy,
            download_media=request.download_media,
            download_concurrency=request.download_concurrency,
            name_media_by_post_id=bool(request.name_media_by_post_id),
            max_video_bytes=media_limits.max_video_bytes,
            cover_writer=generator.generate_from_cover,
            progress=progress,
        )
        if targets:
            batch = service.sync_posts(targets)
            results, failures = list(batch.results), list(batch.failures)
        else:
            results = service.sync_user(
                target,
                limit=request.limit,
                backfill=request.backfill,
                include_replies=request.include_replies,
                media_only=request.media_only,
                page_size=request.page_size,
                max_pages=request.max_pages,
            )
            failures = []
        with session_factory() as session:
            _x_sync_finish(
                storage,
                session,
                catalog,
                results,
                failures=failures,
                session_factory=session_factory,
                principal=principal,
                request=request,
                log_id=log_id,
                extra={
                    "sync_job_id": job_id,
                    "duration_seconds": round(time.monotonic() - started_at, 1),
                },
            )
    except XRateLimitError as exc:
        retry_after = exc.retry_after_seconds or request.retry_base_seconds
        update("error", "x rate limited", {"stage": "error", "retry_after_seconds": retry_after, "options": options})
    except Exception as exc:  # noqa: BLE001 - background job must record any failure
        update("error", str(exc), {"stage": "error", "options": options})


def _x_sync_finish(
    storage: GalleryStorage,
    db: Session,
    catalog: TagCatalog,
    results: list[XTweetResult],
    *,
    failures: list,
    session_factory: sessionmaker[Session],
    principal: Principal,
    request: XSyncRequest,
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
            if asset_result.status == "skipped" or not asset_result.needs_transcode:
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
            job = create_transcode_job(db, asset, source="x", file_size=_asset_original_size(storage, asset))
            jobs.append(transcode_job_to_dict(job))
            cache_tasks.append((storage, session_factory, catalog, asset.asset_key, job.job_id))
        db.commit()
        for task_args in cache_tasks:
            _schedule_background_task(None, _generate_cache_and_refresh_asset, *task_args)
    _update_pixiv_log(
        db,
        log_id,
        status="success",
        message="x sync completed",
        extra={
            "stage": "done",
            "progress": 100,
            "sync_count": len(results),
            "post_count": len(results),
            "asset_count": len(assets),
            "downloaded_assets": len([item for item in assets if item.status == "downloaded"]),
            "skipped_assets": len([item for item in assets if item.status == "skipped"]),
            "duplicate_assets": len([item for item in assets if item.status == "duplicate"]),
            "video_assets": len([item for item in assets if not item.needs_transcode]),
            "asset_keys": _sync_asset_keys(item.asset_key for item in assets),
            "queued_transcode_jobs": len([job for job in jobs if job]),
            "failure_count": len(failures),
            "failures": [failure.to_dict() for failure in failures][:50],
            "rebuild": rebuild_result.__dict__ if rebuild_result else None,
            "options": _x_options_log(request),
            "last_update_at": utc_now_iso(),
            **extra,
        },
    )
    db.commit()


class XPlugin:
    manifest = PluginManifest("official.x", "1.0.0", ("adapter",), permissions=('routes', 'events', 'read_assets', 'write_assets', 'network', 'credentials', 'read_config'))
    info = PluginInfo(title='X', description='X / Twitter post and user sync with saved auth_token / ct0 sessions.', official=True, provides_sections=('x',))

    def setup(self, ctx: PluginContext) -> None:
        state = ctx.app_state
        app = ctx._host.app  # official plugins share the app object (lifespan / state access)
        router = ctx.router()
        storage = state.storage
        catalog = state.catalog
        session_factory = state.session_factory

        @router.get("/api/sync/x/config")
        def api_x_config(request: Request, _principal: UploadPrincipal) -> dict[str, object]:
            state_config: NyaGalleryConfig = request.app.state.nyagallery.config
            return {
                "host": X_DEFAULT_HOST,
                "session_configured": bool(state_config.x.auth_token and state_config.x.ct0),
                "default_request_delay_seconds": state_config.x.default_request_delay_seconds,
                "page_size": state_config.x.page_size,
                "download_concurrency": state_config.x.download_concurrency,
                "proxy_configured": bool(network_proxy_for(state_config, "x")),
                "storage_strategies": _storage_strategy_items(storage),
                "default_storage_strategy": storage.default_storage_strategy(),
                "note": (
                    "Photos and videos are archived as regular gallery assets at original quality; post text, metrics "
                    "and tags are stored as posts and shown on the posts page. Single public posts resolve without "
                    "credentials; timeline sync needs a saved auth_token/ct0 session."
                ),
            }

        @router.get("/api/sync/x/logs")
        def api_x_logs(
            db: DbSession,
            principal: ViewPrincipal,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> dict[str, object]:
            logs = list_x_logs(
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

        @router.post("/api/sync/x/posts")
        def api_sync_x_posts(
            request: XSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            targets = _x_batch_targets(request.targets)
            if not targets:
                raise HTTPException(status_code=400, detail="at least one X post URL or id is required")
            try:
                resolved = _resolve_x_request(
                    request,
                    state_config,
                    storage,
                    db=db,
                    principal=principal,
                    http_request=http_request,
                    require_session=False,
                )
                if resolved.dry_run:
                    client, _downloader = _x_sync_components(resolved, state_config)
                    previews = [_x_tweet_preview(client.get_tweet(target)) for target in targets]
                    _create_x_log(
                        db,
                        principal=principal,
                        target=f"{len(targets)} posts",
                        status="success",
                        message="dry run completed",
                        extra={"tweets": previews, "options": _x_options_log(resolved)},
                    )
                    db.commit()
                    return {
                        "sync": [],
                        "posts": [],
                        "media": [],
                        "rebuild": None,
                        "jobs": [],
                        "preview": previews,
                        "failures": [],
                    }
                return _queue_x_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=f"{len(targets)} posts",
                    request=resolved,
                    targets=targets,
                )
            except XRateLimitError as exc:
                raise _x_rate_limit_error(db, exc, principal=principal, target=f"{len(targets)} posts", request=request)
            except (XError, StorageError) as exc:
                _create_x_log(db, principal=principal, target=f"{len(targets)} posts", status="error", message=str(exc))
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/sync/x/user/{screen_name}")
        def api_sync_x_user(
            screen_name: str,
            request: XSyncRequest,
            db: DbSession,
            principal: UploadPrincipal,
            http_request: Request,
        ) -> dict[str, object]:
            state_config: NyaGalleryConfig = http_request.app.state.nyagallery.config
            handle = normalize_screen_name(screen_name)
            if not handle:
                raise HTTPException(status_code=400, detail="a valid X username is required")
            try:
                resolved = _resolve_x_request(
                    request,
                    state_config,
                    storage,
                    db=db,
                    principal=principal,
                    http_request=http_request,
                    require_session=True,
                )
                if resolved.dry_run:
                    client, _downloader = _x_sync_components(resolved, state_config)
                    user = client.get_user(handle)
                    tweets = [
                        _x_tweet_preview(tweet)
                        for tweet in client.iter_user_tweets(
                            user.user_id,
                            limit=resolved.limit or 20,
                            media_only=resolved.media_only,
                            include_replies=resolved.include_replies,
                            page_size=resolved.page_size,
                            max_pages=resolved.max_pages,
                        )
                    ]
                    _create_x_log(
                        db,
                        principal=principal,
                        target=handle,
                        status="success",
                        message="dry run completed",
                        extra={"tweets": tweets, "user": _x_user_preview(user), "options": _x_options_log(resolved)},
                    )
                    db.commit()
                    return {
                        "sync": [],
                        "posts": [],
                        "media": [],
                        "rebuild": None,
                        "jobs": [],
                        "preview": tweets,
                        "user": _x_user_preview(user),
                        "failures": [],
                    }
                return _queue_x_sync_job(
                    storage,
                    catalog,
                    session_factory=session_factory,
                    db=db,
                    principal=principal,
                    target=handle,
                    request=resolved,
                )
            except XRateLimitError as exc:
                raise _x_rate_limit_error(db, exc, principal=principal, target=handle, request=request)
            except (XError, StorageError) as exc:
                _create_x_log(db, principal=principal, target=handle, status="error", message=str(exc))
                db.commit()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @router.post("/api/users/{username}/x-token")
        def api_save_user_x_token(
            username: str,
            request: XTokenCreate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                token = save_x_token(
                    db,
                    username,
                    request.token,
                    ct0=request.ct0,
                    label=request.label,
                    host=request.host or X_DEFAULT_HOST,
                    x_user=request.x_user,
                    created_by_user_id=principal.user_id,
                    created_by_username=principal.username,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return x_token_to_dict(token)

        @router.get("/api/users/{username}/x-tokens")
        def api_user_x_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            _require_self_or_admin(username, principal)
            try:
                tokens = list_x_tokens(db, username)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"items": [x_token_to_dict(token) for token in tokens]}

        @router.patch("/api/x-tokens/{token_id}")
        def api_update_x_token_label(
            token_id: int,
            request: XTokenUpdate,
            db: DbSession,
            principal: ApiPrincipal,
        ) -> dict[str, object]:
            if not _is_admin_principal(principal) and not x_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = update_x_token_label(db, token_id, request.label)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return x_token_to_dict(token)

        @router.delete("/api/x-tokens/{token_id}")
        def api_revoke_x_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
            if not _is_admin_principal(principal) and not x_token_belongs_to_user(db, token_id, principal.user_id):
                raise HTTPException(status_code=403, detail="permission denied")
            try:
                token = revoke_x_token(db, token_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return x_token_to_dict(token)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = XPlugin()
