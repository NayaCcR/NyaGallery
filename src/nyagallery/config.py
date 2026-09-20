from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

from nyagallery.secret_crypto import (
    SECRET_KEY_ENV,
    decrypt_secret,
    encrypt_secret,
    generate_secret_key,
    secret_encryption_enabled,
)


DEFAULT_CONFIG_FILENAME = "nyagallery.toml"
CONFIG_ENV = "NYAGALLERY_CONFIG"
PROJECT_REPOSITORY = "https://github.com/NayaCcR/NyaGallery"
MiB = 1024 * 1024


@dataclass(frozen=True)
class CoreConfig:
    storage: str = "storage"
    database_url: str | None = None
    tag_catalog_path: str | None = None
    name_media_by_post_id: bool = True


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8001
    access_log: bool = False
    secure_cookies: bool = False


@dataclass(frozen=True)
class SiteConfig:
    project_homepage: str = PROJECT_REPOSITORY
    repository: str = PROJECT_REPOSITORY
    icp_beian: str = ""
    app_name: str = ""
    logo_url: str = ""
    layout: str = ""


@dataclass(frozen=True)
class PixivConfig:
    refresh_token: str | None = None
    cookie: str | None = None
    default_request_delay_seconds: float = 1.0
    max_concurrency: int = 1


@dataclass(frozen=True)
class MisskeyConfig:
    token: str | None = None
    host: str = "misskey.io"
    default_request_delay_seconds: float = 1.0
    page_size: int = 100
    download_concurrency: int = 5


@dataclass(frozen=True)
class XConfig:
    auth_token: str | None = None
    ct0: str | None = None
    default_request_delay_seconds: float = 2.0
    page_size: int = 20
    download_concurrency: int = 4
    tweet_detail_query_id: str = "4Siu98E55GquhG52zHdY5w"
    user_by_screen_name_query_id: str = "32pL5BWe9WKeSK1MoPvFQQ"
    user_tweets_query_id: str = "V7H0Ap3_Hh2FyS75OCDO3Q"
    user_media_query_id: str = "dexO_2tohK86JDudXXG3Yw"


@dataclass(frozen=True)
class FanboxConfig:
    session_id: str | None = None
    default_request_delay_seconds: float = 1.0
    page_size: int = 10
    download_concurrency: int = 3
    download_files: bool = True


@dataclass(frozen=True)
class MediaConfig:
    max_frame_pixels: int = 50_000_000
    max_image_pixels: int = 100_000_000
    max_animation_frames: int = 500
    max_animation_memory_bytes: int = 512 * MiB
    max_zip_uncompressed_bytes: int = 512 * MiB
    max_zip_frame_bytes: int = 64 * MiB
    max_video_bytes: int = 128 * MiB
    generation_timeout_seconds: int = 300
    task_timeout_seconds: int = 300
    max_concurrency: int = 0
    upload_read_chunk_bytes: int = MiB
    preview_max_edge: int = 1800
    thumb_max_edge: int = 420
    avif_quality: int = 70
    webp_quality: int = 75


@dataclass(frozen=True)
class NetworkProxyConfig:
    name: str
    url: str = ""
    auth_enabled: bool = False
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class NetworkSourceConfig:
    source: str
    proxy: str = ""


@dataclass(frozen=True)
class NetworkConfig:
    default_proxy: str = "direct"
    proxies: tuple[NetworkProxyConfig, ...] = (NetworkProxyConfig(name="direct"),)
    sources: tuple[NetworkSourceConfig, ...] = (NetworkSourceConfig(source="pixiv", proxy="direct"),)


@dataclass(frozen=True)
class RedisConfig:
    url: str | None = None
    key_prefix: str = "nyagallery"
    security_limiter: bool = False


@dataclass(frozen=True)
class SecurityConfig:
    secret_key: str = ""


@dataclass(frozen=True)
class StorageStrategyConfig:
    name: str
    type: str = "local"
    prefix: str = "original"
    endpoint: str = ""
    bucket: str = ""
    region: str = ""
    username: str = ""
    password: str = ""
    token: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""
    drive_id: str = ""
    root_path: str = ""
    timeout_seconds: int = 60


@dataclass(frozen=True)
class OriginalStorageConfig:
    default_strategy: str = "local"
    strategies: tuple[StorageStrategyConfig, ...] = ()


@dataclass(frozen=True)
class DeveloperConfig:
    config_editor_enabled: bool = True
    console_enabled: bool = False


@dataclass(frozen=True)
class NyaGalleryConfig:
    core: CoreConfig = CoreConfig()
    server: ServerConfig = ServerConfig()
    site: SiteConfig = SiteConfig()
    pixiv: PixivConfig = PixivConfig()
    misskey: MisskeyConfig = MisskeyConfig()
    x: XConfig = XConfig()
    fanbox: FanboxConfig = FanboxConfig()
    media: MediaConfig = MediaConfig()
    network: NetworkConfig = NetworkConfig()
    redis: RedisConfig = RedisConfig()
    security: SecurityConfig = SecurityConfig()
    original_storage: OriginalStorageConfig = OriginalStorageConfig()
    developer: DeveloperConfig = DeveloperConfig()
    path: Path | None = None


def load_config(path: str | Path | None = None) -> NyaGalleryConfig:
    resolved = _resolve_config_path(path)
    data: dict[str, Any] = {}
    if resolved:
        data = tomllib.loads(resolved.read_text(encoding="utf-8"))
    config = _config_from_dict(data, resolved)
    return _with_env_overrides(config)


