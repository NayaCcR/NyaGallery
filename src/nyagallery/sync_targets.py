"""Classify pasted links / ids into per-platform sync targets for the unified sync page.

Classification itself is pure string parsing with no network access. Expanding share short links
(pixiv.me, t.co, ...) is optional and done by a pluggable expander (the official.shortlinks plugin);
without one, short links are reported as ``short_link`` instead of being followed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

SPLIT_RE = re.compile(r"[\s,，;；|｜]+")
PIXIV_ARTWORK_PATH_RE = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?artworks/(\d+)/?$", re.IGNORECASE)
PIXIV_USER_PATH_RE = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?users/(\d+)(?:/.*)?$", re.IGNORECASE)
X_STATUS_PATH_RE = re.compile(r"^/(?:i/web/)?(?:[^/]+/)?status(?:es)?/(\d+)", re.IGNORECASE)
X_USER_PATH_RE = re.compile(r"^/([A-Za-z0-9_]{1,15})/?$")
X_RESERVED = {"home", "explore", "notifications", "messages", "settings", "search", "i", "compose", "login", "signup", "tos", "privacy"}
FANBOX_POST_PATH_RE = re.compile(r"^/(?:@[A-Za-z0-9_-]+/)?posts/(\d+)/?$")
FANBOX_HANDLE_PATH_RE = re.compile(r"^/@([A-Za-z0-9_-]+)/?")
FANBOX_LEGACY_RE = re.compile(r"^/fanbox/creator/\d+/post/(\d+)")
MISSKEY_NOTE_PATH_RE = re.compile(r"^/notes/([A-Za-z0-9]+)/?$")
MISSKEY_USER_PATH_RE = re.compile(r"^/@([A-Za-z0-9_]+)(?:@([A-Za-z0-9.-]+))?/?$")
MISSKEY_HANDLE_RE = re.compile(r"^@([A-Za-z0-9_]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)$")
KNOWN_MISSKEY_HOSTS = {"misskey.io", "misskey.design", "misskey.art", "nijimiss.moe", "mi.yumechi.jp", "misskey.flowers"}
MAX_INPUTS = 500
# Share-link hosts the short-link plugin may expand (host allowlist; nothing else is fetched).
SHORT_LINK_HOSTS = frozenset({"pixiv.me", "t.co", "x.gd", "b23.tv", "bit.ly", "tinyurl.com", "ow.ly", "is.gd", "buff.ly", "goo.gl", "t.cn", "fanbox.page.link"})


@dataclass(frozen=True)
class SyncTarget:
    input: str
    platform: str  # pixiv | x | fanbox | misskey | unknown
    kind: str  # artwork | user | post | creator | note | short_link | invalid
    value: str = ""
    host: str = ""
    error: str = ""
    expanded_from: str = ""  # set when a short link was expanded to this target

    def key(self) -> str:
        return f"{self.platform}:{self.kind}:{self.host}:{self.value}" if self.value else f"raw:{self.input}"


def _url(text: str):
    candidate = text if "://" in text else ""
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return parsed


def classify(text: str, *, default_platform: str = "pixiv") -> SyncTarget:
    raw = text.strip()
    if raw.isdigit():
        # Bare ids are ambiguous; X ids are long snowflakes, Pixiv ids are short.
        if len(raw) >= 15:
            return SyncTarget(raw, "x", "post", raw)
        if default_platform == "fanbox":
            return SyncTarget(raw, "fanbox", "post", raw)
        return SyncTarget(raw, "pixiv", "artwork", raw.lstrip("0") or raw)
    handle = MISSKEY_HANDLE_RE.match(raw)
    if handle:
        return SyncTarget(raw, "misskey", "user", handle.group(1), handle.group(2).lower())
    parsed = _url(raw)
    if parsed is None:
        return SyncTarget(raw, "unknown", "invalid", error="unrecognized")
    host = parsed.hostname.lower()
    bare = host[4:] if host.startswith("www.") else host
    path = parsed.path or "/"

    if bare in SHORT_LINK_HOSTS:
        platform = {"pixiv.me": "pixiv", "t.co": "x", "fanbox.page.link": "fanbox"}.get(bare, "unknown")
        return SyncTarget(raw, platform, "short_link", error="short_link")
    if bare == "pixiv.net" or bare.endswith(".pixiv.net"):
        legacy = FANBOX_LEGACY_RE.match(path)
        if legacy:
            return SyncTarget(raw, "fanbox", "post", legacy.group(1))
        match = PIXIV_ARTWORK_PATH_RE.match(path)
        if match:
            return SyncTarget(raw, "pixiv", "artwork", match.group(1).lstrip("0") or match.group(1))
        if path == "/member_illust.php":
            ids = parse_qs(parsed.query).get("illust_id", [])
            if len(ids) == 1 and ids[0].isdigit():
                return SyncTarget(raw, "pixiv", "artwork", ids[0].lstrip("0") or ids[0])
        match = PIXIV_USER_PATH_RE.match(path)
        if match:
            return SyncTarget(raw, "pixiv", "user", match.group(1))
        if path == "/member.php":
            ids = parse_qs(parsed.query).get("id", [])
            if len(ids) == 1 and ids[0].isdigit():
                return SyncTarget(raw, "pixiv", "user", ids[0])
        return SyncTarget(raw, "pixiv", "invalid", error="unsupported_pixiv_link")
    if bare in {"x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"}:
        match = X_STATUS_PATH_RE.match(path)
        if match:
            return SyncTarget(raw, "x", "post", match.group(1))
        match = X_USER_PATH_RE.match(path)
        if match and match.group(1).lower() not in X_RESERVED:
            return SyncTarget(raw, "x", "user", match.group(1))
        return SyncTarget(raw, "x", "invalid", error="unsupported_x_link")
    if bare == "fanbox.cc" or bare.endswith(".fanbox.cc"):
        match = FANBOX_POST_PATH_RE.match(path)
        if match:
            return SyncTarget(raw, "fanbox", "post", match.group(1))
        if bare != "fanbox.cc":
            subdomain = bare[: -len(".fanbox.cc")]
            if subdomain and subdomain != "www":
                return SyncTarget(raw, "fanbox", "creator", subdomain)
        match = FANBOX_HANDLE_PATH_RE.match(path)
        if match:
            return SyncTarget(raw, "fanbox", "creator", match.group(1))
        return SyncTarget(raw, "fanbox", "invalid", error="unsupported_fanbox_link")
    note = MISSKEY_NOTE_PATH_RE.match(path)
    user = MISSKEY_USER_PATH_RE.match(path)
    if bare in KNOWN_MISSKEY_HOSTS or note or user:
        if note:
            return SyncTarget(raw, "misskey", "note", note.group(1), bare)
        if user:
            return SyncTarget(raw, "misskey", "user", user.group(1), (user.group(2) or bare).lower())
        return SyncTarget(raw, "misskey", "invalid", host=bare, error="unsupported_misskey_link")
    return SyncTarget(raw, "unknown", "invalid", error="unsupported_site")


ShortLinkExpander = Callable[[str], "str | None"]


def _looks_short(token: str, target: SyncTarget) -> bool:
    if target.kind == "short_link":
        return True
    parsed = _url(token)
    return parsed is not None and is_short_link_host(parsed.hostname or "")


def is_short_link_host(host: str) -> bool:
    return host.lower().removeprefix("www.") in SHORT_LINK_HOSTS


def resolve_targets(text: str, *, default_platform: str = "pixiv", expand: ShortLinkExpander | None = None) -> dict[str, object]:
    """Classify pasted text. With ``expand`` (provided by the short-link plugin), short links are
    expanded once and re-classified; the original input is kept and ``expanded_from`` is set."""
    seen: set[str] = set()
    targets: list[SyncTarget] = []
    for token in SPLIT_RE.split(text or ""):
        token = token.strip().strip("<>()[]\"'")
        if not token:
            continue
        target = classify(token, default_platform=default_platform)
        if expand is not None and _looks_short(token, target):
            try:
                expanded = expand(token)
            except Exception:  # an expander failure leaves the original classification
                expanded = None
            if expanded:
                again = classify(expanded, default_platform=default_platform)
                target = SyncTarget(token, again.platform, again.kind, again.value, again.host, again.error, expanded_from=expanded)
            else:
                target = SyncTarget(token, target.platform if target.platform != "unknown" else "unknown", "short_link", error="short_link_unresolved")
        key = target.key()
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
        if len(targets) >= MAX_INPUTS:
            break
    groups: dict[str, int] = {}
    for target in targets:
        if target.kind not in {"invalid", "short_link"}:
            groups[f"{target.platform}:{target.kind}"] = groups.get(f"{target.platform}:{target.kind}", 0) + 1
    return {
        "items": [asdict(target) for target in targets],
        "groups": groups,
        "valid": sum(1 for target in targets if target.kind not in {"invalid", "short_link"}),
        "invalid": sum(1 for target in targets if target.kind in {"invalid", "short_link"}),
        "truncated": len(targets) >= MAX_INPUTS,
    }
