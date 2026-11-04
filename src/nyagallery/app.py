from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import hashlib
import shutil
import json
from pathlib import Path
import os
import queue
import re
import secrets
import threading
import time
from typing import Annotated, Any
from urllib.parse import quote, unquote
import zipfile

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import Integer, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nyagallery.remote_upload import RemoteImageError, fetch_remote_image
from nyagallery.exif import browser_mtime, extract_photo_metadata
from nyagallery.image_edit import ImageEditError, edit_uploaded_image
from nyagallery.auth import (
    MAX_USERNAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
    Principal,
    permissions_for_role,
    validate_password_strength,
    hash_secret,
    verify_secret,
    validate_role,
    validate_username,
)
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
    EntityModel,
    EntityAssetLinkModel,
    AssetCommentModel,
    AssetMentionModel,
    NotificationModel,
    NotificationPreferenceModel,
    AssetLikeModel,
    AssetAclModel,
    aware_utc,
    PostModel,
    ShareGroupMemberModel,
    ShareGroupInviteModel,
    ShareGroupModel,
    ShareAlbumModel,
    ShareAlbumAssetModel,
    ShareAlbumLinkModel,
    ShareAlbumGroupModel,
    ShareLinkModel,
    AssetShortLinkModel,
    ShareAccessLogModel,
    UserModel,
    TranscodeJobModel,
    UploadLogModel,
    UserAssetModel,
    access_log_to_dict,
    any_users,
    api_token_belongs_to_user,
    api_token_to_dict,
    asset_to_dict,
    authenticate_api_token,
    authenticate_api_token_with_scopes,
    authenticate_login_session,
    authenticate_user,
    backfill_source_tag_index,
    change_user_password,
    claim_registration_invite,
    count_posts,
    post_asset_visibility_clause,
    create_access_log,
    create_engine_for_url,
    create_login_session,
    create_registration_invite,
    create_transcode_job,
    create_upload_log,
    create_user,
    default_database_url,
    encrypt_stored_pixiv_credentials,
    get_user_by_username,
    init_database,
    issue_api_token,
    get_misskey_token,
    get_x_token,
    get_fanbox_session,
    fanbox_session_belongs_to_user,
    fanbox_session_to_dict,
    list_fanbox_logs,
    list_fanbox_sessions,
    revoke_fanbox_session,
    save_fanbox_session,
    update_fanbox_session_label,
    get_pixiv_refresh_token,
    get_pixiv_cookie,
    get_post,
    get_security_settings,
    list_access_logs,
    list_api_tokens,
    list_pixiv_cookies,
    list_pixiv_tokens,
    list_misskey_logs,
    list_misskey_tokens,
    list_x_logs,
    list_x_tokens,
    list_pixiv_logs,
    list_posts,
    list_registration_invites,
    list_users,
    list_transcode_jobs,
    list_upload_history,
    list_upload_logs,
    make_session_factory,
    mark_asset_pending_cleanup,
    misskey_token_belongs_to_user,
    misskey_token_to_dict,
    x_token_belongs_to_user,
    x_token_to_dict,
    normalize_asset_sort,
    normalize_post_sort,
    normalize_sort_order,
    now_utc,
    post_source_counts,
    post_to_dict,
    posts_attachment_asset_map,
    purge_pending_asset,
    random_asset,
    rebuild_database,
    refresh_asset_tag_index,
    rebuild_posts,
    registration_invite_to_dict,
    release_registration_invite,
    search_asset_dicts,
    revoke_api_token,
    update_api_token_scopes,
    revoke_misskey_token,
    revoke_registration_invite,
    revoke_x_token,
    revoke_pixiv_cookie,
    revoke_pixiv_token,
    revoke_login_session,
    search_assets,
    can_view_asset,
    save_misskey_token,
    save_x_token,
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
    upsert_user_asset,
    security_settings_to_dict,
    update_misskey_token_label,
    update_x_token_label,
    update_pixiv_cookie_label,
    update_pixiv_token_label,
    update_security_settings,
    update_transcode_job,
    upload_log_to_dict,
)
from nyagallery.metadata import GalleryMetadata, make_asset_key, normalize_timestamp, parse_pixiv_filename, utc_now_iso
from nyagallery.media import MediaGenerator, is_animated_raster, media_limits_from_config, probe_media_size
from nyagallery.virtual_folders import VirtualFolder, VirtualFolderCatalog
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
from nyagallery.x import (
    X_DEFAULT_HOST,
    XBatchResult,
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
    normalize_screen_name,
    split_batch_input,
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
from nyagallery.posts import PostStore, ensure_sample_posts, link_sample_post_media
from nyagallery.redis_support import close_redis_client, create_redis_client, ping_redis_client
from nyagallery.security import (
    DEFAULT_REGISTRATION_MODE,
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
from nyagallery.tags import InvalidTagRelationError, TagAlreadyExistsError, TagCatalog, TagNotFoundError, source_tag_details_from_extra


bearer = HTTPBearer(auto_error=False)
SENSITIVE_RATING_TAGS = frozenset({"rating:r18", "rating:r18g"})
SENSITIVE_RATINGS = frozenset({"r18", "r18g"})


SESSION_COOKIE = "nya_session"
CSRF_COOKIE = "nya_csrf"
CSRF_HEADER = "x-csrf-token"
OPERATION_LOG_PATHS_SKIP_MIDDLEWARE = frozenset({"/api/auth/login", "/api/login", "/api/auth/register"})
# Unauthenticated entry points: they cannot carry a session CSRF token, so they are exempt
# from the CSRF token and origin checks and rely on their own validation instead.
UNAUTHENTICATED_CSRF_EXEMPT_PATHS = frozenset({"/api/auth/login", "/api/login", "/api/auth/register"})
REGISTRATION_DEFAULT_ROLE = "viewer"
ACCESS_LOG_QUIET_GET_PATHS = frozenset(
    {
        "/api/me",
        "/api/site/config",
        "/api/auth/registration",
        "/api/search",
        "/api/posts",
        "/api/uploads/history",
        "/api/uploads/logs",
        "/api/transcode/jobs",
        "/api/tags/suggest",
        "/api/tags/catalog",
        "/api/tags/summary",
        "/api/sync/x/config",
        "/api/sync/x/logs",
        "/api/sync/fanbox/config",
        "/api/sync/fanbox/logs",
    }
)
ACCESS_LOG_QUIET_GET_PREFIXES = ("/api/assets/", "/api/img/", "/api/posts/")
CACHE_FILE_CACHE_CONTROL = "private, max-age=300, stale-while-revalidate=86400"
ORIGINAL_CACHE_CONTROL = "private, max-age=3600"


@dataclass(frozen=True)
class AppState:
    storage: GalleryStorage
    post_store: PostStore
    catalog: TagCatalog
    engine: Engine
    session_factory: sessionmaker[Session]
    config: NyaGalleryConfig
    security_limiter: SecurityLimiter | RedisSecurityLimiter
    redis_client: Any | None
    pixiv_login_sessions: dict[str, dict[str, object]]
    pixiv_login_lock: threading.Lock
    access_log_queue: queue.Queue[dict[str, object]] | None = None
    access_log_stop: threading.Event | None = None
    access_log_thread: threading.Thread | None = None


class TagsUpdate(BaseModel):
    canonical_tags: list[str] = Field(default_factory=list)


class TagAliasesUpdate(BaseModel):
    aliases: list[str] = Field(default_factory=list)


class TagLabelsUpdate(BaseModel):
    labels: dict[str, str] = Field(default_factory=dict)


class TagRelationsUpdate(BaseModel):
    implications: list[str] = Field(default_factory=list)
    suggestions: list[str] | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = True


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)
    remember: bool = True
    invite_code: str | None = Field(default=None, max_length=200)


class RegistrationInviteCreate(BaseModel):
    label: str = Field(default="", max_length=160)
    code: str | None = Field(default=None, max_length=200)
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=1)


class TokenCreate(BaseModel):
    label: str = ""
    scopes: list[str] | None = None


class TokenScopesUpdate(BaseModel):
    scopes: list[str] | None = None


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


class MisskeyTokenCreate(BaseModel):
    token: str = Field(min_length=1, max_length=4000)
    label: str = ""
    host: str = "misskey.io"
    misskey_user: dict | None = None


class MisskeyTokenUpdate(BaseModel):
    label: str = ""


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


class XTokenCreate(BaseModel):
    token: str = Field(min_length=1, max_length=4000)
    ct0: str = ""
    label: str = ""
    host: str = "x.com"
    x_user: dict | None = None


class XTokenUpdate(BaseModel):
    label: str = ""


class XSyncRequest(BaseModel):
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


class MisskeySyncRequest(BaseModel):
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


class RemoteUploadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    title: str = Field(default="", max_length=500)
    artist_name: str = Field(default="", max_length=200)
    canonical_tags: list[str] = Field(default_factory=list, max_length=200)
    generate_cache: bool = False
    storage_strategy: str | None = Field(default=None, max_length=100)


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
    registration_mode: str | None = Field(default=None, pattern="^(closed|open|invite)$")
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
    bot_protection_enabled: bool | None = None
    bot_blocked_user_agents: list[str] | None = None
    bot_blocked_ips: list[str] | None = None


class DeveloperConfigUpdate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class DeveloperPasswordResetRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    new_password: str = Field(min_length=1)


class VirtualFolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=2000)
    group: str = Field(default="custom", max_length=80)
    description: str = Field(default="", max_length=500)


class ShareGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    member_usernames: list[str] = Field(default_factory=list)


class ShareGroupInviteCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class ShareGroupMemberRoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|member)$")


class ShareAlbumCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    asset_keys: list[str] = Field(default_factory=list, max_length=500)


class ShareAlbumGroupUpdate(BaseModel):
    group_id: int = Field(ge=1)
    permission: str = Field(pattern="^(view|edit|upload)$")


class ShareAlbumLinkCreate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=512)
    expires_at: str | None = None


class AssetGroupAclUpdate(BaseModel):
    group_id: int = Field(ge=1)
    permission: str = Field(pattern="^(view|edit|upload)$")


class AssetGroupAclBulkUpdate(AssetGroupAclUpdate):
    asset_keys: list[str] = Field(min_length=1, max_length=500)


class ShareLinkCreate(BaseModel):
    is_public: bool = True
    password: str | None = Field(default=None, min_length=8, max_length=512)
    expires_at: str | None = None


class ShortLinkCreate(BaseModel):
    slug: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    expires_at: str | None = None


class BulkShortLinkCreate(BaseModel):
    asset_keys: list[str] = Field(min_length=1, max_length=500)
    slugs: dict[str, str] = Field(default_factory=dict, max_length=500)
    expires_at: str | None = None


class AssetCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class EntityCreate(BaseModel):
    type: str = Field(min_length=1, max_length=60)
    entity_id: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=240)
    metadata: dict[str, object] = Field(default_factory=dict)
    asset_keys: list[str] = Field(default_factory=list, max_length=500)


class EntityLinkRequest(BaseModel):
    asset_keys: list[str] = Field(min_length=1, max_length=500)


class AssetVisibilityUpdate(BaseModel):
    visibility: str = Field(pattern="^(public|private)$")


class NotificationReadRequest(BaseModel):
    notification_ids: list[int] = Field(default_factory=list, max_length=200)


class NotificationPreferenceUpdate(BaseModel):
    mention_enabled: bool = True
    like_enabled: bool = True


