from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
import importlib.util
import io
import json
from pathlib import Path
import os
import secrets
import threading
import time
from typing import Annotated, Any
from urllib.parse import quote
import zipfile

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nyagallery.auth import Principal, permissions_for_role, validate_role
from nyagallery.config import (
    DEFAULT_CONFIG_FILENAME,
    NyaGalleryConfig,
    apply_config_environment,
    config_to_dict,
    load_config,
    network_proxy_for,
    read_config_file_data,
    save_config_file,
)
from nyagallery.db import (
    AssetModel,
    TranscodeJobModel,
    UploadLogModel,
    access_log_to_dict,
    any_users,
    api_token_belongs_to_user,
    api_token_to_dict,
    asset_to_dict,
    authenticate_api_token,
    authenticate_login_session,
    authenticate_user,
    backfill_source_tag_index,
    change_user_password,
    create_access_log,
    create_engine_for_url,
    create_login_session,
    create_transcode_job,
    create_upload_log,
    create_user,
    default_database_url,
    encrypt_stored_pixiv_credentials,
    init_database,
    issue_api_token,
    get_pixiv_refresh_token,
    get_pixiv_cookie,
    get_security_settings,
    list_access_logs,
    list_api_tokens,
    list_pixiv_cookies,
    list_pixiv_tokens,
    list_pixiv_logs,
    list_users,
    list_transcode_jobs,
    list_upload_history,
    list_upload_logs,
    make_session_factory,
    mark_asset_pending_cleanup,
    normalize_asset_sort,
    normalize_sort_order,
    now_utc,
    purge_pending_asset,
    random_asset,
    rebuild_database,
    revoke_api_token,
    revoke_pixiv_cookie,
    revoke_pixiv_token,
    revoke_login_session,
    search_assets,
    save_pixiv_cookie,
    save_pixiv_token,
    set_user_password,
    tag_summary,
    transcode_job_to_dict,
    pixiv_cookie_belongs_to_user,
    pixiv_cookie_to_dict,
    pixiv_token_belongs_to_user,
    pixiv_token_to_dict,
    upsert_asset,
    security_settings_to_dict,
    update_pixiv_cookie_label,
    update_pixiv_token_label,
    update_security_settings,
    update_transcode_job,
    upload_log_to_dict,
)
from nyagallery.metadata import GalleryMetadata, make_asset_key, parse_pixiv_filename, utc_now_iso
from nyagallery.media import MediaGenerator, is_animated_raster, probe_media_size
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
from nyagallery.redis_support import close_redis_client, create_redis_client, ping_redis_client
from nyagallery.security import (
    UNSAFE_METHODS,
    RedisSecurityLimiter,
    SecurityLimiter,
    client_ip,
    request_body_size,
    same_or_trusted_origin,
    viewer_api_allowed,
)
from nyagallery.secret_crypto import SecretEncryptionError, secret_encryption_enabled
from nyagallery.storage import GalleryStorage, OriginalAlreadyExistsError, StorageError
from nyagallery.storage import MetadataAlreadyExistsError, sha256_bytes
from nyagallery.tags import TagAlreadyExistsError, TagCatalog, TagNotFoundError, source_tag_details_from_extra


bearer = HTTPBearer(auto_error=False)
SENSITIVE_RATING_TAGS = frozenset({"rating:r18", "rating:r18g"})
SESSION_COOKIE = "nya_session"
CSRF_COOKIE = "nya_csrf"
CSRF_HEADER = "x-csrf-token"
OPERATION_LOG_PATHS_SKIP_MIDDLEWARE = frozenset({"/api/auth/login", "/api/login"})
ACCESS_LOG_QUIET_GET_PATHS = frozenset(
    {
        "/api/me",
        "/api/site/config",
        "/api/search",
        "/api/uploads/history",
        "/api/uploads/logs",
        "/api/transcode/jobs",
        "/api/tags/suggest",
        "/api/tags/catalog",
        "/api/tags/summary",
    }
)
ACCESS_LOG_QUIET_GET_PREFIXES = ("/api/assets/", "/api/img/")


@dataclass(frozen=True)
class AppState:
    storage: GalleryStorage
    catalog: TagCatalog
    engine: Engine
    session_factory: sessionmaker[Session]
    config: NyaGalleryConfig
    security_limiter: SecurityLimiter | RedisSecurityLimiter
    redis_client: Any | None
    pixiv_login_sessions: dict[str, dict[str, object]]
    pixiv_login_lock: threading.Lock


class TagsUpdate(BaseModel):
    canonical_tags: list[str] = Field(default_factory=list)


class TagAliasesUpdate(BaseModel):
    aliases: list[str] = Field(default_factory=list)


class TagLabelsUpdate(BaseModel):
    labels: dict[str, str] = Field(default_factory=dict)


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = True


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=1)


class TokenCreate(BaseModel):
    label: str = ""


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


class RebuildRequest(BaseModel):
    generate_cache: bool = False


class MediaRequest(BaseModel):
    asset_key: str | None = None


class PixivSyncRequest(BaseModel):
    auth_mode: str = "public"
    refresh_token: str | None = None
    pixiv_token_id: int | None = None
    cookie: str | None = None
    pixiv_cookie_id: int | None = None
    proxy_url: str | None = None
    storage_strategy: str | None = None
    public_first: bool = True
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


class SecuritySettingsUpdate(BaseModel):
    enabled: bool | None = None
    access_log_enabled: bool | None = None
    access_log_retention: int | None = Field(default=None, ge=0, le=200_000)
    max_global_concurrency: int | None = Field(default=None, ge=0, le=10_000)
    max_ip_concurrency: int | None = Field(default=None, ge=0, le=10_000)
    max_user_concurrency: int | None = Field(default=None, ge=0, le=10_000)
    ip_requests_per_minute: int | None = Field(default=None, ge=0, le=100_000)
    ip_bytes_per_minute: int | None = Field(default=None, ge=0)
    user_requests_per_minute: int | None = Field(default=None, ge=0, le=100_000)
    user_bytes_per_minute: int | None = Field(default=None, ge=0)
    viewer_requests_per_minute: int | None = Field(default=None, ge=0, le=100_000)
    max_upload_bytes: int | None = Field(default=None, ge=0)
    role_limits: dict[str, dict[str, int]] | None = None
    user_limits: dict[str, dict[str, int]] | None = None
    viewer_api_whitelist_enabled: bool | None = None
    viewer_api_whitelist: list[str] | None = None
    csrf_origin_check_enabled: bool | None = None
    trusted_origins: list[str] | None = None
    trust_proxy_headers: bool | None = None


class DeveloperConfigUpdate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class DeveloperPasswordResetRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    new_password: str = Field(min_length=1)


