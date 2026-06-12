from __future__ import annotations

import base64
from dataclasses import dataclass
from email.utils import formatdate
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

from nyagallery.metadata import GalleryMetadata, make_asset_key


class StorageError(RuntimeError):
    pass


class OriginalAlreadyExistsError(StorageError):
    pass


class MetadataAlreadyExistsError(StorageError):
    pass


class MetadataNotFoundError(StorageError):
    pass


REMOTE_ORIGINAL_PREFIX = "remote"
LOCAL_STORAGE_STRATEGY = "local"
ORIGINAL_STORAGE_SECRET_FIELDS = {"password", "token", "access_key_secret"}


@dataclass(frozen=True)
class StoredOriginal:
    path: Path
    relative_path: str
    filename: str
    sha256: str
    size: int
    was_existing: bool
    strategy: str = LOCAL_STORAGE_STRATEGY


@dataclass(frozen=True)
class StorageStrategyInfo:
    name: str
    type: str
    is_default: bool
    is_remote: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    return name or "original"


def archival_suffix(source_filename: str) -> str:
    suffixes = [suffix.lower() for suffix in Path(source_filename).suffixes]
    if not suffixes:
        return ""
    if len(suffixes) >= 2 and suffixes[-2:] == [".ugoira", ".zip"]:
        return ".ugoira.zip"
    return suffixes[-1]


class OriginalStorageBackend:
    is_remote = True

    def __init__(self, name: str, backend_type: str, *, prefix: str = "original", timeout_seconds: int = 60) -> None:
        self.name = normalize_strategy_name(name)
        self.type = backend_type.casefold().replace("-", "_")
        self.prefix = normalize_object_prefix(prefix)
        self.timeout_seconds = max(1, int(timeout_seconds or 60))

    def object_key(self, asset_key: str, source_filename: str) -> str:
        filename = f"{asset_key}{archival_suffix(source_filename)}"
        return join_object_key(self.prefix, filename)

    def exists(self, object_key: str) -> bool:
        raise NotImplementedError

    def get_bytes(self, object_key: str) -> bytes:
        raise NotImplementedError

    def put_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        raise NotImplementedError

    def delete(self, object_key: str) -> None:
        raise NotImplementedError

    def stat_size(self, object_key: str) -> int | None:
        raise NotImplementedError


class LocalOriginalStorageBackend(OriginalStorageBackend):
    is_remote = False

    def __init__(self, name: str = LOCAL_STORAGE_STRATEGY) -> None:
        super().__init__(name, "local", prefix="original")