class ChunkUploadInit(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    total_size: int = Field(gt=0)
    total_chunks: int = Field(gt=0, le=100000)
    chunk_size: int = Field(default=8 * 1024 * 1024, ge=1024 * 1024, le=32 * 1024 * 1024)
    sha256: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    content_type: str | None = Field(default=None, max_length=120)


class ShareLinkAccess(BaseModel):
    password: str | None = None


class MigrationModeUpdate(BaseModel):
    metadata_mode: str = Field(pattern="^(file|database)$")


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
    media_limits = media_limits_from_config(config.media)
    storage = GalleryStorage(
        storage_root or config.core.storage,
        default_strategy=config.original_storage.default_strategy,
        strategies=config.original_storage.strategies,
    )
    storage.ensure()
    post_store = PostStore(storage.root)
    post_store.ensure()
    catalog = _load_catalog(storage, tag_catalog_path or config.core.tag_catalog_path)
    virtual_folders = VirtualFolderCatalog(storage.tags_dir / "virtual_folders.json")
    virtual_folders.load()
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
        _index_posts_on_startup(session, post_store)
    if source_tag_backfill.tags or source_tag_backfill.labels:
        _save_catalog(storage, catalog)

    access_log_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=4096)
    access_log_stop = threading.Event()
    access_log_thread = threading.Thread(
        target=_access_log_worker,
        args=(session_factory, access_log_queue, access_log_stop),
        name="nyagallery-access-log",
        daemon=True,
    )
    state = AppState(
        storage,
        post_store,
        catalog,
        engine,
        session_factory,
        config,
        security_limiter,
        redis_client,
        {},
        threading.Lock(),
        access_log_queue,
        access_log_stop,
        access_log_thread,
    )
    access_log_thread.start()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await ping_redis_client(redis_client)
        try:
            yield
        finally:
            if state.access_log_stop is not None:
                state.access_log_stop.set()
            if state.access_log_thread is not None:
                state.access_log_thread.join(timeout=5)
            await close_redis_client(redis_client)
            engine.dispose()

    app = FastAPI(title="NyaGallery API", version="0.1.0", lifespan=lifespan)
    app.state.nyagallery = state

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
            "app_name": config.site.app_name or None,
            "logo_url": config.site.logo_url or None,
            "layout": config.site.layout or None,
            "private_asset_image": config.site.private_asset_image or "/jelly.jpg",
        }

    @app.get("/api/storage/strategies")
    def api_storage_strategies(_principal: UploadPrincipal) -> dict[str, object]:
        return _storage_strategy_response(storage)

    @app.get("/api/me/api-addresses")
    def api_me_api_addresses(request: Request, _principal: ApiPrincipal) -> dict[str, object]:
        base = str(request.base_url).rstrip("/")
        asset = "<asset_key>"
        return {
            "base_url": base,
            "metadata": f"{base}/api/assets/{asset}",
            "preview": f"{base}/api/assets/{asset}/preview",
            "original": f"{base}/api/assets/{asset}/original",
            "thumb": f"{base}/api/assets/{asset}/thumb",
            "short_link_create": f"{base}/api/assets/{asset}/short-links",
            "required_scopes": {"metadata": "view", "preview": "view", "thumb": "view", "original": "download", "short_link_create": "edit_tags"},
        }

    @app.get("/api/notification-preferences")
    def api_notification_preferences(db: DbSession, principal: ViewPrincipal) -> dict[str, bool]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        row = db.get(NotificationPreferenceModel, principal.user_id)
        return {"mention_enabled": row.mention_enabled if row else True, "like_enabled": row.like_enabled if row else True}

    @app.put("/api/notification-preferences")
    def api_update_notification_preferences(payload: NotificationPreferenceUpdate, db: DbSession, principal: ViewPrincipal) -> dict[str, bool]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        row = db.get(NotificationPreferenceModel, principal.user_id)
        if row is None:
            row = NotificationPreferenceModel(user_id=principal.user_id)
            db.add(row)
        row.mention_enabled = payload.mention_enabled
        row.like_enabled = payload.like_enabled
        db.commit()
        return {"mention_enabled": row.mention_enabled, "like_enabled": row.like_enabled}

    @app.get("/api/entities")
    def api_list_entities(db: DbSession, principal: EditTagsPrincipal, entity_type: str | None = None) -> dict[str, object]:
        query = select(EntityModel)
        if not principal.has_permission("admin"):
            query = query.where(EntityModel.owner_user_id == principal.user_id)
        if entity_type:
            query = query.where(EntityModel.type == entity_type)
        rows = db.scalars(query.order_by(EntityModel.type.asc(), EntityModel.name.asc(), EntityModel.id.asc())).all()
        return {"items": [_entity_to_dict(db, row) for row in rows]}

    @app.post("/api/entities")
    def api_create_entity(payload: EntityCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        existing = db.scalar(select(EntityModel.id).where(EntityModel.type == payload.type, EntityModel.entity_id == payload.entity_id))
        if existing is not None:
            raise HTTPException(status_code=409, detail="entity already exists")
        keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(keys))).all()) if keys else []
        if len(assets) != len(keys) or any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="entity may only include assets owned by the current user")
        row = EntityModel(type=payload.type.strip(), entity_id=payload.entity_id.strip(), name=payload.name.strip(), metadata_json=payload.metadata, owner_user_id=principal.user_id)
        db.add(row)
        db.flush()
        db.add_all([EntityAssetLinkModel(entity_id=row.id, asset_key=key) for key in keys])
        db.commit()
        return _entity_to_dict(db, row)

    @app.get("/api/entities/{entity_id}")
    def api_get_entity(entity_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = _get_entity(db, entity_id, principal)
        return _entity_to_dict(db, row)

    @app.put("/api/entities/{entity_id}")
    def api_update_entity(entity_id: int, payload: EntityCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = _get_entity(db, entity_id, principal)
        row.type = payload.type.strip(); row.entity_id = payload.entity_id.strip(); row.name = payload.name.strip(); row.metadata_json = payload.metadata
        keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(keys))).all()) if keys else []
        if len(assets) != len(keys) or any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="entity may only include assets owned by the current user")
        db.execute(delete(EntityAssetLinkModel).where(EntityAssetLinkModel.entity_id == row.id))
        db.add_all([EntityAssetLinkModel(entity_id=row.id, asset_key=key) for key in keys])
        db.commit()
        return _entity_to_dict(db, row)

    @app.delete("/api/entities/{entity_id}")
    def api_delete_entity(entity_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = _get_entity(db, entity_id, principal)
        db.delete(row); db.commit()
        return {"id": entity_id, "deleted": True}

    @app.get("/api/entities/{entity_id}/timeline")
    def api_entity_timeline(entity_id: int, db: DbSession, principal: EditTagsPrincipal, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> dict[str, object]:
        entity = _get_entity(db, entity_id, principal)
        assets = db.scalars(select(AssetModel).join(EntityAssetLinkModel, EntityAssetLinkModel.asset_key == AssetModel.asset_key).where(EntityAssetLinkModel.entity_id == entity.id).order_by(AssetModel.uploaded_at.desc(), AssetModel.asset_key.desc()).offset(offset).limit(limit)).all()
        return {"entity": {"id": entity.id, "type": entity.type, "entity_id": entity.entity_id, "name": entity.name}, "items": [_asset_response(storage, asset, catalog) for asset in assets], "limit": limit, "offset": offset, "has_more": len(assets) >= limit}

    @app.post("/api/entities/{entity_id}/assets")
    def api_link_entity_assets(entity_id: int, payload: EntityLinkRequest, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = _get_entity(db, entity_id, principal)
        keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(keys))).all())
        if len(assets) != len(keys) or any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="entity may only include assets owned by the current user")
        existing = set(db.scalars(select(EntityAssetLinkModel.asset_key).where(EntityAssetLinkModel.entity_id == row.id, EntityAssetLinkModel.asset_key.in_(keys))).all())
        db.add_all([EntityAssetLinkModel(entity_id=row.id, asset_key=key) for key in keys if key not in existing]); db.commit()
        return _entity_to_dict(db, row)

    @app.delete("/api/entities/{entity_id}/assets/{asset_key}")
    def api_unlink_entity_asset(entity_id: int, asset_key: str, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = _get_entity(db, entity_id, principal)
        db.execute(delete(EntityAssetLinkModel).where(EntityAssetLinkModel.entity_id == row.id, EntityAssetLinkModel.asset_key == asset_key)); db.commit()
        return {"entity_id": entity_id, "asset_key": asset_key, "deleted": True}

    @app.get("/api/notifications")
    def api_notifications(db: DbSession, principal: ViewPrincipal, limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0, unread_only: bool = False) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        query = select(NotificationModel).where(NotificationModel.recipient_user_id == principal.user_id)
        if unread_only:
            query = query.where(NotificationModel.read_at.is_(None))
        rows = db.scalars(query.order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc()).offset(offset).limit(limit)).all()
        unread = db.scalar(select(func.count(NotificationModel.id)).where(NotificationModel.recipient_user_id == principal.user_id, NotificationModel.read_at.is_(None))) or 0
        return {"items": [{"id": row.id, "kind": row.kind, "asset_key": row.asset_key, "comment_id": row.comment_id, "message": row.message, "read_at": row.read_at, "created_at": row.created_at, "actor_user_id": row.actor_user_id} for row in rows], "unread_count": unread, "limit": limit, "offset": offset}

    @app.post("/api/notifications/read")
    def api_mark_notifications_read(payload: NotificationReadRequest, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        query = select(NotificationModel).where(NotificationModel.recipient_user_id == principal.user_id, NotificationModel.read_at.is_(None))
        if payload.notification_ids:
            query = query.where(NotificationModel.id.in_(payload.notification_ids))
        rows = db.scalars(query).all()
        now = datetime.now(timezone.utc)
        for row in rows:
            row.read_at = now
        db.commit()
        return {"marked": len(rows)}

    @app.get("/api/me")
    def api_me(request: Request, principal: ViewPrincipal) -> dict[str, object]:
        return {
            "username": principal.username,
            "role": principal.role,
            "user_id": principal.user_id,
            "permissions": sorted(principal.effective_permissions()),
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

    @app.get("/api/auth/registration")
    def api_registration_status(db: DbSession) -> dict[str, object]:
        settings = get_security_settings(db)
        mode = str(settings.get("registration_mode") or DEFAULT_REGISTRATION_MODE)
        return {
            "mode": mode,
            "enabled": mode != "closed",
            "invite_required": mode == "invite",
            "default_role": REGISTRATION_DEFAULT_ROLE,
            "username_min_length": MIN_USERNAME_LENGTH,
            "username_max_length": MAX_USERNAME_LENGTH,
            "password_min_length": MIN_PASSWORD_LENGTH,
        }

    @app.post("/api/auth/register")
    def api_register(
        payload: RegistrationRequest,
        request: Request,
        response: Response,
        db: DbSession,
    ) -> dict[str, object]:
        settings = get_security_settings(db)
        mode = str(settings.get("registration_mode") or DEFAULT_REGISTRATION_MODE)
        request_ip = client_ip(request, trust_proxy_headers=bool(settings.get("trust_proxy_headers", False)))
        if mode == "closed":
            _write_operation_log(
                storage,
                request=request,
                identity={
                    "user_id": None,
                    "username": payload.username.strip() or None,
                    "role": None,
                    "auth_method": "guest",
                },
                client_ip_value=request_ip,
                status_code=403,
                action="register",
                detail="registration is closed",
            )
            raise HTTPException(status_code=403, detail="registration is closed")
        try:
            username = validate_username(payload.username)
            validate_password_strength(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        invite_code = (payload.invite_code or "").strip()
        if mode == "invite" and not invite_code:
            raise HTTPException(status_code=400, detail="invite code is required")
        claimed_invite = None
        if mode == "invite":
            try:
                claimed_invite = claim_registration_invite(db, invite_code)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            user = create_user(db, username, payload.password, REGISTRATION_DEFAULT_ROLE)
        except ValueError as exc:
            if claimed_invite is not None:
                release_registration_invite(db, claimed_invite.id)
            raise HTTPException(status_code=409, detail="username is already taken") from exc
        session_token, login_session = create_login_session(
            db,
            user,
            user_agent=request.headers.get("user-agent", ""),
            client_ip=request_ip,
            ttl_days=30 if payload.remember else 1,
        )
        _set_session_cookies(response, session_token, login_session.csrf_token, remember=payload.remember)
        _write_operation_log(
            storage,
            request=request,
            identity={
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "auth_method": "password",
            },
            client_ip_value=request_ip,
            status_code=201,
            action="register",
            detail=f"registration mode: {mode}",
        )
        return {
            "username": user.username,
            "role": user.role,
            "user_id": user.id,
            "permissions": sorted(permissions_for_role(user.role)),
            "auth_method": "session",
            "csrf_token": login_session.csrf_token,
        }

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
        asset_items = search_asset_dicts(
            db, catalog, q, limit=limit, offset=offset, sort=sort_key, order=sort_order,
            user_id=principal.user_id, is_admin=_is_admin_principal(principal),
        )
        return {
            "items": asset_items,
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
            "order": sort_order,
        }

    @app.get("/api/timeline")
    def api_timeline(
        db: DbSession,
        principal: ViewPrincipal,
        time_field: str = "uploaded_at",
        q: str = "",
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        offset: Annotated[int, Query(ge=0)] = 0,
        before: str | None = None,
    ) -> dict[str, object]:
        allowed_fields = {"published_at", "captured_at", "uploaded_at", "scraped_at", "upload_timestamp"}
        if time_field not in allowed_fields:
            raise HTTPException(status_code=422, detail="unsupported timeline time field")
        normalized_before = normalize_timestamp(before) if before else None
        if before and normalized_before is None:
            raise HTTPException(status_code=422, detail="invalid timeline before timestamp")
        safe_query = _query_with_guest_safety(q, principal)
        items = search_asset_dicts(
            db, catalog, safe_query, limit=limit, offset=offset,
            sort=time_field, order="desc", timeline_before=normalized_before, timeline=True,
            user_id=principal.user_id, is_admin=_is_admin_principal(principal),
        )
        return {
            "items": items,
            "limit": limit,
            "offset": offset,
            "time_field": time_field,
            "before": normalized_before,
            "has_more": len(items) >= limit,
        }

    @app.get("/api/posts")
    def api_posts(
        db: DbSession,
        principal: ViewPrincipal,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        source: str = "",
        q: str = "",
        sort: str = "posted_at",
        order: str = "desc",
    ) -> dict[str, object]:
        sort_key = normalize_post_sort(sort)
        sort_order = normalize_sort_order(order)
        excluded = _hidden_post_ratings(principal)
        posts = list_posts(
            db,
            limit=limit,
            offset=offset,
            source=source,
            q=q,
            sort=sort_key,
            order=sort_order,
            exclude_ratings=excluded,
            user_id=principal.user_id,
            is_admin=_is_admin_principal(principal),
        )
        assets = posts_attachment_asset_map(db, posts)
        total = count_posts(db, source=source, q=q, exclude_ratings=excluded, user_id=principal.user_id, is_admin=_is_admin_principal(principal))
        return {
            "items": [post_to_dict(post, assets=assets) for post in posts],
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
            "order": sort_order,
            "source": source,
            "q": q,
            "total": total,
            "has_more": offset + len(posts) < total,
            "sources": post_source_counts(db, exclude_ratings=excluded),
        }

    @app.get("/api/posts/{post_key}")
    def api_post(post_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        post = get_post(db, post_key)
        if post is None:
            raise HTTPException(status_code=404, detail="post not found")
        _require_sensitive_post_view(post, principal)
        if not db.scalar(select(1).where(post_asset_visibility_clause(user_id=principal.user_id, is_admin=_is_admin_principal(principal))).where(PostModel.post_key == post.post_key)):
            raise HTTPException(status_code=404, detail="post not found")
        return post_to_dict(post, assets=posts_attachment_asset_map(db, [post]))

    @app.get("/api/img/random")
    def api_random_image(
        db: DbSession,
        principal: ViewPrincipal,
        q: str | None = None,
        original: bool = False,
    ) -> FileResponse:
        q = _query_with_guest_safety(q or "", principal)
        asset = random_asset(db, catalog, q, exclude_ratings=_hidden_post_ratings(principal), user_id=principal.user_id, is_admin=_is_admin_principal(principal))
        if asset is None:
            raise HTTPException(status_code=404, detail="no matching asset")
        _require_asset_access(db, asset, principal)
        return _file_response(storage, asset, "original" if original else "preview")

    @app.get("/api/img/{tag}")
    def api_random_image_by_tag(
        tag: str,
        db: DbSession,
        principal: ViewPrincipal,
        original: bool = False,
    ) -> FileResponse:
        tag = _query_with_guest_safety(tag, principal)
        asset = random_asset(db, catalog, tag, exclude_ratings=_hidden_post_ratings(principal), user_id=principal.user_id, is_admin=_is_admin_principal(principal))
        if asset is None:
            raise HTTPException(status_code=404, detail="no matching asset")
        _require_asset_access(db, asset, principal)
        return _file_response(storage, asset, "original" if original else "preview")

    @app.post("/api/assets/{asset_key}/share-links")
    def api_create_share_link(asset_key: str, payload: ShareLinkCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_owner_or_admin(asset, principal)
        expires_at = normalize_timestamp(payload.expires_at) if payload.expires_at else None
        if payload.expires_at and expires_at is None:
            raise HTTPException(status_code=422, detail="invalid expires_at")
        token = secrets.token_urlsafe(32)
        row = ShareLinkModel(
            asset_key=asset.asset_key,
            owner_user_id=principal.user_id,
            token_prefix=token[:10],
            token_hash=hash_secret(token),
            is_public=payload.is_public,
            password_hash=hash_secret(payload.password) if payload.password else None,
            expires_at=expires_at,
        )
        db.add(row); db.commit(); db.refresh(row)
        return {"id": row.id, "token": token, "asset_key": row.asset_key, "is_public": row.is_public, "expires_at": row.expires_at, "revoked_at": None}

    @app.post("/api/short-links/bulk")
    def api_create_short_links_bulk(payload: BulkShortLinkCreate, request: Request, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset_keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        if not asset_keys:
            raise HTTPException(status_code=422, detail="asset_keys must not be empty")
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(asset_keys))).all())
        by_key = {asset.asset_key: asset for asset in assets}
        if len(by_key) != len(asset_keys):
            raise HTTPException(status_code=404, detail="one or more assets not found")
        if any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="cannot share assets owned by another user")
        expires_at = normalize_timestamp(payload.expires_at) if payload.expires_at else None
        if payload.expires_at and expires_at is None:
            raise HTTPException(status_code=422, detail="invalid expires_at")
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) if expires_at else None
        slugs: dict[str, str] = {}
        for key in asset_keys:
            slug = payload.slugs.get(key) if key in payload.slugs else f"asset-{secrets.token_urlsafe(8)}"
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,79}", slug):
                raise HTTPException(status_code=422, detail=f"invalid slug for asset {key}")
            if slug in slugs.values() or db.scalar(select(AssetShortLinkModel.id).where(AssetShortLinkModel.slug == slug)) is not None:
                raise HTTPException(status_code=409, detail=f"short-link slug already exists: {slug}")
            slugs[key] = slug
        rows = [AssetShortLinkModel(slug=slugs[key], asset_key=key, owner_user_id=principal.user_id, expires_at=expiry) for key in asset_keys]
        db.add_all(rows)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="short-link slug conflict") from exc
        base = str(request.base_url).rstrip("/")
        return {"items": [{"id": row.id, "asset_key": row.asset_key, "slug": row.slug, "expires_at": row.expires_at, "url": f"{base}/s/{row.slug}"} for row in rows]}

    @app.post("/api/assets/{asset_key}/short-links")
    def api_create_short_link(asset_key: str, payload: ShortLinkCreate, request: Request, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_owner_or_admin(asset, principal)
        normalized_expiry = normalize_timestamp(payload.expires_at) if payload.expires_at else None
        if payload.expires_at and normalized_expiry is None:
            raise HTTPException(status_code=422, detail="invalid expires_at")
        expires_at = datetime.fromisoformat(normalized_expiry.replace("Z", "+00:00")) if normalized_expiry else None
        slug = payload.slug or secrets.token_urlsafe(6).replace("-", "_")
        if db.scalar(select(AssetShortLinkModel.id).where(AssetShortLinkModel.slug == slug)) is not None:
            raise HTTPException(status_code=409, detail="short-link slug already exists")
        row = AssetShortLinkModel(slug=slug, asset_key=asset.asset_key, owner_user_id=principal.user_id, expires_at=expires_at)
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="short-link slug already exists") from exc
        db.refresh(row)
        return {"id": row.id, "slug": row.slug, "asset_key": row.asset_key, "expires_at": row.expires_at, "url": f"{str(request.base_url).rstrip('/')}/s/{row.slug}"}

    @app.get("/api/assets/{asset_key}/short-links")
    def api_list_short_links(asset_key: str, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_owner_or_admin(asset, principal)
        rows = db.scalars(select(AssetShortLinkModel).where(AssetShortLinkModel.asset_key == asset.asset_key).order_by(AssetShortLinkModel.id.desc())).all()
        return {"items": [{"id": row.id, "slug": row.slug, "asset_key": row.asset_key, "expires_at": row.expires_at, "revoked_at": row.revoked_at} for row in rows]}

    @app.delete("/api/short-links/{link_id}")
    def api_revoke_short_link(link_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = db.get(AssetShortLinkModel, link_id)
        if row is None or (row.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="short link not found")
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": row.id, "revoked": True}

    @app.get("/s/{slug}")
    def api_short_link(slug: str, db: DbSession, original: bool = False) -> FileResponse:
        row = db.scalar(select(AssetShortLinkModel).where(AssetShortLinkModel.slug == slug))
        if row is None:
            raise HTTPException(status_code=404, detail="short link not found")
        now = datetime.now(timezone.utc)
        if row.revoked_at is not None or (row.expires_at is not None and aware_utc(row.expires_at) <= now):
            raise HTTPException(status_code=410, detail="short link is no longer active")
        asset = _get_asset(db, row.asset_key)
        _require_sensitive_view(asset, Principal(username="guest", role="guest"))
        return _file_response(storage, asset, "original" if original else "preview")

    @app.get("/api/assets/{asset_key}/share-links")
    def api_list_share_links(asset_key: str, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key); _require_asset_owner_or_admin(asset, principal)
        rows = db.scalars(select(ShareLinkModel).where(ShareLinkModel.asset_key == asset.asset_key).order_by(ShareLinkModel.id.desc())).all()
        return {"items": [{"id": row.id, "asset_key": row.asset_key, "token_prefix": row.token_prefix, "is_public": row.is_public, "expires_at": row.expires_at, "revoked_at": row.revoked_at, "access_count": row.access_count} for row in rows]}

    @app.get("/api/share-links/logs")
    def api_share_access_logs(db: DbSession, _principal: AdminPrincipal, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0, asset_key: str | None = None, status: str | None = None) -> dict[str, object]:
        statement = select(ShareAccessLogModel)
        if asset_key:
            statement = statement.where(ShareAccessLogModel.asset_key == asset_key.strip())
        if status:
            statement = statement.where(ShareAccessLogModel.status == status.strip())
        rows = db.scalars(statement.order_by(ShareAccessLogModel.created_at.desc(), ShareAccessLogModel.id.desc()).offset(offset).limit(limit)).all()
        return {"items": [{"id": row.id, "share_link_id": row.share_link_id, "asset_key": row.asset_key, "status": row.status, "client_ip": row.client_ip, "user_agent": row.user_agent, "created_at": row.created_at} for row in rows], "limit": limit, "offset": offset}

    @app.delete("/api/share-links/{link_id}")
    def api_revoke_share_link(link_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = db.get(ShareLinkModel, link_id)
        if row is None or (row.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="share link not found")
        row.revoked_at = datetime.now(timezone.utc); db.commit()
        return {"id": row.id, "revoked": True}

    @app.get("/api/share/{token}")
    def api_share_metadata(token: str, request: Request, db: DbSession, password: str | None = None) -> dict[str, object]:
        row = _share_link_by_token(db, token)
        asset = _get_asset(db, row.asset_key)
        _validate_share_access(row, asset, password)
        _record_share_access(db, row, request, "metadata")
        return {"asset": _asset_response(storage, asset, catalog), "preview_url": f"/api/share/{token}/preview", "original_url": f"/api/share/{token}/original"}

    @app.get("/api/share/{token}/preview")
    def api_share_preview(token: str, request: Request, db: DbSession, password: str | None = None) -> FileResponse:
        row = _share_link_by_token(db, token); asset = _get_asset(db, row.asset_key); _validate_share_access(row, asset, password)
        _record_share_access(db, row, request, "preview"); return _file_response(storage, asset, "preview")

    @app.get("/api/share/{token}/original")
    def api_share_original(token: str, request: Request, db: DbSession, password: str | None = None) -> FileResponse:
        row = _share_link_by_token(db, token); asset = _get_asset(db, row.asset_key); _validate_share_access(row, asset, password)
        _record_share_access(db, row, request, "original"); return _file_response(storage, asset, "original")

    @app.get("/api/assets/{asset_key}")
    def api_asset(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        owner_id = asset.uploader_user_id or principal.user_id
        visibility_row = db.scalar(select(UserAssetModel).where(UserAssetModel.user_id == owner_id, UserAssetModel.asset_key == asset.asset_key)) if owner_id is not None else None
        visibility = visibility_row.visibility if visibility_row else "private"
        if not can_view_asset(db, asset, user_id=principal.user_id, is_admin=_is_admin_principal(principal)):
            result = _asset_response(storage, asset, catalog)
            result.update({"visibility": visibility, "private_resource": True, "preview_url": "", "thumb_url": "", "original_path": ""})
            return result
        _require_sensitive_view(asset, principal)
        result = _asset_response(storage, asset, catalog)
        result["visibility"] = visibility
        result["private_resource"] = False
        return result

    @app.get("/api/assets/{asset_key}/visibility")
    def api_asset_visibility(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, str]:
        asset = _get_asset(db, asset_key)
        if not _principal_owns_asset(asset, principal):
            raise HTTPException(status_code=404, detail="asset not found")
        owner_id = asset.uploader_user_id or principal.user_id
        row = db.scalar(select(UserAssetModel).where(UserAssetModel.user_id == owner_id, UserAssetModel.asset_key == asset.asset_key)) if owner_id is not None else None
        return {"visibility": row.visibility if row else "private"}

    @app.put("/api/assets/{asset_key}/visibility")
    def api_update_asset_visibility(asset_key: str, payload: AssetVisibilityUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, str]:
        asset = _get_asset(db, asset_key)
        if not _principal_owns_asset(asset, principal):
            raise HTTPException(status_code=404, detail="asset not found")
        owner_id = asset.uploader_user_id or principal.user_id
        if owner_id is None:
            raise HTTPException(status_code=422, detail="asset has no owner")
        if asset.uploader_user_id is None and principal.user_id == owner_id:
            asset.uploader_user_id = owner_id
            asset.uploader_username = principal.username
        row = upsert_user_asset(db, user_id=owner_id, asset_key=asset.asset_key, visibility=payload.visibility)
        db.commit()
        return {"visibility": row.visibility}

    @app.get("/api/assets/{asset_key}/likes")
    def api_asset_likes(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        count = db.scalar(select(func.count(AssetLikeModel.id)).where(AssetLikeModel.asset_key == asset.asset_key)) or 0
        liked = principal.user_id is not None and db.scalar(select(AssetLikeModel.id).where(AssetLikeModel.asset_key == asset.asset_key, AssetLikeModel.user_id == principal.user_id)) is not None
        return {"asset_key": asset.asset_key, "count": count, "liked": liked}

    @app.put("/api/assets/{asset_key}/likes")
    def api_set_asset_like(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        if principal.user_id is None or principal.role == "guest":
            raise HTTPException(status_code=401, detail="login required to like")
        existing = db.scalar(select(AssetLikeModel).where(AssetLikeModel.asset_key == asset.asset_key, AssetLikeModel.user_id == principal.user_id))
        if existing is None:
            db.add(AssetLikeModel(asset_key=asset.asset_key, user_id=principal.user_id))
            if asset.uploader_user_id is not None and asset.uploader_user_id != principal.user_id:
                preference = db.get(NotificationPreferenceModel, asset.uploader_user_id)
                if preference is None or preference.like_enabled:
                    db.add(NotificationModel(recipient_user_id=asset.uploader_user_id, actor_user_id=principal.user_id, kind="asset_like", asset_key=asset.asset_key, message="Your asset was liked"))
            db.commit()
        count = db.scalar(select(func.count(AssetLikeModel.id)).where(AssetLikeModel.asset_key == asset.asset_key)) or 0
        return {"asset_key": asset.asset_key, "count": count, "liked": True}

    @app.delete("/api/assets/{asset_key}/likes")
    def api_remove_asset_like(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        if principal.user_id is None or principal.role == "guest":
            raise HTTPException(status_code=401, detail="login required to unlike")
        existing = db.scalar(select(AssetLikeModel).where(AssetLikeModel.asset_key == asset.asset_key, AssetLikeModel.user_id == principal.user_id))
        if existing is not None:
            db.delete(existing)
            db.commit()
        count = db.scalar(select(func.count(AssetLikeModel.id)).where(AssetLikeModel.asset_key == asset.asset_key)) or 0
        return {"asset_key": asset.asset_key, "count": count, "liked": False}

    @app.get("/api/assets/{asset_key}/comments")
    def api_asset_comments(
        asset_key: str,
        db: DbSession,
        principal: ViewPrincipal,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        rows = db.scalars(select(AssetCommentModel).where(
            AssetCommentModel.asset_key == asset.asset_key,
            AssetCommentModel.deleted_at.is_(None),
        ).order_by(AssetCommentModel.created_at.desc(), AssetCommentModel.id.desc()).offset(offset).limit(limit)).all()
        return {"items": [_asset_comment_to_dict(db, row) for row in rows], "limit": limit, "offset": offset}

    @app.post("/api/assets/{asset_key}/comments")
    def api_create_asset_comment(asset_key: str, payload: AssetCommentCreate, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        if principal.user_id is None or principal.role == "guest":
            raise HTTPException(status_code=401, detail="login required to comment")
        row = AssetCommentModel(asset_key=asset.asset_key, user_id=principal.user_id, username=principal.username, body=payload.body.strip())
        if not row.body:
            raise HTTPException(status_code=422, detail="comment body must not be empty")
        db.add(row)
        db.flush()
        _replace_asset_comment_mentions(db, row.id, row.body, actor_user_id=principal.user_id, asset_key=row.asset_key)
        db.commit()
        db.refresh(row)
        return _asset_comment_to_dict(db, row)

    @app.patch("/api/assets/{asset_key}/comments/{comment_id}")
    def api_update_asset_comment(asset_key: str, comment_id: int, payload: AssetCommentCreate, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        row = db.scalar(select(AssetCommentModel).where(AssetCommentModel.id == comment_id, AssetCommentModel.asset_key == asset.asset_key, AssetCommentModel.deleted_at.is_(None)))
        if row is None:
            raise HTTPException(status_code=404, detail="comment not found")
        if row.user_id != principal.user_id and not _is_admin_principal(principal):
            raise HTTPException(status_code=403, detail="comment owner or admin required")
        body = payload.body.strip()
        if not body:
            raise HTTPException(status_code=422, detail="comment body must not be empty")
        row.body = body
        row.updated_at = datetime.now(timezone.utc)
        _replace_asset_comment_mentions(db, row.id, row.body, actor_user_id=principal.user_id, asset_key=row.asset_key)
        db.commit()
        return _asset_comment_to_dict(db, row)

    @app.delete("/api/assets/{asset_key}/comments/{comment_id}")
    def api_delete_asset_comment(asset_key: str, comment_id: int, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        row = db.scalar(select(AssetCommentModel).where(AssetCommentModel.id == comment_id, AssetCommentModel.asset_key == asset.asset_key, AssetCommentModel.deleted_at.is_(None)))
        if row is None:
            raise HTTPException(status_code=404, detail="comment not found")
        if row.user_id != principal.user_id and not _is_admin_principal(principal):
            raise HTTPException(status_code=403, detail="comment owner or admin required")
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": row.id, "deleted": True}

    @app.get("/api/assets/{asset_key}/api-examples")
    def api_asset_examples(asset_key: str, request: Request, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        """Return copyable examples with a placeholder token only."""
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        _require_sensitive_view(asset, principal)
        base = str(request.base_url).rstrip("/")
        endpoint = f"/api/assets/{asset.asset_key}"
        token = "<nya_token_with_view_or_download_scope>"
        return {
            "asset_key": asset.asset_key,
            "formats": {
                "curl": {
                    "metadata": f'curl -H "Authorization: Bearer {token}" {base}{endpoint}',
                    "original": f'curl -H "Authorization: Bearer {token}" -o original{Path(asset.original_filename).suffix or ".bin"} {base}{endpoint}/original',
                    "preview": f'curl -H "Authorization: Bearer {token}" -o preview{Path(asset.original_filename).suffix or ".bin"} {base}{endpoint}/preview',
                    "thumb": f'curl -H "Authorization: Bearer {token}" -o thumb{Path(asset.original_filename).suffix or ".bin"} {base}{endpoint}/thumb',
                    "upload": f'curl -X POST -H "Authorization: Bearer {token}" -F "file=@image.jpg" -F "visibility=private" {base}/api/assets',
                },
                "fetch": {
                    "metadata": f"fetch('{base}{endpoint}', {{ headers: {{ Authorization: 'Bearer {token}' }} }})",
                    "original": f"fetch('{base}{endpoint}/original', {{ headers: {{ Authorization: 'Bearer {token}' }} }})",
                },
                "python": {
                    "metadata": f"requests.get('{base}{endpoint}', headers={{'Authorization': 'Bearer {token}'}})",
                    "original": f"requests.get('{base}{endpoint}/original', headers={{'Authorization': 'Bearer {token}'}})",
                },
            },
        }

    @app.get("/api/assets/{asset_key}/siblings")
    def api_asset_siblings(asset_key: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
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
        siblings = []
        for item in db.scalars(statement).all():
            if item.asset_key != asset.asset_key and not can_view_asset(
                db,
                item,
                user_id=principal.user_id,
                is_admin=_is_admin_principal(principal),
            ):
                continue
            try:
                _require_sensitive_view(item, principal)
            except HTTPException:
                continue
            siblings.append(item)
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
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, _principal)
        return _file_response(storage, asset, "original")

    @app.get("/api/assets/{asset_key}/preview")
    def api_asset_preview(asset_key: str, db: DbSession, principal: ViewPrincipal) -> FileResponse:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
        _require_sensitive_view(asset, principal)
        return _file_response(storage, asset, "preview")

    @app.get("/api/assets/{asset_key}/thumb")
    def api_asset_thumb(asset_key: str, db: DbSession, principal: ViewPrincipal) -> FileResponse:
        asset = _get_asset(db, asset_key)
        _require_asset_access(db, asset, principal)
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

    @app.get("/api/virtual-folders")
    def api_virtual_folders(_principal: ViewPrincipal) -> dict[str, object]:
        return {"items": [folder.to_dict() for folder in virtual_folders.list()]}

    @app.put("/api/virtual-folders/{folder_name}")
    def api_put_virtual_folder(folder_name: str, update: VirtualFolderUpdate, _principal: AdminPrincipal) -> dict[str, object]:
        if folder_name != update.name:
            raise HTTPException(status_code=400, detail="folder name in path and body must match")
        virtual_folders.put(VirtualFolder(update.name, update.query, update.group, update.description))
        virtual_folders.save()
        return update.model_dump()

    @app.delete("/api/virtual-folders/{folder_name}")
    def api_delete_virtual_folder(folder_name: str, _principal: AdminPrincipal) -> dict[str, object]:
        if not virtual_folders.remove(folder_name):
            raise HTTPException(status_code=404, detail="virtual folder not found")
        virtual_folders.save()
        return {"name": folder_name, "deleted": True}

    @app.get("/api/share/albums")
    def api_list_share_albums(db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        query = select(ShareAlbumModel)
        if not principal.has_permission("admin"):
            query = query.where(ShareAlbumModel.owner_user_id == principal.user_id)
        albums = db.scalars(query.order_by(ShareAlbumModel.updated_at.desc(), ShareAlbumModel.id.desc())).all()
        return {"items": [_share_album_to_dict(db, album) for album in albums]}

    @app.post("/api/share/albums")
    def api_create_share_album(payload: ShareAlbumCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        asset_keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(asset_keys))).all()) if asset_keys else []
        if len(assets) != len(asset_keys) or any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="album may only include assets owned by the current user")
        album = ShareAlbumModel(owner_user_id=principal.user_id, name=payload.name.strip(), description=payload.description.strip())
        db.add(album)
        db.flush()
        db.add_all([ShareAlbumAssetModel(album_id=album.id, asset_key=key) for key in asset_keys])
        db.commit()
        db.refresh(album)
        return _share_album_to_dict(db, album)

    @app.get("/api/share/albums/{album_id}")
    def api_get_share_album(album_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        return _share_album_to_dict(db, album)

    @app.put("/api/share/albums/{album_id}")
    def api_update_share_album(album_id: int, payload: ShareAlbumCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        asset_keys = list(dict.fromkeys(key.strip() for key in payload.asset_keys if key.strip()))
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(asset_keys))).all()) if asset_keys else []
        if len(assets) != len(asset_keys) or any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="album may only include assets owned by the current user")
        album.name = payload.name.strip()
        album.description = payload.description.strip()
        db.execute(delete(ShareAlbumAssetModel).where(ShareAlbumAssetModel.album_id == album.id))
        db.add_all([ShareAlbumAssetModel(album_id=album.id, asset_key=key) for key in asset_keys])
        db.commit()
        return _share_album_to_dict(db, album)

    @app.delete("/api/share/albums/{album_id}")
    def api_delete_share_album(album_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        db.delete(album)
        db.commit()
        return {"id": album_id, "deleted": True}

    @app.post("/api/share/albums/{album_id}/links")
    def api_create_share_album_link(album_id: int, payload: ShareAlbumLinkCreate, request: Request, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        normalized = normalize_timestamp(payload.expires_at) if payload.expires_at else None
        if payload.expires_at and normalized is None:
            raise HTTPException(status_code=422, detail="invalid expires_at")
        token = secrets.token_urlsafe(32)
        row = ShareAlbumLinkModel(album_id=album.id, owner_user_id=principal.user_id, token_prefix=token[:12], token_hash=hash_secret(token), password_hash=hash_secret(payload.password) if payload.password else None, expires_at=datetime.fromisoformat(normalized.replace("Z", "+00:00")) if normalized else None)
        db.add(row)
        db.commit()
        return {"id": row.id, "token": token, "album_id": row.album_id, "expires_at": row.expires_at, "url": f"{str(request.base_url).rstrip('/')}/api/share/albums/token/{token}"}

    @app.get("/api/share/albums/{album_id}/links")
    def api_list_share_album_links(album_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        rows = db.scalars(select(ShareAlbumLinkModel).where(ShareAlbumLinkModel.album_id == album.id).order_by(ShareAlbumLinkModel.id.desc())).all()
        return {"items": [{"id": row.id, "token_prefix": row.token_prefix, "expires_at": row.expires_at, "revoked_at": row.revoked_at, "access_count": row.access_count} for row in rows]}

    @app.delete("/api/share/album-links/{link_id}")
    def api_revoke_share_album_link(link_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        row = db.get(ShareAlbumLinkModel, link_id)
        if row is None or (row.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="album link not found")
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": row.id, "revoked": True}

    @app.get("/api/share/albums/token/{token}")
    def api_public_share_album(token: str, db: DbSession, password: str | None = None) -> dict[str, object]:
        candidates = db.scalars(select(ShareAlbumLinkModel).where(ShareAlbumLinkModel.token_prefix == token[:12])).all()
        row = next((candidate for candidate in candidates if verify_secret(token, candidate.token_hash)), None)
        if row is None:
            raise HTTPException(status_code=404, detail="album link not found")
        if row.revoked_at is not None or (row.expires_at is not None and aware_utc(row.expires_at) <= datetime.now(timezone.utc)):
            raise HTTPException(status_code=410, detail="album link is no longer active")
        if row.password_hash and not verify_secret(password or "", row.password_hash):
            raise HTTPException(status_code=401, detail="password required")
        album = db.get(ShareAlbumModel, row.album_id)
        if album is None:
            raise HTTPException(status_code=404, detail="share album not found")
        assets = list(db.scalars(select(AssetModel).join(ShareAlbumAssetModel, ShareAlbumAssetModel.asset_key == AssetModel.asset_key).where(ShareAlbumAssetModel.album_id == album.id).order_by(ShareAlbumAssetModel.id.asc())).all())
        guest = Principal(username="guest", role="guest")
        visible = []
        for asset in assets:
            try:
                _require_sensitive_view(asset, guest)
            except HTTPException:
                continue
            visible.append(asset_to_dict(asset))
        row.access_count += 1
        db.commit()
        return {"album": {"id": album.id, "name": album.name, "description": album.description}, "items": visible}

    @app.post("/api/share/albums/{album_id}/groups")
    def api_bind_share_album_group(album_id: int, payload: ShareAlbumGroupUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        group = db.get(ShareGroupModel, payload.group_id)
        if group is None or (group.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="share group not found")
        row = db.scalar(select(ShareAlbumGroupModel).where(ShareAlbumGroupModel.album_id == album.id, ShareAlbumGroupModel.group_id == group.id))
        if row is None:
            row = ShareAlbumGroupModel(album_id=album.id, group_id=group.id, permission=payload.permission)
            db.add(row)
        else:
            row.permission = payload.permission
        db.commit()
        return {"album_id": album.id, "group_id": group.id, "permission": row.permission}

    @app.delete("/api/share/albums/{album_id}/groups/{group_id}")
    def api_unbind_share_album_group(album_id: int, group_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        album = _get_share_album(db, album_id, principal)
        db.execute(delete(ShareAlbumGroupModel).where(ShareAlbumGroupModel.album_id == album.id, ShareAlbumGroupModel.group_id == group_id))
        db.commit()
        return {"album_id": album.id, "group_id": group_id, "deleted": True}

    @app.get("/api/access/invitations")
    def api_my_share_group_invitations(db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        rows = db.execute(
            select(ShareGroupInviteModel, ShareGroupModel)
            .join(ShareGroupModel, ShareGroupModel.id == ShareGroupInviteModel.group_id)
            .where(ShareGroupInviteModel.user_id == principal.user_id, ShareGroupInviteModel.status == "pending")
            .order_by(ShareGroupInviteModel.created_at.desc(), ShareGroupInviteModel.id.desc())
        ).all()
        return {"items": [{"id": invite.id, "group_id": group.id, "group_name": group.name, "invited_by_user_id": invite.invited_by_user_id, "created_at": invite.created_at} for invite, group in rows]}

    @app.post("/api/access/invitations/{invite_id}/{decision}")
    def api_respond_share_group_invitation(invite_id: int, decision: str, db: DbSession, principal: ViewPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        if decision not in {"accept", "decline"}:
            raise HTTPException(status_code=404, detail="invitation action not found")
        invite = db.get(ShareGroupInviteModel, invite_id)
        if invite is None or invite.user_id != principal.user_id or invite.status != "pending":
            raise HTTPException(status_code=404, detail="invitation not found")
        invite.status = "accepted" if decision == "accept" else "declined"
        invite.responded_at = datetime.now(timezone.utc)
        if decision == "accept":
            member = db.scalar(select(ShareGroupMemberModel).where(ShareGroupMemberModel.group_id == invite.group_id, ShareGroupMemberModel.user_id == principal.user_id))
            if member is None:
                db.add(ShareGroupMemberModel(group_id=invite.group_id, user_id=principal.user_id, role="member"))
        db.commit()
        return {"id": invite.id, "status": invite.status}

    @app.post("/api/access/groups/{group_id}/invites")
    def api_invite_share_group_member(group_id: int, payload: ShareGroupInviteCreate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        group = db.get(ShareGroupModel, group_id)
        if group is None or principal.user_id is None or not _can_manage_share_group(db, group, principal):
            raise HTTPException(status_code=404, detail="share group not found")
        user = db.scalar(select(UserModel).where(UserModel.username == payload.username.strip(), UserModel.is_active.is_(True)))
        if user is None:
            raise HTTPException(status_code=404, detail="active user not found")
        if user.id == group.owner_user_id or db.scalar(select(ShareGroupMemberModel.id).where(ShareGroupMemberModel.group_id == group.id, ShareGroupMemberModel.user_id == user.id)) is not None:
            raise HTTPException(status_code=409, detail="user is already a group member")
        invite = db.scalar(select(ShareGroupInviteModel).where(ShareGroupInviteModel.group_id == group.id, ShareGroupInviteModel.user_id == user.id))
        if invite is not None and invite.status == "pending":
            raise HTTPException(status_code=409, detail="invitation is already pending")
        if invite is None:
            invite = ShareGroupInviteModel(group_id=group.id, user_id=user.id, invited_by_user_id=principal.user_id)
            db.add(invite)
        else:
            invite.invited_by_user_id = principal.user_id
            invite.status = "pending"
            invite.created_at = datetime.now(timezone.utc)
            invite.responded_at = None
        db.commit()
        return {"id": invite.id, "group_id": group.id, "username": user.username, "status": invite.status}

    @app.put("/api/access/groups/{group_id}/members/{user_id}/role")
    def api_set_share_group_member_role(group_id: int, user_id: int, payload: ShareGroupMemberRoleUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        group = db.get(ShareGroupModel, group_id)
        if group is None or not _can_manage_share_group(db, group, principal):
            raise HTTPException(status_code=404, detail="share group not found")
        member = db.scalar(select(ShareGroupMemberModel).where(ShareGroupMemberModel.group_id == group.id, ShareGroupMemberModel.user_id == user_id))
        if member is None:
            raise HTTPException(status_code=404, detail="group member not found")
        if member.user_id == group.owner_user_id:
            raise HTTPException(status_code=400, detail="group owner role cannot be changed")
        member.role = payload.role
        db.commit()
        return {"group_id": group.id, "user_id": user_id, "role": member.role}

    @app.get("/api/access/permission-groups")
    def api_permission_groups(_principal: AdminPrincipal) -> dict[str, object]:
        return {
            "items": [
                {"role": role, "permissions": sorted(permissions_for_role(role))}
                for role in ("viewer", "editor", "admin", "developer")
            ]
        }

    @app.get("/api/access/my-groups")
    def api_my_access_groups(db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        query = select(ShareGroupModel)
        if not principal.has_permission("admin"):
            query = query.where((ShareGroupModel.owner_user_id == principal.user_id) | ShareGroupModel.id.in_(
                select(ShareGroupMemberModel.group_id).where(ShareGroupMemberModel.user_id == principal.user_id)
            ))
        groups = db.scalars(query.order_by(ShareGroupModel.name.asc(), ShareGroupModel.id.asc())).all()
        return {"items": [{"id": group.id, "name": group.name, "owner_user_id": group.owner_user_id, "role": _share_group_role(db, group, principal.user_id)} for group in groups]}

    @app.get("/api/access/groups")
    def api_access_groups(db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        groups = list(db.scalars(select(ShareGroupModel).order_by(ShareGroupModel.name.asc(), ShareGroupModel.id.asc())).all())
        members = list(db.scalars(select(ShareGroupMemberModel).order_by(ShareGroupMemberModel.id.asc())).all())
        users = {user.id: user for user in db.scalars(select(UserModel)).all()}
        by_group: dict[int, list[dict[str, object]]] = {group.id: [] for group in groups}
        for member in members:
            user = users.get(member.user_id)
            if user is not None and member.group_id in by_group:
                by_group[member.group_id].append({"id": user.id, "username": user.username, "role": member.role})
        return {
            "items": [
                {
                    "id": group.id,
                    "name": group.name,
                    "owner_user_id": group.owner_user_id,
                    "members": by_group.get(group.id, []),
                }
                for group in groups
            ]
        }

    @app.post("/api/access/groups")
    def api_create_access_group(update: ShareGroupUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        if principal.user_id is None:
            raise HTTPException(status_code=401, detail="login required")
        name = update.name.strip()
        if db.scalar(select(ShareGroupModel.id).where(ShareGroupModel.owner_user_id == principal.user_id, ShareGroupModel.name == name)) is not None:
            raise HTTPException(status_code=409, detail="share group already exists")
        group = ShareGroupModel(owner_user_id=principal.user_id, name=name)
        db.add(group)
        db.flush()
        _replace_share_group_members(db, group.id, update.member_usernames)
        db.commit()
        return _access_group_to_dict(db, group)

    @app.put("/api/access/groups/{group_id}")
    def api_update_access_group(group_id: int, update: ShareGroupUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        group = db.get(ShareGroupModel, group_id)
        if group is None or not _can_manage_share_group(db, group, principal):
            raise HTTPException(status_code=404, detail="share group not found")
        group.name = update.name.strip()
        _replace_share_group_members(db, group.id, update.member_usernames)
        db.commit()
        return _access_group_to_dict(db, group)

    @app.delete("/api/access/groups/{group_id}")
    def api_delete_access_group(group_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        group = db.get(ShareGroupModel, group_id)
        if group is None or not _can_manage_share_group(db, group, principal):
            raise HTTPException(status_code=404, detail="share group not found")
        db.delete(group)
        db.commit()
        return {"id": group_id, "deleted": True}

    @app.get("/api/migration/config")
    def api_migration_config(request: Request, _principal: AdminPrincipal) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        return {
            "metadata_mode": state.config.core.metadata_mode,
            "config_path": str(state.config.path or Path(DEFAULT_CONFIG_FILENAME)),
            "sources": ["Lsky Pro", "Chevereto", "Lychee", "EasyImg / EasyImage", "ImgURL", "NyaGallery v1"],
            "commands": {
                "to_file": "nyagallery convert --from database --to file --output <sidecar> --confirm",
                "to_database": "nyagallery convert --from file --to database --confirm",
                "lsky": "nyagallery import <lsky.sqlite> --source-type lsky_pro --source-root <uploads> --output <staging> --confirm",
            },
        }

    @app.put("/api/migration/config")
    def api_update_migration_config(update: MigrationModeUpdate, request: Request, _principal: AdminPrincipal) -> dict[str, object]:
        state: AppState = request.app.state.nyagallery
        config_path = state.config.path or Path(DEFAULT_CONFIG_FILENAME)
        backup_path = config_path.with_name(config_path.name + ".bak")
        try:
            if config_path.exists():
                backup_path.write_bytes(config_path.read_bytes())
            data = read_config_file_data(config_path)
            core = dict(data.get("core") or {})
            core["metadata_mode"] = update.metadata_mode
            data["core"] = core
            saved = save_config_file(data, config_path)
            reloaded = load_config(config_path)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.nyagallery = replace(state, config=reloaded)
        return {"metadata_mode": reloaded.core.metadata_mode, "config_path": str(saved.path or config_path), "backup_path": str(backup_path) if backup_path.exists() else None, "restart_required": True}

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

    @app.put("/api/tags/{tag_name}/relations")
    def api_update_tag_relations(
        tag_name: str,
        update: TagRelationsUpdate,
        db: DbSession,
        _principal: AdminPrincipal,
    ) -> dict[str, object]:
        candidate = TagCatalog.from_dict(catalog.to_dict())
        try:
            candidate.set_implications(tag_name, update.implications)
            if update.suggestions is not None:
                candidate.set_suggestions(tag_name, update.suggestions)
            tag = candidate.require(tag_name)
        except (TagNotFoundError, TagAlreadyExistsError, InvalidTagRelationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            refresh_asset_tag_index(db, candidate)
            _save_catalog(storage, candidate)
            db.commit()
        except Exception:
            db.rollback()
            _save_catalog(storage, catalog)
            raise
        catalog.__dict__.update(candidate.__dict__)
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

    @app.post("/api/assets/acl/groups/bulk")
    def api_bind_asset_group_bulk(update: AssetGroupAclBulkUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        group = db.get(ShareGroupModel, update.group_id)
        if group is None or (group.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="share group not found")
        asset_keys = list(dict.fromkeys(key.strip() for key in update.asset_keys if key.strip()))
        if not asset_keys:
            raise HTTPException(status_code=422, detail="asset_keys must not be empty")
        assets = list(db.scalars(select(AssetModel).where(AssetModel.asset_key.in_(asset_keys))).all())
        by_key = {asset.asset_key: asset for asset in assets}
        if len(by_key) != len(asset_keys):
            raise HTTPException(status_code=404, detail="one or more assets not found")
        if any(asset.uploader_user_id != principal.user_id and not principal.has_permission("admin") for asset in assets):
            raise HTTPException(status_code=403, detail="cannot share assets owned by another user")
        existing_keys = set(db.scalars(select(AssetAclModel.asset_key).where(
            AssetAclModel.asset_key.in_(asset_keys), AssetAclModel.subject_type == "group",
            AssetAclModel.subject_id == str(group.id), AssetAclModel.permission == update.permission,
        )).all())
        for key in asset_keys:
            if key not in existing_keys:
                db.add(AssetAclModel(asset_key=key, subject_type="group", subject_id=str(group.id), permission=update.permission))
        db.commit()
        return {"group_id": group.id, "permission": update.permission, "asset_keys": asset_keys, "bound": len(asset_keys)}

    @app.get("/api/assets/{asset_key}/acl/groups")
    def api_list_asset_groups(asset_key: str, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key)
        _require_asset_owner_or_admin(asset, principal)
        rows = db.execute(select(AssetAclModel, ShareGroupModel).join(ShareGroupModel, ShareGroupModel.id == AssetAclModel.subject_id.cast(Integer)).where(AssetAclModel.asset_key == asset.asset_key, AssetAclModel.subject_type == "group").order_by(ShareGroupModel.name.asc(), AssetAclModel.permission.asc())).all()
        return {"items": [{"group_id": acl.subject_id, "group_name": group.name, "permission": acl.permission} for acl, group in rows]}

    @app.post("/api/assets/{asset_key}/acl/groups")
    def api_bind_asset_group(asset_key: str, update: AssetGroupAclUpdate, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key); _require_asset_owner_or_admin(asset, principal)
        group = db.get(ShareGroupModel, update.group_id)
        if group is None or (group.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="share group not found")
        existing = db.scalar(select(AssetAclModel).where(AssetAclModel.asset_key == asset.asset_key, AssetAclModel.subject_type == "group", AssetAclModel.subject_id == str(group.id), AssetAclModel.permission == update.permission))
        if existing is None:
            db.add(AssetAclModel(asset_key=asset.asset_key, subject_type="group", subject_id=str(group.id), permission=update.permission)); db.commit()
        return {"asset_key": asset.asset_key, "group_id": group.id, "permission": update.permission}

    @app.delete("/api/assets/{asset_key}/acl/groups/{group_id}")
    def api_unbind_asset_group(asset_key: str, group_id: int, db: DbSession, principal: EditTagsPrincipal) -> dict[str, object]:
        asset = _get_asset(db, asset_key); _require_asset_owner_or_admin(asset, principal)
        group = db.get(ShareGroupModel, group_id)
        if group is None or (group.owner_user_id != principal.user_id and not principal.has_permission("admin")):
            raise HTTPException(status_code=404, detail="share group not found")
        db.execute(delete(AssetAclModel).where(AssetAclModel.asset_key == asset.asset_key, AssetAclModel.subject_type == "group", AssetAclModel.subject_id == str(group_id))); db.commit()
        return {"asset_key": asset.asset_key, "group_id": group_id, "deleted": True}

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
            media_items = [item.__dict__ for item in MediaGenerator(storage, limits=media_limits).generate_all()]
        result = rebuild_database(db, storage, catalog)
        _save_catalog(storage, catalog)
        return {
            "assets": result.assets,
            "tags": result.tags,
            "duplicates": result.duplicates,
            "posts": result.posts,
            "post_attachments": result.post_attachments,
            "media": media_items,
        }

    @app.post("/api/media/generate")
    def api_generate_media(request: MediaRequest, _db: DbSession, _principal: EditTagsPrincipal) -> dict[str, object]:
        generator = MediaGenerator(storage, limits=media_limits)
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

    @app.get("/api/registration/invites")
    def api_registration_invites(db: DbSession, _principal: AdminPrincipal) -> dict[str, object]:
        return {"items": [registration_invite_to_dict(invite) for invite in list_registration_invites(db)]}

    @app.post("/api/registration/invites")
    def api_create_registration_invite(
        payload: RegistrationInviteCreate,
        request: Request,
        db: DbSession,
        principal: AdminPrincipal,
    ) -> dict[str, object]:
        custom_code = (payload.code or "").strip() or None
        expires_at = now_utc() + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
        try:
            invite, code = create_registration_invite(
                db,
                code=custom_code,
                label=payload.label,
                max_uses=payload.max_uses,
                expires_at=expires_at,
                created_by_user_id=principal.user_id,
                created_by_username=principal.username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _write_operation_log(
            storage,
            request=request,
            identity={
                "user_id": principal.user_id,
                "username": principal.username,
                "role": principal.role,
                "auth_method": getattr(request.state, "nyagallery_auth_method", None),
            },
            client_ip_value=client_ip(request, trust_proxy_headers=False),
            status_code=201,
            action="registration_invite_create",
            detail=f"invite_id={invite.id} max_uses={invite.max_uses}",
        )
        created = registration_invite_to_dict(invite)
        created["code"] = code
        return created

    @app.delete("/api/registration/invites/{invite_id}")
    def api_revoke_registration_invite(
        invite_id: int,
        request: Request,
        db: DbSession,
        principal: AdminPrincipal,
    ) -> dict[str, object]:
        try:
            invite = revoke_registration_invite(db, invite_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _write_operation_log(
            storage,
            request=request,
            identity={
                "user_id": principal.user_id,
                "username": principal.username,
                "role": principal.role,
                "auth_method": getattr(request.state, "nyagallery_auth_method", None),
            },
            client_ip_value=client_ip(request, trust_proxy_headers=False),
            status_code=200,
            action="registration_invite_revoke",
            detail=f"invite_id={invite.id}",
        )
        return registration_invite_to_dict(invite)

    @app.get("/api/security/access-logs")
    def api_access_logs(
        db: DbSession,
        _principal: AdminPrincipal,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: str = "",
        asset_key: str | None = None,
        user_id: Annotated[int | None, Query(ge=1)] = None,
        access_type: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> dict[str, object]:
        after = normalize_timestamp(created_after) if created_after else None
        before = normalize_timestamp(created_before) if created_before else None
        if (created_after and after is None) or (created_before and before is None):
            raise HTTPException(status_code=422, detail="invalid access-log time filter")
        logs = list_access_logs(
            db, limit=limit, offset=offset, q=q, asset_key=asset_key, user_id=user_id,
            access_type=access_type, created_after=datetime.fromisoformat(after.replace("Z", "+00:00")) if after else None,
            created_before=datetime.fromisoformat(before.replace("Z", "+00:00")) if before else None,
        )
        return {
            "items": [access_log_to_dict(log) for log in logs],
            "limit": limit,
            "offset": offset,
            "q": q,
            "asset_key": asset_key,
            "user_id": user_id,
            "access_type": access_type,
            "created_after": after,
            "created_before": before,
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
                "misskey.token",
                "x.auth_token",
                "x.ct0",
                "fanbox.session_id",
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
                "misskey.token",
                "x.auth_token",
                "x.ct0",
                "fanbox.session_id",
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

    @app.post("/api/upload/chunks/init")
    def api_chunk_upload_init(payload: ChunkUploadInit, request: Request, db: DbSession, principal: UploadPrincipal) -> dict[str, object]:
        security_settings = get_security_settings(db)
        max_upload_bytes = int(security_settings.get("max_upload_bytes") or 0)
        if max_upload_bytes > 0 and payload.total_size > max_upload_bytes:
            raise HTTPException(status_code=413, detail="request body too large")
        if payload.total_chunks != (payload.total_size + payload.chunk_size - 1) // payload.chunk_size:
            raise HTTPException(status_code=422, detail="total_chunks does not match chunk_size")
        upload_id = secrets.token_urlsafe(18)
        root = storage.root / "chunked" / upload_id
        root.mkdir(parents=True, exist_ok=False)
        (root / "manifest.json").write_text(json.dumps({"filename": payload.filename, "total_size": payload.total_size, "total_chunks": payload.total_chunks, "chunk_size": payload.chunk_size, "sha256": payload.sha256, "content_type": payload.content_type, "user_id": principal.user_id}, ensure_ascii=True), encoding="utf-8")
        return {"upload_id": upload_id, "total_chunks": payload.total_chunks, "received": []}

    @app.get("/api/upload/chunks/{upload_id}")
    def api_chunk_upload_status(upload_id: str, principal: UploadPrincipal) -> dict[str, object]:
        root = storage.root / "chunked" / upload_id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise HTTPException(status_code=404, detail="upload session not found")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("user_id") != principal.user_id:
            raise HTTPException(status_code=404, detail="upload session not found")
        received = sorted(int(path.stem) for path in root.glob("*.part"))
        chunk_size = int(manifest.get("chunk_size") or 8 * 1024 * 1024)
        return {"upload_id": upload_id, "total_chunks": int(manifest["total_chunks"]), "chunk_size": chunk_size, "received": received}

    @app.put("/api/upload/chunks/{upload_id}/{chunk_index}")
    async def api_chunk_upload_part(upload_id: str, chunk_index: int, request: Request, db: DbSession, principal: UploadPrincipal) -> dict[str, object]:
        if chunk_index < 0:
            raise HTTPException(status_code=422, detail="invalid chunk index")
        root = storage.root / "chunked" / upload_id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise HTTPException(status_code=404, detail="upload session not found")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("user_id") != principal.user_id:
            raise HTTPException(status_code=403, detail="upload session owner required")
        if chunk_index >= int(manifest["total_chunks"]):
            raise HTTPException(status_code=422, detail="chunk index out of range")
        content = await request.body()
        if not content:
            raise HTTPException(status_code=422, detail="empty chunk")
        max_upload_bytes = int(get_security_settings(db).get("max_upload_bytes") or 0)
        if max_upload_bytes > 0 and len(content) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="chunk too large")
        (root / f"{chunk_index:08d}.part").write_bytes(content)
        received = sorted(int(path.stem) for path in root.glob("*.part"))
        return {"upload_id": upload_id, "chunk_index": chunk_index, "received": received}

    @app.post("/api/upload/chunks/{upload_id}/complete")
    async def api_chunk_upload_complete(
        upload_id: str,
        background_tasks: BackgroundTasks,
        db: DbSession,
        principal: UploadPrincipal,
        title: str = Form(""),
        source_id: str | None = Form(None),
        artist_name: str = Form(""),
        canonical_tags: str = Form(""),
        tag_aliases: str = Form(""),
        generate_cache: bool = Form(False),
        storage_strategy: str | None = Form(None),
        original_url: str = Form(""),
        last_modified_ms: str | None = Form(None),
        rotation: int = Form(0),
        crop_left: float = Form(0),
        crop_top: float = Form(0),
        crop_right: float = Form(0),
        crop_bottom: float = Form(0),
        flip_horizontal: bool = Form(False),
        flip_vertical: bool = Form(False),
        exif_policy: str = Form("keep"),
        duplicate_strategy: str = Form("keep"),
    ) -> dict[str, object]:
        root = storage.root / "chunked" / upload_id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise HTTPException(status_code=404, detail="upload session not found")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("user_id") != principal.user_id:
            raise HTTPException(status_code=403, detail="upload session owner required")
        parts = [root / f"{index:08d}.part" for index in range(int(manifest["total_chunks"]))]
        if any(not part.is_file() for part in parts):
            raise HTTPException(status_code=409, detail="upload is missing chunks")
        combined = root / "complete.bin"
        digest = hashlib.sha256()
        total = 0
        with combined.open("wb") as output:
            for part in parts:
                data = part.read_bytes()
                total += len(data)
                digest.update(data)
                output.write(data)
        if total != int(manifest["total_size"]):
            raise HTTPException(status_code=422, detail="uploaded size does not match manifest")
        if manifest.get("sha256") and digest.hexdigest().lower() != str(manifest["sha256"]).lower():
            raise HTTPException(status_code=422, detail="uploaded sha256 does not match manifest")
        with combined.open("rb") as stream:
            upload_file = UploadFile(filename=str(manifest["filename"]), file=stream, size=total, headers={"content-type": str(manifest.get("content_type") or "application/octet-stream")})
            response = await api_upload(background_tasks, db, principal, upload_file, title=title, source_id=source_id, artist_name=artist_name, canonical_tags=canonical_tags, tag_aliases=tag_aliases, generate_cache=generate_cache, storage_strategy=storage_strategy, original_url=original_url, last_modified_ms=last_modified_ms, rotation=rotation, crop_left=crop_left, crop_top=crop_top, crop_right=crop_right, crop_bottom=crop_bottom, flip_horizontal=flip_horizontal, flip_vertical=flip_vertical, exif_policy=exif_policy, duplicate_strategy=duplicate_strategy)
        shutil.rmtree(root, ignore_errors=True)
        return response

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
        original_url: str = Form(""),
        last_modified_ms: str | None = Form(None),
        rotation: int = Form(0),
        crop_left: float = Form(0),
        crop_top: float = Form(0),
        crop_right: float = Form(0),
        crop_bottom: float = Form(0),
        flip_horizontal: bool = Form(False),
        flip_vertical: bool = Form(False),
        exif_policy: str = Form("keep"),
        duplicate_strategy: str = Form("keep"),
    ) -> dict[str, object]:
        if duplicate_strategy not in {"skip", "overwrite", "keep"}:
            raise HTTPException(status_code=422, detail="duplicate_strategy must be skip, overwrite, or keep")
        try:
            original_mtime = browser_mtime(last_modified_ms)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        content = await file.read()
        security_settings = get_security_settings(db)
        max_upload_bytes = int(security_settings.get("max_upload_bytes") or 0)
        if security_settings.get("enabled", True) and max_upload_bytes > 0 and len(content) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="request body too large")
        edited_photo_extra: dict[str, object] | None = None
        if rotation or crop_left or crop_top or crop_right or crop_bottom or flip_horizontal or flip_vertical or exif_policy == "strip":
            try:
                content, edited_photo_extra = edit_uploaded_image(
                    content, mime_type=file.content_type, rotation=rotation,
                    crop_left=crop_left, crop_top=crop_top, crop_right=crop_right, crop_bottom=crop_bottom,
                    flip_horizontal=flip_horizontal, flip_vertical=flip_vertical, exif_policy=exif_policy,
                    default_timezone=app.state.nyagallery.config.media.exif_timezone,
                    fallback_time=original_mtime, fallback_source="browser_last_modified",
                    max_pixels=app.state.nyagallery.config.media.max_image_pixels,
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except ImageEditError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if security_settings.get("enabled", True) and max_upload_bytes > 0 and len(content) > max_upload_bytes:
                raise HTTPException(status_code=413, detail="edited image exceeds upload size limit")
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
        extra.update(edited_photo_extra if edited_photo_extra is not None else extract_photo_metadata(
            stored.path, default_timezone=app.state.nyagallery.config.media.exif_timezone,
            fallback_time=original_mtime, fallback_source="browser_last_modified",
        ))
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
            original_url=original_url,
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
        if duplicate_of:
            existing_asset = db.get(AssetModel, duplicate_of)
            if existing_asset is not None and duplicate_strategy in {"skip", "overwrite"}:
                storage.delete_asset_files(metadata)
                if duplicate_strategy == "skip":
                    db.commit()
                    return _asset_response(storage, existing_asset, catalog) | {"duplicate_of": duplicate_of, "duplicate_strategy": "skip"}
                metadata = replace(
                    metadata,
                    asset_key=existing_asset.asset_key,
                    file_sha256=existing_asset.file_sha256,
                    original_filename=existing_asset.original_filename,
                    original_path=existing_asset.original_path,
                    width=existing_asset.width,
                    height=existing_asset.height,
                    mime_type=existing_asset.mime_type,
                    is_animated=existing_asset.is_animated,
                )
                storage.write_metadata(metadata, replace=True)
                asset = upsert_asset(db, storage, metadata, tags, duplicate_of=existing_asset.duplicate_of)
                duplicate_of = None
            else:
                asset = upsert_asset(db, storage, metadata, tags, duplicate_of=duplicate_of)
        else:
            asset = upsert_asset(db, storage, metadata, tags, duplicate_of=None)
        effective_file_size = _file_size_for_kind(storage, asset, "original") or stored.size
        job_id: str | None = None
        if generate_cache:
            job = create_transcode_job(db, asset, source="upload", file_size=effective_file_size)
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

    @app.post("/api/upload/url")
    async def api_upload_url(
        payload: RemoteUploadRequest,
        background_tasks: BackgroundTasks,
        db: DbSession,
        principal: UploadPrincipal,
    ) -> dict[str, object]:
        security_settings = get_security_settings(db)
        max_upload_bytes = int(security_settings.get("max_upload_bytes") or 0)
        max_download_bytes = min(max_upload_bytes, 100 * 1024 * 1024) if max_upload_bytes > 0 else 100 * 1024 * 1024
        try:
            remote = await run_in_threadpool(fetch_remote_image, payload.url.strip(), max_download_bytes)
        except RemoteImageError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        remote_file = UploadFile(filename=remote.filename, file=io.BytesIO(remote.content), size=len(remote.content), headers={"content-type": remote.content_type})
        try:
            return await api_upload(
                background_tasks,
                db,
                principal,
                remote_file,
                payload.title,
                None,
                payload.artist_name,
                " ".join(payload.canonical_tags),
                "",
                payload.generate_cache,
                payload.storage_strategy,
                payload.url.strip(),
                None,
            )
        finally:
            await remote_file.close()

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

    @app.get("/api/sync/misskey/config")
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

    @app.get("/api/sync/misskey/logs")
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
            "items": [upload_log_to_dict(log) for log in logs],
            "limit": limit,
            "offset": offset,
        }

    @app.post("/api/sync/misskey/user/{username}")
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

    @app.get("/api/sync/fanbox/config")
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

    @app.get("/api/sync/fanbox/logs")
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
        return {"items": [upload_log_to_dict(log) for log in logs], "limit": limit, "offset": offset}

    @app.post("/api/sync/fanbox/login")
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

    @app.post("/api/sync/fanbox/creator/{creator_id}")
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

    @app.post("/api/sync/fanbox/posts")
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

    @app.post("/api/users/{username}/fanbox-session")
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

    @app.get("/api/users/{username}/fanbox-sessions")
    def api_user_fanbox_sessions(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            rows = list_fanbox_sessions(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [fanbox_session_to_dict(row) for row in rows]}

    @app.patch("/api/fanbox-sessions/{session_row_id}")
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

    @app.delete("/api/fanbox-sessions/{session_row_id}")
    def api_revoke_fanbox_session(session_row_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not fanbox_session_belongs_to_user(db, session_row_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            row = revoke_fanbox_session(db, session_row_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return fanbox_session_to_dict(row)

    @app.get("/api/sync/x/config")
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

    @app.get("/api/sync/x/logs")
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
            "items": [upload_log_to_dict(log) for log in logs],
            "limit": limit,
            "offset": offset,
        }

    @app.post("/api/sync/x/posts")
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

    @app.post("/api/sync/x/user/{screen_name}")
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

    @app.post("/api/users/{username}/x-token")
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

    @app.get("/api/users/{username}/x-tokens")
    def api_user_x_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            tokens = list_x_tokens(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [x_token_to_dict(token) for token in tokens]}

    @app.patch("/api/x-tokens/{token_id}")
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

    @app.delete("/api/x-tokens/{token_id}")
    def api_revoke_x_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not x_token_belongs_to_user(db, token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            token = revoke_x_token(db, token_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return x_token_to_dict(token)

    @app.post("/api/users")
    def api_create_user(user: UserCreate, db: DbSession, principal: AdminPrincipal) -> dict[str, object]:
        role = validate_role(user.role)
        if role == "developer" and not _is_developer_principal(principal):
            raise HTTPException(status_code=403, detail="developer users can only be created by developer role or CLI")
        try:
            created = create_user(db, user.username, user.password, role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        requested_scopes = request.scopes if request else None
        if principal.permissions is not None:
            allowed = principal.effective_permissions()
            requested_scopes = sorted(allowed if requested_scopes is None else set(requested_scopes))
            if not set(requested_scopes).issubset(allowed):
                raise HTTPException(status_code=403, detail="token scopes cannot exceed caller scopes")
        token = issue_api_token(
            db,
            username,
            label=request.label if request else "",
            scopes=requested_scopes,
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

    @app.patch("/api/tokens/{token_id}")
    def api_update_token_scopes(
        token_id: int,
        request: TokenScopesUpdate,
        db: DbSession,
        principal: ApiPrincipal,
    ) -> dict[str, object]:
        if not _is_admin_principal(principal) and not api_token_belongs_to_user(db, token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        requested_scopes = request.scopes
        if principal.permissions is not None:
            allowed = principal.effective_permissions()
            requested_scopes = sorted(allowed if requested_scopes is None else set(requested_scopes))
            if not set(requested_scopes).issubset(allowed):
                raise HTTPException(status_code=403, detail="token scopes cannot exceed caller scopes")
        try:
            token = update_api_token_scopes(db, token_id, requested_scopes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_token_to_dict(token)

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

    @app.post("/api/users/{username}/misskey-token")
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

    @app.get("/api/users/{username}/misskey-tokens")
    def api_user_misskey_tokens(username: str, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        _require_self_or_admin(username, principal)
        try:
            tokens = list_misskey_tokens(db, username)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": [misskey_token_to_dict(token) for token in tokens]}

    @app.patch("/api/misskey-tokens/{token_id}")
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

    @app.delete("/api/misskey-tokens/{token_id}")
    def api_revoke_misskey_token(token_id: int, db: DbSession, principal: ApiPrincipal) -> dict[str, object]:
        if not _is_admin_principal(principal) and not misskey_token_belongs_to_user(db, token_id, principal.user_id):
            raise HTTPException(status_code=403, detail="permission denied")
        try:
            token = revoke_misskey_token(db, token_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return misskey_token_to_dict(token)

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
    file_misskey = file_data.get("misskey") if isinstance(file_data.get("misskey"), dict) else {}
    misskey = data.setdefault("misskey", {})
    if misskey.get("token") is None or str(misskey.get("token") or "").strip() == "":
        misskey["token"] = str(file_misskey.get("token") or "")
    file_x = file_data.get("x") if isinstance(file_data.get("x"), dict) else {}
    x_section = data.setdefault("x", {})
    for key in ("auth_token", "ct0"):
        if x_section.get(key) is None or str(x_section.get(key) or "").strip() == "":
            x_section[key] = str(file_x.get(key) or "")
    file_fanbox = file_data.get("fanbox") if isinstance(file_data.get("fanbox"), dict) else {}
    fanbox_section = data.setdefault("fanbox", {})
    if fanbox_section.get("session_id") is None or str(fanbox_section.get("session_id") or "").strip() == "":
        fanbox_section["session_id"] = str(file_fanbox.get("session_id") or "")
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
    return principal.has_permission("admin")


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
    rebuild_result = rebuild_database(db, storage, catalog) if request.rebuild_db or request.generate_cache else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
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
    rebuild_result = rebuild_database(db, storage, catalog) if request.rebuild_db or request.generate_cache else None
    if rebuild_result is not None:
        _save_catalog(storage, catalog)
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
            "queued_transcode_jobs": len([job for job in jobs if job]),
            "rebuild": rebuild_result.__dict__ if rebuild_result else None,
            "options": _misskey_options_log(request),
            "last_update_at": utc_now_iso(),
            **extra,
        },
    )
    db.commit()


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
        generated = MediaGenerator(
            storage,
            limits=media_limits_from_config(load_config().media),
        ).generate_for_metadata(metadata, progress=report)
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
        authenticated = authenticate_api_token_with_scopes(db, token.strip(), record_usage=True, client_ip=client_ip_value)
        if authenticated is None:
            return {"user_id": None, "username": None, "role": None, "auth_method": "bearer"}
        user, scopes = authenticated
        return {"user_id": user.id, "username": user.username, "role": user.role, "permissions": sorted(scopes) if scopes is not None else None, "auth_method": "bearer"}

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
    request.state.nyagallery_permissions = identity.get("permissions")
    request.state.nyagallery_csrf_token = identity.get("csrf_token")


def _security_rejection_reason(
    request: Request,
    settings: dict[str, object],
    identity: dict[str, object],
    request_bytes: int,
) -> str | None:
    if settings.get("bot_protection_enabled", False):
        user_agent = request.headers.get("user-agent", "").casefold()
        blocked_agents = [str(value).strip().casefold() for value in settings.get("bot_blocked_user_agents", []) if str(value).strip()]
        if any(value in user_agent for value in blocked_agents):
            return "bot user-agent blocked"
        ip = client_ip(request, trust_proxy_headers=bool(settings.get("trust_proxy_headers")))
        blocked_ips = {str(value).strip() for value in settings.get("bot_blocked_ips", []) if str(value).strip()}
        if ip in blocked_ips:
            return "bot IP blocked"

    if request.method.upper() in UNSAFE_METHODS:
        max_upload_bytes = int(settings.get("max_upload_bytes") or 0)
        if max_upload_bytes > 0 and request_bytes > max_upload_bytes:
            return "request body too large"
        if identity.get("auth_method") == "session" and request.url.path not in UNAUTHENTICATED_CSRF_EXEMPT_PATHS:
            expected = str(identity.get("csrf_token") or "")
            actual = request.headers.get(CSRF_HEADER, "")
            if not expected or not secrets.compare_digest(actual, expected):
                return "csrf token invalid"
        if (
            settings.get("csrf_origin_check_enabled", True)
            and identity.get("auth_method") != "session"
            and request.url.path not in UNAUTHENTICATED_CSRF_EXEMPT_PATHS
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
    if reason in {"csrf origin denied", "csrf token invalid", "viewer API path is not whitelisted", "bot user-agent blocked", "bot IP blocked"}:
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


def _get_entity(db: Session, entity_id: int, principal: Principal) -> EntityModel:
    row = db.get(EntityModel, entity_id)
    if row is None or (row.owner_user_id != principal.user_id and not principal.has_permission("admin")):
        raise HTTPException(status_code=404, detail="entity not found")
    return row


def _entity_to_dict(db: Session, row: EntityModel) -> dict[str, object]:
    links = db.scalars(select(EntityAssetLinkModel).where(EntityAssetLinkModel.entity_id == row.id).order_by(EntityAssetLinkModel.id.asc())).all()
    return {"id": row.id, "type": row.type, "entity_id": row.entity_id, "name": row.name, "metadata": row.metadata_json, "owner_user_id": row.owner_user_id, "asset_keys": [link.asset_key for link in links], "created_at": row.created_at, "updated_at": row.updated_at}


def _get_share_album(db: Session, album_id: int, principal: Principal) -> ShareAlbumModel:
    album = db.get(ShareAlbumModel, album_id)
    if album is None or (album.owner_user_id != principal.user_id and not principal.has_permission("admin")):
        raise HTTPException(status_code=404, detail="share album not found")
    return album


def _share_album_to_dict(db: Session, album: ShareAlbumModel) -> dict[str, object]:
    assets = db.scalars(select(ShareAlbumAssetModel).where(ShareAlbumAssetModel.album_id == album.id).order_by(ShareAlbumAssetModel.id.asc())).all()
    groups = db.execute(select(ShareAlbumGroupModel, ShareGroupModel).join(ShareGroupModel, ShareGroupModel.id == ShareAlbumGroupModel.group_id).where(ShareAlbumGroupModel.album_id == album.id).order_by(ShareGroupModel.name.asc())).all()
    return {"id": album.id, "owner_user_id": album.owner_user_id, "name": album.name, "description": album.description, "asset_keys": [row.asset_key for row in assets], "groups": [{"group_id": row.group_id, "group_name": group.name, "permission": row.permission} for row, group in groups], "created_at": album.created_at, "updated_at": album.updated_at}


def _access_log_asset_context(path: str) -> tuple[str | None, str | None]:
    parts = [unquote(part) for part in path.strip("/").split("/")]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "assets":
        kind = parts[3] if len(parts) >= 4 else "metadata"
        if kind in {"original", "preview", "thumb"}:
            return parts[2], kind
        if kind == "api-examples":
            return parts[2], "api_examples"
        return parts[2], "metadata"
    if len(parts) >= 2 and parts[0] == "s":
        return None, "short_link"
    if len(parts) >= 2 and parts[0] == "api" and parts[1] == "share":
        return None, "share_link"
    return None, None


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
    asset_key, access_type = _access_log_asset_context(request.url.path)
    record = {
        "client_ip": client_ip_value,
        "user_id": identity.get("user_id") if isinstance(identity.get("user_id"), int) else None,
        "username": str(identity.get("username")) if identity.get("username") else None,
        "role": str(identity.get("role")) if identity.get("role") else None,
        "asset_key": asset_key,
        "access_type": access_type,
        "method": request.method.upper(),
        "path": request.url.path,
        "query_string": request.url.query,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "request_bytes": request_bytes,
        "response_bytes": response_bytes,
        "user_agent": request.headers.get("user-agent", ""),
        "referer": request.headers.get("referer", ""),
        "origin": request.headers.get("origin", ""),
        "rejection_reason": rejection_reason,
        "error": error,
        "retention": int(settings.get("access_log_retention") or 5000),
    }
    if state.access_log_queue is not None:
        try:
            state.access_log_queue.put_nowait(record)
        except queue.Full:
            # Access logs are best-effort telemetry; never make a request wait
            # for an audit database writer during a burst.
            pass
        return
    try:
        with state.session_factory() as session:
            create_access_log(session, **record)
            session.commit()
    except Exception as exc:
        print(f"failed to record access log: {exc}")


def _access_log_worker(
    session_factory: sessionmaker[Session],
    records: queue.Queue[dict[str, object]],
    stop: threading.Event,
) -> None:
    last_prune = time.monotonic()
    pending_since_prune = 0
    while not stop.is_set() or not records.empty():
        try:
            first = records.get(timeout=0.5)
        except queue.Empty:
            continue
        batch = [first]
        while len(batch) < 128:
            try:
                batch.append(records.get_nowait())
            except queue.Empty:
                break
        try:
            with session_factory() as session:
                retentions = [int(item.get("retention") or 0) for item in batch]
                for item in batch:
                    create_access_log(session, **item, prune=False, flush=False)
                session.flush()
                pending_since_prune += len(batch)
                now = time.monotonic()
                positive_retentions = [value for value in retentions if value > 0]
                if positive_retentions and (now - last_prune >= 60 or pending_since_prune >= 256):
                    _prune_access_logs(session, min(positive_retentions))
                    last_prune = now
                    pending_since_prune = 0
                session.commit()
        except Exception as exc:
            print(f"failed to flush access logs: {exc}")


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
    raw_permissions = getattr(request.state, "nyagallery_permissions", None)
    permissions = frozenset(raw_permissions) if isinstance(raw_permissions, (list, tuple, set, frozenset)) else None
    return Principal(str(username), str(role), user_id if isinstance(user_id, int) else None, permissions)


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
                if state_principal.has_permission(permission):
                    return state_principal
                raise HTTPException(status_code=403, detail="permission denied")
            authenticated = authenticate_api_token_with_scopes(db, credentials.credentials)
            if authenticated:
                user, scopes = authenticated
                principal = Principal(user.username, user.role, user.id, scopes)
                if principal.has_permission(permission):
                    return principal
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
            raise HTTPException(
                status_code=401,
                detail="no users exist yet; create the first account with `nyagallery setup` on the server",
            )
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


def _share_link_by_token(db: Session, token: str) -> ShareLinkModel:
    digest = hash_secret(token)
    row = db.scalar(select(ShareLinkModel).where(ShareLinkModel.token_hash == digest))
    if row is None:
        raise HTTPException(status_code=404, detail="share link not found")
    return row


def _validate_share_access(row: ShareLinkModel, asset: AssetModel, password: str | None) -> None:
    if row.revoked_at is not None:
        raise HTTPException(status_code=410, detail="share link revoked")
    if row.expires_at is not None and aware_utc(row.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="share link expired")
    if row.password_hash and not password:
        raise HTTPException(status_code=401, detail="share link password required")
    if row.password_hash and not verify_secret(password or "", row.password_hash):
        raise HTTPException(status_code=403, detail="share link password invalid")
    guest = Principal("guest", "guest")
    _require_sensitive_view(asset, guest)


def _record_share_access(db: Session, row: ShareLinkModel, request: Request, status: str) -> None:
    ip = request.client.host if request.client else ""
    db.add(ShareAccessLogModel(share_link_id=row.id, asset_key=row.asset_key, status=status, client_ip=ip[:80], user_agent=request.headers.get("user-agent", "")[:300]))
    row.last_access_at = datetime.now(timezone.utc); row.access_count = int(row.access_count or 0) + 1; db.commit()


def _get_asset(db: Session, asset_key: str) -> AssetModel:
    asset = db.get(AssetModel, asset_key)
    if asset is None or asset.deletion_status is not None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


def _replace_share_group_members(db: Session, group_id: int, usernames: list[str]) -> None:
    existing = list(db.scalars(select(ShareGroupMemberModel).where(ShareGroupMemberModel.group_id == group_id)).all())
    for member in existing:
        db.delete(member)
    normalized = sorted({str(username).strip() for username in usernames if str(username).strip()})
    if not normalized:
        return
    users = list(db.scalars(select(UserModel).where(UserModel.username.in_(normalized), UserModel.is_active.is_(True))).all())
    found = {user.username for user in users}
    missing = sorted(set(normalized) - found)
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown users: {', '.join(missing)}")
    for user in users:
        db.add(ShareGroupMemberModel(group_id=group_id, user_id=user.id))


def _access_group_to_dict(db: Session, group: ShareGroupModel) -> dict[str, object]:
    members = db.execute(
        select(UserModel, ShareGroupMemberModel.role)
        .join(ShareGroupMemberModel, ShareGroupMemberModel.user_id == UserModel.id)
        .where(ShareGroupMemberModel.group_id == group.id)
        .order_by(UserModel.username.asc())
    ).all()
    return {
        "id": group.id,
        "name": group.name,
        "owner_user_id": group.owner_user_id,
        "members": [{"id": user.id, "username": user.username, "role": role} for user, role in members],
    }


def _share_group_role(db: Session, group: ShareGroupModel, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    if group.owner_user_id == user_id:
        return "owner"
    return db.scalar(select(ShareGroupMemberModel.role).where(ShareGroupMemberModel.group_id == group.id, ShareGroupMemberModel.user_id == user_id))


def _can_manage_share_group(db: Session, group: ShareGroupModel, principal: Principal) -> bool:
    if principal.has_permission("admin") or group.owner_user_id == principal.user_id:
        return True
    return db.scalar(select(ShareGroupMemberModel.id).where(
        ShareGroupMemberModel.group_id == group.id,
        ShareGroupMemberModel.user_id == principal.user_id,
        ShareGroupMemberModel.role == "admin",
    )) is not None


def _asset_comment_to_dict(db: Session, row: AssetCommentModel) -> dict[str, object]:
    mentions = db.scalars(select(AssetMentionModel).where(AssetMentionModel.comment_id == row.id).order_by(AssetMentionModel.id)).all()
    return {"id": row.id, "asset_key": row.asset_key, "user_id": row.user_id, "username": row.username, "body": row.body, "created_at": row.created_at, "updated_at": row.updated_at, "mentions": [{"user_id": item.user_id, "username": item.username} for item in mentions]}


def _replace_asset_comment_mentions(db: Session, comment_id: int, body: str, *, actor_user_id: int | None, asset_key: str) -> None:
    db.query(AssetMentionModel).filter(AssetMentionModel.comment_id == comment_id).delete(synchronize_session=False)
    db.query(NotificationModel).filter(NotificationModel.comment_id == comment_id, NotificationModel.kind == "comment_mention").delete(synchronize_session=False)
    usernames = {match.lower() for match in re.findall(r"@([A-Za-z0-9][A-Za-z0-9_.-]{0,79})", body)}
    if not usernames:
        return
    users = db.scalars(select(UserModel).where(func.lower(UserModel.username).in_(usernames), UserModel.is_active.is_(True))).all()
    for user in users:
        db.add(AssetMentionModel(comment_id=comment_id, user_id=user.id, username=user.username))
        preference = db.get(NotificationPreferenceModel, user.id)
        if actor_user_id != user.id and (preference is None or preference.mention_enabled):
            db.add(NotificationModel(recipient_user_id=user.id, actor_user_id=actor_user_id, kind="comment_mention", asset_key=asset_key, comment_id=comment_id, message="You were mentioned in an asset comment"))


def _principal_owns_asset(asset: AssetModel, principal: Principal) -> bool:
    if _is_admin_principal(principal):
        return True
    if principal.user_id is not None and asset.uploader_user_id == principal.user_id:
        return True
    return asset.uploader_user_id is None and bool(asset.uploader_username) and asset.uploader_username.casefold() == principal.username.casefold()


def _require_asset_access(db: Session, asset: AssetModel, principal: Principal) -> None:
    if _principal_owns_asset(asset, principal):
        return
    if not can_view_asset(db, asset, user_id=principal.user_id, is_admin=_is_admin_principal(principal)):
        raise HTTPException(status_code=404, detail="asset not found")


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


def _hidden_post_ratings(principal: Principal) -> tuple[str, ...]:
    if principal.role != "guest":
        return ()
    return tuple(sorted(tag.split(":", 1)[1] for tag in SENSITIVE_RATING_TAGS))


def _require_sensitive_post_view(post: PostModel, principal: Principal) -> None:
    if post.age_rating and post.age_rating in _hidden_post_ratings(principal):
        raise HTTPException(status_code=403, detail="viewer role required for sensitive content")


def _index_posts_on_startup(session: Session, post_store: PostStore) -> int:
    asset_keys = list(
        session.scalars(
            select(AssetModel.asset_key)
            .where(AssetModel.deletion_status.is_(None))
            .order_by(AssetModel.asset_key)
            .limit(3)
        ).all()
    )
    seeded = ensure_sample_posts(post_store, asset_keys=asset_keys)
    linked = link_sample_post_media(post_store, asset_keys=asset_keys)
    indexed = int(session.scalar(select(func.count()).select_from(PostModel)) or 0)
    if seeded or linked or (indexed == 0 and not post_store.is_empty()):
        result = rebuild_posts(session, post_store, replace=True)
        session.commit()
        return result.posts
    return 0


def _require_sensitive_view(asset: AssetModel, principal: Principal) -> None:
    if principal.role != "guest":
        return
    if (str(asset.age_rating or "").casefold() in SENSITIVE_RATINGS) or any(
        tag.tag in SENSITIVE_RATING_TAGS for tag in asset.tags
    ):
        raise HTTPException(status_code=403, detail="viewer role required for sensitive content")


def _can_view_asset(asset: AssetModel, principal: Principal) -> bool:
    if asset.deletion_status is not None:
        return False
    if principal.role != "guest":
        return True
    return not (
        str(asset.age_rating or "").casefold() in SENSITIVE_RATINGS
        or any(tag.tag in SENSITIVE_RATING_TAGS for tag in asset.tags)
    )


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
    try:
        path, _filename = _asset_file_path(storage, asset, kind)
        return path.stat().st_size if path.exists() else None
    except (HTTPException, OSError, StorageError):
        return None


def _file_response(storage: GalleryStorage, asset: AssetModel, kind: str) -> FileResponse:
    path, filename = _asset_file_path(storage, asset, kind)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{kind} file not found")
    resp = FileResponse(path, filename=filename, media_type=_media_type_for_path(path))
    resp.headers["Content-Disposition"] = _inline_content_disposition(filename)
    resp.headers["X-Asset-Key"] = asset.asset_key
    resp.headers["Cache-Control"] = CACHE_FILE_CACHE_CONTROL if kind in {"preview", "thumb"} else ORIGINAL_CACHE_CONTROL
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
            or _cache_fallback_original(storage, asset)
        )
        filename = path.name
    else:
        path = (
            _existing_path(storage, asset.preview_path)
            or _existing_preview_path(storage, asset.asset_key)
            or _existing_path(storage, asset.thumb_path)
            or _cache_fallback_original(storage, asset)
        )
        filename = path.name
    return path, filename


def _cache_fallback_original(storage: GalleryStorage, asset: AssetModel) -> Path:
    """Serving a whole video as its own thumbnail downloads megabytes per tile, so ask for a cover instead."""
    if str(asset.mime_type or "").casefold().startswith("video/"):
        raise HTTPException(status_code=404, detail="no cover generated for this video yet")
    return storage.resolve_relative_path(asset.original_path)


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
    if suffix in {".mp4", ".m4v"}:
        return "video/mp4"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".mov":
        return "video/quicktime"
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
