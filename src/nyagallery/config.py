from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from typing import Any, Mapping


DEFAULT_CONFIG_FILENAME = "nyagallery.toml"
CONFIG_ENV = "NYAGALLERY_CONFIG"
PROJECT_REPOSITORY = "https://github.com/NayaCcR/NyaGallery"


@dataclass(frozen=True)
class CoreConfig:
    storage: str = "storage"
    database_url: str | None = None
    tag_catalog_path: str | None = None


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


@dataclass(frozen=True)
class PixivConfig:
    refresh_token: str | None = None
    cookie: str | None = None
    default_request_delay_seconds: float = 1.0
    max_concurrency: int = 1


@dataclass(frozen=True)
class RedisConfig:
    url: str | None = None
    key_prefix: str = "nyagallery"
    security_limiter: bool = False


@dataclass(frozen=True)
class StorageStrategyConfig:
    name: str
    type: str = "local"
    prefix: str = "original"
    endpoint: str = ""
    bucket: str = ""
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
    redis: RedisConfig = RedisConfig()
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
    if config.redis.url:
        os.environ.setdefault("NYAGALLERY_REDIS_URL", config.redis.url)


def config_to_dict(config: NyaGalleryConfig, *, redact_secrets: bool = False) -> dict[str, object]:
    pixiv_refresh_token = "" if redact_secrets and config.pixiv.refresh_token else config.pixiv.refresh_token or ""
    pixiv_cookie = "" if redact_secrets and config.pixiv.cookie else config.pixiv.cookie or ""
    return {
        "core": {
            "storage": config.core.storage,
            "database_url": config.core.database_url or "",
            "tag_catalog_path": config.core.tag_catalog_path or "",
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
        },
        "pixiv": {
            "refresh_token": pixiv_refresh_token,
            "cookie": pixiv_cookie,
            "default_request_delay_seconds": config.pixiv.default_request_delay_seconds,
            "max_concurrency": config.pixiv.max_concurrency,
        },
        "redis": {
            "url": config.redis.url or "",
            "key_prefix": config.redis.key_prefix,
            "security_limiter": config.redis.security_limiter,
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
    config = _config_from_dict(dict(data), resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(render_config(config), encoding="utf-8")
    return config


def render_config(config: NyaGalleryConfig) -> str:
    lines: list[str] = [
        "# NyaGallery backend configuration.",
        "# Managed by the admin developer config editor.",
        "",
        "[core]",
        f"storage = {_toml_string(config.core.storage)}",
        f"database_url = {_toml_string(config.core.database_url or '')}",
        f"tag_catalog_path = {_toml_string(config.core.tag_catalog_path or '')}",
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
        "",
        "[pixiv]",
        f"refresh_token = {_toml_string(config.pixiv.refresh_token or '')}",
        f"cookie = {_toml_string(config.pixiv.cookie or '')}",
        f"default_request_delay_seconds = {float(config.pixiv.default_request_delay_seconds):g}",
        f"max_concurrency = {int(config.pixiv.max_concurrency)}",
        "",
        "[redis]",
        f"url = {_toml_string(config.redis.url or '')}",
        f"key_prefix = {_toml_string(config.redis.key_prefix)}",
        f"security_limiter = {_toml_bool(config.redis.security_limiter)}",
        "",
        "[original_storage]",
        f"default_strategy = {_toml_string(config.original_storage.default_strategy)}",
        "",
        *_render_storage_strategies(config.original_storage.strategies),
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
        "username": strategy.username,
        "password": password,
        "token": token,
        "access_key_id": strategy.access_key_id,
        "access_key_secret": access_key_secret,
        "drive_id": strategy.drive_id,
        "root_path": strategy.root_path,
        "timeout_seconds": strategy.timeout_seconds,
    }


def _render_storage_strategies(strategies: tuple[StorageStrategyConfig, ...]) -> list[str]:
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
                f"username = {_toml_string(strategy.username)}",
                f"password = {_toml_string(strategy.password)}",
                f"token = {_toml_string(strategy.token)}",
                f"access_key_id = {_toml_string(strategy.access_key_id)}",
                f"access_key_secret = {_toml_string(strategy.access_key_secret)}",
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
    redis = _table(data, "redis")
    original_storage = _table(data, "original_storage")
    developer = _table(data, "developer")
    return NyaGalleryConfig(
        core=CoreConfig(
            storage=_str(core.get("storage"), "storage"),
            database_url=_optional_str(core.get("database_url")),
            tag_catalog_path=_optional_str(core.get("tag_catalog_path")),
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
        ),
        pixiv=PixivConfig(
            refresh_token=_optional_str(pixiv.get("refresh_token")),
            cookie=_optional_str(pixiv.get("cookie")),
            default_request_delay_seconds=_float(pixiv.get("default_request_delay_seconds"), 1.0),
            max_concurrency=_int(pixiv.get("max_concurrency"), 1),
        ),
        redis=RedisConfig(
            url=_optional_str(redis.get("url")),
            key_prefix=_str(redis.get("key_prefix"), "nyagallery"),
            security_limiter=_bool(redis.get("security_limiter"), False),
        ),
        original_storage=OriginalStorageConfig(
            default_strategy=_str(original_storage.get("default_strategy"), "local"),
            strategies=tuple(_storage_strategy_from_dict(item) for item in _strategy_items(original_storage)),
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
    redis = RedisConfig(
        url=os.environ.get("NYAGALLERY_REDIS_URL") or config.redis.url,
        key_prefix=os.environ.get("NYAGALLERY_REDIS_KEY_PREFIX") or config.redis.key_prefix,
        security_limiter=_bool(
            os.environ.get("NYAGALLERY_REDIS_SECURITY_LIMITER"),
            config.redis.security_limiter,
        ),
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
        redis=redis,
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


def _storage_strategy_from_dict(data: dict[str, Any]) -> StorageStrategyConfig:
    return StorageStrategyConfig(
        name=_str(data.get("name"), "local"),
        type=_str(data.get("type"), "local").casefold().replace("-", "_"),
        prefix=_str(data.get("prefix"), "original").strip("/"),
        endpoint=_str(data.get("endpoint") or data.get("url"), ""),
        bucket=_str(data.get("bucket") or data.get("service"), ""),
        username=_str(data.get("username") or data.get("operator"), ""),
        password=_str(data.get("password"), ""),
        token=_str(data.get("token") or data.get("access_token"), ""),
        access_key_id=_str(data.get("access_key_id"), ""),
        access_key_secret=_str(data.get("access_key_secret"), ""),
        drive_id=_str(data.get("drive_id"), ""),
        root_path=_str(data.get("root_path"), "").strip("/"),
        timeout_seconds=_int(data.get("timeout_seconds"), 60),
    )


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