def apply_config_environment(config: NyaGalleryConfig) -> None:
    os.environ.setdefault("NYAGALLERY_STORAGE", config.core.storage)
    if config.core.database_url:
        os.environ.setdefault("NYAGALLERY_DATABASE_URL", config.core.database_url)
    if config.server.secure_cookies:
        os.environ.setdefault("NYAGALLERY_SECURE_COOKIES", "1")
    if config.pixiv.refresh_token:
        os.environ.setdefault("PIXIV_REFRESH_TOKEN", config.pixiv.refresh_token)
    if config.misskey.token:
        os.environ.setdefault("MISSKEY_TOKEN", config.misskey.token)
    if config.x.auth_token:
        os.environ.setdefault("X_AUTH_TOKEN", config.x.auth_token)
    if config.x.ct0:
        os.environ.setdefault("X_CT0", config.x.ct0)
    if config.fanbox.session_id:
        os.environ.setdefault("FANBOXSESSID", config.fanbox.session_id)
    if config.redis.url:
        os.environ.setdefault("NYAGALLERY_REDIS_URL", config.redis.url)
    if config.security.secret_key:
        os.environ.setdefault(SECRET_KEY_ENV, config.security.secret_key)
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_FRAME_PIXELS", str(config.media.max_frame_pixels))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_IMAGE_PIXELS", str(config.media.max_image_pixels))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_ANIMATION_FRAMES", str(config.media.max_animation_frames))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_ANIMATION_MEMORY_BYTES", str(config.media.max_animation_memory_bytes))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_ZIP_UNCOMPRESSED_BYTES", str(config.media.max_zip_uncompressed_bytes))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_ZIP_FRAME_BYTES", str(config.media.max_zip_frame_bytes))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_VIDEO_BYTES", str(config.media.max_video_bytes))
    os.environ.setdefault("NYAGALLERY_MEDIA_GENERATION_TIMEOUT_SECONDS", str(config.media.generation_timeout_seconds))
    os.environ.setdefault("NYAGALLERY_MEDIA_TASK_TIMEOUT_SECONDS", str(config.media.task_timeout_seconds))
    os.environ.setdefault("NYAGALLERY_MEDIA_MAX_CONCURRENCY", str(config.media.max_concurrency))
    os.environ.setdefault("NYAGALLERY_UPLOAD_READ_CHUNK_BYTES", str(config.media.upload_read_chunk_bytes))


def config_to_dict(config: NyaGalleryConfig, *, redact_secrets: bool = False) -> dict[str, object]:
    pixiv_refresh_token = "" if redact_secrets and config.pixiv.refresh_token else config.pixiv.refresh_token or ""
    pixiv_cookie = "" if redact_secrets and config.pixiv.cookie else config.pixiv.cookie or ""
    misskey_token = "" if redact_secrets and config.misskey.token else config.misskey.token or ""
    x_auth_token = "" if redact_secrets and config.x.auth_token else config.x.auth_token or ""
    x_ct0 = "" if redact_secrets and config.x.ct0 else config.x.ct0 or ""
    fanbox_session = "" if redact_secrets and config.fanbox.session_id else config.fanbox.session_id or ""
    secret_key = "" if redact_secrets and config.security.secret_key else config.security.secret_key
    return {
        "core": {
            "storage": config.core.storage,
            "database_url": config.core.database_url or "",
            "tag_catalog_path": config.core.tag_catalog_path or "",
            "name_media_by_post_id": config.core.name_media_by_post_id,
        },
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "access_log": config.server.access_log,
            "secure_cookies": config.server.secure_cookies,
        },
        "site": {
            "project_homepage": config.site.project_homepage,
            "repository": config.site.repository,
            "icp_beian": config.site.icp_beian,
            "app_name": config.site.app_name,
            "logo_url": config.site.logo_url,
            "layout": config.site.layout,
        },
        "pixiv": {
            "refresh_token": pixiv_refresh_token,
            "cookie": pixiv_cookie,
            "default_request_delay_seconds": config.pixiv.default_request_delay_seconds,
            "max_concurrency": config.pixiv.max_concurrency,
        },
        "misskey": {
            "token": misskey_token,
            "host": config.misskey.host,
            "default_request_delay_seconds": config.misskey.default_request_delay_seconds,
            "page_size": config.misskey.page_size,
            "download_concurrency": config.misskey.download_concurrency,
        },
        "x": {
            "auth_token": x_auth_token,
            "ct0": x_ct0,
            "default_request_delay_seconds": config.x.default_request_delay_seconds,
            "page_size": config.x.page_size,
            "download_concurrency": config.x.download_concurrency,
            "tweet_detail_query_id": config.x.tweet_detail_query_id,
            "user_by_screen_name_query_id": config.x.user_by_screen_name_query_id,
            "user_tweets_query_id": config.x.user_tweets_query_id,
            "user_media_query_id": config.x.user_media_query_id,
        },
        "fanbox": {
            "session_id": fanbox_session,
            "default_request_delay_seconds": config.fanbox.default_request_delay_seconds,
            "page_size": config.fanbox.page_size,
            "download_concurrency": config.fanbox.download_concurrency,
            "download_files": config.fanbox.download_files,
        },
        "media": {
            "max_frame_pixels": config.media.max_frame_pixels,
            "max_image_pixels": config.media.max_image_pixels,
            "max_animation_frames": config.media.max_animation_frames,
            "max_animation_memory_bytes": config.media.max_animation_memory_bytes,
            "max_zip_uncompressed_bytes": config.media.max_zip_uncompressed_bytes,
            "max_zip_frame_bytes": config.media.max_zip_frame_bytes,
            "max_video_bytes": config.media.max_video_bytes,
            "generation_timeout_seconds": config.media.generation_timeout_seconds,
            "task_timeout_seconds": config.media.task_timeout_seconds,
            "max_concurrency": config.media.max_concurrency,
            "upload_read_chunk_bytes": config.media.upload_read_chunk_bytes,
            "preview_max_edge": config.media.preview_max_edge,
            "thumb_max_edge": config.media.thumb_max_edge,
            "avif_quality": config.media.avif_quality,
            "webp_quality": config.media.webp_quality,
        },
        "network": {
            "default_proxy": config.network.default_proxy,
            "proxies": [
                _network_proxy_to_dict(proxy, redact_secrets=redact_secrets)
                for proxy in config.network.proxies
            ],
            "sources": [
                {"source": source.source, "proxy": source.proxy}
                for source in config.network.sources
            ],
        },
        "redis": {
            "url": config.redis.url or "",
            "key_prefix": config.redis.key_prefix,
            "security_limiter": config.redis.security_limiter,
        },
        "security": {
            "secret_key": secret_key,
            "secret_encryption_enabled": secret_encryption_enabled(config.security.secret_key),
        },
        "original_storage": {
            "default_strategy": config.original_storage.default_strategy,
            "strategies": [
                _storage_strategy_to_dict(strategy, redact_secrets=redact_secrets)
                for strategy in config.original_storage.strategies
            ],
        },
        "developer": {
            "config_editor_enabled": config.developer.config_editor_enabled,
            "console_enabled": config.developer.console_enabled,
        },
    }


