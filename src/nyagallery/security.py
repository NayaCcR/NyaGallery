from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
import secrets
from typing import Any, Mapping
from urllib.parse import urlparse

from starlette.requests import Request


MiB = 1024 * 1024


DEFAULT_VIEWER_API_WHITELIST = [
    "GET /api/me",
    "GET /api/site/config",
    "GET /api/search",
    "GET /api/img/",
    "GET /api/assets/",
    "GET /api/tags/suggest",
    "GET /api/tags/catalog",
    "GET /api/tags/summary",
    "GET /api/uploads/history",
    "GET /api/uploads/logs",
    "GET /api/transcode/jobs",
    "POST /api/auth/logout",
    "POST /api/logout",
]

DEFAULT_SECURITY_SETTINGS: dict[str, object] = {
    "enabled": True,
    "access_log_enabled": True,
    "access_log_retention": 5000,
    "max_global_concurrency": 128,
    "max_ip_concurrency": 32,
    "max_user_concurrency": 24,
    "ip_requests_per_minute": 2400,
    "ip_bytes_per_minute": 2 * 1024 * MiB,
    "user_requests_per_minute": 1800,
    "user_bytes_per_minute": 1024 * MiB,
    "viewer_requests_per_minute": 900,
    "max_upload_bytes": 1024 * MiB,
    "role_limits": {
        "viewer": {
            "user_requests_per_minute": 900,
        },
    },
    "user_limits": {},
    "viewer_api_whitelist_enabled": False,
    "viewer_api_whitelist": DEFAULT_VIEWER_API_WHITELIST,
    "csrf_origin_check_enabled": True,
    "trusted_origins": [],
    "trust_proxy_headers": False,
}

BOOL_FIELDS = {
    "enabled",
    "access_log_enabled",
    "viewer_api_whitelist_enabled",
    "csrf_origin_check_enabled",
    "trust_proxy_headers",
}

INT_FIELDS = {
    "access_log_retention",
    "max_global_concurrency",
    "max_ip_concurrency",
    "max_user_concurrency",
    "ip_requests_per_minute",
    "ip_bytes_per_minute",
    "user_requests_per_minute",
    "user_bytes_per_minute",
    "viewer_requests_per_minute",
    "max_upload_bytes",
}

LIST_FIELDS = {
    "viewer_api_whitelist",
    "trusted_origins",
}

LIMIT_OVERRIDE_FIELDS = {
    "max_user_concurrency",
    "user_requests_per_minute",
    "user_bytes_per_minute",
}

ROLE_NAMES = {"viewer", "editor", "admin", "developer"}

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def normalize_security_settings(raw: Mapping[str, object] | None) -> dict[str, object]:
    normalized = dict(DEFAULT_SECURITY_SETTINGS)
    normalized["role_limits"] = _normalize_limit_overrides(DEFAULT_SECURITY_SETTINGS.get("role_limits"), role_names_only=True)
    normalized["user_limits"] = {}
    if not raw:
        normalized["viewer_api_whitelist"] = list(DEFAULT_VIEWER_API_WHITELIST)
        normalized["trusted_origins"] = []
        return normalized

    for key, value in raw.items():
        if key in BOOL_FIELDS:
            normalized[key] = _coerce_bool(value)
        elif key in INT_FIELDS:
            normalized[key] = max(0, _coerce_int(value, int(DEFAULT_SECURITY_SETTINGS[key])))
        elif key in LIST_FIELDS:
            normalized[key] = _coerce_string_list(value)
        elif key == "role_limits":
            normalized[key] = _normalize_limit_overrides(value, role_names_only=True)
        elif key == "user_limits":
            normalized[key] = _normalize_limit_overrides(value, role_names_only=False)

    if not normalized["viewer_api_whitelist"] and "viewer_api_whitelist" not in raw:
        normalized["viewer_api_whitelist"] = list(DEFAULT_VIEWER_API_WHITELIST)
    role_limits = dict(normalized.get("role_limits") or {})
    if "viewer" not in role_limits and "viewer_requests_per_minute" in raw:
        role_limits["viewer"] = {
            "user_requests_per_minute": max(
                0,
                _coerce_int(raw.get("viewer_requests_per_minute"), int(DEFAULT_SECURITY_SETTINGS["viewer_requests_per_minute"])),
            )
        }
    normalized["role_limits"] = role_limits
    return normalized


def client_ip(request: Request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",", 1)[0].strip() or "unknown"
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"


