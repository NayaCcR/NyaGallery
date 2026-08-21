from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Any

from nyagallery.metadata import _safe_key_part, normalize_age_rating, utc_now_iso
from nyagallery.storage import atomic_write_json


POST_SCHEMA = "nyagallery.author_posts.v1"
POST_SOURCES = ("x", "misskey", "fanbox", "mastodon", "bluesky", "manual")
SEED_MARKER_NAME = ".seeded"
SEED_MEDIA_MARKER_NAME = ".seeded-media"
SEED_EXTRA_FLAG = "sample"

_SOURCE_ALIASES = {
    "twitter": "x",
    "tweet": "x",
    "misskey_io": "misskey",
    "fediverse": "mastodon",
    "upload": "manual",
}


class PostError(RuntimeError):
    pass


class PostNotFoundError(PostError):
    pass


def normalize_post_source(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    text = _SOURCE_ALIASES.get(text, text)
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text).strip("_")
    return cleaned or "manual"


def make_post_key(source: str, source_id: str) -> str:
    safe_source = _safe_key_part(normalize_post_source(source))
    return f"{safe_source}_{_safe_key_part(str(source_id))}"


def make_post_author_key(
    *,
    source: str,
    author_id: str = "",
    author_handle: str = "",
    author_name: str = "",
) -> str:
    safe_source = _safe_key_part(normalize_post_source(source))
    if str(author_id).strip():
        return f"{safe_source}_{_safe_key_part(str(author_id))}"
    if author_handle.strip():
        return f"{safe_source}_handle_{_safe_key_part(author_handle)}"
    if author_name.strip():
        return f"{safe_source}_author_{_safe_key_part(author_name)}"
    return f"{safe_source}_unknown"


