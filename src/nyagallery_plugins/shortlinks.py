"""Official plugin: expand share short links (pixiv.me, t.co, b23.tv, ...) for the sync center.

Basic by design:
- only hosts in ``SHORT_LINK_HOSTS`` are ever requested (the first hop must be a known short host);
- every hop goes through the same DNS-pinned, public-address-only connection as remote uploads
  (no proxies from the environment, no private / loopback targets);
- ``HEAD`` first (falls back to ``GET`` without reading the body), at most 5 redirects, 8 s total;
- only the ``Location`` header is used; page bodies are never read or parsed;
- results are cached in memory for an hour.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urljoin, urlsplit

from nyagallery.plugin_host import PluginContext, PluginInfo
from nyagallery.plugins import PluginManifest
from nyagallery.remote_upload import RemoteImageError, _PinnedConnection, _resolve
from nyagallery.sync_targets import SHORT_LINK_HOSTS

MAX_HOPS = 5
TOTAL_TIMEOUT = 8.0
CACHE_SECONDS = 3600
CACHE_LIMIT = 2000


class ShortLinkError(RuntimeError):
    pass


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _one_hop(url: str, deadline: float) -> str | None:
    """Location header of one request, or None if the response is not a redirect."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ShortLinkError("unsupported url")
    host = parsed.hostname.encode("idna").decode("ascii")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ShortLinkError("timed out")
    try:
        addresses = _resolve(host, port, remaining)
    except RemoteImageError as exc:
        raise ShortLinkError(exc.detail) from exc
    target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    for method in ("HEAD", "GET"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ShortLinkError("timed out")
        connection = _PinnedConnection(host, port, addresses[0], secure=parsed.scheme == "https", timeout=min(4.0, remaining))
        timer = threading.Timer(remaining, connection.abort)
        timer.daemon = True
        timer.start()
        try:
            connection.request(method, target, headers={"User-Agent": "NyaGallery-ShortLink/1.0", "Accept": "*/*", "Connection": "close"})
            response = connection.getresponse()
            status = response.status
            location = response.getheader("Location")
            response.close()  # never read the body
        finally:
            timer.cancel()
            connection.close()
        if status in {301, 302, 303, 307, 308} and location:
            return urljoin(url, location.strip())
        if method == "HEAD" and status in {400, 403, 405, 501}:
            continue  # some shorteners reject HEAD; retry once with GET
        return None
    return None


def expand_short_link(url: str) -> str | None:
    """Follow redirects from an allowlisted short host until a non-short URL is reached."""
    if _host(url) not in SHORT_LINK_HOSTS:
        return None
    deadline = time.monotonic() + TOTAL_TIMEOUT
    current = url
    for _ in range(MAX_HOPS):
        nxt = _one_hop(current, deadline)
        if nxt is None:
            return current if current != url else None
        if _host(nxt) not in SHORT_LINK_HOSTS:
            return nxt  # reached the real destination; do not request it
        current = nxt
    raise ShortLinkError("too many redirects")


class _Cache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, str | None]] = {}

    def get(self, key: str) -> tuple[bool, str | None]:
        with self._lock:
            hit = self._items.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return True, hit[1]
            return False, None

    def put(self, key: str, value: str | None) -> None:
        with self._lock:
            if len(self._items) >= CACHE_LIMIT:
                self._items.clear()
            self._items[key] = (time.monotonic(), value)


class ShortLinksPlugin:
    manifest = PluginManifest("official.shortlinks", "1.0.0", ("adapter",), permissions=("routes", "network"))
    info = PluginInfo(
        title="Short links",
        description="Expands share short links (pixiv.me, t.co, b23.tv, bit.ly, ...) in the sync center by following redirects from an allowlist of short-link hosts; page content is never downloaded.",
        official=True,
    )

    def __init__(self) -> None:
        self.cache = _Cache()

    def expand(self, url: str) -> str | None:
        hit, value = self.cache.get(url)
        if hit:
            return value
        try:
            value = expand_short_link(url)
        except (ShortLinkError, OSError):
            value = None
        self.cache.put(url, value)
        return value

    def setup(self, ctx: PluginContext) -> None:
        ctx.provide("short_link_expander", self.expand)
        router = ctx.router(prefix="/api/sync/short-links")

        @router.get("/hosts")
        def hosts() -> dict[str, object]:
            return {"hosts": sorted(SHORT_LINK_HOSTS), "max_hops": MAX_HOPS}

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = ShortLinksPlugin()