def request_body_size(request: Request) -> int:
    raw = request.headers.get("content-length")
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def same_or_trusted_origin(request: Request, trusted_origins: list[str]) -> bool:
    origin = request.headers.get("origin") or _origin_from_referer(request.headers.get("referer"))
    if not origin:
        return True

    normalized_origin = _normalize_origin(origin)
    if not normalized_origin:
        return False

    allowed = {_normalize_origin(item) for item in trusted_origins}
    if normalized_origin in allowed:
        return True

    host = request.headers.get("host", "")
    if not host:
        return False
    request_origin = f"{request.url.scheme}://{host}".lower()
    return normalized_origin == request_origin


def viewer_api_allowed(method: str, path: str, whitelist: list[str]) -> bool:
    method = method.upper()
    for entry in whitelist:
        entry_method, pattern = _parse_whitelist_entry(entry)
        if not pattern:
            continue
        if entry_method not in {"*", method} and not (method == "HEAD" and entry_method == "GET"):
            continue
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return True
        if pattern.endswith("/") and path.startswith(pattern):
            return True
        if path == pattern:
            return True
    return False


@dataclass(frozen=True)
class LimitLease:
    allowed: bool
    reason: str | None = None
    ip: str | None = None
    user_key: str | None = None


class SecurityLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._total_active = 0
        self._ip_active: defaultdict[str, int] = defaultdict(int)
        self._user_active: defaultdict[str, int] = defaultdict(int)
        self._buckets: defaultdict[str, deque[tuple[float, int]]] = defaultdict(deque)

    async def acquire(
        self,
        settings: Mapping[str, object],
        *,
        ip: str,
        user_key: str | None,
        username: str | None,
        role: str | None,
        request_bytes: int,
    ) -> LimitLease:
        if not settings.get("enabled", True):
            return LimitLease(True)

        async with self._lock:
            if self._over_limit(self._total_active, _setting_int(settings, "max_global_concurrency")):
                return LimitLease(False, "global concurrency limit exceeded")
            if self._over_limit(self._ip_active[ip], _setting_int(settings, "max_ip_concurrency")):
                return LimitLease(False, "ip concurrency limit exceeded")
            user_concurrency_limit = _identity_setting_int(
                settings,
                "max_user_concurrency",
                role=role,
                username=username,
                user_key=user_key,
            )
            if user_key and self._over_limit(self._user_active[user_key], user_concurrency_limit):
                return LimitLease(False, "user concurrency limit exceeded")

            now = asyncio.get_running_loop().time()
            checks = [
                (f"ip:{ip}", _setting_int(settings, "ip_requests_per_minute"), _setting_int(settings, "ip_bytes_per_minute")),
            ]
            if user_key:
                checks.append(
                    (
                        f"user:{user_key}",
                        _identity_setting_int(
                            settings,
                            "user_requests_per_minute",
                            role=role,
                            username=username,
                            user_key=user_key,
                        ),
                        _identity_setting_int(
                            settings,
                            "user_bytes_per_minute",
                            role=role,
                            username=username,
                            user_key=user_key,
                        ),
                    )
                )

            for key, count_limit, bytes_limit in checks:
                reason = self._bucket_rejection(key, now, count_limit, bytes_limit, request_bytes)
                if reason:
                    return LimitLease(False, reason)

            for key, _count_limit, _bytes_limit in checks:
                self._buckets[key].append((now, request_bytes))
            self._total_active += 1
            self._ip_active[ip] += 1
            if user_key:
                self._user_active[user_key] += 1
            return LimitLease(True, ip=ip, user_key=user_key)

    async def release(self, lease: LimitLease) -> None:
        if not lease.allowed or lease.ip is None:
            return
        async with self._lock:
            self._total_active = max(0, self._total_active - 1)
            self._ip_active[lease.ip] = max(0, self._ip_active[lease.ip] - 1)
            if lease.user_key:
                self._user_active[lease.user_key] = max(0, self._user_active[lease.user_key] - 1)

    @staticmethod
    def _over_limit(current: int, limit: int) -> bool:
        return limit > 0 and current >= limit

    def _bucket_rejection(
        self,
        key: str,
        now: float,
        count_limit: int,
        bytes_limit: int,
        request_bytes: int,
    ) -> str | None:
        bucket = self._buckets[key]
        while bucket and now - bucket[0][0] >= 60:
            bucket.popleft()
        if count_limit > 0 and len(bucket) + 1 > count_limit:
            return f"{key} request rate limit exceeded"
        if bytes_limit > 0 and sum(item[1] for item in bucket) + request_bytes > bytes_limit:
            return f"{key} traffic limit exceeded"
        return None