def create_app(
    *,
    storage_root: str | Path | None = None,
    database_url: str | None = None,
    tag_catalog_path: str | Path | None = None,
) -> FastAPI:
    config = load_config()
    if config.path and not config.security.secret_key:
        config = save_config_file(config_to_dict(config, redact_secrets=False), config.path)
    apply_config_environment(config)
    storage = GalleryStorage(
        storage_root or config.core.storage,
        default_strategy=config.original_storage.default_strategy,
        strategies=config.original_storage.strategies,
    )
    storage.ensure()
    catalog = _load_catalog(storage, tag_catalog_path or config.core.tag_catalog_path)
    engine = create_engine_for_url(database_url or config.core.database_url or default_database_url(storage))
    init_database(engine)
    session_factory = make_session_factory(engine)
    redis_client = create_redis_client(config.redis)
    security_limiter = (
        RedisSecurityLimiter(redis_client, key_prefix=config.redis.key_prefix)
        if redis_client is not None and config.redis.security_limiter
        else SecurityLimiter()
    )
    with session_factory() as session:
        source_tag_backfill = backfill_source_tag_index(session, catalog)
        encrypted_credentials = encrypt_stored_pixiv_credentials(session)
    if source_tag_backfill.tags or source_tag_backfill.labels:
        _save_catalog(storage, catalog)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await ping_redis_client(redis_client)
        try:
            yield
        finally:
            await close_redis_client(redis_client)
            engine.dispose()

    app = FastAPI(title="NyaGallery API", version="0.1.0", lifespan=lifespan)
    app.state.nyagallery = AppState(storage, catalog, engine, session_factory, config, security_limiter, redis_client, {}, threading.Lock())

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        return await _security_middleware(request, call_next)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "storage": str(storage.root),
            "redis": redis_client is not None,
            "redis_security_limiter": redis_client is not None and config.redis.security_limiter,
            "secret_encryption_enabled": secret_encryption_enabled(config.security.secret_key),
            "encrypted_pixiv_credentials": encrypted_credentials,
        }

    @app.get("/api/site/config")
    def api_site_config() -> dict[str, object]:
        return {
            "project_homepage": config.site.project_homepage,
            "repository": config.site.repository,
            "icp_beian": config.site.icp_beian or None,
        }

    @app.get("/api/storage/strategies")
    def api_storage_strategies(_principal: UploadPrincipal) -> dict[str, object]:
        return _storage_strategy_response(storage)

    @app.get("/api/me")
    def api_me(request: Request, principal: ViewPrincipal) -> dict[str, object]:
        return {
            "username": principal.username,
            "role": principal.role,
            "user_id": principal.user_id,
            "permissions": sorted(permissions_for_role(principal.role)),
            "auth_method": getattr(request.state, "nyagallery_auth_method", "guest"),
            "csrf_token": getattr(request.state, "nyagallery_csrf_token", None),
        }

    @app.post("/api/login")
    @app.post("/api/auth/login")
    def api_login(login: LoginRequest, request: Request, response: Response, db: DbSession) -> dict[str, object]:
        user = authenticate_user(db, login.username, login.password)
        if user is None:
            _write_operation_log(
                storage,
                request=request,
                identity={
                    "user_id": None,
                    "username": login.username.strip() or None,
                    "role": None,
                    "auth_method": "password",
                },
                client_ip_value=client_ip(request, trust_proxy_headers=False),
                status_code=401,
                action="login",
                detail="invalid username or password",
            )
            raise HTTPException(status_code=401, detail="invalid username or password")
        session_token, login_session = create_login_session(
            db,
            user,
            user_agent=request.headers.get("user-agent", ""),
            client_ip=client_ip(request, trust_proxy_headers=False),
            ttl_days=30 if login.remember else 1,
        )
        _set_session_cookies(response, session_token, login_session.csrf_token, remember=login.remember)
        _write_operation_log(
            storage,
            request=request,
            identity={
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "auth_method": "password",
            },
            client_ip_value=client_ip(request, trust_proxy_headers=False),
            status_code=200,
            action="login",
            detail="login success",
        )
        return {
            "username": user.username,
            "role": user.role,
            "user_id": user.id,
            "permissions": sorted(permissions_for_role(user.role)),
            "auth_method": "session",
            "csrf_token": login_session.csrf_token,
        }

    @app.post("/api/logout")
    @app.post("/api/auth/logout")
    def api_logout(request: Request, response: Response, db: DbSession) -> dict[str, object]:
        session_token = request.cookies.get(SESSION_COOKIE, "")
        if session_token:
            revoke_login_session(db, session_token)
        _clear_session_cookies(response)
        return {"ok": True}

    @app.post("/api/password")
    @app.post("/api/auth/password")
    def api_change_password(update: PasswordChangeRequest, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        try:
            user = change_user_password(db, principal.user_id, update.old_password, update.new_password)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "username": user.username}

    @app.get("/api/search")
    def api_search(
        db: DbSession,
        principal: ViewPrincipal,
        q: str = "",
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        sort: str = "asset_key",
        order: str = "asc",
    ) -> dict[str, object]:
        sort_key = normalize_asset_sort(sort)
        sort_order = normalize_sort_order(order)
        q = _query_with_guest_safety(q, principal)
        assets = search_assets(db, catalog, q, limit=limit, offset=offset, sort=sort_key, order=sort_order)
        return {
            "items": [asset_to_dict(asset, catalog) for asset in assets],
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
            "order": sort_order,
        }

    @app.get("/api/img/random")
    def api_random_image(
        db: DbSession,
        principal: ViewPrincipal,
        q: str | None = None,
        original: bool = False,
    ) -> FileResponse:
        q = _query_with_guest_safety(q or "", principal)
        asset = random_asset(db, catalog, q)
        if asset is None:
            raise HTTPException(status_code=404, detail="no matching asset")
        return _file_response(storage, asset, "original" if original else "preview")

    @app.get("/api/img/{tag}")
    def api_random_image_by_tag(
        tag: str,
        db: DbSession,
        principal: ViewPrincipal,
        original: bool = False,
    ) -> FileResponse:
        tag = _query_with_guest_safety(tag, principal)
        asset = random_asset(db, catalog, tag)
        if asset is None:
            raise HTTPException(status_code=404, detail="no matching asset")
        return _file_response(storage, asset, "original" if original else "preview")

    @app.get("/api/assets/{asset_key}")
    def api_asset(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_sensitive_view(asset, principal)
        return _asset_response(storage, asset, catalog)

    @app.get("/api/assets/{asset_key}/siblings")
    def api_asset_siblings(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_sensitive_view(asset, principal)
        statement = (
            select(AssetModel)
            .where(
                AssetModel.source == asset.source,
                AssetModel.source_id == asset.source_id,
                AssetModel.deletion_status.is_(None),
            )
            .order_by(
                AssetModel.page_index.is_(None).asc(),
                AssetModel.page_index.asc(),
                AssetModel.asset_key.asc(),
            )
        )
        siblings = [
            item
            for item in db.scalars(statement).all()
            if item.asset_key == asset.asset_key or _can_view_asset(item, principal)
        ]
        return {
            "items": [_asset_response(storage, item, catalog) for item in siblings],
            "current_asset_key": asset.asset_key,
            "source": asset.source,
            "source_id": asset.source_id,
            "count": len(siblings),
        }

    @app.delete("/api/assets/{asset_key}")
    def api_delete_asset(asset_key: str, db: DbSession, principal: DeleteRequestPrincipal) -> dict[str, object]:
        try:
            asset = mark_asset_pending_cleanup(
                db,
                storage,
                asset_key,
                deleted_by_user_id=principal.user_id,
                deleted_by_username=principal.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _asset_response(storage, asset, catalog)

    @app.delete("/api/assets/{asset_key}/cleanup")
    def api_cleanup_asset(asset_key: str, db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        try:
            return purge_pending_asset(db, storage, asset_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/assets/{asset_key}/original")
    def api_asset_original(asset_key: str, db: DbSession, _principal: DownloadPrincipal) -> FileResponse:
        return _file_response(storage, _get_asset(db, asset_key), "original")

    @app.get("/api/assets/{asset_key}/preview")
    def api_asset_preview(asset_key: str, db: DbSession, principal: ViewPrincipal) -> FileResponse:
        asset = _get_asset(db, asset_key)
        _require_sensitive_view(asset, principal)
        return _file_response(storage, asset, "preview")

    @app.get("/api/assets/{asset_key}/thumb")
    def api_asset_thumb(asset_key: str, db: DbSession, principal: ViewPrincipal) -> FileResponse:
        asset = _get_asset(db, asset_key)
        _require_sensitive_view(asset, principal)
        return _file_response(storage, asset, "thumb")

    @app.get("/api/tags/suggest")
    def api_tag_suggest(_principal: ViewPrincipal, q: str, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> dict[str, object]:
        return {"items": [tag.to_dict() for tag in catalog.suggest(q, limit=limit)]}

    @app.get("/api/tags/catalog")
    def api_tag_catalog(_principal: ViewPrincipal) -> dict[str, object]:
        return catalog.to_dict()

    @app.get("/api/tags/summary")
    def api_tag_summary(db: DbSession, _principal: ViewPrincipal) -> dict[str, object]:
        return tag_summary(db, catalog)

    @app.post("/api/tags/summary/export")
    def api_export_tag_summary(db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        summary = tag_summary(db, catalog)
        path = storage.tags_dir / "summary.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {"path": storage.cache_relative_path(path), "total": summary["total"]}

    @app.put("/api/tags/{tag_name}/aliases")
    def api_update_tag_aliases(
        tag_name: str,
        update: TagAliasesUpdate,
        _principal: AdminPrincipal,
    ) -> dict[str, object]:
        try:
            tag = catalog.set_aliases(tag_name, update.aliases)
        except (TagNotFoundError, TagAlreadyExistsError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_catalog(storage, catalog)
        return tag.to_dict()

    @app.put("/api/tags/{tag_name}/labels")
    def api_update_tag_labels(
        tag_name: str,
        update: TagLabelsUpdate,
        _principal: AdminPrincipal,
    ) -> dict[str, object]:
        try:
            tag = catalog.set_labels(tag_name, update.labels)
        except (TagNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _save_catalog(storage, catalog)
        return tag.to_dict()

    @app.post("/api/assets/{asset_key}/tags")
    def api_update_asset_tags(
        asset_key: str,
        update: TagsUpdate,
        db: DbSession,
        _principal: EditTagsPrincipal,
    ) -> dict[str, object]:
        metadata = storage.read_metadata(asset_key)
        try:
            canonical_tags = tuple(catalog.require(tag).name for tag in update.canonical_tags)
        except TagNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated = replace(metadata, canonical_tags=tuple(dict.fromkeys(canonical_tags)))
        storage.write_metadata(updated, replace=True)
        tags = catalog.canonicalize_tags(
            pixiv_tags=updated.pixiv_tags,
            source_tag_details=source_tag_details_from_extra(updated.extra),
            canonical_tags=updated.canonical_tags,
            source=updated.source,
            artist_name=updated.artist_name,
            uploader_username=updated.uploader_username,
            width=updated.width,
            height=updated.height,
            artwork_date=updated.artwork_date,
            source_type=updated.source_type,
            age_rating=updated.age_rating,
            is_ai_generated=updated.is_ai_generated,
            is_animated=updated.is_animated,
            mime_type=updated.mime_type,
        )
        asset = upsert_asset(db, storage, updated, tags)
        db.commit()
        _save_catalog(storage, catalog)
        return _asset_response(storage, asset, catalog)

    @app.post("/api/rebuild")
    def api_rebuild(request: RebuildRequest, db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        media_items = []
        if request.generate_cache:
            media_items = [item.__dict__ for item in MediaGenerator(storage).generate_all()]
        result = rebuild_database(db, storage, catalog)
        _save_catalog(storage, catalog)
        return {"assets": result.assets, "tags": result.tags, "duplicates": result.duplicates, "media": media_items}

    @app.post("/api/media/generate")
    def api_generate_media(request: MediaRequest, _db: DbSession, _principal: EditTagsPrincipal) -> dict[str, object]:
        generator = MediaGenerator(storage)
        if request.asset_key:
            return {"items": [generator.generate_for_asset_key(request.asset_key).__dict__]}
        return {"items": [item.__dict__ for item in generator.generate_all()]}

    @app.get("/api/uploads/history")
    def api_upload_history(
        db: DbSession,
        principal: ApiPrincipal,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        return {
            "items": list_upload_history(
                db,
                storage,
                user_id=principal.user_id,
                is_admin=_is_admin_principal(principal),
                limit=limit,
                offset=offset,
            ),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/uploads/logs")
    def api_upload_logs(
        db: DbSession,
        principal: ApiPrincipal,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        logs = list_upload_logs(
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
            "items": [upload_log_to_dict(log, storage=storage, asset=assets.get(log.asset_key or "")) for log in logs],
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/sync/pixiv/logs")
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
            "items": [upload_log_to_dict(log, storage=storage, asset=assets.get(log.asset_key or "")) for log in logs],
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/transcode/jobs")
    def api_transcode_jobs(
        db: DbSession,
        principal: ApiPrincipal,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        jobs = list_transcode_jobs(
            db,
            user_id=principal.user_id,
            is_admin=_is_admin_principal(principal),
            limit=limit,
            offset=offset,
        )
        return {"items": [transcode_job_to_dict(job) for job in jobs], "limit": limit, "offset": offset}

    @app.post("/api/transcode/cancel-all")
    def api_cancel_all_transcode(
        db: DbSession,
        _principal: UploadPrincipal,
    ) -> dict[str, object]:
        now = now_utc()
        rows = db.execute(
            select(TranscodeJobModel)
            .where(TranscodeJobModel.status.in_(("queued", "running")))
        ).scalars().all()
        count = len(rows)
        for job in rows:
            job.status = "error"
            job.error = "cancelled by user"
            job.stage = "cancelled"
            job.message = "cancelled by user"
            job.finished_at = now
            job.updated_at = now
        db.commit()
        return {"cancelled": count}

    @app.post("/api/transcode/assets/{asset_key}/start")
    def api_start_transcode(
        asset_key: str,
        background_tasks: BackgroundTasks,
        db: DbSession,
        principal: ApiPrincipal,
    ) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_owner_or_admin(asset, principal)
        existing = db.scalar(
            select(TranscodeJobModel)
            .where(
                TranscodeJobModel.asset_key == asset.asset_key,
                TranscodeJobModel.status.in_(("queued", "running")),
            )
            .order_by(TranscodeJobModel.id.desc())
        )
        if existing:
            return {"job": transcode_job_to_dict(existing), "status": "already_running"}

        job = create_transcode_job(db, asset, source="manual", file_size=_asset_original_size(storage, asset))
        create_upload_log(
            db,
            asset_key=asset.asset_key,
            uploader_user_id=asset.uploader_user_id,
            uploader_username=asset.uploader_username,
            original_filename=asset.original_filename,
            file_size=_asset_original_size(storage, asset),
            mime_type=asset.mime_type,
            event="transcode_request",
            status="queued",
            message=f"requested by {principal.username}",
            extra={"job_id": job.job_id},
        )
        db.commit()
        background_tasks.add_task(_generate_cache_and_refresh_asset, storage, session_factory, catalog, asset.asset_key, job.job_id)
        return {"job": transcode_job_to_dict(job), "status": "queued"}

    @app.get("/api/security/settings")
    def api_security_settings(db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        return security_settings_to_dict(db)

    @app.put("/api/security/settings")
    def api_update_security_settings(
        update: SecuritySettingsUpdate,
        db: DbSession,
        principal: AdminPrincipal,
    ) -> dict[str, object]:
        return update_security_settings(db, _model_dump(update), updated_by_username=principal.username)

    @app.get("/api/security/access-logs")
    def api_access_logs(
        db: DbSession,
        _principal: AdminPrincipal,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: str = "",
    ) -> dict[str, object]:
        logs = list_access_logs(db, limit=limit, offset=offset, q=q)
        return {
            "items": [access_log_to_dict(log) for log in logs],
            "limit": limit,
            "offset": offset,
            "q": q,
        }

    @app.get("/api/developer/config")
    def api_developer_config(request: Request, _principal: DeveloperPrincipal) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        if not state.config.developer.config_editor_enabled:
            raise HTTPException(status_code=403, detail="developer config editor is disabled")
        config_path = state.config.path or Path(DEFAULT_CONFIG_FILENAME)
        return {
            "path": str(config_path),
            "exists": config_path.exists(),
            "config": config_to_dict(state.config, redact_secrets=True),
            "secret_fields": [
                "security.secret_key",
                "pixiv.refresh_token",
                "pixiv.cookie",
                "network.proxies.password",
                "original_storage.strategies.password",
                "original_storage.strategies.token",
                "original_storage.strategies.access_key_secret",
            ],
            "restart_required": True,
            "message": "Saved config is written to TOML. Restart the backend to apply all runtime settings.",
        }

    @app.put("/api/developer/config")
    def api_update_developer_config(
        update: DeveloperConfigUpdate,
        request: Request,
        _principal: DeveloperPrincipal,
    ) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        if not state.config.developer.config_editor_enabled:
            raise HTTPException(status_code=403, detail="developer config editor is disabled")
        config_path = state.config.path or Path(DEFAULT_CONFIG_FILENAME)
        data = _developer_config_payload_with_preserved_secrets(update.config, config_path)
        try:
            saved = save_config_file(data, config_path)
            reloaded = load_config(config_path)
            apply_config_environment(reloaded)
            with state.session_factory() as db:
                encrypt_stored_pixiv_credentials(db)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.nyagallery = replace(state, config=reloaded)
        return {
            "path": str(saved.path or config_path),
            "exists": True,
            "config": config_to_dict(reloaded, redact_secrets=True),
            "secret_fields": [
                "security.secret_key",
                "pixiv.refresh_token",
                "pixiv.cookie",
                "network.proxies.password",
                "original_storage.strategies.password",
                "original_storage.strategies.token",
                "original_storage.strategies.access_key_secret",
            ],
            "restart_required": True,
            "message": "Config saved. Restart the backend to apply settings captured at startup.",
        }

    @app.get("/api/developer/console")
    def api_developer_console(request: Request, _principal: DeveloperPrincipal) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        return {
            "enabled": state.config.developer.console_enabled,
            "warning": "The web console is restricted to allowlisted maintenance actions.",
            "nodes": [
                {
                    "id": "local",
                    "label": "Local backend",
                    "status": "online",
                    "storage": str(state.storage.root),
                    "database_url": _redact_database_url(str(state.engine.url)),
                    "redis": state.redis_client is not None,
                    "config_path": str(state.config.path or Path(DEFAULT_CONFIG_FILENAME)),
                }
            ],
            "actions": ["reset_user_password"] if state.config.developer.console_enabled else [],
        }

    @app.post("/api/developer/console/reset-password")
    def api_developer_reset_password(
        update: DeveloperPasswordResetRequest,
        request: Request,
        db: DbSession,
        principal: DeveloperPrincipal,
    ) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        if not state.config.developer.console_enabled:
            raise HTTPException(status_code=403, detail="developer console is disabled")
        try:
            user = set_user_password(db, update.username, update.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _write_operation_log(
            state.storage,
            request=request,
            identity={
                "user_id": principal.user_id,
                "username": principal.username,
                "role": principal.role,
                "auth_method": getattr(request.state, "nyagallery_auth_method", None),
            },
            client_ip_value=client_ip(request, trust_proxy_headers=False),
            status_code=200,
            action="developer_password_reset",
            detail=f"target={user.username}",
        )
        return user_to_dict(user)

    @app.post("/api/upload")
    async def api_upload(
        background_tasks: BackgroundTasks,
        db: DbSession,
        principal: UploadPrincipal,
        file: UploadFile = File(...),
        title: str = Form(""),
        source_id: str | None = Form(None),
        artist_name: str = Form(""),
        canonical_tags: str = Form(""),
        tag_aliases: str = Form(""),
        generate_cache: bool = Form(False),
        storage_strategy: str | None = Form(None),
    ) -> dict[str, object]:
        content = await file.read()
        security_settings = get_security_settings(db)
        max_upload_bytes = int(security_settings.get("max_upload_bytes") or 0)
        if security_settings.get("enabled", True) and max_upload_bytes > 0 and len(content) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="request body too large")
        digest = sha256_bytes(content)
        upload_id = source_id or digest[:16]
        asset_key = make_asset_key("upload", upload_id)
        upload_filename = _safe_upload_filename(file.filename, f"{upload_id}.bin")
        upload_name_stem = Path(upload_filename).stem or upload_id
        parsed_filename = parse_pixiv_filename(upload_name_stem)
        extra = parsed_filename.to_extra() if parsed_filename else {}
        try:
            selected_storage_strategy = storage.validate_storage_strategy(storage_strategy)
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            stored = storage.write_original(
                asset_key,
                upload_filename,
                content,
                strategy_name=selected_storage_strategy,
                content_type=file.content_type,
            )
        except OriginalAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        width, height = probe_media_size(stored.path, mime_type=file.content_type)
        is_animated = _is_animated_upload(stored.path, file.content_type)
        try:
            alias_updates = _apply_tag_aliases(storage, catalog, tag_aliases)
        except (TagNotFoundError, TagAlreadyExistsError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            requested_tags = tuple(
                catalog.require(tag).name
                for tag in canonical_tags.split()
                if tag.strip()
            )
        except TagNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metadata = GalleryMetadata(
            source="upload",
            source_id=upload_id,
            title=title or (parsed_filename.title if parsed_filename else upload_name_stem),
            artist_id="",
            artist_name=artist_name,
            original_url="",
            crawl_time=utc_now_iso(),
            file_sha256=stored.sha256,
            original_filename=upload_name_stem,
            original_path=stored.relative_path,
            pixiv_tags=(),
            canonical_tags=tuple(dict.fromkeys(requested_tags)),
            mime_type=file.content_type,
            width=width,
            height=height,
            artwork_date=parsed_filename.artwork_date if parsed_filename else None,
            is_animated=is_animated,
            extra=extra,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
        )
        try:
            storage.write_metadata(metadata)
        except MetadataAlreadyExistsError:
            metadata = storage.read_metadata(asset_key)
        tags = catalog.canonicalize_tags(
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
        duplicate_of = db.scalar(
            select(AssetModel.asset_key).where(
                AssetModel.file_sha256 == metadata.file_sha256,
                AssetModel.asset_key != metadata.asset_key,
            )
        )
        asset = upsert_asset(db, storage, metadata, tags, duplicate_of=duplicate_of)
        job_id: str | None = None
        if generate_cache:
            job = create_transcode_job(db, asset, source="upload", file_size=stored.size)
            job_id = job.job_id
        create_upload_log(
            db,
            asset_key=asset.asset_key,
            uploader_user_id=principal.user_id,
            uploader_username=principal.username,
            original_filename=upload_filename,
            file_size=stored.size,
            mime_type=file.content_type,
            event="upload",
            status="success",
            message="duplicate upload" if duplicate_of else "uploaded",
            extra={
                "duplicate_of": duplicate_of,
                "transcode_job_id": job_id,
                "cache_status": "queued" if job_id else "missing",
                "has_preview_cache": False,
                "has_thumb_cache": False,
                "storage_strategy": stored.strategy,
            },
        )
        db.commit()
        _save_catalog(storage, catalog)
        response = _asset_response(storage, asset, catalog)
        if alias_updates:
            response["tag_aliases"] = alias_updates
        if job_id:
            background_tasks.add_task(_generate_cache_and_refresh_asset, storage, session_factory, catalog, metadata.asset_key, job_id)
            response["cache_status"] = "queued"
            response["transcode_job_id"] = job_id
        return response

    @app.get("/api/sync/pixiv/config")
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

    @app.get("/api/sync/pixiv/extension/download")
    def api_pixiv_extension_download(_principal: UploadPrincipal) -> StreamingResponse:
        return _pixiv_extension_zip_response()

    @app.post("/api/sync/pixiv/oauth/start")
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

    @app.post("/api/sync/pixiv/oauth/exchange")
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

    @app.post("/api/sync/pixiv/oauth/browser-login")
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

    @app.post("/api/sync/pixiv/oauth/visible/start")
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

    @app.get("/api/sync/pixiv/oauth/visible/{session_id}")
    def api_pixiv_oauth_visible_status(session_id: str, _principal: AdminPrincipal) -> dict[str, object]:
        with app.state.nyagallery.pixiv_login_lock:
            _prune_pixiv_login_sessions(app.state.nyagallery.pixiv_login_sessions)
            session = app.state.nyagallery.pixiv_login_sessions.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Pixiv login session not found")
            return _pixiv_login_session_public(session)

    @app.post("/api/sync/pixiv/session/exchange")
    @app.post("/api/pixiv/session/exchange")
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

    @app.post("/api/sync/pixiv/{pid}")
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

    @app.post("/api/sync/pixiv/user/{uid}")
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

    @app.post("/api/sync/pixiv/bookmarks/{uid}")
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

    @app.post("/api/users")
    def api_create_user(user: UserCreate, db: DbSession, principal: AdminPrincipal) -> dict[str, object]:
        role = validate_role(user.role)
        if role == "developer" and not _is_developer_principal(principal):
            raise HTTPException(status_code=403, detail="developer users can only be created by developer role or CLI")
        created = create_user(db, user.username, user.password, role)
        return {"id": created.id, "username": created.username, "role": created.role}

    @app.get("/api/users")
    def api_users(db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        return {"items": [user_to_dict(user) for user in list_users(db)]}

    @app.post("/api/users/{username}/password")
    def api_admin_reset_user_password(
        username: str,
        update: PasswordResetRequest,
        db: DbSession,
        principal: AdminPrincipal,
        http_request: Request,
    ) -> dict[str, object]:
        target = next(
            (
                user
                for user in list_users(db)
                if user.username.strip().casefold() == username.strip().casefold()
            ),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail=f"user not found: {username}")
        if _role_has_admin_permission(target.role):
            raise HTTPException(
                status_code=403,
                detail="privileged user password can only be changed by self or developer console",
            )
        try:
            updated = set_user_password(db, target.username, update.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _write_operation_log(
            storage,
            request=http_request,
            identity={
                "user_id": principal.user_id,
                "username": principal.username,
                "role": principal.role,
                "auth_method": getattr(http_request.state, "nyagallery_auth_method", None),
            },
            client_ip_value=client_ip(http_request, trust_proxy_headers=False),
            status_code=200,
            action="admin_password_reset",
            detail=f"target={updated.username}",
        )
        return user_to_dict(updated)

    @app.post("/api/users/{username}/token")
    def api_issue_token(
        username: str,
        db: DbSession,
        principal: ApiPrincipal,
        request: TokenCreate | None = None,
    ) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        token = issue_api_token(
            db,
            username,
            label=request.label if request else "",
            created_by_user_id=principal.user_id,
            created_by_username=principal.username,
        )
        return {"token": token}

    @app.get("/api/users/{username}/tokens")
    def api_user_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            tokens = list_api_tokens(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [api_token_to_dict(token) for token in tokens]}

    @app.delete("/api/tokens/{token_id}")
    def api_revoke_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not api_token_belongs_to_user(db, token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            token = revoke_api_token(db, token_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return api_token_to_dict(token)

    @app.post("/api/users/{username}/pixiv-token")
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

    @app.get("/api/users/{username}/pixiv-tokens")
    def api_user_pixiv_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            tokens = list_pixiv_tokens(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [pixiv_token_to_dict(token) for token in tokens]}

    @app.post("/api/users/{username}/pixiv-cookie")
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

    @app.get("/api/users/{username}/pixiv-cookies")
    def api_user_pixiv_cookies(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            cookies = list_pixiv_cookies(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [pixiv_cookie_to_dict(cookie) for cookie in cookies]}

    @app.patch("/api/pixiv-cookies/{cookie_id}")
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

    @app.delete("/api/pixiv-cookies/{cookie_id}")
    def api_revoke_pixiv_cookie(cookie_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not pixiv_cookie_belongs_to_user(db, cookie_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            cookie = revoke_pixiv_cookie(db, cookie_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return pixiv_cookie_to_dict(cookie)

    @app.patch("/api/pixiv-tokens/{token_id}")
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

    @app.delete("/api/pixiv-tokens/{token_id}")
    def api_revoke_pixiv_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not pixiv_token_belongs_to_user(db, token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            token = revoke_pixiv_token(db, token_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return pixiv_token_to_dict(token)

    return app


def _model_dump(model: BaseModel) -> dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return, union-attr]
    return model.dict()  # type: ignore[no-any-return]


def _storage_strategy_response(storage: GalleryStorage) -> dict[str, object]:
    return {
        "default_strategy": storage.default_storage_strategy(),
        "items": _storage_strategy_items(storage),
    }


def _storage_strategy_items(storage: GalleryStorage) -> list[dict[str, object]]:
    return [item.__dict__ for item in storage.storage_strategies()]


def _developer_config_payload_with_preserved_secrets(
    payload: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    data = {section: dict(value) for section, value in payload.items() if isinstance(value, dict)}
    file_data = read_config_file_data(config_path)
    file_security = file_data.get("security") if isinstance(file_data.get("security"), dict) else {}
    security = data.setdefault("security", {})
    if not str(security.get("secret_key") or "").strip():
        security["secret_key"] = str(file_security.get("secret_key") or "")
    file_pixiv = file_data.get("pixiv") if isinstance(file_data.get("pixiv"), dict) else {}
    pixiv = data.setdefault("pixiv", {})
    for key in ("refresh_token", "cookie"):
        value = pixiv.get(key)
        if value is None or str(value).strip() == "":
            pixiv[key] = str(file_pixiv.get(key) or "")
    file_network = file_data.get("network") if isinstance(file_data.get("network"), dict) else {}
    file_proxies = file_network.get("proxies") if isinstance(file_network.get("proxies"), list) else []
    saved_proxies_by_name = {
        str(item.get("name") or "").strip(): item
        for item in file_proxies
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    network = data.setdefault("network", {})
    proxies = network.get("proxies")
    if isinstance(proxies, list):
        for index, item in enumerate(proxies):
            if not isinstance(item, dict):
                continue
            saved = saved_proxies_by_name.get(str(item.get("name") or "").strip())
            if not saved and index < len(file_proxies) and isinstance(file_proxies[index], dict):
                saved = file_proxies[index]
            if not saved:
                continue
            if item.get("auth_enabled") is not True:
                continue
            value = item.get("password")
            if value is None or str(value).strip() == "":
                item["password"] = str(saved.get("password") or "")
    file_original_storage = file_data.get("original_storage") if isinstance(file_data.get("original_storage"), dict) else {}
    file_strategies = file_original_storage.get("strategies") if isinstance(file_original_storage.get("strategies"), list) else []
    saved_by_name = {
        str(item.get("name") or "").strip(): item
        for item in file_strategies
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    original_storage = data.setdefault("original_storage", {})
    strategies = original_storage.get("strategies")
    if isinstance(strategies, list):
        for item in strategies:
            if not isinstance(item, dict):
                continue
            saved = saved_by_name.get(str(item.get("name") or "").strip())
            if not saved:
                continue
            for key in ("password", "token", "access_key_secret"):
                value = item.get(key)
                if value is None or str(value).strip() == "":
                    item[key] = str(saved.get(key) or "")
    return data


def _redact_database_url(value: str) -> str:
    if "://" not in value or "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    _, host = rest.rsplit("@", 1)
    return f"{scheme}://***@{host}"


def _role_has_admin_permission(role: str) -> bool:
    return "admin" in permissions_for_role(role)


def _is_admin_principal(principal: Principal) -> bool:
    return _role_has_admin_permission(principal.role)


def _is_developer_principal(principal: Principal) -> bool:
    return "developer" in permissions_for_role(principal.role)


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


def _secure_cookies() -> bool:
    return os.environ.get("NYAGALLERY_SECURE_COOKIES", "").strip().lower() in {"1", "true", "yes", "on"}


def _set_session_cookies(response: Response, session_token: str, csrf_token: str, *, remember: bool) -> None:
    max_age = 30 * 24 * 60 * 60 if remember else 24 * 60 * 60
    common = {
        "path": "/",
        "max_age": max_age,
        "secure": _secure_cookies(),
        "samesite": "lax",
    }
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=_secure_cookies(), samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=_secure_cookies(), samesite="lax")


def _load_catalog(storage: GalleryStorage, tag_catalog_path: str | Path | None) -> TagCatalog:
    path = Path(tag_catalog_path) if tag_catalog_path else storage.tags_dir / "catalog.json"
    return TagCatalog.load(path) if path.exists() else TagCatalog.default()


def _save_catalog(storage: GalleryStorage, catalog: TagCatalog) -> None:
    catalog.save(storage.tags_dir / "catalog.json")


def _apply_tag_aliases(storage: GalleryStorage, catalog: TagCatalog, raw: str) -> dict[str, list[str]]:
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("tag_aliases must be a JSON object")
    applied: dict[str, list[str]] = {}
    for tag_name, aliases in data.items():
        if isinstance(aliases, str):
            alias_list = [aliases]
        elif isinstance(aliases, list):
            alias_list = [str(alias) for alias in aliases]
        else:
            raise ValueError(f"aliases for {tag_name} must be a string or list")
        tag = catalog.add_aliases(str(tag_name), tuple(alias_list))
        applied[tag.name] = sorted(tag.aliases)
    if applied:
        _save_catalog(storage, catalog)
    return applied


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


def _commit_pixiv_log_update(
    session_factory: sessionmaker[Session],
    log_id: int,
    *,
    status: str,
    message: str,
    extra: dict[str, object],
) -> None:
    with session_factory() as session:
        _update_pixiv_log(session, log_id, status=status, message=message, extra=extra)
        session.commit()


def _update_pixiv_log(
    db: Session,
    log_id: int,
    *,
    status: str | None = None,
    message: str | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    log = db.get(UploadLogModel, log_id)
    if log is None:
        return
    if status is not None:
        log.status = status
    if message is not None:
        log.message = _clip_log_text(message)
    if extra:
        current = dict(log.extra or {})
        current.update(extra)
        log.extra = current
    db.flush()


def _schedule_background_task(background_tasks: BackgroundTasks | None, func, *args) -> None:
    if background_tasks is not None:
        background_tasks.add_task(func, *args)
        return
    thread = threading.Thread(target=func, args=args, daemon=True)
    thread.start()


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


def _clip_log_text(value: str, limit: int = 500) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[: max(0, limit - 3)]}..."


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
    rebuild_result = rebuild_database(db, storage, catalog) if rebuild_db or generate_cache else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
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
    }


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


def _generate_cache_and_refresh_asset(
    storage: GalleryStorage,
    session_factory: sessionmaker[Session],
    catalog: TagCatalog,
    asset_key: str,
    job_id: str,
) -> None:
    def report(payload: dict[str, object]) -> None:
        with session_factory() as session:
            update_transcode_job(session, job_id, status="running", **payload)
            session.commit()

    try:
        metadata = storage.read_metadata(asset_key)
        with session_factory() as session:
            update_transcode_job(
                session,
                job_id,
                status="running",
                stage="starting",
                progress=0.0,
                message="starting media cache generation",
            )
            session.commit()
        generated = MediaGenerator(storage).generate_for_metadata(metadata, progress=report)
        metadata = storage.read_metadata(asset_key)
        tags = catalog.canonicalize_tags(
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
        with session_factory() as session:
            existing = session.get(AssetModel, metadata.asset_key)
            duplicate_of = existing.duplicate_of if existing else None
            if duplicate_of is None:
                duplicate_of = session.scalar(
                    select(AssetModel.asset_key).where(
                        AssetModel.file_sha256 == metadata.file_sha256,
                        AssetModel.asset_key != metadata.asset_key,
                    )
            )
            upsert_asset(session, storage, metadata, tags, duplicate_of=duplicate_of)
            update_transcode_job(
                session,
                job_id,
                status="success",
                stage="done",
                progress=100.0,
                kind=generated.kind,
                message="media cache generated",
            )
            create_upload_log(
                session,
                asset_key=metadata.asset_key,
                uploader_user_id=metadata.uploader_user_id,
                uploader_username=metadata.uploader_username,
                original_filename=metadata.original_filename,
                file_size=None,
                mime_type=metadata.mime_type,
                event="transcode",
                status="success",
                message=f"generated {generated.kind} preview",
                extra={"job_id": job_id},
            )
            session.commit()
        _save_catalog(storage, catalog)
    except Exception as exc:
        with session_factory() as session:
            failed_job = update_transcode_job(
                session,
                job_id,
                status="error",
                stage="error",
                progress=0.0,
                message="media cache generation failed",
                error=str(exc),
            )
            create_upload_log(
                session,
                asset_key=asset_key,
                uploader_user_id=failed_job.uploader_user_id if failed_job else None,
                uploader_username=failed_job.uploader_username if failed_job else None,
                original_filename="",
                file_size=None,
                mime_type=None,
                event="transcode",
                status="error",
                message=str(exc),
                extra={"job_id": job_id},
            )
            session.commit()
        print(f"failed to generate cache for {asset_key}: {exc}")


async def _security_middleware(request: Request, call_next):
    state: AppState = request.app.state.nyagallery
    started = time.perf_counter()
    response = None
    status_code = 500
    rejection_reason: str | None = None
    error: str | None = None
    lease = None
    identity: dict[str, object] = {"user_id": None, "username": None, "role": "guest"}

    with state.session_factory() as session:
        settings = get_security_settings(session)
        ip = client_ip(request, trust_proxy_headers=bool(settings.get("trust_proxy_headers")))
        identity = _request_identity(request, session, client_ip_value=ip)
        session.commit()
    _attach_request_identity(request, identity)

    request_bytes = request_body_size(request)

    try:
        if settings.get("enabled", True):
            rejection_reason = _security_rejection_reason(request, settings, identity, request_bytes)
            if rejection_reason:
                status_code = _security_rejection_status(rejection_reason)
                response = JSONResponse({"detail": rejection_reason}, status_code=status_code)
            else:
                lease = await state.security_limiter.acquire(
                    settings,
                    ip=ip,
                    user_key=_identity_rate_key(identity),
                    username=str(identity.get("username") or ""),
                    role=str(identity.get("role") or ""),
                    request_bytes=request_bytes,
                )
                if not lease.allowed:
                    rejection_reason = lease.reason or "rate limit exceeded"
                    status_code = 429
                    response = JSONResponse({"detail": rejection_reason}, status_code=429)
                    response.headers["Retry-After"] = "60"
                    response.headers["X-RateLimit-Reason"] = rejection_reason
                else:
                    response = await call_next(request)
                    status_code = response.status_code
        else:
            response = await call_next(request)
            status_code = response.status_code
        return _add_security_headers(response)
    except Exception as exc:
        error = str(exc)
        status_code = 500
        raise
    finally:
        if lease is not None and lease.allowed:
            await state.security_limiter.release(lease)
        duration_ms = (time.perf_counter() - started) * 1000
        _record_access_log(
            state,
            settings=settings,
            request=request,
            identity=identity,
            client_ip_value=ip,
            status_code=status_code,
            duration_ms=duration_ms,
            request_bytes=request_bytes,
            response_bytes=_response_size(response),
            rejection_reason=rejection_reason,
            error=error,
        )
        _record_operation_log(
            state,
            request=request,
            identity=identity,
            client_ip_value=ip,
            status_code=status_code,
            rejection_reason=rejection_reason,
            error=error,
        )


def _request_identity(request: Request, db: Session, *, client_ip_value: str) -> dict[str, object]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        user = authenticate_api_token(db, token.strip(), record_usage=True, client_ip=client_ip_value)
        if user is None:
            return {"user_id": None, "username": None, "role": None, "auth_method": "bearer"}
        return {"user_id": user.id, "username": user.username, "role": user.role, "auth_method": "bearer"}

    session_token = request.cookies.get(SESSION_COOKIE, "")
    authenticated = authenticate_login_session(db, session_token)
    if authenticated:
        user, login_session = authenticated
        return {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "auth_method": "session",
            "csrf_token": login_session.csrf_token,
        }
    return {"user_id": None, "username": None, "role": "guest", "auth_method": "guest"}


def _attach_request_identity(request: Request, identity: dict[str, object]) -> None:
    request.state.nyagallery_auth_method = identity.get("auth_method") or "guest"
    request.state.nyagallery_user_id = identity.get("user_id")
    request.state.nyagallery_username = identity.get("username")
    request.state.nyagallery_role = identity.get("role")
    request.state.nyagallery_csrf_token = identity.get("csrf_token")


def _security_rejection_reason(
    request: Request,
    settings: dict[str, object],
    identity: dict[str, object],
    request_bytes: int,
) -> str | None:
    if request.method.upper() in UNSAFE_METHODS:
        max_upload_bytes = int(settings.get("max_upload_bytes") or 0)
        if max_upload_bytes > 0 and request_bytes > max_upload_bytes:
            return "request body too large"
        if identity.get("auth_method") == "session" and request.url.path not in {"/api/auth/login", "/api/login"}:
            expected = str(identity.get("csrf_token") or "")
            actual = request.headers.get(CSRF_HEADER, "")
            if not expected or not secrets.compare_digest(actual, expected):
                return "csrf token invalid"
        if (
            settings.get("csrf_origin_check_enabled", True)
            and identity.get("auth_method") != "session"
            and request.url.path not in {"/api/auth/login", "/api/login"}
        ):
            trusted = [str(item) for item in settings.get("trusted_origins", []) if str(item).strip()]
            if not same_or_trusted_origin(request, trusted):
                return "csrf origin denied"

    role = identity.get("role")
    if (
        role == "viewer"
        and settings.get("viewer_api_whitelist_enabled", True)
        and request.url.path.startswith("/api/")
    ):
        whitelist = [str(item) for item in settings.get("viewer_api_whitelist", [])]
        if not viewer_api_allowed(request.method, request.url.path, whitelist):
            return "viewer API path is not whitelisted"
    return None


def _security_rejection_status(reason: str) -> int:
    if reason == "request body too large":
        return 413
    if reason in {"csrf origin denied", "csrf token invalid", "viewer API path is not whitelisted"}:
        return 403
    return 429


def _identity_rate_key(identity: dict[str, object]) -> str | None:
    user_id = identity.get("user_id")
    if user_id is not None:
        return f"user:{user_id}"
    return None


def user_to_dict(user) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


def _add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


def _response_size(response) -> int | None:
    if response is None:
        return None
    raw = response.headers.get("content-length")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    body = getattr(response, "body", None)
    return len(body) if isinstance(body, (bytes, bytearray)) else None


def _record_access_log(
    state: AppState,
    *,
    settings: dict[str, object],
    request: Request,
    identity: dict[str, object],
    client_ip_value: str,
    status_code: int,
    duration_ms: float,
    request_bytes: int,
    response_bytes: int | None,
    rejection_reason: str | None,
    error: str | None,
) -> None:
    if not settings.get("access_log_enabled", True):
        return
    if not _should_record_access_log(request, status_code=status_code, rejection_reason=rejection_reason, error=error):
        return
    try:
        with state.session_factory() as session:
            create_access_log(
                session,
                client_ip=client_ip_value,
                user_id=identity.get("user_id") if isinstance(identity.get("user_id"), int) else None,
                username=str(identity.get("username")) if identity.get("username") else None,
                role=str(identity.get("role")) if identity.get("role") else None,
                method=request.method.upper(),
                path=request.url.path,
                query_string=request.url.query,
                status_code=status_code,
                duration_ms=duration_ms,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                user_agent=request.headers.get("user-agent", ""),
                referer=request.headers.get("referer", ""),
                origin=request.headers.get("origin", ""),
                rejection_reason=rejection_reason,
                error=error,
                retention=int(settings.get("access_log_retention") or 5000),
            )
            session.commit()
    except Exception as exc:
        print(f"failed to record access log: {exc}")


def _should_record_access_log(
    request: Request,
    *,
    status_code: int,
    rejection_reason: str | None,
    error: str | None,
) -> bool:
    if rejection_reason or error or status_code >= 400:
        return True
    method = request.method.upper()
    if method in UNSAFE_METHODS:
        return True
    if method not in {"GET", "HEAD"}:
        return True
    path = request.url.path
    if path in ACCESS_LOG_QUIET_GET_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in ACCESS_LOG_QUIET_GET_PREFIXES)


def _record_operation_log(
    state: AppState,
    *,
    request: Request,
    identity: dict[str, object],
    client_ip_value: str,
    status_code: int,
    rejection_reason: str | None,
    error: str | None,
) -> None:
    if request.url.path in OPERATION_LOG_PATHS_SKIP_MIDDLEWARE:
        return
    if not _should_record_operation_log(request, status_code=status_code, rejection_reason=rejection_reason, error=error):
        return
    _write_operation_log(
        state.storage,
        request=request,
        identity=identity,
        client_ip_value=client_ip_value,
        status_code=status_code,
        action="http_request",
        detail=rejection_reason or error,
    )


def _should_record_operation_log(
    request: Request,
    *,
    status_code: int,
    rejection_reason: str | None,
    error: str | None,
) -> bool:
    if not request.url.path.startswith("/api/"):
        return False
    if request.method.upper() in UNSAFE_METHODS:
        return True
    return bool(rejection_reason or error or status_code >= 400)


def _write_operation_log(
    storage: GalleryStorage,
    *,
    request: Request,
    identity: dict[str, object],
    client_ip_value: str,
    status_code: int,
    action: str,
    detail: str | None = None,
) -> None:
    try:
        path = storage.root / "logs" / "operations.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": utc_now_iso(),
            "action": action,
            "method": request.method.upper(),
            "path": request.url.path,
            "query_string": request.url.query,
            "status_code": status_code,
            "client_ip": client_ip_value,
            "user_id": identity.get("user_id") if isinstance(identity.get("user_id"), int) else None,
            "username": str(identity.get("username")) if identity.get("username") else None,
            "role": str(identity.get("role")) if identity.get("role") else None,
            "auth_method": str(identity.get("auth_method")) if identity.get("auth_method") else None,
            "user_agent": request.headers.get("user-agent", "")[:1000],
            "detail": detail[:1000] if detail else None,
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        print(f"failed to write operation log: {exc}")


def get_db(request: Request) -> Iterator[Session]:
    state: AppState = request.app.state.nyagallery
    with state.session_factory() as session:
        yield session


def _principal_from_state(request: Request) -> Principal | None:
    username = getattr(request.state, "nyagallery_username", None)
    role = getattr(request.state, "nyagallery_role", None)
    if not username or not role or role == "guest":
        return None
    user_id = getattr(request.state, "nyagallery_user_id", None)
    return Principal(str(username), str(role), user_id if isinstance(user_id, int) else None)


def _require_self_or_admin(username: str, principal: Principal) -> None:
    if _is_admin_principal(principal):
        return
    if username.strip().casefold() == principal.username.strip().casefold():
        return
    raise HTTPException(status_code=403, detail="permission denied")


def require_permission(permission: str):
    def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        db: Session = Depends(get_db),
    ) -> Principal:
        state_principal = _principal_from_state(request)
        state_auth_method = getattr(request.state, "nyagallery_auth_method", None)
        if credentials:
            if state_auth_method == "bearer" and state_principal:
                if permission in permissions_for_role(state_principal.role):
                    return state_principal
                raise HTTPException(status_code=403, detail="permission denied")
            user = authenticate_api_token(db, credentials.credentials)
            if user and permission in permissions_for_role(user.role):
                return Principal(user.username, user.role, user.id)
            raise HTTPException(status_code=403, detail="permission denied")

        session_token = request.cookies.get(SESSION_COOKIE, "")
        if session_token:
            if state_auth_method == "session" and state_principal:
                if permission in permissions_for_role(state_principal.role):
                    return state_principal
                raise HTTPException(status_code=403, detail="permission denied")
            authenticated = authenticate_login_session(db, session_token)
            if authenticated:
                user, login_session = authenticated
                request.state.nyagallery_auth_method = "session"
                request.state.nyagallery_csrf_token = login_session.csrf_token
                if permission in permissions_for_role(user.role):
                    return Principal(user.username, user.role, user.id)
                raise HTTPException(status_code=403, detail="permission denied")

        if permission in permissions_for_role("guest"):
            return Principal("guest", "guest")
        if not any_users(db):
            return Principal("bootstrap-admin", "admin")
        raise HTTPException(status_code=401, detail="login required")

    return dependency


DbSession = Annotated[Session, Depends(get_db)]
ApiPrincipal = Annotated[Principal, Depends(require_permission("api"))]
ViewPrincipal = Annotated[Principal, Depends(require_permission("view"))]
DownloadPrincipal = Annotated[Principal, Depends(require_permission("download"))]
EditTagsPrincipal = Annotated[Principal, Depends(require_permission("edit_tags"))]
UploadPrincipal = Annotated[Principal, Depends(require_permission("upload"))]
DeleteRequestPrincipal = Annotated[Principal, Depends(require_permission("delete_request"))]
AdminPrincipal = Annotated[Principal, Depends(require_permission("admin"))]
DeveloperPrincipal = Annotated[Principal, Depends(require_permission("developer"))]


def _get_asset(db: Session, asset_key: str) -> AssetModel:
    asset = db.get(AssetModel, asset_key)
    if asset is None or asset.deletion_status is not None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


def _require_asset_owner_or_admin(asset: AssetModel, principal: Principal) -> None:
    if _is_admin_principal(principal):
        return
    if principal.user_id is not None and asset.uploader_user_id == principal.user_id:
        return
    raise HTTPException(status_code=403, detail="permission denied")


def _query_with_guest_safety(query: str, principal: Principal) -> str:
    if principal.role != "guest":
        return query
    parts = [query.strip()] if query.strip() else []
    parts.extend(f"-{tag}" for tag in sorted(SENSITIVE_RATING_TAGS))
    return " ".join(parts)


def _require_sensitive_view(asset: AssetModel, principal: Principal) -> None:
    if principal.role != "guest":
        return
    if any(tag.tag in SENSITIVE_RATING_TAGS for tag in asset.tags):
        raise HTTPException(status_code=403, detail="viewer role required for sensitive content")


def _can_view_asset(asset: AssetModel, principal: Principal) -> bool:
    if asset.deletion_status is not None:
        return False
    if principal.role != "guest":
        return True
    return not any(tag.tag in SENSITIVE_RATING_TAGS for tag in asset.tags)


def _asset_original_size(storage: GalleryStorage, asset: AssetModel) -> int | None:
    try:
        return storage.file_size(asset.original_path)
    except Exception:
        return None


def _asset_response(storage: GalleryStorage, asset: AssetModel, catalog: TagCatalog) -> dict[str, object]:
    response = asset_to_dict(asset, catalog)
    response["file_size"] = _file_size_for_kind(storage, asset, "original")
    response["preview_file_size"] = _file_size_for_kind(storage, asset, "preview")
    response["thumb_file_size"] = _file_size_for_kind(storage, asset, "thumb")
    return response


def _file_size_for_kind(storage: GalleryStorage, asset: AssetModel, kind: str) -> int | None:
    if kind == "original":
        try:
            return storage.file_size(asset.original_path)
        except Exception:
            return None
    path, _filename = _asset_file_path(storage, asset, kind)
    try:
        return path.stat().st_size if path.exists() else None
    except Exception:
        return None


def _file_response(storage: GalleryStorage, asset: AssetModel, kind: str) -> FileResponse:
    path, filename = _asset_file_path(storage, asset, kind)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{kind} file not found")
    resp = FileResponse(path, filename=filename, media_type=_media_type_for_path(path))
    resp.headers["Content-Disposition"] = _inline_content_disposition(filename)
    resp.headers["X-Asset-Key"] = asset.asset_key
    return resp


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


def _asset_file_path(storage: GalleryStorage, asset: AssetModel, kind: str) -> tuple[Path, str]:
    if kind == "original":
        path = storage.resolve_relative_path(asset.original_path)
        filename = _download_filename(asset, path)
    elif kind == "thumb":
        path = (
            _existing_path(storage, asset.thumb_path)
            or _path_if_exists(storage.thumb_path(asset.asset_key, ".avif"))
            or storage.resolve_relative_path(asset.original_path)
        )
        filename = path.name
    else:
        path = (
            _existing_path(storage, asset.preview_path)
            or _existing_preview_path(storage, asset.asset_key)
            or _existing_path(storage, asset.thumb_path)
            or storage.resolve_relative_path(asset.original_path)
        )
        filename = path.name
    return path, filename


def _inline_content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", errors="ignore").decode("ascii")
    fallback = fallback.replace("\\", "").replace('"', "").strip() or "download"
    return f'inline; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'


def _media_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.casefold()
    if suffix == ".avif":
        return "image/avif"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".zip":
        return "application/zip"
    return None


def _existing_path(storage: GalleryStorage, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    path = storage.resolve_relative_path(relative_path)
    return path if path.exists() else None


def _existing_preview_path(storage: GalleryStorage, asset_key: str) -> Path | None:
    return (
        _path_if_exists(storage.preview_path(asset_key, ".webp"))
        or _path_if_exists(storage.preview_path(asset_key, ".avif"))
    )


def _path_if_exists(path: Path) -> Path | None:
    return path if path.exists() else None


def _safe_upload_filename(filename: str | None, fallback: str) -> str:
    name = Path(filename or "").name.strip()
    return name or fallback


def _is_animated_upload(path: Path, mime_type: str | None) -> bool:
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().casefold()
    if path.suffix.casefold() == ".zip" or normalized_mime == "application/zip":
        return True
    if is_animated_raster(path):
        return True
    return normalized_mime == "image/apng"


def _download_filename(asset: AssetModel, original_path: Path) -> str:
    source_name = Path(asset.original_filename or "").name.strip()
    if not source_name:
        return original_path.name

    stored_suffix = original_path.suffix
    source_path = Path(source_name)
    if stored_suffix and source_path.suffix.lower() != stored_suffix.lower():
        return f"{source_path.stem}{stored_suffix}"
    return source_name
