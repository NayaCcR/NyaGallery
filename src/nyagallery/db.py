from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
import uuid
from types import SimpleNamespace

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, event, exists, func, inspect, or_, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from nyagallery.auth import (
    generate_api_token,
    generate_csrf_token,
    generate_session_token,
    hash_opaque_token,
    hash_password,
    hash_secret,
    token_prefix,
    validate_role,
    verify_opaque_token,
    verify_password,
    verify_secret,
)
from nyagallery.metadata import GalleryMetadata
from nyagallery.metadata import utc_now_iso
from nyagallery.posts import GalleryPost, PostStore
from nyagallery.security import normalize_security_settings
from nyagallery.secret_crypto import decrypt_secret, encrypt_secret, is_encrypted_secret, secret_encryption_enabled
from nyagallery.storage import GalleryStorage
from nyagallery.tags import HIDDEN_TAG, SearchQuery, TagCatalog, is_hidden_tag, normalize_name, source_tag_details_from_extra, source_tag_name, tag_sort_key


ASSET_SORT_ALIASES = {
    "key": "asset_key",
    "asset": "asset_key",
    "date": "artwork_date",
    "created_date": "artwork_date",
    "pixiv_date": "artwork_date",
    "upload_time": "uploaded_at",
    "upload": "uploaded_at",
    "created_at": "uploaded_at",
    "crawl_time": "uploaded_at",
    "filename": "original_filename",
    "file": "original_filename",
}
ASSET_SORT_KEYS = {
    "asset_key",
    "artwork_date",
    "pixiv_upload_date",
    "uploaded_at",
    "original_filename",
    "title",
    "artist",
    "source",
    "source_id",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def sqlite_url(path: str | Path) -> str:
    return f"sqlite:///{Path(path).resolve().as_posix()}"


def default_database_url(storage: GalleryStorage) -> str:
    return sqlite_url(storage.root / "nyagallery.db")


class Base(DeclarativeBase):
    pass


class AssetModel(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("source", "source_id", "page_index", name="uq_asset_source_page"),
    )

    asset_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(120), index=True)
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    artist_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    artist_name: Mapped[str] = mapped_column(String(240), default="")
    original_url: Mapped[str] = mapped_column(String(1000), default="")
    crawl_time: Mapped[str] = mapped_column(String(80), default="")
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str] = mapped_column(String(300))
    original_path: Mapped[str] = mapped_column(String(1000))
    preview_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pixiv_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    canonical_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    artwork_date: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    pixiv_upload_date: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    age_rating: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    is_ai_generated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_animated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploader_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deletion_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(String(160), ForeignKey("assets.asset_key"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    tags: Mapped[list["AssetTagModel"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AssetTagModel(Base):
    __tablename__ = "asset_tags"

    asset_key: Mapped[str] = mapped_column(String(160), ForeignKey("assets.asset_key", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(240), primary_key=True, index=True)

    asset: Mapped[AssetModel] = relationship(back_populates="tags")


class PostModel(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_post_source_id"),
    )

    post_key: Mapped[str] = mapped_column(String(180), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(180), index=True)
    author_id: Mapped[str] = mapped_column(String(180), default="", index=True)
    author_name: Mapped[str] = mapped_column(String(240), default="")
    author_handle: Mapped[str] = mapped_column(String(240), default="", index=True)
    author_avatar_url: Mapped[str] = mapped_column(String(1000), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    content_warning: Mapped[str] = mapped_column(String(1000), default="")
    posted_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    crawl_time: Mapped[str] = mapped_column(String(80), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    visibility: Mapped[str] = mapped_column(String(40), default="public")
    age_rating: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    canonical_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reply_to_url: Mapped[str] = mapped_column(String(1000), default="")
    repost_of_url: Mapped[str] = mapped_column(String(1000), default="")
    quote_of_url: Mapped[str] = mapped_column(String(1000), default="")
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    attachments: Mapped[list["PostAttachmentModel"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PostAttachmentModel.position",
    )


class PostAttachmentModel(Base):
    __tablename__ = "post_attachments"

    post_key: Mapped[str] = mapped_column(String(180), ForeignKey("posts.post_key", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    remote_url: Mapped[str] = mapped_column(String(1000), default="")
    thumbnail_url: Mapped[str] = mapped_column(String(1000), default="")
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String(1000), default="")
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)

    post: Mapped[PostModel] = relationship(back_populates="attachments")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    api_token_prefix: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    api_token_hash: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserTokenModel(Base):
    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(500))
    label: Mapped[str] = mapped_column(String(160), default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PixivTokenModel(Base):
    __tablename__ = "pixiv_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token: Mapped[str] = mapped_column(String(4000))
    refresh_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_prefix: Mapped[str] = mapped_column(String(32), index=True)
    token_suffix: Mapped[str] = mapped_column(String(32), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    pixiv_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    pixiv_account: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pixiv_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PixivCookieModel(Base):
    __tablename__ = "pixiv_cookies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cookie: Mapped[str] = mapped_column(String(100_000))
    cookie_hash: Mapped[str] = mapped_column(String(64), index=True)
    cookie_prefix: Mapped[str] = mapped_column(String(32), index=True)
    cookie_suffix: Mapped[str] = mapped_column(String(32), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    pixiv_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    pixiv_account: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pixiv_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MisskeyTokenModel(Base):
    __tablename__ = "misskey_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(4000))
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_prefix: Mapped[str] = mapped_column(String(32), index=True)
    token_suffix: Mapped[str] = mapped_column(String(32), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    host: Mapped[str] = mapped_column(String(240), default="misskey.io", index=True)
    misskey_user_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    misskey_username: Mapped[str | None] = mapped_column(String(240), nullable=True)
    misskey_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class XTokenModel(Base):
    __tablename__ = "x_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(4000))
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_prefix: Mapped[str] = mapped_column(String(32), index=True)
    token_suffix: Mapped[str] = mapped_column(String(32), default="")
    ct0: Mapped[str] = mapped_column(String(4000), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    host: Mapped[str] = mapped_column(String(240), default="x.com", index=True)
    x_user_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    x_screen_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    x_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FanboxSessionModel(Base):
    __tablename__ = "fanbox_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(4000))
    session_hash: Mapped[str] = mapped_column(String(64), index=True)
    session_prefix: Mapped[str] = mapped_column(String(32), index=True)
    session_suffix: Mapped[str] = mapped_column(String(32), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    fanbox_user_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    fanbox_creator_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    fanbox_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LoginSessionModel(Base):
    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    session_hash: Mapped[str] = mapped_column(String(64))
    csrf_token: Mapped[str] = mapped_column(String(120))
    user_agent: Mapped[str] = mapped_column(String(1000), default="")
    client_ip: Mapped[str] = mapped_column(String(120), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TranscodeJobModel(Base):
    __tablename__ = "transcode_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    asset_key: Mapped[str] = mapped_column(String(160), ForeignKey("assets.asset_key", ondelete="CASCADE"), index=True)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(String(500), default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    frames_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="upload")
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UploadLogModel(Base):
    __tablename__ = "upload_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_key: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event: Mapped[str] = mapped_column(String(80), default="upload")
    status: Mapped[str] = mapped_column(String(40), default="success", index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AccessLogModel(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_ip: Mapped[str] = mapped_column(String(120), default="", index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(16), default="", index=True)
    path: Mapped[str] = mapped_column(String(1000), default="", index=True)
    query_string: Mapped[str] = mapped_column(String(1000), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    request_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(1000), default="")
    referer: Mapped[str] = mapped_column(String(1000), default="")
    origin: Mapped[str] = mapped_column(String(1000), default="")
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class SecuritySettingsModel(Base):
    __tablename__ = "security_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


@dataclass(frozen=True)
class RebuildResult:
    assets: int
    tags: int
    duplicates: int
    posts: int = 0
    post_attachments: int = 0


@dataclass(frozen=True)
class PostRebuildResult:
    posts: int
    attachments: int


@dataclass(frozen=True)
class SourceTagBackfillResult:
    assets: int
    tags: int
    labels: int


def create_engine_for_url(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite:") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                for pragma in ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL"):
                    try:
                        cursor.execute(pragma)
                    except Exception:
                        pass
            finally:
                cursor.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, class_=Session)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_column(engine, "assets", "uploader_user_id", "INTEGER")
    _ensure_column(engine, "assets", "uploader_username", "VARCHAR(80)")
    _ensure_column(engine, "assets", "deletion_status", "VARCHAR(40)")
    _ensure_column(engine, "assets", "deleted_at", "VARCHAR(80)")
    _ensure_column(engine, "assets", "deleted_by_user_id", "INTEGER")
    _ensure_column(engine, "assets", "deleted_by_username", "VARCHAR(80)")
    _ensure_column(engine, "assets", "artwork_date", "VARCHAR(40)")
    _ensure_column(engine, "assets", "pixiv_upload_date", "VARCHAR(40)")
    _ensure_column(engine, "assets", "source_type", "VARCHAR(40)")
    _ensure_column(engine, "assets", "age_rating", "VARCHAR(40)")
    _ensure_column(engine, "assets", "is_ai_generated", "BOOLEAN")
    _ensure_column(engine, "assets", "is_animated", "BOOLEAN")
    _ensure_column(engine, "assets", "extra", "JSON")
    _ensure_column(engine, "user_tokens", "last_used_at", "DATETIME")
    _ensure_column(engine, "user_tokens", "last_used_ip", "VARCHAR(120)")
    _ensure_column(engine, "upload_logs", "asset_key", "VARCHAR(160)")
    _ensure_column(engine, "upload_logs", "uploader_user_id", "INTEGER")
    _ensure_column(engine, "upload_logs", "uploader_username", "VARCHAR(80)")
    _ensure_column(engine, "upload_logs", "original_filename", "VARCHAR(500)")
    _ensure_column(engine, "upload_logs", "file_size", "INTEGER")
    _ensure_column(engine, "upload_logs", "mime_type", "VARCHAR(120)")
    _ensure_column(engine, "upload_logs", "event", "VARCHAR(80)")
    _ensure_column(engine, "upload_logs", "status", "VARCHAR(40)")
    _ensure_column(engine, "upload_logs", "message", "VARCHAR(500)")
    _ensure_column(engine, "upload_logs", "extra", "JSON")
    _ensure_column(engine, "upload_logs", "created_at", "DATETIME")
    _ensure_column(engine, "transcode_jobs", "job_id", "VARCHAR(80)")
    _ensure_column(engine, "transcode_jobs", "asset_key", "VARCHAR(160)")
    _ensure_column(engine, "transcode_jobs", "uploader_user_id", "INTEGER")
    _ensure_column(engine, "transcode_jobs", "uploader_username", "VARCHAR(80)")
    _ensure_column(engine, "transcode_jobs", "status", "VARCHAR(40)")
    _ensure_column(engine, "transcode_jobs", "stage", "VARCHAR(80)")
    _ensure_column(engine, "transcode_jobs", "message", "VARCHAR(500)")
    _ensure_column(engine, "transcode_jobs", "progress", "FLOAT")
    _ensure_column(engine, "transcode_jobs", "frames_done", "INTEGER")
    _ensure_column(engine, "transcode_jobs", "frames_total", "INTEGER")
    _ensure_column(engine, "transcode_jobs", "frames_per_second", "FLOAT")
    _ensure_column(engine, "transcode_jobs", "file_size", "INTEGER")
    _ensure_column(engine, "transcode_jobs", "kind", "VARCHAR(40)")
    _ensure_column(engine, "transcode_jobs", "source", "VARCHAR(40)")
    _ensure_column(engine, "transcode_jobs", "error", "VARCHAR(1000)")
    _ensure_column(engine, "transcode_jobs", "created_at", "DATETIME")
    _ensure_column(engine, "transcode_jobs", "started_at", "DATETIME")
    _ensure_column(engine, "transcode_jobs", "stage_started_at", "DATETIME")
    _ensure_column(engine, "transcode_jobs", "finished_at", "DATETIME")
    _ensure_column(engine, "transcode_jobs", "updated_at", "DATETIME")


def rebuild_database(
    session: Session,
    storage: GalleryStorage,
    catalog: TagCatalog,
    *,
    replace: bool = True,
) -> RebuildResult:
    storage.ensure()
    if replace:
        session.execute(update(AssetModel).values(duplicate_of=None))
        session.execute(delete(AssetTagModel))
        session.execute(delete(AssetModel))
        session.flush()

    seen_sha: dict[str, str] = {}
    asset_count = 0
    tag_count = 0
    duplicate_count = 0
    for metadata in storage.iter_metadata():
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
        duplicate_of = seen_sha.get(metadata.file_sha256)
        if duplicate_of is None and not replace:
            duplicate_of = session.scalar(
                select(AssetModel.asset_key).where(
                    AssetModel.file_sha256 == metadata.file_sha256,
                    AssetModel.asset_key != metadata.asset_key,
                )
            )
        asset = upsert_asset(session, storage, metadata, tags, duplicate_of=duplicate_of)
        if duplicate_of:
            duplicate_count += 1
        else:
            seen_sha[asset.file_sha256] = asset.asset_key
        asset_count += 1
        tag_count += len(tags)

    posts = rebuild_posts(session, PostStore(storage.root), replace=replace)
    session.commit()
    return RebuildResult(asset_count, tag_count, duplicate_count, posts.posts, posts.attachments)


def rebuild_posts(session: Session, store: PostStore, *, replace: bool = True) -> PostRebuildResult:
    store.ensure()
    if replace:
        session.execute(delete(PostAttachmentModel))
        session.execute(delete(PostModel))
        session.flush()

    post_count = 0
    attachment_count = 0
    for post in store.iter_posts():
        row = upsert_post(session, post)
        post_count += 1
        attachment_count += len(row.attachments)
    return PostRebuildResult(post_count, attachment_count)


def upsert_post(session: Session, post: GalleryPost) -> PostModel:
    row = session.get(PostModel, post.post_key)
    if row is None:
        row = PostModel(post_key=post.post_key)
        session.add(row)

    row.source = post.source
    row.source_id = post.source_id
    row.author_id = post.author_id
    row.author_name = post.author_name
    row.author_handle = post.author_handle
    row.author_avatar_url = post.author_avatar_url
    row.content = post.content
    row.content_warning = post.content_warning
    row.posted_at = post.posted_at or None
    row.crawl_time = post.crawl_time
    row.source_url = post.source_url
    row.language = post.language
    row.visibility = post.visibility
    row.age_rating = post.age_rating
    row.tags = list(post.tags)
    row.canonical_tags = list(post.canonical_tags)
    row.metrics = dict(post.metrics) or None
    row.extra = post.extra or None
    row.reply_to_url = post.reply_to_url
    row.repost_of_url = post.repost_of_url
    row.quote_of_url = post.quote_of_url
    row.attachment_count = len(post.attachments)
    row.updated_at = now_utc()
    row.attachments = [
        PostAttachmentModel(
            post_key=post.post_key,
            position=position,
            asset_key=attachment.asset_key,
            remote_url=attachment.remote_url,
            thumbnail_url=attachment.thumbnail_url,
            mime_type=attachment.mime_type,
            width=attachment.width,
            height=attachment.height,
            description=attachment.description,
            is_sensitive=attachment.is_sensitive,
        )
        for position, attachment in enumerate(post.attachments)
    ]
    session.flush()
    return row


POST_SORT_KEYS = {"posted_at", "added"}


def normalize_post_sort(sort: str | None) -> str:
    key = str(sort or "").strip().casefold()
    if key in {"added", "crawl_time", "archived"}:
        return "added"
    return "posted_at"


def list_posts(
    session: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    source: str = "",
    q: str = "",
    sort: str = "posted_at",
    order: str = "desc",
    exclude_ratings: Iterable[str] = (),
) -> list[PostModel]:
    statement = _apply_post_filters(select(PostModel), source=source, q=q, exclude_ratings=exclude_ratings)
    descending = normalize_sort_order(order) == "desc"
    # crawl_time survives a rebuild because it lives in the post JSON; created_at is reset by it.
    column = PostModel.crawl_time if normalize_post_sort(sort) == "added" else PostModel.posted_at
    if descending:
        statement = statement.order_by(column.is_(None).asc(), column.desc(), PostModel.post_key.desc())
    else:
        statement = statement.order_by(column.is_(None).desc(), column.asc(), PostModel.post_key.asc())
    return list(session.scalars(statement.limit(limit).offset(offset)).unique().all())


def count_posts(
    session: Session,
    *,
    source: str = "",
    q: str = "",
    exclude_ratings: Iterable[str] = (),
) -> int:
    statement = _apply_post_filters(
        select(func.count()).select_from(PostModel),
        source=source,
        q=q,
        exclude_ratings=exclude_ratings,
    )
    return int(session.scalar(statement) or 0)


def get_post(session: Session, post_key: str) -> PostModel | None:
    return session.get(PostModel, post_key)


def post_source_counts(session: Session, *, exclude_ratings: Iterable[str] = ()) -> list[dict[str, object]]:
    statement = _apply_post_filters(
        select(PostModel.source, func.count()).group_by(PostModel.source),
        exclude_ratings=exclude_ratings,
    )
    rows = session.execute(statement).all()
    return [
        {"source": source, "count": int(count)}
        for source, count in sorted(rows, key=lambda row: (-int(row[1]), str(row[0])))
    ]


def posts_attachment_asset_map(session: Session, posts: Iterable[PostModel]) -> dict[str, AssetModel]:
    asset_keys = {
        attachment.asset_key
        for post in posts
        for attachment in post.attachments
        if attachment.asset_key
    }
    if not asset_keys:
        return {}
    statement = select(AssetModel).where(
        AssetModel.asset_key.in_(sorted(asset_keys)),
        AssetModel.deletion_status.is_(None),
    )
    return {asset.asset_key: asset for asset in session.scalars(statement).unique().all()}


def post_to_dict(post: PostModel, *, assets: dict[str, AssetModel] | None = None) -> dict[str, object]:
    return {
        "post_key": post.post_key,
        "source": post.source,
        "source_id": post.source_id,
        "author_id": post.author_id,
        "author_name": post.author_name,
        "author_handle": post.author_handle,
        "author_avatar_url": post.author_avatar_url,
        "content": post.content,
        "content_warning": post.content_warning,
        "posted_at": post.posted_at,
        "crawl_time": post.crawl_time,
        "source_url": post.source_url,
        "language": post.language,
        "visibility": post.visibility,
        "age_rating": post.age_rating,
        "tags": list(post.tags or []),
        "canonical_tags": list(post.canonical_tags or []),
        "metrics": dict(post.metrics or {}),
        "extra": dict(post.extra or {}),
        "reply_to_url": post.reply_to_url,
        "repost_of_url": post.repost_of_url,
        "quote_of_url": post.quote_of_url,
        "attachment_count": post.attachment_count,
        "attachments": [
            _post_attachment_to_dict(attachment, assets or {})
            for attachment in sorted(post.attachments, key=lambda item: item.position)
        ],
    }


def _post_attachment_to_dict(
    attachment: PostAttachmentModel,
    assets: dict[str, AssetModel],
) -> dict[str, object]:
    asset = assets.get(attachment.asset_key) if attachment.asset_key else None
    width = attachment.width
    height = attachment.height
    if asset is not None:
        width = width or asset.width
        height = height or asset.height
    return {
        "position": attachment.position,
        "asset_key": attachment.asset_key,
        "source_type": asset.source_type if asset is not None else None,
        "remote_url": attachment.remote_url,
        "thumbnail_url": attachment.thumbnail_url,
        "mime_type": attachment.mime_type or (asset.mime_type if asset is not None else None),
        "width": width,
        "height": height,
        "description": attachment.description,
        "is_sensitive": bool(attachment.is_sensitive),
        "asset_available": asset is not None,
        "preview_url": (
            f"/api/assets/{asset.asset_key}/preview" if asset is not None else attachment.remote_url or None
        ),
        "thumb_url": (
            f"/api/assets/{asset.asset_key}/thumb"
            if asset is not None
            else attachment.thumbnail_url or attachment.remote_url or None
        ),
    }


def _apply_post_filters(statement, *, source: str = "", q: str = "", exclude_ratings: Iterable[str] = ()):
    source_key = str(source or "").strip().casefold()
    if source_key:
        statement = statement.where(PostModel.source == source_key)
    term = str(q or "").strip()
    if term:
        pattern = _contains_pattern(term)
        statement = statement.where(
            or_(
                func.lower(PostModel.content).like(pattern, escape="\\"),
                func.lower(PostModel.author_name).like(pattern, escape="\\"),
                func.lower(PostModel.author_handle).like(pattern, escape="\\"),
            )
        )
    ratings = [rating for rating in exclude_ratings if rating]
    if ratings:
        statement = statement.where(
            or_(PostModel.age_rating.is_(None), PostModel.age_rating.notin_(ratings))
        )
    return statement


def backfill_source_tag_index(session: Session, catalog: TagCatalog) -> SourceTagBackfillResult:
    asset_count = 0
    tag_count = 0
    labels_before = {name: dict(tag.labels) for name, tag in catalog.tags.items()}
    for asset in session.scalars(select(AssetModel)).unique().all():
        source_tags = {
            tag
            for tag in catalog.canonicalize_tags(
                pixiv_tags=asset.pixiv_tags or [],
                source_tag_details=source_tag_details_from_extra(asset.extra or {}),
            )
            if tag.startswith("source_tag:")
        }
        if not source_tags:
            continue
        existing = {tag.tag for tag in asset.tags}
        missing = sorted(source_tags - existing, key=tag_sort_key)
        if not missing:
            continue
        for tag in missing:
            asset.tags.append(AssetTagModel(asset_key=asset.asset_key, tag=tag))
        asset_count += 1
        tag_count += len(missing)
    if tag_count:
        session.commit()
    label_count = sum(
        1
        for name, tag in catalog.tags.items()
        if labels_before.get(name, {}) != tag.labels
    )
    return SourceTagBackfillResult(asset_count, tag_count, label_count)


def upsert_asset(
    session: Session,
    storage: GalleryStorage,
    metadata: GalleryMetadata,
    tags: Iterable[str],
    *,
    duplicate_of: str | None = None,
) -> AssetModel:
    tag_set = sorted(set(tags), key=tag_sort_key)
    asset = session.get(AssetModel, metadata.asset_key)
    if asset is None:
        asset = AssetModel(asset_key=metadata.asset_key)
        session.add(asset)

    asset.source = metadata.source
    asset.source_id = metadata.source_id
    asset.page_index = metadata.page_index
    asset.title = metadata.title
    asset.artist_id = metadata.artist_id
    asset.artist_name = metadata.artist_name
    asset.original_url = metadata.original_url
    asset.crawl_time = metadata.crawl_time
    asset.file_sha256 = metadata.file_sha256
    asset.original_filename = metadata.original_filename
    asset.original_path = metadata.original_path
    asset.preview_path = _existing_preview_relative(storage, metadata.asset_key)
    asset.thumb_path = _existing_cache_relative(storage, storage.thumb_path(metadata.asset_key, ".avif"))
    asset.pixiv_tags = list(metadata.pixiv_tags)
    asset.canonical_tags = list(metadata.canonical_tags)
    asset.width = metadata.width
    asset.height = metadata.height
    asset.mime_type = metadata.mime_type
    asset.artwork_date = metadata.artwork_date
    asset.pixiv_upload_date = metadata.pixiv_upload_date
    asset.source_type = metadata.source_type
    asset.age_rating = metadata.age_rating
    asset.is_ai_generated = metadata.is_ai_generated
    asset.is_animated = metadata.is_animated
    asset.extra = metadata.extra or None
    asset.uploader_user_id = metadata.uploader_user_id
    asset.uploader_username = metadata.uploader_username
    asset.deletion_status = metadata.deletion_status
    asset.deleted_at = metadata.deleted_at
    asset.deleted_by_user_id = metadata.deleted_by_user_id
    asset.deleted_by_username = metadata.deleted_by_username
    asset.duplicate_of = duplicate_of
    asset.updated_at = now_utc()
    asset.tags = [AssetTagModel(asset_key=metadata.asset_key, tag=tag) for tag in tag_set]
    session.flush()
    return asset


def search_assets(
    session: Session,
    catalog: TagCatalog,
    query: str | SearchQuery,
    *,
    limit: int = 50,
    offset: int = 0,
    sort: str = "asset_key",
    order: str = "asc",
    include_deleted: bool = False,
) -> list[AssetModel]:
    parsed = catalog.parse_query(query) if isinstance(query, str) else query
    if parsed.unknown_required:
        return []
    statement = select(AssetModel)
    if not include_deleted:
        statement = statement.where(AssetModel.deletion_status.is_(None))
    statement = _apply_tag_filters(statement, parsed)
    statement = _apply_sort(statement, sort, order)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def search_asset_dicts(
    session: Session,
    catalog: TagCatalog,
    query: str | SearchQuery,
    *,
    limit: int = 50,
    offset: int = 0,
    sort: str = "asset_key",
    order: str = "asc",
    include_deleted: bool = False,
) -> list[dict[str, object]]:
    """Return search results through SQLAlchemy Core and the normal API mapper."""
    parsed = catalog.parse_query(query) if isinstance(query, str) else query
    if parsed.unknown_required:
        return []
    assets = AssetModel.__table__
    asset_tags = AssetTagModel.__table__
    statement = select(*assets.c)
    if not include_deleted:
        statement = statement.where(assets.c.deletion_status.is_(None))
    for tag in parsed.required:
        statement = statement.where(exists(select(asset_tags.c.asset_key).where(
            asset_tags.c.asset_key == assets.c.asset_key,
            asset_tags.c.tag == tag,
        )))
    for tag in parsed.excluded:
        statement = statement.where(~exists(select(asset_tags.c.asset_key).where(
            asset_tags.c.asset_key == assets.c.asset_key,
            asset_tags.c.tag == tag,
        )))
    if parsed.exclude_hidden:
        statement = statement.where(~exists(select(asset_tags.c.asset_key).where(
            asset_tags.c.asset_key == assets.c.asset_key,
            or_(
                asset_tags.c.tag == HIDDEN_TAG,
                asset_tags.c.tag.like("meta:hide\\_%", escape="\\"),
                asset_tags.c.tag.like("meta:hide-%", escape="\\"),
            ),
        )))
    filename_column = func.lower(assets.c.original_filename)
    for term in parsed.filename_required:
        statement = statement.where(filename_column.like(_contains_pattern(term), escape="\\"))
    for term in parsed.filename_excluded:
        statement = statement.where(~filename_column.like(_contains_pattern(term), escape="\\"))
    sort_columns = {
        "artwork_date": assets.c.artwork_date,
        "pixiv_upload_date": assets.c.pixiv_upload_date,
        "uploaded_at": assets.c.crawl_time,
        "original_filename": func.lower(assets.c.original_filename),
        "title": func.lower(assets.c.title),
        "artist": func.lower(assets.c.artist_name),
        "source": func.lower(assets.c.source),
        "source_id": func.lower(assets.c.source_id),
        "asset_key": assets.c.asset_key,
    }
    expression = sort_columns.get(normalize_asset_sort(sort), assets.c.asset_key)
    sorted_expression = expression.desc() if normalize_sort_order(order) == "desc" else expression.asc()
    group = assets.c.source_id.desc() if normalize_sort_order(order) == "desc" else assets.c.source_id.asc()
    statement = statement.order_by(
        (func.coalesce(expression, "") == "").asc(),
        sorted_expression,
        group,
        assets.c.page_index.is_(None).asc(),
        assets.c.page_index.asc(),
        assets.c.asset_key.asc(),
    ).limit(limit).offset(offset)
    rows = session.execute(statement).mappings().all()
    if not rows:
        return []
    keys = [str(row["asset_key"]) for row in rows]
    tag_rows = session.execute(
        select(asset_tags.c.asset_key, asset_tags.c.tag).where(asset_tags.c.asset_key.in_(keys))
    ).all()
    tags_by_asset: dict[str, list[SimpleNamespace]] = {key: [] for key in keys}
    for asset_key, tag in tag_rows:
        tags_by_asset.setdefault(str(asset_key), []).append(SimpleNamespace(tag=str(tag)))
    return [
        asset_to_dict(SimpleNamespace(**dict(row), tags=tags_by_asset.get(str(row["asset_key"]), [])), catalog)
        for row in rows
    ]


def random_asset(
    session: Session,
    catalog: TagCatalog,
    query: str | None = None,
    *,
    include_deleted: bool = False,
    exclude_ratings: Iterable[str] = (),
) -> AssetModel | None:
    parsed = catalog.parse_query(query or "")
    if parsed.unknown_required:
        return None
    statement = select(AssetModel).order_by(func.random()).limit(1)
    if not include_deleted:
        statement = statement.where(AssetModel.deletion_status.is_(None))
    ratings = tuple(str(rating).strip().casefold() for rating in exclude_ratings if str(rating).strip())
    if ratings:
        statement = statement.where(or_(AssetModel.age_rating.is_(None), func.lower(AssetModel.age_rating).notin_(ratings)))
    statement = _apply_tag_filters(statement, parsed)
    return session.scalar(statement)


def create_user(session: Session, username: str, password: str, role: str) -> UserModel:
    normalized_role = validate_role(role)
    user = UserModel(username=username.strip(), password_hash=hash_password(password), role=normalized_role)
    session.add(user)
    session.commit()
    return user


def authenticate_user(session: Session, username: str, password: str) -> UserModel | None:
    user = session.scalar(select(UserModel).where(UserModel.username == username.strip(), UserModel.is_active.is_(True)))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def set_user_password(session: Session, username: str, password: str) -> UserModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    user.password_hash = hash_password(password)
    user.updated_at = now_utc()
    session.commit()
    return user


def list_users(session: Session) -> list[UserModel]:
    return list(
        session.scalars(
            select(UserModel)
            .where(UserModel.is_active.is_(True))
            .order_by(UserModel.username.asc(), UserModel.id.asc())
        ).all()
    )


def change_user_password(session: Session, user_id: int, old_password: str, new_password: str) -> UserModel:
    user = session.get(UserModel, user_id)
    if user is None or not user.is_active:
        raise ValueError(f"user not found: {user_id}")
    if not verify_password(old_password, user.password_hash):
        raise PermissionError("old password is incorrect")
    user.password_hash = hash_password(new_password)
    user.updated_at = now_utc()
    session.commit()
    return user


def issue_api_token(
    session: Session,
    username: str,
    *,
    label: str = "",
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> str:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    token = generate_api_token()
    row = UserTokenModel(
        user_id=user.id,
        token_prefix=token_prefix(token),
        token_hash=hash_secret(token),
        label=label.strip(),
        created_by_user_id=created_by_user_id,
        created_by_username=created_by_username,
    )
    session.add(row)
    user.updated_at = now_utc()
    session.commit()
    return token


def authenticate_api_token(
    session: Session,
    token: str,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> UserModel | None:
    prefix = token_prefix(token)
    row = session.scalar(
        select(UserTokenModel).where(
            UserTokenModel.token_prefix == prefix,
            UserTokenModel.revoked_at.is_(None),
        )
    )
    if row and verify_secret(token, row.token_hash):
        user = session.get(UserModel, row.user_id)
        if user and user.is_active:
            if record_usage:
                row.last_used_at = now_utc()
                row.last_used_ip = (client_ip or "")[:120] or None
                session.flush()
            return user

    # Legacy single-token column support.
    user = session.scalar(
        select(UserModel).where(
            UserModel.api_token_prefix == prefix,
            UserModel.is_active.is_(True),
        )
    )
    if user and user.api_token_hash and verify_secret(token, user.api_token_hash):
        return user
    return None


def list_api_tokens(session: Session, username: str) -> list[UserTokenModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(UserTokenModel)
            .where(UserTokenModel.user_id == user.id)
            .order_by(UserTokenModel.created_at.desc(), UserTokenModel.id.desc())
        ).all()
    )


def revoke_api_token(session: Session, token_id: int) -> UserTokenModel:
    row = session.get(UserTokenModel, token_id)
    if row is None:
        raise ValueError(f"token not found: {token_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        session.commit()
    return row


def api_token_belongs_to_user(session: Session, token_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(UserTokenModel, token_id)
    return bool(row and row.user_id == user_id)


def api_token_to_dict(token: UserTokenModel) -> dict[str, object]:
    return {
        "id": token.id,
        "user_id": token.user_id,
        "token_prefix": token.token_prefix,
        "label": token.label,
        "created_by_user_id": token.created_by_user_id,
        "created_by_username": token.created_by_username,
        "last_used_at": _datetime_to_iso(token.last_used_at),
        "last_used_ip": token.last_used_ip,
        "revoked_at": _datetime_to_iso(token.revoked_at),
        "created_at": _datetime_to_iso(token.created_at),
        "is_active": token.revoked_at is None,
    }


def save_pixiv_token(
    session: Session,
    username: str,
    refresh_token: str,
    *,
    label: str = "",
    pixiv_user: dict | None = None,
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> PixivTokenModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    token = refresh_token.strip()
    if not token:
        raise ValueError("Pixiv refresh token cannot be empty")

    token_hash = hash_opaque_token(token)
    row = session.scalar(
        select(PixivTokenModel).where(
            PixivTokenModel.user_id == user.id,
            PixivTokenModel.refresh_token_hash == token_hash,
        )
    )
    if row is None:
        row = PixivTokenModel(
            user_id=user.id,
            refresh_token=encrypt_secret(token),
            refresh_token_hash=token_hash,
            token_prefix=token_prefix(token),
            token_suffix=token[-8:] if len(token) > 8 else token,
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
        )
        session.add(row)
    else:
        row.refresh_token = encrypt_secret(token)
        row.token_prefix = token_prefix(token)
        row.token_suffix = token[-8:] if len(token) > 8 else token
        row.revoked_at = None

    row.label = label.strip()[:160]
    _apply_pixiv_user(row, pixiv_user)
    row.updated_at = now_utc()
    user.updated_at = now_utc()
    session.commit()
    return row


def list_pixiv_tokens(session: Session, username: str) -> list[PixivTokenModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(PixivTokenModel)
            .where(PixivTokenModel.user_id == user.id)
            .order_by(PixivTokenModel.updated_at.desc(), PixivTokenModel.id.desc())
        ).all()
    )


def update_pixiv_token_label(session: Session, token_id: int, label: str) -> PixivTokenModel:
    row = session.get(PixivTokenModel, token_id)
    if row is None:
        raise ValueError(f"Pixiv token not found: {token_id}")
    row.label = label.strip()[:160]
    row.updated_at = now_utc()
    session.commit()
    return row


def revoke_pixiv_token(session: Session, token_id: int) -> PixivTokenModel:
    row = session.get(PixivTokenModel, token_id)
    if row is None:
        raise ValueError(f"Pixiv token not found: {token_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        row.updated_at = row.revoked_at
        session.commit()
    return row


def pixiv_token_belongs_to_user(session: Session, token_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(PixivTokenModel, token_id)
    return bool(row and row.user_id == user_id)


def get_pixiv_refresh_token(
    session: Session,
    token_id: int,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> str:
    row = session.get(PixivTokenModel, token_id)
    if row is None or row.revoked_at is not None:
        raise ValueError(f"Pixiv token not found: {token_id}")
    if record_usage:
        row.last_used_at = now_utc()
        row.last_used_ip = (client_ip or "")[:120] or None
        row.updated_at = now_utc()
        session.flush()
    return decrypt_secret(row.refresh_token)


def pixiv_token_to_dict(token: PixivTokenModel) -> dict[str, object]:
    return {
        "id": token.id,
        "user_id": token.user_id,
        "token_prefix": token.token_prefix,
        "token_suffix": token.token_suffix,
        "label": token.label,
        "pixiv_user_id": token.pixiv_user_id,
        "pixiv_account": token.pixiv_account,
        "pixiv_name": token.pixiv_name,
        "created_by_user_id": token.created_by_user_id,
        "created_by_username": token.created_by_username,
        "last_used_at": _datetime_to_iso(token.last_used_at),
        "last_used_ip": token.last_used_ip,
        "revoked_at": _datetime_to_iso(token.revoked_at),
        "created_at": _datetime_to_iso(token.created_at),
        "updated_at": _datetime_to_iso(token.updated_at),
        "is_active": token.revoked_at is None,
    }


def save_misskey_token(
    session: Session,
    username: str,
    token: str,
    *,
    label: str = "",
    host: str = "misskey.io",
    misskey_user: dict | None = None,
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> MisskeyTokenModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    value = token.strip()
    if not value:
        raise ValueError("Misskey token cannot be empty")

    token_hash = hash_opaque_token(value)
    row = session.scalar(
        select(MisskeyTokenModel).where(
            MisskeyTokenModel.user_id == user.id,
            MisskeyTokenModel.token_hash == token_hash,
        )
    )
    if row is None:
        row = MisskeyTokenModel(
            user_id=user.id,
            token=encrypt_secret(value),
            token_hash=token_hash,
            token_prefix=token_prefix(value),
            token_suffix=value[-8:] if len(value) > 8 else value,
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
        )
        session.add(row)
    else:
        row.token = encrypt_secret(value)
        row.token_prefix = token_prefix(value)
        row.token_suffix = value[-8:] if len(value) > 8 else value
        row.revoked_at = None

    row.label = label.strip()[:160]
    row.host = (host or "misskey.io").strip()[:240] or "misskey.io"
    _apply_misskey_user(row, misskey_user)
    row.updated_at = now_utc()
    user.updated_at = now_utc()
    session.commit()
    return row


def list_misskey_tokens(session: Session, username: str) -> list[MisskeyTokenModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(MisskeyTokenModel)
            .where(MisskeyTokenModel.user_id == user.id)
            .order_by(MisskeyTokenModel.updated_at.desc(), MisskeyTokenModel.id.desc())
        ).all()
    )


def update_misskey_token_label(session: Session, token_id: int, label: str) -> MisskeyTokenModel:
    row = session.get(MisskeyTokenModel, token_id)
    if row is None:
        raise ValueError(f"Misskey token not found: {token_id}")
    row.label = label.strip()[:160]
    row.updated_at = now_utc()
    session.commit()
    return row


def revoke_misskey_token(session: Session, token_id: int) -> MisskeyTokenModel:
    row = session.get(MisskeyTokenModel, token_id)
    if row is None:
        raise ValueError(f"Misskey token not found: {token_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        row.updated_at = row.revoked_at
        session.commit()
    return row


def misskey_token_belongs_to_user(session: Session, token_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(MisskeyTokenModel, token_id)
    return bool(row and row.user_id == user_id)


def get_misskey_token(
    session: Session,
    token_id: int,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> tuple[str, str]:
    """Returns the decrypted token and its instance host."""
    row = session.get(MisskeyTokenModel, token_id)
    if row is None or row.revoked_at is not None:
        raise ValueError(f"Misskey token not found: {token_id}")
    if record_usage:
        row.last_used_at = now_utc()
        row.last_used_ip = (client_ip or "")[:120] or None
        row.updated_at = now_utc()
        session.flush()
    return decrypt_secret(row.token), row.host


def misskey_token_to_dict(token: MisskeyTokenModel) -> dict[str, object]:
    return {
        "id": token.id,
        "user_id": token.user_id,
        "token_prefix": token.token_prefix,
        "token_suffix": token.token_suffix,
        "label": token.label,
        "host": token.host,
        "misskey_user_id": token.misskey_user_id,
        "misskey_username": token.misskey_username,
        "misskey_name": token.misskey_name,
        "created_by_user_id": token.created_by_user_id,
        "created_by_username": token.created_by_username,
        "last_used_at": _datetime_to_iso(token.last_used_at),
        "last_used_ip": token.last_used_ip,
        "revoked_at": _datetime_to_iso(token.revoked_at),
        "created_at": _datetime_to_iso(token.created_at),
        "updated_at": _datetime_to_iso(token.updated_at),
        "is_active": token.revoked_at is None,
    }


def _apply_misskey_user(row: MisskeyTokenModel, misskey_user: dict | None) -> None:
    if not isinstance(misskey_user, dict):
        return
    user_id = _optional_text(misskey_user.get("user_id") or misskey_user.get("id"), max_length=180)
    username = _optional_text(misskey_user.get("username"), max_length=240)
    name = _optional_text(misskey_user.get("name"), max_length=240)
    if user_id:
        row.misskey_user_id = user_id
    if username:
        row.misskey_username = username
    if name:
        row.misskey_name = name


def save_x_token(
    session: Session,
    username: str,
    token: str,
    *,
    ct0: str = "",
    label: str = "",
    host: str = "x.com",
    x_user: dict | None = None,
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> XTokenModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    value = token.strip()
    if not value:
        raise ValueError("X auth_token cannot be empty")

    token_hash = hash_opaque_token(value)
    row = session.scalar(
        select(XTokenModel).where(
            XTokenModel.user_id == user.id,
            XTokenModel.token_hash == token_hash,
        )
    )
    if row is None:
        row = XTokenModel(
            user_id=user.id,
            token=encrypt_secret(value),
            token_hash=token_hash,
            token_prefix=token_prefix(value),
            token_suffix=value[-8:] if len(value) > 8 else value,
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
        )
        session.add(row)
    else:
        row.token = encrypt_secret(value)
        row.token_prefix = token_prefix(value)
        row.token_suffix = value[-8:] if len(value) > 8 else value
        row.revoked_at = None

    if ct0.strip():
        row.ct0 = encrypt_secret(ct0.strip())
    row.label = label.strip()[:160]
    row.host = (host or "x.com").strip()[:240] or "x.com"
    _apply_x_user(row, x_user)
    row.updated_at = now_utc()
    user.updated_at = now_utc()
    session.commit()
    return row


def list_x_tokens(session: Session, username: str) -> list[XTokenModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(XTokenModel)
            .where(XTokenModel.user_id == user.id)
            .order_by(XTokenModel.updated_at.desc(), XTokenModel.id.desc())
        ).all()
    )


def update_x_token_label(session: Session, token_id: int, label: str) -> XTokenModel:
    row = session.get(XTokenModel, token_id)
    if row is None:
        raise ValueError(f"X token not found: {token_id}")
    row.label = label.strip()[:160]
    row.updated_at = now_utc()
    session.commit()
    return row


def revoke_x_token(session: Session, token_id: int) -> XTokenModel:
    row = session.get(XTokenModel, token_id)
    if row is None:
        raise ValueError(f"X token not found: {token_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        row.updated_at = row.revoked_at
        session.commit()
    return row


def x_token_belongs_to_user(session: Session, token_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(XTokenModel, token_id)
    return bool(row and row.user_id == user_id)


def get_x_token(
    session: Session,
    token_id: int,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> tuple[str, str, str]:
    """Returns the decrypted auth_token, its ct0 companion and the instance host."""
    row = session.get(XTokenModel, token_id)
    if row is None or row.revoked_at is not None:
        raise ValueError(f"X token not found: {token_id}")
    if record_usage:
        row.last_used_at = now_utc()
        row.last_used_ip = (client_ip or "")[:120] or None
        row.updated_at = now_utc()
        session.flush()
    return decrypt_secret(row.token), decrypt_secret(row.ct0) if row.ct0 else "", row.host


def x_token_to_dict(token: XTokenModel) -> dict[str, object]:
    return {
        "id": token.id,
        "user_id": token.user_id,
        "token_prefix": token.token_prefix,
        "token_suffix": token.token_suffix,
        "has_ct0": bool(token.ct0),
        "label": token.label,
        "host": token.host,
        "x_user_id": token.x_user_id,
        "x_screen_name": token.x_screen_name,
        "x_name": token.x_name,
        "created_by_user_id": token.created_by_user_id,
        "created_by_username": token.created_by_username,
        "last_used_at": _datetime_to_iso(token.last_used_at),
        "last_used_ip": token.last_used_ip,
        "revoked_at": _datetime_to_iso(token.revoked_at),
        "created_at": _datetime_to_iso(token.created_at),
        "updated_at": _datetime_to_iso(token.updated_at),
        "is_active": token.revoked_at is None,
    }


def _apply_x_user(row: XTokenModel, x_user: dict | None) -> None:
    if not isinstance(x_user, dict):
        return
    user_id = _optional_text(x_user.get("user_id") or x_user.get("id"), max_length=180)
    screen_name = _optional_text(x_user.get("screen_name") or x_user.get("username"), max_length=240)
    name = _optional_text(x_user.get("name"), max_length=240)
    if user_id:
        row.x_user_id = user_id
    if screen_name:
        row.x_screen_name = screen_name
    if name:
        row.x_name = name


def save_fanbox_session(
    session: Session,
    username: str,
    session_id: str,
    *,
    label: str = "",
    source: str = "manual",
    fanbox_user: dict | None = None,
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> FanboxSessionModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    value = session_id.strip()
    if not value:
        raise ValueError("FANBOXSESSID cannot be empty")

    session_hash = hash_opaque_token(value)
    row = session.scalar(
        select(FanboxSessionModel).where(
            FanboxSessionModel.user_id == user.id,
            FanboxSessionModel.session_hash == session_hash,
        )
    )
    if row is None:
        row = FanboxSessionModel(
            user_id=user.id,
            session_id=encrypt_secret(value),
            session_hash=session_hash,
            session_prefix=token_prefix(value),
            session_suffix=value[-8:] if len(value) > 8 else value,
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
        )
        session.add(row)
    else:
        row.session_id = encrypt_secret(value)
        row.session_prefix = token_prefix(value)
        row.session_suffix = value[-8:] if len(value) > 8 else value
        row.revoked_at = None

    row.label = label.strip()[:160]
    row.source = (source or "manual").strip()[:32] or "manual"
    _apply_fanbox_user(row, fanbox_user)
    row.updated_at = now_utc()
    user.updated_at = now_utc()
    session.commit()
    return row


def list_fanbox_sessions(session: Session, username: str) -> list[FanboxSessionModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(FanboxSessionModel)
            .where(FanboxSessionModel.user_id == user.id)
            .order_by(FanboxSessionModel.updated_at.desc(), FanboxSessionModel.id.desc())
        ).all()
    )


def update_fanbox_session_label(session: Session, session_row_id: int, label: str) -> FanboxSessionModel:
    row = session.get(FanboxSessionModel, session_row_id)
    if row is None:
        raise ValueError(f"Fanbox session not found: {session_row_id}")
    row.label = label.strip()[:160]
    row.updated_at = now_utc()
    session.commit()
    return row


def revoke_fanbox_session(session: Session, session_row_id: int) -> FanboxSessionModel:
    row = session.get(FanboxSessionModel, session_row_id)
    if row is None:
        raise ValueError(f"Fanbox session not found: {session_row_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        row.updated_at = row.revoked_at
        session.commit()
    return row


def fanbox_session_belongs_to_user(session: Session, session_row_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(FanboxSessionModel, session_row_id)
    return bool(row and row.user_id == user_id)


def get_fanbox_session(
    session: Session,
    session_row_id: int,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> str:
    """Returns the decrypted FANBOXSESSID."""
    row = session.get(FanboxSessionModel, session_row_id)
    if row is None or row.revoked_at is not None:
        raise ValueError(f"Fanbox session not found: {session_row_id}")
    if record_usage:
        row.last_used_at = now_utc()
        row.last_used_ip = (client_ip or "")[:120] or None
        row.updated_at = now_utc()
        session.flush()
    return decrypt_secret(row.session_id)


def fanbox_session_to_dict(row: FanboxSessionModel) -> dict[str, object]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "session_prefix": row.session_prefix,
        "session_suffix": row.session_suffix,
        "label": row.label,
        "source": row.source,
        "fanbox_user_id": row.fanbox_user_id,
        "fanbox_creator_id": row.fanbox_creator_id,
        "fanbox_name": row.fanbox_name,
        "created_by_user_id": row.created_by_user_id,
        "created_by_username": row.created_by_username,
        "last_used_at": _datetime_to_iso(row.last_used_at),
        "last_used_ip": row.last_used_ip,
        "revoked_at": _datetime_to_iso(row.revoked_at),
        "created_at": _datetime_to_iso(row.created_at),
        "updated_at": _datetime_to_iso(row.updated_at),
        "is_active": row.revoked_at is None,
    }


def _apply_fanbox_user(row: FanboxSessionModel, fanbox_user: dict | None) -> None:
    if not isinstance(fanbox_user, dict):
        return
    user_id = _optional_text(fanbox_user.get("user_id") or fanbox_user.get("userId"), max_length=180)
    creator_id = _optional_text(fanbox_user.get("creator_id") or fanbox_user.get("creatorId"), max_length=240)
    name = _optional_text(fanbox_user.get("name"), max_length=240)
    if user_id:
        row.fanbox_user_id = user_id
    if creator_id:
        row.fanbox_creator_id = creator_id
    if name:
        row.fanbox_name = name


def save_pixiv_cookie(
    session: Session,
    username: str,
    cookie: str,
    *,
    label: str = "",
    pixiv_user: dict | None = None,
    created_by_user_id: int | None = None,
    created_by_username: str | None = None,
) -> PixivCookieModel:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    cookie_value = cookie.strip()
    if not cookie_value:
        raise ValueError("Pixiv cookie cannot be empty")

    cookie_hash = hash_opaque_token(cookie_value)
    row = session.scalar(
        select(PixivCookieModel).where(
            PixivCookieModel.user_id == user.id,
            PixivCookieModel.cookie_hash == cookie_hash,
        )
    )
    if row is None:
        row = PixivCookieModel(
            user_id=user.id,
            cookie=encrypt_secret(cookie_value),
            cookie_hash=cookie_hash,
            cookie_prefix=cookie_hash[:16],
            cookie_suffix=cookie_hash[-8:],
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
        )
        session.add(row)
    else:
        row.cookie = encrypt_secret(cookie_value)
        row.cookie_prefix = cookie_hash[:16]
        row.cookie_suffix = cookie_hash[-8:]
        row.revoked_at = None

    row.label = label.strip()[:160]
    _apply_pixiv_user(row, pixiv_user)
    row.updated_at = now_utc()
    user.updated_at = now_utc()
    session.commit()
    return row


def list_pixiv_cookies(session: Session, username: str) -> list[PixivCookieModel]:
    user = session.scalar(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    if user is None:
        raise ValueError(f"user not found: {username}")
    return list(
        session.scalars(
            select(PixivCookieModel)
            .where(PixivCookieModel.user_id == user.id)
            .order_by(PixivCookieModel.updated_at.desc(), PixivCookieModel.id.desc())
        ).all()
    )


def update_pixiv_cookie_label(session: Session, cookie_id: int, label: str) -> PixivCookieModel:
    row = session.get(PixivCookieModel, cookie_id)
    if row is None:
        raise ValueError(f"Pixiv cookie not found: {cookie_id}")
    row.label = label.strip()[:160]
    row.updated_at = now_utc()
    session.commit()
    return row


def revoke_pixiv_cookie(session: Session, cookie_id: int) -> PixivCookieModel:
    row = session.get(PixivCookieModel, cookie_id)
    if row is None:
        raise ValueError(f"Pixiv cookie not found: {cookie_id}")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        row.updated_at = row.revoked_at
        session.commit()
    return row


def pixiv_cookie_belongs_to_user(session: Session, cookie_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    row = session.get(PixivCookieModel, cookie_id)
    return bool(row and row.user_id == user_id)


def get_pixiv_cookie(
    session: Session,
    cookie_id: int,
    *,
    record_usage: bool = False,
    client_ip: str | None = None,
) -> str:
    row = session.get(PixivCookieModel, cookie_id)
    if row is None or row.revoked_at is not None:
        raise ValueError(f"Pixiv cookie not found: {cookie_id}")
    if record_usage:
        row.last_used_at = now_utc()
        row.last_used_ip = (client_ip or "")[:120] or None
        row.updated_at = now_utc()
        session.flush()
    return decrypt_secret(row.cookie)


def encrypt_stored_pixiv_credentials(session: Session) -> dict[str, int]:
    if not secret_encryption_enabled():
        return {"pixiv_tokens": 0, "pixiv_cookies": 0, "misskey_tokens": 0, "x_tokens": 0, "fanbox_sessions": 0}
    token_count = 0
    cookie_count = 0
    misskey_count = 0
    x_count = 0
    fanbox_count = 0
    for row in session.scalars(select(PixivTokenModel)).all():
        if row.refresh_token and not is_encrypted_secret(row.refresh_token):
            row.refresh_token = encrypt_secret(row.refresh_token)
            row.updated_at = now_utc()
            token_count += 1
    for row in session.scalars(select(PixivCookieModel)).all():
        if row.cookie and not is_encrypted_secret(row.cookie):
            row.cookie = encrypt_secret(row.cookie)
            row.updated_at = now_utc()
            cookie_count += 1
    for row in session.scalars(select(MisskeyTokenModel)).all():
        if row.token and not is_encrypted_secret(row.token):
            row.token = encrypt_secret(row.token)
            row.updated_at = now_utc()
            misskey_count += 1
    for row in session.scalars(select(XTokenModel)).all():
        changed = False
        if row.token and not is_encrypted_secret(row.token):
            row.token = encrypt_secret(row.token)
            changed = True
        if row.ct0 and not is_encrypted_secret(row.ct0):
            row.ct0 = encrypt_secret(row.ct0)
            changed = True
        if changed:
            row.updated_at = now_utc()
            x_count += 1
    for row in session.scalars(select(FanboxSessionModel)).all():
        if row.session_id and not is_encrypted_secret(row.session_id):
            row.session_id = encrypt_secret(row.session_id)
            row.updated_at = now_utc()
            fanbox_count += 1
    if token_count or cookie_count or misskey_count or x_count or fanbox_count:
        session.commit()
    return {
        "pixiv_tokens": token_count,
        "pixiv_cookies": cookie_count,
        "misskey_tokens": misskey_count,
        "x_tokens": x_count,
        "fanbox_sessions": fanbox_count,
    }


def pixiv_cookie_to_dict(cookie: PixivCookieModel) -> dict[str, object]:
    return {
        "id": cookie.id,
        "user_id": cookie.user_id,
        "cookie_prefix": cookie.cookie_prefix,
        "cookie_suffix": cookie.cookie_suffix,
        "label": cookie.label,
        "pixiv_user_id": cookie.pixiv_user_id,
        "pixiv_account": cookie.pixiv_account,
        "pixiv_name": cookie.pixiv_name,
        "created_by_user_id": cookie.created_by_user_id,
        "created_by_username": cookie.created_by_username,
        "last_used_at": _datetime_to_iso(cookie.last_used_at),
        "last_used_ip": cookie.last_used_ip,
        "revoked_at": _datetime_to_iso(cookie.revoked_at),
        "created_at": _datetime_to_iso(cookie.created_at),
        "updated_at": _datetime_to_iso(cookie.updated_at),
        "is_active": cookie.revoked_at is None,
    }


def _apply_pixiv_user(row: PixivTokenModel | PixivCookieModel, pixiv_user: dict | None) -> None:
    if not isinstance(pixiv_user, dict):
        return
    row.pixiv_user_id = _optional_text(
        pixiv_user.get("id")
        or pixiv_user.get("user_id")
        or pixiv_user.get("account_id"),
        max_length=80,
    )
    row.pixiv_account = _optional_text(
        pixiv_user.get("account")
        or pixiv_user.get("pixiv_id")
        or pixiv_user.get("mail_address")
        or pixiv_user.get("email"),
        max_length=160,
    )
    row.pixiv_name = _optional_text(
        pixiv_user.get("name")
        or pixiv_user.get("username")
        or pixiv_user.get("display_name")
    )


def _optional_text(value: object, *, max_length: int = 240) -> str | None:
    text_value = str(value or "").strip()
    return text_value[:max_length] if text_value else None


def create_login_session(
    session: Session,
    user: UserModel,
    *,
    user_agent: str = "",
    client_ip: str = "",
    ttl_days: int = 30,
) -> tuple[str, LoginSessionModel]:
    session_token = generate_session_token()
    row = LoginSessionModel(
        user_id=user.id,
        session_prefix=token_prefix(session_token),
        session_hash=hash_opaque_token(session_token),
        csrf_token=generate_csrf_token(),
        user_agent=user_agent[:1000],
        client_ip=client_ip[:120],
        expires_at=now_utc() + timedelta(days=ttl_days),
        last_seen_at=now_utc(),
    )
    session.add(row)
    session.commit()
    return session_token, row


def authenticate_login_session(session: Session, session_token: str) -> tuple[UserModel, LoginSessionModel] | None:
    if not session_token:
        return None
    row = session.scalar(
        select(LoginSessionModel).where(
            LoginSessionModel.session_prefix == token_prefix(session_token),
            LoginSessionModel.revoked_at.is_(None),
        )
    )
    if row is None or not verify_opaque_token(session_token, row.session_hash):
        return None
    if aware_utc(row.expires_at) <= now_utc():
        row.revoked_at = now_utc()
        session.flush()
        return None
    user = session.get(UserModel, row.user_id)
    if user is None or not user.is_active:
        return None
    return user, row


def revoke_login_session(session: Session, session_token: str) -> LoginSessionModel | None:
    authenticated = authenticate_login_session(session, session_token)
    if authenticated is None:
        return None
    _user, row = authenticated
    row.revoked_at = now_utc()
    session.commit()
    return row


def any_users(session: Session) -> bool:
    return session.scalar(select(UserModel.id).limit(1)) is not None


def asset_to_dict(asset: AssetModel, catalog: TagCatalog | None = None) -> dict[str, object]:
    return {
        "id": asset.asset_key,
        "asset_key": asset.asset_key,
        "source": asset.source,
        "source_id": asset.source_id,
        "page_index": asset.page_index,
        "title": asset.title,
        "description": _asset_description(asset),
        "artist": _web_artist_name(asset),
        "artist_id": asset.artist_id,
        "original_url": asset.original_url,
        "original_filename": asset.original_filename,
        "original_path": asset.original_path,
        "preview_url": f"/api/assets/{asset.asset_key}/preview",
        "thumb_url": f"/api/assets/{asset.asset_key}/thumb",
        "tags": sorted((tag.tag for tag in asset.tags), key=tag_sort_key),
        "tag_details": _asset_tag_details(asset, catalog),
        "pixiv_tags": list(asset.pixiv_tags or []),
        "pixiv_tag_details": _asset_pixiv_tag_details(asset),
        "canonical_tags": list(asset.canonical_tags or []),
        "width": asset.width,
        "height": asset.height,
        "mime_type": asset.mime_type,
        "crawl_time": asset.crawl_time,
        "artwork_date": asset.artwork_date,
        "pixiv_upload_date": asset.pixiv_upload_date,
        "source_type": asset.source_type,
        "age_rating": asset.age_rating,
        "is_ai_generated": asset.is_ai_generated,
        "is_animated": asset.is_animated,
        "extra": asset.extra or {},
        "uploader_user_id": asset.uploader_user_id,
        "uploader_username": asset.uploader_username,
        "deletion_status": asset.deletion_status,
        "deleted_at": asset.deleted_at,
        "deleted_by_user_id": asset.deleted_by_user_id,
        "deleted_by_username": asset.deleted_by_username,
        "source_file_sha256": asset.file_sha256,
        "duplicate_of": asset.duplicate_of,
    }


def _asset_tag_details(asset: AssetModel, catalog: TagCatalog | None = None) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for tag_row in sorted(asset.tags, key=lambda item: tag_sort_key(item.tag)):
        tag = catalog.tags.get(tag_row.tag) if catalog is not None else None
        details.append(
            {
                "name": tag_row.tag,
                "category": tag.category if tag else tag_row.tag.split(":", 1)[0] if ":" in tag_row.tag else "general",
                "aliases": sorted(tag.aliases, key=normalize_name) if tag else [],
                "labels": dict(sorted(tag.labels.items())) if tag else {},
                "implications": sorted(tag.implications) if tag else [],
                "suggestions": sorted(tag.suggestions) if tag else [],
                **({"description": tag.description} if tag and tag.description else {}),
            }
        )
    return details


def _asset_description(asset: AssetModel) -> str:
    extra = asset.extra or {}
    for key in ("pixiv_description", "description", "caption"):
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _asset_pixiv_tag_details(asset: AssetModel) -> list[dict[str, str | None]]:
    extra = asset.extra or {}
    details = extra.get("pixiv_tag_details")
    if isinstance(details, list):
        items: list[dict[str, str | None]] = []
        for item in details:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            translated = item.get("translated_name")
            translated_name = str(translated).strip() if translated else None
            items.append(
                {
                    "name": name,
                    "translated_name": translated_name,
                    "source_tag": _asset_source_tag_name(name, translated_name),
                }
            )
        if items:
            return items
    return [
        {
            "name": str(tag),
            "translated_name": None,
            "source_tag": _asset_source_tag_name(str(tag), None),
        }
        for tag in asset.pixiv_tags or []
    ]


def _asset_source_tag_name(name: str, translated_name: str | None) -> str | None:
    try:
        return source_tag_name(name, translated_name)
    except ValueError:
        return None


def create_upload_log(
    session: Session,
    *,
    asset_key: str | None,
    uploader_user_id: int | None,
    uploader_username: str | None,
    original_filename: str,
    file_size: int | None,
    mime_type: str | None,
    event: str,
    status: str,
    message: str = "",
    extra: dict | None = None,
) -> UploadLogModel:
    log = UploadLogModel(
        asset_key=asset_key,
        uploader_user_id=uploader_user_id,
        uploader_username=uploader_username,
        original_filename=original_filename,
        file_size=file_size,
        mime_type=mime_type,
        event=event,
        status=status,
        message=message,
        extra=extra or None,
    )
    session.add(log)
    session.flush()
    return log


def create_transcode_job(
    session: Session,
    asset: AssetModel,
    *,
    source: str = "upload",
    file_size: int | None = None,
) -> TranscodeJobModel:
    job = TranscodeJobModel(
        job_id=f"{asset.asset_key}-{uuid.uuid4().hex[:12]}",
        asset_key=asset.asset_key,
        uploader_user_id=asset.uploader_user_id,
        uploader_username=asset.uploader_username,
        status="queued",
        stage="queued",
        message="waiting for media cache generation",
        progress=0.0,
        file_size=file_size,
        source=source,
    )
    session.add(job)
    session.flush()
    return job


def update_transcode_job(session: Session, job_id: str, **changes: object) -> TranscodeJobModel | None:
    job = session.scalar(select(TranscodeJobModel).where(TranscodeJobModel.job_id == job_id))
    if job is None:
        return None
    next_stage = str(changes["stage"]) if "stage" in changes and changes["stage"] is not None else None
    if next_stage and next_stage != job.stage:
        job.stage_started_at = now_utc()
    allowed = {
        "status",
        "stage",
        "message",
        "progress",
        "frames_done",
        "frames_total",
        "frames_per_second",
        "kind",
        "error",
    }
    for key, value in changes.items():
        if key in allowed:
            setattr(job, key, value)
    if changes.get("status") == "running" and job.started_at is None:
        job.started_at = now_utc()
    if changes.get("status") in {"success", "error"} and job.finished_at is None:
        job.finished_at = now_utc()
    job.updated_at = now_utc()
    session.flush()
    return job


def list_transcode_jobs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[TranscodeJobModel]:
    if not is_admin and user_id is None:
        return []
    statement = select(TranscodeJobModel).order_by(TranscodeJobModel.updated_at.desc(), TranscodeJobModel.id.desc())
    if not is_admin:
        statement = statement.where(TranscodeJobModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_upload_logs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadLogModel]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(UploadLogModel)
        .where(~UploadLogModel.event.in_(("pixiv_sync", "pixiv_import")))
        .order_by(UploadLogModel.created_at.desc(), UploadLogModel.id.desc())
    )
    if not is_admin:
        statement = statement.where(UploadLogModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_pixiv_logs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadLogModel]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(UploadLogModel)
        .where(UploadLogModel.event.in_(("pixiv_sync", "pixiv_import")))
        .order_by(UploadLogModel.created_at.desc(), UploadLogModel.id.desc())
    )
    if not is_admin:
        statement = statement.where(UploadLogModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_misskey_logs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadLogModel]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(UploadLogModel)
        .where(UploadLogModel.event.in_(("misskey_sync", "misskey_import")))
        .order_by(UploadLogModel.created_at.desc(), UploadLogModel.id.desc())
    )
    if not is_admin:
        statement = statement.where(UploadLogModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_x_logs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadLogModel]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(UploadLogModel)
        .where(UploadLogModel.event.in_(("x_sync", "x_import")))
        .order_by(UploadLogModel.created_at.desc(), UploadLogModel.id.desc())
    )
    if not is_admin:
        statement = statement.where(UploadLogModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_fanbox_logs(
    session: Session,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadLogModel]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(UploadLogModel)
        .where(UploadLogModel.event.in_(("fanbox_sync", "fanbox_import")))
        .order_by(UploadLogModel.created_at.desc(), UploadLogModel.id.desc())
    )
    if not is_admin:
        statement = statement.where(UploadLogModel.uploader_user_id == user_id)
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def list_upload_history(
    session: Session,
    storage: GalleryStorage,
    *,
    user_id: int | None,
    is_admin: bool,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, object]]:
    if not is_admin and user_id is None:
        return []
    statement = (
        select(AssetModel)
        .where(AssetModel.source == "upload")
        .order_by(AssetModel.crawl_time.desc(), AssetModel.asset_key.desc())
    )
    if not is_admin:
        statement = statement.where(AssetModel.uploader_user_id == user_id)
    assets = list(session.scalars(statement.limit(limit).offset(offset)).all())
    latest_jobs = _latest_jobs_for_assets(session, [asset.asset_key for asset in assets])
    return [
        upload_history_to_dict(asset, storage, latest_jobs.get(asset.asset_key))
        for asset in assets
    ]


def upload_history_to_dict(
    asset: AssetModel,
    storage: GalleryStorage,
    latest_job: TranscodeJobModel | None = None,
) -> dict[str, object]:
    cache = _asset_cache_state(storage, asset)
    return {
        "asset_key": asset.asset_key,
        "title": asset.title,
        "original_filename": asset.original_filename,
        "original_path": asset.original_path,
        "file_size": _asset_file_size(storage, asset),
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "is_animated": asset.is_animated,
        "uploaded_at": asset.crawl_time or _datetime_to_iso(asset.created_at),
        "uploader_user_id": asset.uploader_user_id,
        "uploader_username": asset.uploader_username,
        "duplicate_of": asset.duplicate_of,
        "preview_path": cache["preview_path"],
        "thumb_path": cache["thumb_path"],
        "has_preview_cache": cache["has_preview_cache"],
        "has_thumb_cache": cache["has_thumb_cache"],
        "cache_status": cache["cache_status"],
        "is_hidden": _asset_has_tag(asset, HIDDEN_TAG),
        "latest_transcode_job": transcode_job_to_dict(latest_job) if latest_job else None,
    }


def transcode_job_to_dict(job: TranscodeJobModel | None) -> dict[str, object] | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "job_id": job.job_id or f"legacy-{job.id}",
        "asset_key": job.asset_key or "",
        "uploader_user_id": job.uploader_user_id,
        "uploader_username": job.uploader_username,
        "status": job.status or "queued",
        "stage": job.stage or "",
        "message": job.message or "",
        "progress": round(float(job.progress or 0.0), 2),
        "frames_done": job.frames_done,
        "frames_total": job.frames_total,
        "frames_per_second": round(float(job.frames_per_second), 2) if job.frames_per_second is not None else None,
        "file_size": job.file_size,
        "kind": job.kind,
        "source": job.source or "upload",
        "error": job.error,
        "created_at": _datetime_to_iso(job.created_at),
        "started_at": _datetime_to_iso(job.started_at),
        "stage_started_at": _datetime_to_iso(job.stage_started_at),
        "finished_at": _datetime_to_iso(job.finished_at),
        "updated_at": _datetime_to_iso(job.updated_at),
    }


def upload_log_to_dict(
    log: UploadLogModel,
    *,
    storage: GalleryStorage | None = None,
    asset: AssetModel | None = None,
) -> dict[str, object]:
    cache = _asset_cache_state(storage, asset) if storage and asset else None
    data: dict[str, object] = {
        "id": log.id,
        "asset_key": log.asset_key,
        "uploader_user_id": log.uploader_user_id,
        "uploader_username": log.uploader_username,
        "original_filename": log.original_filename or "",
        "file_size": log.file_size,
        "mime_type": log.mime_type,
        "event": log.event or "upload",
        "status": log.status or "success",
        "message": log.message or "",
        "extra": log.extra or {},
        "is_hidden": _asset_has_tag(asset, HIDDEN_TAG),
        "created_at": _datetime_to_iso(log.created_at),
    }
    if cache:
        data.update(cache)
    return data


def get_security_settings(session: Session) -> dict[str, object]:
    row = session.get(SecuritySettingsModel, 1)
    return normalize_security_settings(row.settings if row else None)


def security_settings_to_dict(session: Session) -> dict[str, object]:
    row = session.get(SecuritySettingsModel, 1)
    data = get_security_settings(session)
    data["updated_by_username"] = row.updated_by_username if row else None
    data["updated_at"] = _datetime_to_iso(row.updated_at) if row else None
    return data


def update_security_settings(
    session: Session,
    updates: dict[str, object],
    *,
    updated_by_username: str,
) -> dict[str, object]:
    row = session.get(SecuritySettingsModel, 1)
    current = normalize_security_settings(row.settings if row else None)
    merged = {
        **current,
        **{key: value for key, value in updates.items() if value is not None},
    }
    normalized = normalize_security_settings(merged)
    if row is None:
        row = SecuritySettingsModel(id=1)
        session.add(row)
    row.settings = normalized
    row.updated_by_username = updated_by_username
    row.updated_at = now_utc()
    session.commit()
    return security_settings_to_dict(session)


def create_access_log(
    session: Session,
    *,
    client_ip: str,
    user_id: int | None,
    username: str | None,
    role: str | None,
    method: str,
    path: str,
    query_string: str,
    status_code: int,
    duration_ms: float,
    request_bytes: int | None,
    response_bytes: int | None,
    user_agent: str,
    referer: str,
    origin: str,
    rejection_reason: str | None = None,
    error: str | None = None,
    retention: int = 5000,
    prune: bool = True,
    flush: bool = True,
) -> AccessLogModel:
    log = AccessLogModel(
        client_ip=client_ip,
        user_id=user_id,
        username=username,
        role=role,
        method=method,
        path=path,
        query_string=query_string,
        status_code=status_code,
        duration_ms=duration_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        user_agent=user_agent[:1000],
        referer=referer[:1000],
        origin=origin[:1000],
        rejection_reason=rejection_reason,
        error=error[:1000] if error else None,
    )
    session.add(log)
    if flush:
        session.flush()
    if prune:
        _prune_access_logs(session, retention)
        if flush:
            session.flush()
    return log


def list_access_logs(
    session: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    q: str = "",
) -> list[AccessLogModel]:
    statement = select(AccessLogModel).order_by(AccessLogModel.created_at.desc(), AccessLogModel.id.desc())
    needle = q.strip().lower()
    if needle:
        pattern = _contains_pattern(needle)
        statement = statement.where(
            func.lower(
                AccessLogModel.method
                + " "
                + AccessLogModel.path
                + " "
                + func.coalesce(AccessLogModel.username, "")
                + " "
                + AccessLogModel.client_ip
                + " "
                + func.coalesce(AccessLogModel.rejection_reason, "")
            ).like(pattern, escape="\\")
        )
    return list(session.scalars(statement.limit(limit).offset(offset)).all())


def access_log_to_dict(log: AccessLogModel) -> dict[str, object]:
    return {
        "id": log.id,
        "client_ip": log.client_ip,
        "user_id": log.user_id,
        "username": log.username,
        "role": log.role,
        "method": log.method,
        "path": log.path,
        "query_string": log.query_string,
        "status_code": log.status_code,
        "duration_ms": round(float(log.duration_ms or 0.0), 2),
        "request_bytes": log.request_bytes,
        "response_bytes": log.response_bytes,
        "user_agent": log.user_agent,
        "referer": log.referer,
        "origin": log.origin,
        "rejection_reason": log.rejection_reason,
        "error": log.error,
        "created_at": _datetime_to_iso(log.created_at),
    }


def _prune_access_logs(session: Session, retention: int) -> None:
    if retention <= 0:
        return
    cutoff = session.scalar(
        select(AccessLogModel.id)
        .order_by(AccessLogModel.id.desc())
        .offset(retention)
        .limit(1)
    )
    if cutoff is None:
        return
    session.execute(delete(AccessLogModel).where(AccessLogModel.id <= cutoff))


def _web_artist_name(asset: AssetModel) -> str:
    artist_name = asset.artist_name or ""
    uploader_username = asset.uploader_username or ""
    if (
        asset.source == "upload"
        and not (asset.artist_id or "").strip()
        and artist_name
        and uploader_username
        and normalize_name(artist_name) == normalize_name(uploader_username)
    ):
        return ""
    return artist_name


def tag_summary(session: Session, catalog: TagCatalog) -> dict[str, object]:
    counts = {
        tag: count
        for tag, count in session.execute(
            select(AssetTagModel.tag, func.count(AssetTagModel.asset_key))
            .group_by(AssetTagModel.tag)
        )
    }
    items: dict[str, dict[str, object]] = {}
    for name, tag in catalog.tags.items():
        items[name] = {
            **tag.to_dict(),
            "count": int(counts.get(name, 0)),
            "source": "catalog",
        }
    for name, count in counts.items():
        if name in items:
            if count:
                items[name]["source"] = "catalog+observed"
            continue
        items[name] = {
            "name": name,
            "category": name.split(":", 1)[0] if ":" in name else "general",
            "aliases": [],
            "labels": {},
            "implications": [],
            "suggestions": [],
            "count": int(count),
            "source": "observed",
        }

    categories = [
        {
            "name": category.name,
            "color": category.color,
            "order": category.order,
            "is_default": category.is_default,
        }
        for category in sorted(catalog.categories.values(), key=lambda item: item.order)
    ]
    return {
        "categories": categories,
        "items": sorted(
            items.values(),
            key=lambda item: (
                tag_sort_key(str(item["name"]))[0],
                -int(item["count"]),
                str(item["name"]),
            ),
        ),
        "total": len(items),
    }


def mark_asset_pending_cleanup(
    session: Session,
    storage: GalleryStorage,
    asset_key: str,
    *,
    deleted_by_user_id: int | None,
    deleted_by_username: str,
) -> AssetModel:
    asset = session.get(AssetModel, asset_key)
    if asset is None:
        raise ValueError(f"asset not found: {asset_key}")

    metadata = storage.read_metadata(asset_key)
    updated = metadata.__class__(
        **{
            **metadata.to_dict(),
            "deletion_status": "pending_cleanup",
            "deleted_at": utc_now_iso(),
            "deleted_by_user_id": deleted_by_user_id,
            "deleted_by_username": deleted_by_username,
        }
    )
    storage.write_metadata(updated, replace=True)
    tags = [tag.tag for tag in asset.tags]
    updated_asset = upsert_asset(session, storage, updated, tags, duplicate_of=asset.duplicate_of)
    session.commit()
    return updated_asset


def purge_pending_asset(session: Session, storage: GalleryStorage, asset_key: str) -> dict[str, object]:
    asset = session.get(AssetModel, asset_key)
    metadata = storage.read_metadata(asset_key)
    if metadata.deletion_status != "pending_cleanup":
        raise ValueError(f"asset is not pending cleanup: {asset_key}")

    deleted_files = storage.delete_asset_files(metadata)
    storage.remove_metadata(asset_key)
    if asset is not None:
        session.execute(delete(AssetTagModel).where(AssetTagModel.asset_key == asset_key))
        session.execute(delete(AssetModel).where(AssetModel.asset_key == asset_key))
    session.commit()
    return {
        "asset_key": asset_key,
        "status": "purged",
        "deleted_files": deleted_files,
    }


def _apply_tag_filters(statement, parsed: SearchQuery):
    for tag in parsed.required:
        statement = statement.where(
            exists(
                select(AssetTagModel.asset_key).where(
                    AssetTagModel.asset_key == AssetModel.asset_key,
                    AssetTagModel.tag == tag,
                )
            )
        )
    for tag in parsed.excluded:
        statement = statement.where(
            ~exists(
                select(AssetTagModel.asset_key).where(
                    AssetTagModel.asset_key == AssetModel.asset_key,
                    AssetTagModel.tag == tag,
                )
            )
        )
    if parsed.exclude_hidden:
        statement = statement.where(
            ~exists(
                select(AssetTagModel.asset_key).where(
                    AssetTagModel.asset_key == AssetModel.asset_key,
                    _hidden_tag_clause(),
                )
            )
        )
    filename_column = func.lower(AssetModel.original_filename)
    for term in parsed.filename_required:
        statement = statement.where(filename_column.like(_contains_pattern(term), escape="\\"))
    for term in parsed.filename_excluded:
        statement = statement.where(~filename_column.like(_contains_pattern(term), escape="\\"))
    return statement

def normalize_asset_sort(sort: str | None) -> str:
    requested = normalize_name(sort or "asset_key")
    normalized = ASSET_SORT_ALIASES.get(requested, requested)
    return normalized if normalized in ASSET_SORT_KEYS else "asset_key"


def normalize_sort_order(order: str | None) -> str:
    return "desc" if normalize_name(order or "") == "desc" else "asc"


def _apply_sort(statement, sort: str | None, order: str | None):
    sort_key = normalize_asset_sort(sort)
    direction = normalize_sort_order(order)
    expression = _sort_expression(sort_key)
    empty_last = func.coalesce(expression, "") == ""
    sorted_expression = expression.desc() if direction == "desc" else expression.asc()
    # Pages of one work always read p0, p1, p2 even when the works themselves are newest-first.
    group = AssetModel.source_id.desc() if direction == "desc" else AssetModel.source_id.asc()
    return statement.order_by(
        empty_last.asc(),
        sorted_expression,
        group,
        AssetModel.page_index.is_(None).asc(),
        AssetModel.page_index.asc(),
        AssetModel.asset_key.asc(),
    )


def _sort_expression(sort_key: str):
    if sort_key == "artwork_date":
        return AssetModel.artwork_date
    if sort_key == "pixiv_upload_date":
        return AssetModel.pixiv_upload_date
    if sort_key == "uploaded_at":
        return AssetModel.crawl_time
    if sort_key == "original_filename":
        return func.lower(AssetModel.original_filename)
    if sort_key == "title":
        return func.lower(AssetModel.title)
    if sort_key == "artist":
        return func.lower(AssetModel.artist_name)
    if sort_key == "source":
        return func.lower(AssetModel.source)
    if sort_key == "source_id":
        return func.lower(AssetModel.source_id)
    return AssetModel.asset_key


def _contains_pattern(term: str) -> str:
    lowered = normalize_name(term)
    escaped = (
        lowered
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _existing_cache_relative(storage: GalleryStorage, path: Path) -> str | None:
    return storage.cache_relative_path(path) if path.exists() else None


def _existing_preview_relative(storage: GalleryStorage, asset_key: str) -> str | None:
    return (
        _existing_cache_relative(storage, storage.preview_path(asset_key, ".webp"))
        or _existing_cache_relative(storage, storage.preview_path(asset_key, ".avif"))
    )


def _latest_jobs_for_assets(session: Session, asset_keys: list[str]) -> dict[str, TranscodeJobModel]:
    if not asset_keys:
        return {}
    jobs: dict[str, TranscodeJobModel] = {}
    for job in session.scalars(
        select(TranscodeJobModel)
        .where(TranscodeJobModel.asset_key.in_(asset_keys))
        .order_by(TranscodeJobModel.id.desc())
    ):
        jobs.setdefault(job.asset_key, job)
    return jobs


def _asset_file_size(storage: GalleryStorage, asset: AssetModel) -> int | None:
    try:
        return storage.file_size(asset.original_path)
    except Exception:
        return None


def _asset_has_tag(asset: AssetModel | None, tag: str) -> bool:
    if asset is None:
        return False
    if is_hidden_tag(tag):
        return any(is_hidden_tag(item.tag) for item in asset.tags)
    return any(item.tag == tag for item in asset.tags)


def _hidden_tag_clause():
    return or_(
        AssetTagModel.tag == HIDDEN_TAG,
        AssetTagModel.tag.like("meta:hide\\_%", escape="\\"),
        AssetTagModel.tag.like("meta:hide-%", escape="\\"),
    )


def _asset_cache_state(storage: GalleryStorage | None, asset: AssetModel | None) -> dict[str, object]:
    if storage is None or asset is None:
        return {
            "preview_path": None,
            "thumb_path": None,
            "has_preview_cache": False,
            "has_thumb_cache": False,
            "cache_status": "missing",
        }
    preview_path = _existing_preview_relative(storage, asset.asset_key)
    thumb_path = _existing_cache_relative(storage, storage.thumb_path(asset.asset_key, ".avif"))
    has_preview = preview_path is not None
    has_thumb = thumb_path is not None
    if has_preview and has_thumb:
        status = "ready"
    elif has_preview or has_thumb:
        status = "partial"
    else:
        status = "missing"
    return {
        "preview_path": preview_path,
        "thumb_path": thumb_path,
        "has_preview_cache": has_preview,
        "has_thumb_cache": has_thumb,
        "cache_status": status,
    }


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _ensure_column(engine: Engine, table_name: str, column_name: str, sql_type: str) -> None:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))