class RedisSecurityLimiter:
    _ACQUIRE_SCRIPT = """
local global_active = tonumber(redis.call('GET', KEYS[1]) or '0')
local ip_active = tonumber(redis.call('GET', KEYS[2]) or '0')
local user_active = tonumber(redis.call('GET', KEYS[3]) or '0')
local global_limit = tonumber(ARGV[1])
local ip_limit = tonumber(ARGV[2])
local user_limit = tonumber(ARGV[3])
local request_bytes = tonumber(ARGV[4])
local active_ttl_ms = tonumber(ARGV[5])
local window_ms = tonumber(ARGV[6])
local event_id = ARGV[7]
local check_count = tonumber(ARGV[8])

if global_limit > 0 and global_active >= global_limit then
  return {0, 'global concurrency limit exceeded'}
end
if ip_limit > 0 and ip_active >= ip_limit then
  return {0, 'ip concurrency limit exceeded'}
end
if user_limit > 0 and user_active >= user_limit then
  return {0, 'user concurrency limit exceeded'}
end

local now_reply = redis.call('TIME')
local now_ms = tonumber(now_reply[1]) * 1000 + math.floor(tonumber(now_reply[2]) / 1000)
local key_index = 4
local arg_index = 9
for i = 1, check_count do
  local label = ARGV[arg_index]
  local count_limit = tonumber(ARGV[arg_index + 1])
  local bytes_limit = tonumber(ARGV[arg_index + 2])
  local zkey = KEYS[key_index]
  local hkey = KEYS[key_index + 1]
  local expired = redis.call('ZRANGEBYSCORE', zkey, '-inf', now_ms - window_ms)
  if #expired > 0 then
    redis.call('ZREMRANGEBYSCORE', zkey, '-inf', now_ms - window_ms)
    for _, member in ipairs(expired) do
      redis.call('HDEL', hkey, member)
    end
  end
  local current_count = redis.call('ZCARD', zkey)
  if count_limit > 0 and current_count + 1 > count_limit then
    return {0, label .. ' request rate limit exceeded'}
  end
  if bytes_limit > 0 then
    local current_bytes = 0
    local values = redis.call('HVALS', hkey)
    for _, value in ipairs(values) do
      current_bytes = current_bytes + tonumber(value)
    end
    if current_bytes + request_bytes > bytes_limit then
      return {0, label .. ' traffic limit exceeded'}
    end
  end
  key_index = key_index + 2
  arg_index = arg_index + 3
end

redis.call('INCR', KEYS[1])
redis.call('PEXPIRE', KEYS[1], active_ttl_ms)
redis.call('INCR', KEYS[2])
redis.call('PEXPIRE', KEYS[2], active_ttl_ms)
if ARGV[3] ~= '-1' then
  redis.call('INCR', KEYS[3])
  redis.call('PEXPIRE', KEYS[3], active_ttl_ms)
end

key_index = 4
arg_index = 9
for i = 1, check_count do
  local zkey = KEYS[key_index]
  local hkey = KEYS[key_index + 1]
  local member = event_id .. ':' .. tostring(i)
  redis.call('ZADD', zkey, now_ms, member)
  redis.call('HSET', hkey, member, request_bytes)
  redis.call('PEXPIRE', zkey, window_ms * 2)
  redis.call('PEXPIRE', hkey, window_ms * 2)
  key_index = key_index + 2
  arg_index = arg_index + 3
end

return {1, ''}
"""

    _RELEASE_SCRIPT = """
for _, key in ipairs(KEYS) do
  if key ~= '' then
    local value = tonumber(redis.call('DECR', key))
    if value <= 0 then
      redis.call('SET', key, 0)
    end
    redis.call('PEXPIRE', key, tonumber(ARGV[1]))
  end
end
return 1
"""

    def __init__(
        self,
        client: Any,
        *,
        key_prefix: str = "nyagallery",
        window_seconds: int = 60,
        active_ttl_seconds: int = 300,
    ) -> None:
        self._client = client
        self._prefix = key_prefix.strip(":") or "nyagallery"
        self._window_ms = max(1, window_seconds) * 1000
        self._active_ttl_ms = max(1, active_ttl_seconds) * 1000

    async def acquire(
        self,
        settings: Mapping[str, object],
        *,
        ip: str,
        user_key: str | None,
        username: str | None,
        role: str | None,
        request_bytes: int,
    ) -> LimitLease:
        if not settings.get("enabled", True):
            return LimitLease(True)

        user_concurrency_limit = _identity_setting_int(
            settings,
            "max_user_concurrency",
            role=role,
            username=username,
            user_key=user_key,
        ) if user_key else -1
        checks: list[tuple[str, int, int]] = [
            (
                f"ip:{ip}",
                _setting_int(settings, "ip_requests_per_minute"),
                _setting_int(settings, "ip_bytes_per_minute"),
            )
        ]
        if user_key:
            checks.append(
                (
                    f"user:{user_key}",
                    _identity_setting_int(
                        settings,
                        "user_requests_per_minute",
                        role=role,
                        username=username,
                        user_key=user_key,
                    ),
                    _identity_setting_int(
                        settings,
                        "user_bytes_per_minute",
                        role=role,
                        username=username,
                        user_key=user_key,
                    ),
                )
            )

        keys = [
            self._key("security:active:global"),
            self._key(f"security:active:ip:{ip}"),
            self._key(f"security:active:user:{user_key or '_none'}"),
        ]
        args: list[object] = [
            _setting_int(settings, "max_global_concurrency"),
            _setting_int(settings, "max_ip_concurrency"),
            user_concurrency_limit,
            max(0, request_bytes),
            self._active_ttl_ms,
            self._window_ms,
            secrets.token_urlsafe(12),
            len(checks),
        ]
        for label, count_limit, bytes_limit in checks:
            keys.extend([
                self._key(f"security:bucket:{label}:events"),
                self._key(f"security:bucket:{label}:bytes"),
            ])
            args.extend([label, count_limit, bytes_limit])

        result = await self._client.eval(self._ACQUIRE_SCRIPT, len(keys), *keys, *args)
        allowed = bool(int(result[0]))
        if not allowed:
            return LimitLease(False, str(result[1] or "rate limit exceeded"))
        return LimitLease(True, ip=ip, user_key=user_key)

    async def release(self, lease: LimitLease) -> None:
        if not lease.allowed or lease.ip is None:
            return
        keys = [
            self._key("security:active:global"),
            self._key(f"security:active:ip:{lease.ip}"),
            self._key(f"security:active:user:{lease.user_key}") if lease.user_key else "",
        ]
        await self._client.eval(self._RELEASE_SCRIPT, len(keys), *keys, self._active_ttl_ms)

    def _key(self, suffix: str) -> str:
        return f"{self._prefix}:{suffix}"


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        items = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        return []
    return [item.strip() for item in items if item and item.strip()]