def read_config_file_data(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return {}
    return tomllib.loads(resolved.read_text(encoding="utf-8"))


def save_config_file(data: Mapping[str, Any], path: str | Path | None = None) -> NyaGalleryConfig:
    resolved = Path(path or DEFAULT_CONFIG_FILENAME).expanduser()
    config = _config_from_dict(_data_with_secret_key(dict(data)), resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(render_config(config), encoding="utf-8")
    return config


def network_proxy_for(config: NyaGalleryConfig, source: str) -> str | None:
    source_key = _network_source_key(source)
    env_default = str(os.environ.get("NYAGALLERY_NETWORK_PROXY") or "").strip()
    if env_default:
        return env_default
    resolved = _network_proxy_url_for(config.network, source_key)
    if resolved:
        return resolved
    return None


def render_config(config: NyaGalleryConfig) -> str:
    secret_key = config.security.secret_key
    lines: list[str] = [
        "[core]",
        f"storage = {_toml_string(config.core.storage)}",
        f"database_url = {_toml_string(config.core.database_url or '')}",
        f"tag_catalog_path = {_toml_string(config.core.tag_catalog_path or '')}",
        f"name_media_by_post_id = {_toml_bool(config.core.name_media_by_post_id)}",
        "",
        "[server]",
        f"host = {_toml_string(config.server.host)}",
        f"port = {int(config.server.port)}",
        f"access_log = {_toml_bool(config.server.access_log)}",
        f"secure_cookies = {_toml_bool(config.server.secure_cookies)}",
        "",
        "[site]",
        f"project_homepage = {_toml_string(config.site.project_homepage)}",
        f"repository = {_toml_string(config.site.repository)}",
        f"icp_beian = {_toml_string(config.site.icp_beian)}",
        f"app_name = {_toml_string(config.site.app_name)}",
        f"logo_url = {_toml_string(config.site.logo_url)}",
        f"layout = {_toml_string(config.site.layout)}",
        "",
        "[pixiv]",
        f"refresh_token = {_toml_string(encrypt_secret(config.pixiv.refresh_token or '', secret_key))}",
        f"cookie = {_toml_string(encrypt_secret(config.pixiv.cookie or '', secret_key))}",
        f"default_request_delay_seconds = {float(config.pixiv.default_request_delay_seconds):g}",
        f"max_concurrency = {int(config.pixiv.max_concurrency)}",
        "",
        "[misskey]",
        f"token = {_toml_string(encrypt_secret(config.misskey.token or '', secret_key))}",
        f"host = {_toml_string(config.misskey.host)}",
        f"default_request_delay_seconds = {float(config.misskey.default_request_delay_seconds):g}",
        f"page_size = {int(config.misskey.page_size)}",
        f"download_concurrency = {int(config.misskey.download_concurrency)}",
        "",
        "[x]",
        f"auth_token = {_toml_string(encrypt_secret(config.x.auth_token or '', secret_key))}",
        f"ct0 = {_toml_string(encrypt_secret(config.x.ct0 or '', secret_key))}",
        f"default_request_delay_seconds = {float(config.x.default_request_delay_seconds):g}",
        f"page_size = {int(config.x.page_size)}",
        f"download_concurrency = {int(config.x.download_concurrency)}",
        f"tweet_detail_query_id = {_toml_string(config.x.tweet_detail_query_id)}",
        f"user_by_screen_name_query_id = {_toml_string(config.x.user_by_screen_name_query_id)}",
        f"user_tweets_query_id = {_toml_string(config.x.user_tweets_query_id)}",
        f"user_media_query_id = {_toml_string(config.x.user_media_query_id)}",
        "",
        "[fanbox]",
        f"session_id = {_toml_string(encrypt_secret(config.fanbox.session_id or '', secret_key))}",
        f"default_request_delay_seconds = {float(config.fanbox.default_request_delay_seconds):g}",
        f"page_size = {int(config.fanbox.page_size)}",
        f"download_concurrency = {int(config.fanbox.download_concurrency)}",
        f"download_files = {'true' if config.fanbox.download_files else 'false'}",
        "",
        "[media]",
        f"max_frame_pixels = {int(config.media.max_frame_pixels)}",
        f"max_image_pixels = {int(config.media.max_image_pixels)}",
        f"max_animation_frames = {int(config.media.max_animation_frames)}",
        f"max_animation_memory_bytes = {int(config.media.max_animation_memory_bytes)}",
        f"max_zip_uncompressed_bytes = {int(config.media.max_zip_uncompressed_bytes)}",
        f"max_zip_frame_bytes = {int(config.media.max_zip_frame_bytes)}",
        f"max_video_bytes = {int(config.media.max_video_bytes)}",
        f"generation_timeout_seconds = {int(config.media.generation_timeout_seconds)}",
        f"task_timeout_seconds = {int(config.media.task_timeout_seconds)}",
        f"max_concurrency = {int(config.media.max_concurrency)}",
        f"upload_read_chunk_bytes = {int(config.media.upload_read_chunk_bytes)}",
        f"preview_max_edge = {int(config.media.preview_max_edge)}",
        f"thumb_max_edge = {int(config.media.thumb_max_edge)}",
        f"avif_quality = {int(config.media.avif_quality)}",
        f"webp_quality = {int(config.media.webp_quality)}",
        "",
        "[network]",
        f"default_proxy = {_toml_string(config.network.default_proxy)}",
        "",
        *_render_network_proxies(config.network.proxies, secret_key=secret_key),
        *_render_network_sources(config.network.sources),
        "[redis]",
        f"url = {_toml_string(config.redis.url or '')}",
        f"key_prefix = {_toml_string(config.redis.key_prefix)}",
        f"security_limiter = {_toml_bool(config.redis.security_limiter)}",
        "",
        "[security]",
        f"secret_key = {_toml_string(config.security.secret_key)}",
        "",
        "[original_storage]",
        f"default_strategy = {_toml_string(config.original_storage.default_strategy)}",
        "",
        *_render_storage_strategies(config.original_storage.strategies, secret_key=secret_key),
        "[developer]",
        f"config_editor_enabled = {_toml_bool(config.developer.config_editor_enabled)}",
        f"console_enabled = {_toml_bool(config.developer.console_enabled)}",
        "",
    ]
    return "\n".join(lines)


def _storage_strategy_to_dict(strategy: StorageStrategyConfig, *, redact_secrets: bool = False) -> dict[str, object]:
    password = "" if redact_secrets and strategy.password else strategy.password
    token = "" if redact_secrets and strategy.token else strategy.token
    access_key_secret = "" if redact_secrets and strategy.access_key_secret else strategy.access_key_secret
    return {
        "name": strategy.name,
        "type": strategy.type,
        "prefix": strategy.prefix,
        "endpoint": strategy.endpoint,
        "bucket": strategy.bucket,
        "region": strategy.region,
        "username": strategy.username,
        "password": password,
        "token": token,
        "access_key_id": strategy.access_key_id,
        "access_key_secret": access_key_secret,
        "drive_id": strategy.drive_id,
        "root_path": strategy.root_path,
        "timeout_seconds": strategy.timeout_seconds,
    }


def _network_proxy_to_dict(proxy: NetworkProxyConfig, *, redact_secrets: bool = False) -> dict[str, object]:
    return {
        "name": proxy.name,
        "url": proxy.url,
        "url_configured": bool(proxy.url),
        "auth_enabled": proxy.auth_enabled,
        "username": proxy.username,
        "password": "" if redact_secrets and proxy.password else proxy.password,
        "password_configured": bool(proxy.password),
    }


def _render_network_proxies(proxies: tuple[NetworkProxyConfig, ...], *, secret_key: str = "") -> list[str]:
    lines: list[str] = []
    for proxy in proxies:
        lines.extend(
            [
                "[[network.proxies]]",
                f"name = {_toml_string(proxy.name)}",
                f"url = {_toml_string(proxy.url)}",
                f"auth_enabled = {_toml_bool(proxy.auth_enabled)}",
                f"username = {_toml_string(proxy.username if proxy.auth_enabled else '')}",
                f"password = {_toml_string(encrypt_secret(proxy.password if proxy.auth_enabled else '', secret_key))}",
                "",
            ]
        )
    return lines


def _render_network_sources(sources: tuple[NetworkSourceConfig, ...]) -> list[str]:
    lines: list[str] = []
    for source in sources:
        source_key = _network_source_key(source.source)
        if not source_key:
            continue
        lines.extend(
            [
                f"[network.sources.{source_key}]",
                f"proxy = {_toml_string(source.proxy)}",
                "",
            ]
        )
    return lines


def _render_storage_strategies(strategies: tuple[StorageStrategyConfig, ...], *, secret_key: str = "") -> list[str]:
    lines: list[str] = []
    for strategy in strategies:
        lines.extend(
            [
                "[[original_storage.strategies]]",
                f"name = {_toml_string(strategy.name)}",
                f"type = {_toml_string(strategy.type)}",
                f"prefix = {_toml_string(strategy.prefix)}",
                f"endpoint = {_toml_string(strategy.endpoint)}",
                f"bucket = {_toml_string(strategy.bucket)}",
                f"region = {_toml_string(strategy.region)}",
                f"username = {_toml_string(strategy.username)}",
                f"password = {_toml_string(encrypt_secret(strategy.password, secret_key))}",
                f"token = {_toml_string(encrypt_secret(strategy.token, secret_key))}",
                f"access_key_id = {_toml_string(strategy.access_key_id)}",
                f"access_key_secret = {_toml_string(encrypt_secret(strategy.access_key_secret, secret_key))}",
                f"drive_id = {_toml_string(strategy.drive_id)}",
                f"root_path = {_toml_string(strategy.root_path)}",
                f"timeout_seconds = {int(strategy.timeout_seconds)}",
                "",
            ]
        )
    return lines


def _resolve_config_path(path: str | Path | None) -> Path | None:
    requested = path or os.environ.get(CONFIG_ENV)
    if requested:
        resolved = Path(requested).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"config file not found: {resolved}")
        return resolved

    default_path = Path(DEFAULT_CONFIG_FILENAME)
    return default_path if default_path.exists() else None


def _config_from_dict(data: dict[str, Any], path: Path | None) -> NyaGalleryConfig:
    core = _table(data, "core")
    server = _table(data, "server")
    site = _table(data, "site")
    pixiv = _table(data, "pixiv")
    misskey = _table(data, "misskey")
    x = _table(data, "x")
    fanbox = _table(data, "fanbox")
    media = _table(data, "media")
    network = _table(data, "network")
    redis = _table(data, "redis")
    security = _table(data, "security")
    original_storage = _table(data, "original_storage")
    developer = _table(data, "developer")
    secret_key = os.environ.get(SECRET_KEY_ENV) or _str(security.get("secret_key"), "")
    return NyaGalleryConfig(
        core=CoreConfig(
            storage=_str(core.get("storage"), "storage"),
            database_url=_optional_str(core.get("database_url")),
            tag_catalog_path=_optional_str(core.get("tag_catalog_path")),
            name_media_by_post_id=_bool(core.get("name_media_by_post_id"), True),
        ),
        server=ServerConfig(
            host=_str(server.get("host"), "127.0.0.1"),
            port=_int(server.get("port"), 8001),
            access_log=_bool(server.get("access_log"), False),
            secure_cookies=_bool(server.get("secure_cookies"), False),
        ),
        site=SiteConfig(
            project_homepage=_str(site.get("project_homepage"), PROJECT_REPOSITORY),
            repository=_str(site.get("repository"), PROJECT_REPOSITORY),
            icp_beian=_str(site.get("icp_beian"), ""),
            app_name=_str(site.get("app_name"), ""),
            logo_url=_str(site.get("logo_url"), ""),
            layout=_str(site.get("layout"), "").strip().casefold(),
        ),
        pixiv=PixivConfig(
            refresh_token=_optional_secret(pixiv.get("refresh_token"), secret_key),
            cookie=_optional_secret(pixiv.get("cookie"), secret_key),
            default_request_delay_seconds=_float(pixiv.get("default_request_delay_seconds"), 1.0),
            max_concurrency=_int(pixiv.get("max_concurrency"), 1),
        ),
        misskey=MisskeyConfig(
            token=_optional_secret(misskey.get("token") or misskey.get("access_token"), secret_key),
            host=_str(misskey.get("host"), "misskey.io"),
            default_request_delay_seconds=_float(misskey.get("default_request_delay_seconds"), 1.0),
            page_size=_bounded_int(misskey.get("page_size"), 100, minimum=1, maximum=100),
            download_concurrency=_bounded_int(misskey.get("download_concurrency"), 5, minimum=1, maximum=16),
        ),
        x=XConfig(
            auth_token=_optional_secret(x.get("auth_token"), secret_key),
            ct0=_optional_secret(x.get("ct0") or x.get("csrf_token"), secret_key),
            default_request_delay_seconds=_float(x.get("default_request_delay_seconds"), 2.0),
            page_size=_bounded_int(x.get("page_size"), 20, minimum=1, maximum=100),
            download_concurrency=_bounded_int(x.get("download_concurrency"), 4, minimum=1, maximum=16),
            tweet_detail_query_id=_str(x.get("tweet_detail_query_id"), XConfig.tweet_detail_query_id),
            user_by_screen_name_query_id=_str(
                x.get("user_by_screen_name_query_id"), XConfig.user_by_screen_name_query_id
            ),
            user_tweets_query_id=_str(x.get("user_tweets_query_id"), XConfig.user_tweets_query_id),
            user_media_query_id=_str(x.get("user_media_query_id"), XConfig.user_media_query_id),
        ),
        fanbox=FanboxConfig(
            session_id=_optional_secret(fanbox.get("session_id") or fanbox.get("fanboxsessid"), secret_key),
            default_request_delay_seconds=_float(fanbox.get("default_request_delay_seconds"), 1.0),
            page_size=_bounded_int(fanbox.get("page_size"), 10, minimum=1, maximum=300),
            download_concurrency=_bounded_int(fanbox.get("download_concurrency"), 3, minimum=1, maximum=16),
            download_files=_bool(fanbox.get("download_files"), True),
        ),
        media=MediaConfig(
            max_frame_pixels=_positive_int(media.get("max_frame_pixels"), 50_000_000),
            max_image_pixels=_positive_int(media.get("max_image_pixels"), 100_000_000),
            max_animation_frames=_positive_int(media.get("max_animation_frames"), 500),
            max_animation_memory_bytes=_positive_int(media.get("max_animation_memory_bytes"), 512 * MiB),
            max_zip_uncompressed_bytes=_positive_int(media.get("max_zip_uncompressed_bytes"), 512 * MiB),
            max_zip_frame_bytes=_positive_int(media.get("max_zip_frame_bytes"), 64 * MiB),
            max_video_bytes=_positive_int(media.get("max_video_bytes"), 128 * MiB),
            generation_timeout_seconds=_positive_int(media.get("generation_timeout_seconds"), 300),
            task_timeout_seconds=_positive_int(media.get("task_timeout_seconds"), 300),
            max_concurrency=max(0, _int(media.get("max_concurrency"), 0)),
            upload_read_chunk_bytes=max(64 * 1024, _positive_int(media.get("upload_read_chunk_bytes"), MiB)),
            preview_max_edge=_positive_int(media.get("preview_max_edge"), 1800),
            thumb_max_edge=_positive_int(media.get("thumb_max_edge"), 420),
            avif_quality=_bounded_int(media.get("avif_quality"), 70, minimum=1, maximum=100),
            webp_quality=_bounded_int(media.get("webp_quality"), 75, minimum=1, maximum=100),
        ),
        network=_network_from_dict(network, secret_key=secret_key),
        redis=RedisConfig(
            url=_optional_str(redis.get("url")),
            key_prefix=_str(redis.get("key_prefix"), "nyagallery"),
            security_limiter=_bool(redis.get("security_limiter"), False),
        ),
        security=SecurityConfig(secret_key=secret_key),
        original_storage=OriginalStorageConfig(
            default_strategy=_str(original_storage.get("default_strategy"), "local"),
            strategies=tuple(_storage_strategy_from_dict(item, secret_key=secret_key) for item in _strategy_items(original_storage)),
        ),
        developer=DeveloperConfig(
            config_editor_enabled=_bool(developer.get("config_editor_enabled"), True),
            console_enabled=_bool(developer.get("console_enabled"), False),
        ),
        path=path,
    )


def _with_env_overrides(config: NyaGalleryConfig) -> NyaGalleryConfig:
    core = CoreConfig(
        storage=os.environ.get("NYAGALLERY_STORAGE") or config.core.storage,
        database_url=os.environ.get("NYAGALLERY_DATABASE_URL") or config.core.database_url,
        tag_catalog_path=os.environ.get("NYAGALLERY_TAG_CATALOG") or config.core.tag_catalog_path,
        name_media_by_post_id=_bool(
            os.environ.get("NYAGALLERY_NAME_MEDIA_BY_POST_ID"),
            config.core.name_media_by_post_id,
        ),
    )
    server = ServerConfig(
        host=os.environ.get("NYAGALLERY_HOST") or config.server.host,
        port=_int(os.environ.get("NYAGALLERY_PORT"), config.server.port),
        access_log=_bool(os.environ.get("NYAGALLERY_ACCESS_LOG"), config.server.access_log),
        secure_cookies=_bool(os.environ.get("NYAGALLERY_SECURE_COOKIES"), config.server.secure_cookies),
    )
    site = SiteConfig(
        project_homepage=os.environ.get("NYAGALLERY_SITE_HOMEPAGE") or config.site.project_homepage,
        repository=os.environ.get("NYAGALLERY_SITE_REPOSITORY") or config.site.repository,
        icp_beian=os.environ.get("NYAGALLERY_SITE_ICP_BEIAN") or config.site.icp_beian,
        app_name=os.environ.get("NYAGALLERY_SITE_APP_NAME") or config.site.app_name,
        logo_url=os.environ.get("NYAGALLERY_SITE_LOGO_URL") or config.site.logo_url,
        layout=(os.environ.get("NYAGALLERY_SITE_LAYOUT") or config.site.layout).strip().casefold(),
    )
    pixiv = PixivConfig(
        refresh_token=os.environ.get("PIXIV_REFRESH_TOKEN") or config.pixiv.refresh_token,
        cookie=os.environ.get("PIXIV_COOKIE") or config.pixiv.cookie,
        default_request_delay_seconds=_float(
            os.environ.get("NYAGALLERY_PIXIV_DEFAULT_DELAY"),
            config.pixiv.default_request_delay_seconds,
        ),
        max_concurrency=_int(os.environ.get("NYAGALLERY_PIXIV_MAX_CONCURRENCY"), config.pixiv.max_concurrency),
    )
    misskey = MisskeyConfig(
        token=os.environ.get("MISSKEY_TOKEN") or config.misskey.token,
        host=os.environ.get("NYAGALLERY_MISSKEY_HOST") or config.misskey.host,
        default_request_delay_seconds=_float(
            os.environ.get("NYAGALLERY_MISSKEY_DEFAULT_DELAY"),
            config.misskey.default_request_delay_seconds,
        ),
        page_size=_bounded_int(
            os.environ.get("NYAGALLERY_MISSKEY_PAGE_SIZE"),
            config.misskey.page_size,
            minimum=1,
            maximum=100,
        ),
        download_concurrency=_bounded_int(
            os.environ.get("NYAGALLERY_MISSKEY_DOWNLOAD_CONCURRENCY"),
            config.misskey.download_concurrency,
            minimum=1,
            maximum=16,
        ),
    )
    x = XConfig(
        auth_token=os.environ.get("X_AUTH_TOKEN") or config.x.auth_token,
        ct0=os.environ.get("X_CT0") or config.x.ct0,
        default_request_delay_seconds=_float(
            os.environ.get("NYAGALLERY_X_DEFAULT_DELAY"),
            config.x.default_request_delay_seconds,
        ),
        page_size=_bounded_int(os.environ.get("NYAGALLERY_X_PAGE_SIZE"), config.x.page_size, minimum=1, maximum=100),
        download_concurrency=_bounded_int(
            os.environ.get("NYAGALLERY_X_DOWNLOAD_CONCURRENCY"),
            config.x.download_concurrency,
            minimum=1,
            maximum=16,
        ),
        tweet_detail_query_id=os.environ.get("NYAGALLERY_X_TWEET_DETAIL_QUERY_ID") or config.x.tweet_detail_query_id,
        user_by_screen_name_query_id=(
            os.environ.get("NYAGALLERY_X_USER_QUERY_ID") or config.x.user_by_screen_name_query_id
        ),
        user_tweets_query_id=os.environ.get("NYAGALLERY_X_USER_TWEETS_QUERY_ID") or config.x.user_tweets_query_id,
        user_media_query_id=os.environ.get("NYAGALLERY_X_USER_MEDIA_QUERY_ID") or config.x.user_media_query_id,
    )
    fanbox = FanboxConfig(
        session_id=os.environ.get("FANBOXSESSID") or config.fanbox.session_id,
        default_request_delay_seconds=_float(
            os.environ.get("NYAGALLERY_FANBOX_DEFAULT_DELAY"),
            config.fanbox.default_request_delay_seconds,
        ),
        page_size=_bounded_int(
            os.environ.get("NYAGALLERY_FANBOX_PAGE_SIZE"), config.fanbox.page_size, minimum=1, maximum=300
        ),
        download_concurrency=_bounded_int(
            os.environ.get("NYAGALLERY_FANBOX_DOWNLOAD_CONCURRENCY"),
            config.fanbox.download_concurrency,
            minimum=1,
            maximum=16,
        ),
        download_files=_bool(os.environ.get("NYAGALLERY_FANBOX_DOWNLOAD_FILES"), config.fanbox.download_files),
    )
    media = MediaConfig(
        max_frame_pixels=_positive_int(os.environ.get("NYAGALLERY_MEDIA_MAX_FRAME_PIXELS"), config.media.max_frame_pixels),
        max_image_pixels=_positive_int(os.environ.get("NYAGALLERY_MEDIA_MAX_IMAGE_PIXELS"), config.media.max_image_pixels),
        max_animation_frames=_positive_int(os.environ.get("NYAGALLERY_MEDIA_MAX_ANIMATION_FRAMES"), config.media.max_animation_frames),
        max_animation_memory_bytes=_positive_int(
            os.environ.get("NYAGALLERY_MEDIA_MAX_ANIMATION_MEMORY_BYTES"),
            config.media.max_animation_memory_bytes,
        ),
        max_zip_uncompressed_bytes=_positive_int(
            os.environ.get("NYAGALLERY_MEDIA_MAX_ZIP_UNCOMPRESSED_BYTES"),
            config.media.max_zip_uncompressed_bytes,
        ),
        max_zip_frame_bytes=_positive_int(os.environ.get("NYAGALLERY_MEDIA_MAX_ZIP_FRAME_BYTES"), config.media.max_zip_frame_bytes),
        max_video_bytes=_positive_int(os.environ.get("NYAGALLERY_MEDIA_MAX_VIDEO_BYTES"), config.media.max_video_bytes),
        generation_timeout_seconds=_positive_int(
            os.environ.get("NYAGALLERY_MEDIA_GENERATION_TIMEOUT_SECONDS"),
            config.media.generation_timeout_seconds,
        ),
        task_timeout_seconds=_positive_int(
            os.environ.get("NYAGALLERY_MEDIA_TASK_TIMEOUT_SECONDS"),
            config.media.task_timeout_seconds,
        ),
        max_concurrency=max(0, _int(os.environ.get("NYAGALLERY_MEDIA_MAX_CONCURRENCY"), config.media.max_concurrency)),
        upload_read_chunk_bytes=max(
            64 * 1024,
            _positive_int(os.environ.get("NYAGALLERY_UPLOAD_READ_CHUNK_BYTES"), config.media.upload_read_chunk_bytes),
        ),
        preview_max_edge=_positive_int(os.environ.get("NYAGALLERY_MEDIA_PREVIEW_MAX_EDGE"), config.media.preview_max_edge),
        thumb_max_edge=_positive_int(os.environ.get("NYAGALLERY_MEDIA_THUMB_MAX_EDGE"), config.media.thumb_max_edge),
        avif_quality=_bounded_int(os.environ.get("NYAGALLERY_MEDIA_AVIF_QUALITY"), config.media.avif_quality, minimum=1, maximum=100),
        webp_quality=_bounded_int(os.environ.get("NYAGALLERY_MEDIA_WEBP_QUALITY"), config.media.webp_quality, minimum=1, maximum=100),
    )
    network = config.network
    network_proxy = os.environ.get("NYAGALLERY_NETWORK_PROXY")
    if network_proxy:
        network = _network_with_proxy_override(network, name="env-default", url=network_proxy, source=None)
    redis = RedisConfig(
        url=os.environ.get("NYAGALLERY_REDIS_URL") or config.redis.url,
        key_prefix=os.environ.get("NYAGALLERY_REDIS_KEY_PREFIX") or config.redis.key_prefix,
        security_limiter=_bool(
            os.environ.get("NYAGALLERY_REDIS_SECURITY_LIMITER"),
            config.redis.security_limiter,
        ),
    )
    security = SecurityConfig(
        secret_key=os.environ.get(SECRET_KEY_ENV) or config.security.secret_key,
    )
    original_storage = OriginalStorageConfig(
        default_strategy=os.environ.get("NYAGALLERY_STORAGE_STRATEGY") or config.original_storage.default_strategy,
        strategies=config.original_storage.strategies,
    )
    developer = DeveloperConfig(
        config_editor_enabled=_bool(
            os.environ.get("NYAGALLERY_CONFIG_EDITOR_ENABLED"),
            config.developer.config_editor_enabled,
        ),
        console_enabled=_bool(os.environ.get("NYAGALLERY_DEVELOPER_CONSOLE_ENABLED"), config.developer.console_enabled),
    )
    return NyaGalleryConfig(
        core=core,
        server=server,
        site=site,
        pixiv=pixiv,
        misskey=misskey,
        x=x,
        fanbox=fanbox,
        media=media,
        network=network,
        redis=redis,
        security=security,
        original_storage=original_storage,
        developer=developer,
        path=config.path,
    )


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _strategy_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    value = data.get("strategies", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _storage_strategy_from_dict(data: dict[str, Any], *, secret_key: str = "") -> StorageStrategyConfig:
    return StorageStrategyConfig(
        name=_str(data.get("name"), "local"),
        type=_str(data.get("type"), "local").casefold().replace("-", "_"),
        prefix=_str(data.get("prefix"), "original").strip("/"),
        endpoint=_str(data.get("endpoint") or data.get("url"), ""),
        bucket=_str(data.get("bucket") or data.get("service"), ""),
        region=_str(data.get("region"), ""),
        username=_str(data.get("username") or data.get("operator"), ""),
        password=_secret_str(data.get("password"), secret_key),
        token=_secret_str(data.get("token") or data.get("access_token"), secret_key),
        access_key_id=_str(data.get("access_key_id"), ""),
        access_key_secret=_secret_str(data.get("access_key_secret"), secret_key),
        drive_id=_str(data.get("drive_id"), ""),
        root_path=_str(data.get("root_path"), ""),
        timeout_seconds=_int(data.get("timeout_seconds"), 60),
    )


def _network_from_dict(
    data: dict[str, Any],
    *,
    secret_key: str = "",
) -> NetworkConfig:
    defaults = NetworkConfig()
    proxies = list(_network_proxy_items(data, secret_key=secret_key))
    sources = list(_network_source_items(data))
    has_network_config = any(key in data for key in ("default_proxy", "proxies", "sources"))
    if not has_network_config:
        return defaults
    return NetworkConfig(
        default_proxy=_str(data.get("default_proxy"), defaults.default_proxy),
        proxies=tuple(proxies) if "proxies" in data else defaults.proxies,
        sources=tuple(sources) if "sources" in data else (),
    )


def _network_proxy_items(data: dict[str, Any], *, secret_key: str = "") -> list[NetworkProxyConfig]:
    value = data.get("proxies", [])
    if not isinstance(value, list):
        return []
    proxies: list[NetworkProxyConfig] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _str(item.get("name"), "").strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        auth_enabled = _bool(item.get("auth_enabled"), bool(item.get("username") or item.get("password")))
        proxies.append(
            NetworkProxyConfig(
                name=name,
                url=_secret_str(item.get("url") or item.get("proxy"), secret_key),
                auth_enabled=auth_enabled,
                username=_str(item.get("username"), "") if auth_enabled else "",
                password=_secret_str(item.get("password"), secret_key) if auth_enabled else "",
            )
        )
    return proxies


def _network_source_items(data: dict[str, Any]) -> list[NetworkSourceConfig]:
    value = data.get("sources", {})
    sources: list[NetworkSourceConfig] = []
    seen: set[str] = set()
    if isinstance(value, dict):
        for source, item in value.items():
            proxy = ""
            if isinstance(item, dict):
                proxy = _str(item.get("proxy"), "")
            elif isinstance(item, str):
                proxy = item.strip()
            source_key = _network_source_key(source)
            if not source_key or source_key in seen:
                continue
            seen.add(source_key)
            sources.append(NetworkSourceConfig(source=source_key, proxy=proxy))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            source_key = _network_source_key(item.get("source") or item.get("name"))
            if not source_key or source_key in seen:
                continue
            seen.add(source_key)
            sources.append(NetworkSourceConfig(source=source_key, proxy=_str(item.get("proxy"), "")))
    return sources


def _network_proxy_url_for(network: NetworkConfig, source: str) -> str | None:
    ref = _network_source_proxy_ref(network, source) or network.default_proxy
    return _network_resolve_proxy_ref(network, ref)


def _network_source_proxy_ref(network: NetworkConfig, source: str) -> str:
    source_key = _network_source_key(source)
    for item in network.sources:
        if _network_source_key(item.source) == source_key:
            return item.proxy.strip()
    return ""


def _network_resolve_proxy_ref(network: NetworkConfig, value: str | None) -> str | None:
    ref = str(value or "").strip()
    if not ref or ref.casefold() in {"direct", "none", "off", "false"}:
        return None
    for proxy in network.proxies:
        if proxy.name.casefold() == ref.casefold():
            return _network_proxy_runtime_url(proxy)
    return ref if "://" in ref else None


def _network_proxy_runtime_url(proxy: NetworkProxyConfig) -> str | None:
    url = proxy.url.strip()
    if not url:
        return None
    if not proxy.auth_enabled or not (proxy.username or proxy.password):
        return url
    return _url_with_basic_auth(url, proxy.username, proxy.password)


def _url_with_basic_auth(url: str, username: str, password: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return url
    if not parts.scheme or not parts.netloc or not host:
        return url
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    user = quote(username, safe="")
    secret = quote(password, safe="")
    userinfo = f"{user}:{secret}@" if password else f"{user}@"
    netloc = f"{userinfo}{host}{f':{port}' if port is not None else ''}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _network_with_proxy_override(
    network: NetworkConfig,
    *,
    name: str,
    url: str,
    source: str | None,
) -> NetworkConfig:
    proxy_name = name
    proxies = tuple(item for item in network.proxies if item.name.casefold() != proxy_name.casefold())
    proxies = (*proxies, NetworkProxyConfig(name=proxy_name, url=url))
    if source is None:
        return NetworkConfig(default_proxy=proxy_name, proxies=proxies, sources=network.sources)
    source_key = _network_source_key(source)
    sources = tuple(item for item in network.sources if _network_source_key(item.source) != source_key)
    sources = (*sources, NetworkSourceConfig(source=source_key, proxy=proxy_name))
    return NetworkConfig(default_proxy=network.default_proxy, proxies=proxies, sources=sources)


def _unique_network_proxy_name(proxies: list[NetworkProxyConfig], preferred: str) -> str:
    existing = {proxy.name.casefold() for proxy in proxies}
    if preferred.casefold() not in existing:
        return preferred
    index = 2
    while f"{preferred}-{index}".casefold() in existing:
        index += 1
    return f"{preferred}-{index}"


def _network_source_key(value: Any) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(".", "_")


def _data_with_secret_key(data: dict[str, Any]) -> dict[str, Any]:
    security = data.get("security") if isinstance(data.get("security"), dict) else {}
    next_security = dict(security)
    if not _str(next_security.get("secret_key"), ""):
        next_security["secret_key"] = os.environ.get(SECRET_KEY_ENV) or generate_secret_key()
    next_data = dict(data)
    next_data["security"] = next_security
    return next_data


def _optional_secret(value: Any, secret_key: str) -> str | None:
    return _optional_str(_secret_str(value, secret_key))


def _secret_str(value: Any, secret_key: str) -> str:
    text = _str(value, "")
    return decrypt_secret(text, secret_key) if text else ""


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _str(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, _int(value, default))
    except (TypeError, ValueError):
        return default


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, _int(value, default)))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _toml_string(value: str) -> str:
    return json_escape(value)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def json_escape(value: str) -> str:
    import json

    return json.dumps(str(value), ensure_ascii=False)