@dataclass(frozen=True)
class PostAttachment:
    asset_key: str | None = None
    remote_url: str = ""
    thumbnail_url: str = ""
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str = ""
    is_sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        optional: dict[str, Any] = {
            "asset_key": self.asset_key or None,
            "remote_url": self.remote_url or None,
            "thumbnail_url": self.thumbnail_url or None,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "description": self.description or None,
            "is_sensitive": self.is_sensitive or None,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PostAttachment":
        asset_key = str(data.get("asset_key") or "").strip()
        return cls(
            asset_key=asset_key or None,
            remote_url=str(data.get("remote_url") or data.get("url") or ""),
            thumbnail_url=str(data.get("thumbnail_url") or data.get("thumb_url") or ""),
            mime_type=str(data["mime_type"]) if data.get("mime_type") else None,
            width=_optional_int(data.get("width")),
            height=_optional_int(data.get("height")),
            description=str(data.get("description") or data.get("alt") or ""),
            is_sensitive=bool(data.get("is_sensitive")),
        )


@dataclass(frozen=True)
class GalleryPost:
    source: str
    source_id: str
    author_id: str = ""
    author_name: str = ""
    author_handle: str = ""
    author_avatar_url: str = ""
    content: str = ""
    content_warning: str = ""
    posted_at: str = ""
    crawl_time: str = ""
    source_url: str = ""
    language: str | None = None
    visibility: str = "public"
    age_rating: str | None = None
    tags: tuple[str, ...] = ()
    canonical_tags: tuple[str, ...] = ()
    attachments: tuple[PostAttachment, ...] = ()
    reply_to_url: str = ""
    repost_of_url: str = ""
    quote_of_url: str = ""
    metrics: dict[str, int] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def post_key(self) -> str:
        return make_post_key(self.source, self.source_id)

    @property
    def author_key(self) -> str:
        return make_post_author_key(
            source=self.source,
            author_id=self.author_id,
            author_handle=self.author_handle,
            author_name=self.author_name,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "source_id": self.source_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_handle": self.author_handle,
            "content": self.content,
            "posted_at": self.posted_at,
            "crawl_time": self.crawl_time,
            "source_url": self.source_url,
            "tags": list(self.tags),
            "canonical_tags": list(self.canonical_tags),
            "attachments": [attachment.to_dict() for attachment in self.attachments],
        }
        optional: dict[str, Any] = {
            "author_avatar_url": self.author_avatar_url or None,
            "content_warning": self.content_warning or None,
            "language": self.language,
            "visibility": self.visibility if self.visibility != "public" else None,
            "age_rating": self.age_rating,
            "reply_to_url": self.reply_to_url or None,
            "repost_of_url": self.repost_of_url or None,
            "quote_of_url": self.quote_of_url or None,
            "metrics": self.metrics or None,
            "extra": self.extra or None,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GalleryPost":
        attachments = data.get("attachments")
        return cls(
            source=normalize_post_source(data["source"]),
            source_id=str(data["source_id"]),
            author_id=str(data.get("author_id") or ""),
            author_name=str(data.get("author_name") or ""),
            author_handle=str(data.get("author_handle") or ""),
            author_avatar_url=str(data.get("author_avatar_url") or ""),
            content=str(data.get("content") or ""),
            content_warning=str(data.get("content_warning") or data.get("spoiler_text") or ""),
            posted_at=str(data.get("posted_at") or ""),
            crawl_time=str(data.get("crawl_time") or ""),
            source_url=str(data.get("source_url") or ""),
            language=str(data["language"]) if data.get("language") else None,
            visibility=str(data.get("visibility") or "public"),
            age_rating=normalize_age_rating(data.get("age_rating")),
            tags=tuple(str(tag) for tag in data.get("tags", ())),
            canonical_tags=tuple(str(tag) for tag in data.get("canonical_tags", ())),
            attachments=tuple(
                PostAttachment.from_dict(item)
                for item in (attachments if isinstance(attachments, list) else [])
                if isinstance(item, dict)
            ),
            reply_to_url=str(data.get("reply_to_url") or ""),
            repost_of_url=str(data.get("repost_of_url") or ""),
            quote_of_url=str(data.get("quote_of_url") or ""),
            metrics=_metrics_from_value(data.get("metrics")),
            extra=dict(data.get("extra") or {}),
        )


class PostStore:
    """Author-grouped JSON storage for social posts, rebuildable into the database index."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.posts_dir = self.root / "posts"

    def ensure(self) -> None:
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    def author_group_path(self, author_key: str) -> Path:
        return self.posts_dir / f"{author_key}.json"

    def group_path_for(self, post: GalleryPost) -> Path:
        return self.author_group_path(post.author_key)

    def is_empty(self) -> bool:
        return not any(self._group_paths())

    def write_post(self, post: GalleryPost, *, replace: bool = True) -> Path:
        self.ensure()
        path = self.group_path_for(post)
        found = self.find_post(post.post_key)
        if found is not None and found[0] != path:
            self._remove_post_from_file(found[0], post.post_key)

        posts = self._read_group(path)
        if post.post_key in posts and not replace:
            return path
        posts[post.post_key] = post
        self._write_group(path, posts.values())
        return path

    def read_post(self, post_key: str) -> GalleryPost:
        found = self.find_post(post_key)
        if found is None:
            raise PostNotFoundError(f"post not found: {post_key}")
        return found[1]

    def find_post(self, post_key: str) -> tuple[Path, GalleryPost] | None:
        for path in self._group_paths():
            for post in self._posts_from_file(path):
                if post.post_key == post_key:
                    return path, post
        return None

    def iter_posts(self) -> list[GalleryPost]:
        posts: dict[str, GalleryPost] = {}
        for path in self._group_paths():
            for post in self._posts_from_file(path):
                posts[post.post_key] = post
        return [posts[key] for key in sorted(posts)]

    def remove_post(self, post_key: str) -> bool:
        found = self.find_post(post_key)
        if found is None:
            return False
        self._remove_post_from_file(found[0], post_key)
        return True

    def _group_paths(self) -> list[Path]:
        if not self.posts_dir.exists():
            return []
        return [path for path in sorted(self.posts_dir.glob("*.json")) if not path.name.startswith("_")]

    def _posts_from_file(self, path: Path) -> list[GalleryPost]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("posts"), list):
            return [GalleryPost.from_dict(item) for item in data["posts"] if isinstance(item, dict)]
        if isinstance(data, dict):
            return [GalleryPost.from_dict(data)]
        return []

    def _read_group(self, path: Path) -> dict[str, GalleryPost]:
        if not path.exists():
            return {}
        return {post.post_key: post for post in self._posts_from_file(path)}

    def _write_group(self, path: Path, items: Iterable[GalleryPost]) -> None:
        posts = sorted(items, key=lambda post: post.post_key)
        first = posts[0] if posts else None
        document = {
            "schema": POST_SCHEMA,
            "author_key": first.author_key if first else path.stem,
            "author": {
                "source": first.source if first else "",
                "author_id": first.author_id if first else "",
                "author_name": first.author_name if first else "",
                "author_handle": first.author_handle if first else "",
                "author_avatar_url": first.author_avatar_url if first else "",
            },
            "posts": [post.to_dict() for post in posts],
        }
        atomic_write_json(path, document)

    def _remove_post_from_file(self, path: Path, post_key: str) -> None:
        remaining = [post for post in self._posts_from_file(path) if post.post_key != post_key]
        if remaining:
            self._write_group(path, remaining)
        elif path.exists():
            path.unlink()


def sample_posts(asset_keys: Sequence[str] = ()) -> list[GalleryPost]:
    keys = [key for key in asset_keys if key]
    crawl_time = utc_now_iso()
    return [
        GalleryPost(
            source="x",
            source_id="1000000000000000001",
            author_id="1",
            author_name="NyaGallery",
            author_handle="nyagallery",
            content=(
                "帖子归档上线了：X / Misskey 的正文、作者和互动数据会写进 storage/posts，"
                "附带的图片走原有的资产管线，和画廊共用一套预览与缩略图。\n\n"
                "Posts are archived next to your artwork now.\n\n#NyaGallery #archive"
            ),
            posted_at="2026-07-20T09:30:00Z",
            crawl_time=crawl_time,
            source_url="https://x.com/nyagallery/status/1000000000000000001",
            language="zh",
            tags=("NyaGallery", "archive"),
            attachments=tuple(PostAttachment(asset_key=key) for key in keys[:2]),
            metrics={"likes": 128, "reposts": 32, "replies": 8},
            extra={"seed": SEED_EXTRA_FLAG},
        ),
        GalleryPost(
            source="misskey",
            source_id="9abcdef0",
            author_id="9abcdef0",
            author_name="のあ",
            author_handle="noa@misskey.io",
            content="新しいイラストの下書きができました。完成したらまた上げますね〜\n\n#misskey #fediverse",
            content_warning="作業進捗 / WIP",
            posted_at="2026-07-18T14:05:00Z",
            crawl_time=crawl_time,
            source_url="https://misskey.io/notes/9abcdef0",
            language="ja",
            tags=("misskey", "fediverse"),
            attachments=tuple(PostAttachment(asset_key=key) for key in keys[2:3]),
            metrics={"likes": 42, "reposts": 7, "replies": 3},
            extra={"seed": SEED_EXTRA_FLAG},
        ),
    ]


def ensure_sample_posts(store: PostStore, *, asset_keys: Sequence[str] = ()) -> int:
    store.ensure()
    marker = store.posts_dir / SEED_MARKER_NAME
    if marker.exists():
        return 0
    if not store.is_empty():
        marker.touch()
        return 0
    written = 0
    for post in sample_posts(asset_keys):
        store.write_post(post)
        written += 1
    marker.touch()
    if asset_keys:
        (store.posts_dir / SEED_MEDIA_MARKER_NAME).touch()
    return written


def link_sample_post_media(store: PostStore, *, asset_keys: Sequence[str] = ()) -> int:
    """Attach gallery assets to the seeded sample posts once the gallery has images."""
    keys = [key for key in asset_keys if key]
    marker = store.posts_dir / SEED_MEDIA_MARKER_NAME
    if not keys or marker.exists() or not (store.posts_dir / SEED_MARKER_NAME).exists():
        return 0
    templates = {post.post_key: post for post in sample_posts(keys)}
    updated = 0
    for path in {store.author_group_path(post.author_key) for post in templates.values()}:
        if not path.exists():
            continue
        for post in store._posts_from_file(path):
            template = templates.get(post.post_key)
            if template is None or post.attachments or not template.attachments:
                continue
            if post.extra.get("seed") != SEED_EXTRA_FLAG:
                continue
            store.write_post(replace(post, attachments=template.attachments))
            updated += 1
    marker.touch()
    return updated


def _metrics_from_value(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    metrics: dict[str, int] = {}
    for key, raw in value.items():
        count = _optional_int(raw)
        if count is not None:
            metrics[str(key)] = count
    return metrics


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