def _setting_int(settings: Mapping[str, object], key: str) -> int:
    return _coerce_int(settings.get(key), int(DEFAULT_SECURITY_SETTINGS[key]))


def _identity_setting_int(
    settings: Mapping[str, object],
    key: str,
    *,
    role: str | None,
    username: str | None,
    user_key: str | None,
) -> int:
    value = _setting_int(settings, key)
    role_limits = settings.get("role_limits")
    if isinstance(role_limits, Mapping) and role:
        role_override = role_limits.get(str(role))
        if isinstance(role_override, Mapping) and key in role_override:
            value = _coerce_int(role_override.get(key), value)

    user_limits = settings.get("user_limits")
    if isinstance(user_limits, Mapping):
        user_candidates = [
            str(username or "").strip(),
            str(user_key or "").strip(),
        ]
        if user_key and str(user_key).startswith("user:"):
            user_candidates.append(str(user_key)[5:])
        for candidate in user_candidates:
            if not candidate:
                continue
            user_override = user_limits.get(candidate)
            if isinstance(user_override, Mapping) and key in user_override:
                value = _coerce_int(user_override.get(key), value)
                break
    return max(0, value)


def _normalize_limit_overrides(value: object, *, role_names_only: bool) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, dict[str, int]] = {}
    for raw_name, raw_limits in value.items():
        name = str(raw_name).strip()
        if not name:
            continue
        if role_names_only:
            name = name.lower()
            if name not in ROLE_NAMES:
                continue
        if not isinstance(raw_limits, Mapping):
            continue
        limits: dict[str, int] = {}
        for field in LIMIT_OVERRIDE_FIELDS:
            if field in raw_limits:
                limits[field] = max(0, _coerce_int(raw_limits.get(field), 0))
        if limits:
            normalized[name] = limits
    return normalized


def _origin_from_referer(referer: str | None) -> str | None:
    if not referer:
        return None
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _parse_whitelist_entry(entry: str) -> tuple[str, str]:
    parts = entry.strip().split(None, 1)
    if len(parts) == 2 and parts[0].upper() in HTTP_METHODS:
        return parts[0].upper(), parts[1].strip()
    return "*", entry.strip()