class WebDAVOriginalStorageBackend(OriginalStorageBackend):
    def __init__(self, config: Any) -> None:
        super().__init__(
            _strategy_value(config, "name", "webdav"),
            "webdav",
            prefix=_strategy_value(config, "prefix", "original"),
            timeout_seconds=_strategy_int(config, "timeout_seconds", 60),
        )
        endpoint = _strategy_value(config, "endpoint", "") or _strategy_value(config, "url", "")
        if not endpoint:
            raise StorageError(f"WebDAV storage strategy {self.name!r} requires endpoint")
        self.endpoint = endpoint.rstrip("/") + "/"
        self.username = _strategy_value(config, "username", "")
        self.password = _strategy_value(config, "password", "")
        self.token = _strategy_value(config, "token", "") or _strategy_value(config, "access_token", "")

    def exists(self, object_key: str) -> bool:
        response = _http_request(self._url(object_key), "HEAD", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        return response is not None

    def get_bytes(self, object_key: str) -> bytes:
        response = _http_request(self._url(object_key), "GET", headers=self._headers(), timeout=self.timeout_seconds)
        return response.body

    def put_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        self._ensure_parent_collections(object_key)
        headers = self._headers()
        headers["Content-Type"] = content_type or "application/octet-stream"
        _http_request(self._url(object_key), "PUT", headers=headers, data=content, timeout=self.timeout_seconds)

    def delete(self, object_key: str) -> None:
        _http_request(self._url(object_key), "DELETE", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)

    def stat_size(self, object_key: str) -> int | None:
        response = _http_request(self._url(object_key), "HEAD", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        return _content_length(response.headers) if response is not None else None

    def _ensure_parent_collections(self, object_key: str) -> None:
        parts = [part for part in object_key.split("/")[:-1] if part]
        current = ""
        for part in parts:
            current = join_object_key(current, part)
            _http_request(
                self._url(current) + "/",
                "MKCOL",
                headers=self._headers(),
                timeout=self.timeout_seconds,
                acceptable={200, 201, 204, 405, 409},
            )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.username or self.password:
            headers["Authorization"] = _basic_auth(self.username, self.password)
        return headers

    def _url(self, object_key: str) -> str:
        return self.endpoint + quote_object_key(object_key)


class UpyunOriginalStorageBackend(OriginalStorageBackend):
    def __init__(self, config: Any) -> None:
        super().__init__(
            _strategy_value(config, "name", "upyun"),
            "upyun",
            prefix=_strategy_value(config, "prefix", "original"),
            timeout_seconds=_strategy_int(config, "timeout_seconds", 60),
        )
        self.endpoint = (_strategy_value(config, "endpoint", "") or "https://v0.api.upyun.com").rstrip("/")
        self.bucket = _strategy_value(config, "bucket", "") or _strategy_value(config, "service", "")
        self.username = _strategy_value(config, "username", "") or _strategy_value(config, "operator", "")
        self.password = _strategy_value(config, "password", "")
        if not self.bucket or not self.username or not self.password:
            raise StorageError(f"UPYUN storage strategy {self.name!r} requires bucket, username, and password")

    def exists(self, object_key: str) -> bool:
        response = _http_request(self._url(object_key), "HEAD", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        return response is not None

    def get_bytes(self, object_key: str) -> bytes:
        response = _http_request(self._url(object_key), "GET", headers=self._headers(), timeout=self.timeout_seconds)
        return response.body

    def put_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        headers = self._headers()
        headers["Content-Type"] = content_type or "application/octet-stream"
        _http_request(self._url(object_key), "PUT", headers=headers, data=content, timeout=self.timeout_seconds)

    def delete(self, object_key: str) -> None:
        _http_request(self._url(object_key), "DELETE", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)

    def stat_size(self, object_key: str) -> int | None:
        response = _http_request(self._url(object_key), "HEAD", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        return _content_length(response.headers) if response is not None else None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": _basic_auth(self.username, self.password)}

    def _url(self, object_key: str) -> str:
        return f"{self.endpoint}/{quote(self.bucket.strip('/'), safe='')}/{quote_object_key(object_key)}"


class AliyunOSSOriginalStorageBackend(OriginalStorageBackend):
    def __init__(self, config: Any) -> None:
        super().__init__(
            _strategy_value(config, "name", "aliyun_oss"),
            "aliyun_oss",
            prefix=_strategy_value(config, "prefix", "original"),
            timeout_seconds=_strategy_int(config, "timeout_seconds", 60),
        )
        self.endpoint = _with_scheme(_strategy_value(config, "endpoint", ""))
        self.bucket = _strategy_value(config, "bucket", "")
        self.access_key_id = _strategy_value(config, "access_key_id", "")
        self.access_key_secret = _strategy_value(config, "access_key_secret", "")
        if not self.endpoint or not self.bucket or not self.access_key_id or not self.access_key_secret:
            raise StorageError(
                f"Aliyun OSS storage strategy {self.name!r} requires endpoint, bucket, access_key_id, and access_key_secret"
            )
        parsed = urlparse(self.endpoint)
        host = parsed.netloc or parsed.path
        scheme = parsed.scheme or "https"
        if host.startswith(f"{self.bucket}."):
            self.base_url = f"{scheme}://{host.rstrip('/')}"
        else:
            self.base_url = f"{scheme}://{self.bucket}.{host.rstrip('/')}"

    def exists(self, object_key: str) -> bool:
        response = self._request(object_key, "HEAD", allow_404=True)
        return response is not None

    def get_bytes(self, object_key: str) -> bytes:
        return self._request(object_key, "GET").body

    def put_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        self._request(object_key, "PUT", data=content, content_type=content_type or "application/octet-stream")

    def delete(self, object_key: str) -> None:
        self._request(object_key, "DELETE", allow_404=True)

    def stat_size(self, object_key: str) -> int | None:
        response = self._request(object_key, "HEAD", allow_404=True)
        return _content_length(response.headers) if response is not None else None

    def _request(
        self,
        object_key: str,
        method: str,
        *,
        data: bytes | None = None,
        content_type: str = "",
        allow_404: bool = False,
    ) -> "_HTTPResponse | None":
        headers = self._headers(method, object_key, content_type=content_type)
        return _http_request(
            f"{self.base_url}/{quote_object_key(object_key)}",
            method,
            headers=headers,
            data=data,
            timeout=self.timeout_seconds,
            allow_404=allow_404,
        )

    def _headers(self, method: str, object_key: str, *, content_type: str = "") -> dict[str, str]:
        date = formatdate(usegmt=True)
        canonical_resource = f"/{self.bucket}/{object_key}"
        string_to_sign = f"{method}\n\n{content_type}\n{date}\n{canonical_resource}"
        signature = base64.b64encode(
            hmac.new(
                self.access_key_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        headers = {
            "Date": date,
            "Authorization": f"OSS {self.access_key_id}:{signature}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers


class OneDriveOriginalStorageBackend(OriginalStorageBackend):
    def __init__(self, config: Any) -> None:
        super().__init__(
            _strategy_value(config, "name", "onedrive"),
            "onedrive",
            prefix=_strategy_value(config, "prefix", "original"),
            timeout_seconds=_strategy_int(config, "timeout_seconds", 60),
        )
        self.endpoint = (_strategy_value(config, "endpoint", "") or "https://graph.microsoft.com/v1.0").rstrip("/")
        self.token = _strategy_value(config, "token", "") or _strategy_value(config, "access_token", "")
        self.drive_id = _strategy_value(config, "drive_id", "")
        self.root_path = _strategy_value(config, "root_path", "").strip("/")
        if not self.token:
            raise StorageError(f"OneDrive storage strategy {self.name!r} requires token")

    def exists(self, object_key: str) -> bool:
        response = _http_request(self._item_url(object_key), "GET", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        return response is not None

    def get_bytes(self, object_key: str) -> bytes:
        response = _http_request(self._content_url(object_key), "GET", headers=self._headers(), timeout=self.timeout_seconds)
        return response.body

    def put_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        self._ensure_parent_folders(object_key)
        headers = self._headers()
        headers["Content-Type"] = content_type or "application/octet-stream"
        _http_request(self._content_url(object_key), "PUT", headers=headers, data=content, timeout=self.timeout_seconds)

    def delete(self, object_key: str) -> None:
        _http_request(self._item_url(object_key), "DELETE", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)

    def stat_size(self, object_key: str) -> int | None:
        response = _http_request(self._item_url(object_key), "GET", headers=self._headers(), timeout=self.timeout_seconds, allow_404=True)
        if response is None:
            return None
        try:
            data = json.loads(response.body.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        try:
            return int(data.get("size"))
        except (TypeError, ValueError, AttributeError):
            return None

    def _ensure_parent_folders(self, object_key: str) -> None:
        parts = [part for part in self._drive_path(object_key).split("/")[:-1] if part]
        current = ""
        for part in parts:
            parent = current
            current = join_object_key(current, part)
            payload = json.dumps(
                {
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "fail",
                }
            ).encode("utf-8")
            headers = self._headers()
            headers["Content-Type"] = "application/json"
            _http_request(
                self._children_url(parent),
                "POST",
                headers=headers,
                data=payload,
                timeout=self.timeout_seconds,
                acceptable={200, 201, 409},
            )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _item_url(self, object_key: str) -> str:
        return f"{self._root_url()}:{quote_drive_path(self._drive_path(object_key))}"

    def _content_url(self, object_key: str) -> str:
        return f"{self._item_url(object_key)}:/content"

    def _children_url(self, parent_path: str) -> str:
        if not parent_path:
            return f"{self._root_url()}/children"
        return f"{self._root_url()}:{quote_drive_path(parent_path)}:/children"

    def _root_url(self) -> str:
        if self.drive_id:
            return f"{self.endpoint}/drives/{quote(self.drive_id, safe='')}/root"
        return f"{self.endpoint}/me/drive/root"

    def _drive_path(self, object_key: str) -> str:
        return join_object_key(self.root_path, object_key)


@dataclass(frozen=True)
class _HTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def _http_request(
    url: str,
    method: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 60,
    acceptable: set[int] | None = None,
    allow_404: bool = False,
) -> _HTTPResponse | None:
    acceptable_status = acceptable or {200, 201, 202, 204}
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = int(getattr(response, "status", response.getcode()))
            body = response.read() if method.upper() != "HEAD" else b""
            if status not in acceptable_status:
                raise StorageError(f"HTTP {method} {url} returned unexpected status {status}")
            return _HTTPResponse(status=status, headers=dict(response.headers.items()), body=body)
    except HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        if acceptable and exc.code in acceptable:
            try:
                body = exc.read()
            except Exception:
                body = b""
            return _HTTPResponse(status=exc.code, headers=dict(exc.headers.items()), body=body)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        message = f"HTTP {method} {url} failed with {exc.code}"
        if detail:
            message = f"{message}: {detail}"
        raise StorageError(message) from exc
    except OSError as exc:
        raise StorageError(f"HTTP {method} {url} failed: {exc}") from exc


def _content_length(headers: dict[str, str]) -> int | None:
    for key in ("Content-Length", "content-length"):
        value = headers.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _with_scheme(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    return text if "://" in text else f"https://{text}"


def normalize_strategy_name(value: str) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    text = "".join(ch if ch.isalnum() or ch in "._" else "_" for ch in text).strip("._")
    return text or LOCAL_STORAGE_STRATEGY


def normalize_object_prefix(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip("/")
    parts = [part for part in text.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) or "original"


def join_object_key(*parts: str) -> str:
    segments: list[str] = []
    for raw in parts:
        text = str(raw or "").replace("\\", "/").strip("/")
        if not text:
            continue
        segments.extend(part for part in text.split("/") if part not in {"", ".", ".."})
    return "/".join(segments)


def quote_object_key(object_key: str) -> str:
    return "/".join(quote(part, safe="") for part in object_key.split("/") if part)


def quote_drive_path(object_key: str) -> str:
    key = quote_object_key(object_key)
    return f"/{key}" if key else ""


def _strategy_value(config: Any, key: str, default: str = "") -> str:
    if isinstance(config, dict):
        value = config.get(key, default)
    else:
        value = getattr(config, key, default)
    text = str(value or "").strip()
    return text or default


def _strategy_int(config: Any, key: str, default: int) -> int:
    if isinstance(config, dict):
        value = config.get(key, default)
    else:
        value = getattr(config, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class GalleryStorage:
    """Filesystem storage that keeps originals immutable and metadata rebuildable."""

    def __init__(
        self,
        root: str | Path,
        *,
        default_strategy: str = LOCAL_STORAGE_STRATEGY,
        strategies: tuple[Any, ...] | list[Any] = (),
    ) -> None:
        self.root = Path(root).resolve()
        self.original_dir = self.root / "original"
        self.preview_dir = self.root / "preview"
        self.thumbs_dir = self.root / "thumbs"
        self.metadata_dir = self.root / "metadata"
        self.tags_dir = self.root / "tags"
        self.remote_cache_dir = self.root / "remote-cache"
        self.default_strategy_name = normalize_strategy_name(default_strategy)
        self._original_backends = self._build_original_backends(strategies)
        if self.default_strategy_name not in self._original_backends:
            available = ", ".join(sorted(self._original_backends))
            raise StorageError(f"unknown default storage strategy {self.default_strategy_name!r}; available: {available}")

    def ensure(self) -> None:
        for directory in (
            self.original_dir,
            self.preview_dir,
            self.thumbs_dir,
            self.metadata_dir,
            self.tags_dir,
            self.remote_cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def storage_strategies(self) -> list[StorageStrategyInfo]:
        return [
            StorageStrategyInfo(
                name=backend.name,
                type=backend.type,
                is_default=backend.name == self.default_strategy_name,
                is_remote=backend.is_remote,
            )
            for backend in sorted(self._original_backends.values(), key=lambda item: item.name)
        ]

    def default_storage_strategy(self) -> str:
        return self.default_strategy_name

    def validate_storage_strategy(self, strategy_name: str | None) -> str:
        name = normalize_strategy_name(strategy_name or self.default_strategy_name)
        if name not in self._original_backends:
            available = ", ".join(sorted(self._original_backends))
            raise StorageError(f"unknown storage strategy {name!r}; available: {available}")
        return name

    def original_path(self, asset_key: str, source_filename: str) -> Path:
        suffix = archival_suffix(source_filename)
        return self.original_dir / f"{asset_key}{suffix}"

    def metadata_path(self, asset_key: str) -> Path:
        return self.metadata_dir / f"{asset_key}.json"

    def metadata_group_path(self, group_key: str) -> Path:
        return self.metadata_dir / f"{group_key}.json"

    def metadata_path_for(self, metadata: GalleryMetadata) -> Path:
        return self.metadata_group_path(metadata.metadata_group_key)

    def preview_path(self, asset_key: str, suffix: str = ".avif") -> Path:
        return self.preview_dir / f"{asset_key}{suffix}"

    def thumb_path(self, asset_key: str, suffix: str = ".avif") -> Path:
        return self.thumbs_dir / f"{asset_key}{suffix}"

    def cache_relative_path(self, path: Path) -> str:
        return self._relative(path)

    def resolve_relative_path(self, relative_path: str) -> Path:
        remote = self._remote_location(relative_path)
        if remote is not None:
            strategy_name, object_key = remote
            return self._cached_remote_original(strategy_name, object_key)
        root = self.root.resolve()
        resolved = (self.root / relative_path).resolve()
        if not resolved.is_relative_to(root):
            raise StorageError(f"path escapes storage root: {relative_path}")
        return resolved

    def file_size(self, relative_path: str | None) -> int | None:
        if not relative_path:
            return None
        remote = self._remote_location(relative_path)
        if remote is not None:
            strategy_name, object_key = remote
            backend = self._original_backends.get(strategy_name)
            if backend is None:
                return None
            size = backend.stat_size(object_key)
            if size is not None:
                return size
            cache_path = self._remote_cache_path(strategy_name, object_key)
            return cache_path.stat().st_size if cache_path.exists() else None
        path = self.resolve_relative_path(relative_path)
        return path.stat().st_size if path.exists() else None

    def source_metadata_path(self, source: str, source_id: str, page_index: int | None = None) -> Path:
        return self.metadata_path(make_asset_key(source, source_id, page_index))

    def metadata_exists(self, source: str, source_id: str, page_index: int | None = None) -> bool:
        asset_key = make_asset_key(source, source_id, page_index)
        return self.find_metadata_path(asset_key) is not None

    def write_original(
        self,
        asset_key: str,
        source_filename: str,
        content: bytes,
        *,
        strategy_name: str | None = None,
        content_type: str | None = None,
    ) -> StoredOriginal:
        self.ensure()
        strategy = self.validate_storage_strategy(strategy_name)
        backend = self._original_backends[strategy]
        if backend.is_remote:
            return self._write_remote_original(backend, asset_key, source_filename, content, content_type=content_type)
        return self._write_local_original(asset_key, source_filename, content, strategy=backend.name)

    def _write_local_original(
        self,
        asset_key: str,
        source_filename: str,
        content: bytes,
        *,
        strategy: str = LOCAL_STORAGE_STRATEGY,
    ) -> StoredOriginal:
        final_path = self.original_path(asset_key, source_filename)
        new_sha = sha256_bytes(content)

        try:
            fd = os.open(final_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            existing_sha = sha256_file(final_path)
            if existing_sha != new_sha:
                raise OriginalAlreadyExistsError(
                    f"refusing to overwrite immutable original {final_path}"
                ) from None
            return StoredOriginal(
                path=final_path,
                relative_path=self._relative(final_path),
                filename=final_path.name,
                sha256=existing_sha,
                size=final_path.stat().st_size,
                was_existing=True,
                strategy=strategy,
            )

        with os.fdopen(fd, "wb") as file:
            file.write(content)

        return StoredOriginal(
            path=final_path,
            relative_path=self._relative(final_path),
            filename=final_path.name,
            sha256=new_sha,
            size=len(content),
            was_existing=False,
            strategy=strategy,
        )

    def _write_remote_original(
        self,
        backend: OriginalStorageBackend,
        asset_key: str,
        source_filename: str,
        content: bytes,
        *,
        content_type: str | None = None,
    ) -> StoredOriginal:
        object_key = backend.object_key(asset_key, source_filename)
        relative_path = self._remote_relative_path(backend.name, object_key)
        cache_path = self._remote_cache_path(backend.name, object_key)
        new_sha = sha256_bytes(content)
        was_existing = False

        if backend.exists(object_key):
            was_existing = True
            existing = backend.get_bytes(object_key)
            existing_sha = sha256_bytes(existing)
            if existing_sha != new_sha:
                raise OriginalAlreadyExistsError(
                    f"refusing to overwrite immutable original {relative_path}"
                )

        if not was_existing:
            backend.put_bytes(object_key, content, content_type=content_type)

        self._atomic_write_bytes(cache_path, content)
        return StoredOriginal(
            path=cache_path,
            relative_path=relative_path,
            filename=Path(object_key).name,
            sha256=new_sha,
            size=len(content),
            was_existing=was_existing,
            strategy=backend.name,
        )

    def write_metadata(self, metadata: GalleryMetadata, *, replace: bool = False) -> Path:
        self.ensure()
        path = self.metadata_path_for(metadata)
        existing_path = self.find_metadata_path(metadata.asset_key)
        if existing_path and existing_path != path:
            self._remove_metadata_from_file(existing_path, metadata.asset_key)

        group = self._read_metadata_group(path)
        assets = group["assets"]
        old = assets.get(metadata.asset_key)
        if old is not None and not replace:
            if old.to_dict() == metadata.to_dict():
                return path
            raise MetadataAlreadyExistsError(f"metadata already exists: {path}#{metadata.asset_key}")

        assets[metadata.asset_key] = metadata
        self._write_metadata_group(path, assets.values())
        return path

    def read_metadata(self, asset_key: str) -> GalleryMetadata:
        found = self._find_metadata(asset_key)
        if found is None:
            raise MetadataNotFoundError(f"metadata not found: {asset_key}")
        return found[1]

    def find_metadata_path(self, asset_key: str) -> Path | None:
        found = self._find_metadata(asset_key)
        return found[0] if found else None

    def iter_metadata(self) -> list[GalleryMetadata]:
        self.ensure()
        items: dict[str, GalleryMetadata] = {}
        for path in sorted(self.metadata_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for metadata in self._metadata_items_from_json(data):
                items[metadata.asset_key] = metadata
        return [items[key] for key in sorted(items)]

    def migrate_metadata_to_groups(self, *, archive_legacy: bool = True) -> dict[str, int]:
        self.ensure()
        legacy_paths: list[Path] = []
        metadata_items: dict[str, GalleryMetadata] = {}
        for path in sorted(self.metadata_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            is_group = isinstance(data, dict) and isinstance(data.get("assets"), list)
            for metadata in self._metadata_items_from_json(data):
                metadata_items[metadata.asset_key] = metadata
            if not is_group:
                legacy_paths.append(path)

        grouped_paths: set[Path] = set()
        groups: dict[Path, list[GalleryMetadata]] = {}
        for metadata in metadata_items.values():
            path = self.metadata_path_for(metadata)
            groups.setdefault(path, []).append(metadata)
        for path, items in groups.items():
            self._write_metadata_group(path, items)
            grouped_paths.add(path)

        archived = 0
        if archive_legacy and legacy_paths:
            archive_dir = self.metadata_dir / "_legacy"
            archive_dir.mkdir(parents=True, exist_ok=True)
            for path in legacy_paths:
                if path.exists() and path not in grouped_paths:
                    target = archive_dir / path.name
                    os.replace(path, target)
                    archived += 1

        return {
            "assets": len(metadata_items),
            "groups": len(grouped_paths),
            "archived_legacy_files": archived,
        }

    def remove_metadata(self, asset_key: str) -> bool:
        found = self._find_metadata(asset_key)
        if found is None:
            return False
        self._remove_metadata_from_file(found[0], asset_key)
        return True

    def delete_asset_files(self, metadata: GalleryMetadata) -> list[str]:
        deleted: list[str] = []
        if self._delete_original_path(metadata.original_path):
            deleted.append(metadata.original_path)
        for path in [
            self.preview_path(metadata.asset_key, ".avif"),
            self.preview_path(metadata.asset_key, ".webp"),
            self.thumb_path(metadata.asset_key, ".avif"),
        ]:
            if path.exists():
                path.unlink()
                deleted.append(self._relative(path))
        return deleted

    def find_by_sha256(self, sha256: str, *, exclude_asset_key: str | None = None) -> GalleryMetadata | None:
        for metadata in self.iter_metadata():
            if metadata.asset_key == exclude_asset_key:
                continue
            if metadata.file_sha256 == sha256:
                return metadata
        return None

    def _build_original_backends(self, strategies: tuple[Any, ...] | list[Any]) -> dict[str, OriginalStorageBackend]:
        backends: dict[str, OriginalStorageBackend] = {
            LOCAL_STORAGE_STRATEGY: LocalOriginalStorageBackend(),
        }
        for config in strategies:
            backend = self._backend_from_strategy(config)
            backends[backend.name] = backend
        return backends

    def _backend_from_strategy(self, config: Any) -> OriginalStorageBackend:
        name = normalize_strategy_name(_strategy_value(config, "name", LOCAL_STORAGE_STRATEGY))
        backend_type = _strategy_value(config, "type", "local").casefold().replace("-", "_")
        if backend_type == "local":
            return LocalOriginalStorageBackend(name)
        if backend_type == "webdav":
            return WebDAVOriginalStorageBackend(config)
        if backend_type in {"upyun", "upai"}:
            return UpyunOriginalStorageBackend(config)
        if backend_type in {"aliyun_oss", "ali_oss", "oss"}:
            return AliyunOSSOriginalStorageBackend(config)
        if backend_type in {"onedrive", "one_drive", "graph"}:
            return OneDriveOriginalStorageBackend(config)
        raise StorageError(f"unsupported storage strategy type {backend_type!r} for {name!r}")

    def _remote_location(self, relative_path: str | None) -> tuple[str, str] | None:
        text = str(relative_path or "").replace("\\", "/").strip("/")
        parts = text.split("/", 2)
        if len(parts) != 3 or parts[0] != REMOTE_ORIGINAL_PREFIX:
            return None
        strategy_name = normalize_strategy_name(parts[1])
        object_key = join_object_key(parts[2])
        if not object_key:
            raise StorageError(f"remote original path is missing object key: {relative_path}")
        return strategy_name, object_key

    def _remote_relative_path(self, strategy_name: str, object_key: str) -> str:
        return f"{REMOTE_ORIGINAL_PREFIX}/{normalize_strategy_name(strategy_name)}/{join_object_key(object_key)}"

    def _remote_cache_path(self, strategy_name: str, object_key: str) -> Path:
        root = self.remote_cache_dir.resolve()
        path = (self.remote_cache_dir / normalize_strategy_name(strategy_name) / join_object_key(object_key)).resolve()
        if not path.is_relative_to(root):
            raise StorageError(f"remote cache path escapes storage root: {strategy_name}/{object_key}")
        return path

    def _cached_remote_original(self, strategy_name: str, object_key: str) -> Path:
        backend = self._original_backends.get(strategy_name)
        if backend is None:
            raise StorageError(f"unknown storage strategy {strategy_name!r}")
        cache_path = self._remote_cache_path(strategy_name, object_key)
        if cache_path.exists():
            return cache_path
        content = backend.get_bytes(object_key)
        self._atomic_write_bytes(cache_path, content)
        return cache_path

    def _delete_original_path(self, relative_path: str) -> bool:
        remote = self._remote_location(relative_path)
        if remote is not None:
            strategy_name, object_key = remote
            backend = self._original_backends.get(strategy_name)
            deleted = False
            if backend is not None:
                backend.delete(object_key)
                deleted = True
            cache_path = self._remote_cache_path(strategy_name, object_key)
            if cache_path.exists():
                cache_path.unlink()
                deleted = True
            return deleted

        path = self.resolve_relative_path(relative_path)
        if path.exists():
            path.unlink()
            return True
        return False

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _find_metadata(self, asset_key: str) -> tuple[Path, GalleryMetadata] | None:
        self.ensure()
        legacy_path = self.metadata_path(asset_key)
        if legacy_path.exists():
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
            if not (isinstance(data, dict) and isinstance(data.get("assets"), list)):
                metadata = GalleryMetadata.from_dict(data)
                if metadata.asset_key == asset_key:
                    return legacy_path, metadata

        for path in sorted(self.metadata_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for metadata in self._metadata_items_from_json(data):
                if metadata.asset_key == asset_key:
                    return path, metadata
        return None

    def _metadata_items_from_json(self, data: dict) -> list[GalleryMetadata]:
        if isinstance(data, dict) and isinstance(data.get("assets"), list):
            return [GalleryMetadata.from_dict(item) for item in data["assets"]]
        return [GalleryMetadata.from_dict(data)]

    def _read_metadata_group(self, path: Path) -> dict[str, dict[str, GalleryMetadata]]:
        if not path.exists():
            return {"assets": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "assets": {
                metadata.asset_key: metadata
                for metadata in self._metadata_items_from_json(data)
            }
        }

    def _write_metadata_group(self, path: Path, items) -> None:
        assets = sorted(items, key=lambda metadata: metadata.asset_key)
        first = assets[0] if assets else None
        document = {
            "schema": "nyagallery.creator_metadata.v1",
            "creator_key": first.metadata_group_key if first else path.stem,
            "creator": {
                "artist_id": first.artist_id if first else "",
                "artist_name": first.artist_name if first else "",
                "uploader_user_id": first.uploader_user_id if first else None,
                "uploader_username": first.uploader_username if first else None,
            },
            "assets": [metadata.to_dict() for metadata in assets],
        }
        self._atomic_write_json(path, document)

    def _remove_metadata_from_file(self, path: Path, asset_key: str) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("assets"), list):
            remaining = [
                metadata
                for metadata in self._metadata_items_from_json(data)
                if metadata.asset_key != asset_key
            ]
            if remaining:
                self._write_metadata_group(path, remaining)
            else:
                path.unlink()
        elif path.exists():
            metadata = GalleryMetadata.from_dict(data)
            if metadata.asset_key == asset_key:
                path.unlink()

    def _atomic_write_json(self, path: Path, data: dict) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        content_bytes = f"{content}\n".encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as tmp:
            tmp.write(content_bytes)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)

    def _atomic_write_bytes(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
