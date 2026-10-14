from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_DATE_PREFIX_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T\s].*)?$")
_PIXIV_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[_\s-]+(?P<body>.+?)(?P<pid>\d{5,})(?:_p(?P<page>\d+))?$"
)
_ANIMATED_MIME_TYPES = {"application/zip", "image/apng", "image/gif"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_key_part(value: str) -> str:
    value = value.strip()
    value = _SAFE_KEY_RE.sub("_", value)
    value = value.strip("._-")
    if not value:
        raise ValueError("asset key part cannot be empty")
    return value


def make_asset_key(source: str, source_id: str, page_index: int | None = None) -> str:
    """Return the deterministic archival key used by original and metadata files."""
    safe_source = _safe_key_part(source.lower())
    safe_source_id = _safe_key_part(str(source_id))
    if safe_source == "pixiv":
        base = safe_source_id
    else:
        base = f"{safe_source}_{safe_source_id}"
    if page_index is not None:
        if page_index < 0:
            raise ValueError("page_index cannot be negative")
        base = f"{base}_p{page_index}"
    return base


def make_metadata_group_key(
    *,
    source: str,
    artist_id: str = "",
    artist_name: str = "",
    uploader_user_id: int | None = None,
    uploader_username: str | None = None,
) -> str:
    """Return the metadata JSON group key for a creator/uploader bucket."""
    safe_source = _safe_key_part(source.lower())
    if safe_source == "pixiv" and artist_id.strip():
        return f"pixiv_{_safe_key_part(artist_id)}"
    if artist_id.strip():
        return f"{safe_source}_{_safe_key_part(artist_id)}"
    if artist_name.strip():
        return f"{safe_source}_artist_{_safe_key_part(artist_name)}"
    if uploader_user_id is not None:
        return f"user_{uploader_user_id}"
    if uploader_username:
        return f"user_{_safe_key_part(uploader_username)}"
    return f"{safe_source}_unknown"


@dataclass(frozen=True)
class ParsedPixivFilename:
    artwork_date: str
    title: str
    pixiv_id: str
    page_index: int | None = None

    def to_extra(self) -> dict[str, Any]:
        extra: dict[str, Any] = {
            "filename_date": self.artwork_date,
            "pixiv_artwork_id": self.pixiv_id,
        }
        if self.page_index is not None:
            extra["pixiv_page_index"] = self.page_index
        return extra


def parse_pixiv_filename(filename: str) -> ParsedPixivFilename | None:
    """Parse filenames shaped like "2026-04-22_ Title_143856839_p0"."""
    stem = Path(filename).stem.strip()
    match = _PIXIV_FILENAME_RE.match(stem)
    if not match:
        return None

    body = match.group("body").strip(" _-")
    pid = match.group("pid")
    title = body.removesuffix(pid).strip(" _-") or body
    page = match.group("page")
    return ParsedPixivFilename(
        artwork_date=match.group("date"),
        title=title,
        pixiv_id=pid,
        page_index=int(page) if page is not None else None,
    )


def normalize_date_value(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _DATE_PREFIX_RE.match(text)
    if match:
        return match.group("date")
    return text


def normalize_timestamp(value: Any) -> str | None:
    """Normalize historical ISO dates/times to UTC; naive values mean UTC."""
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError):
        return None


def asset_timestamps(data: dict[str, Any]) -> dict[str, str | None]:
    """Resolve explicit times and known legacy fields without inventing events."""
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
    source = data.get("source")
    def first(*values: Any) -> str | None:
        return next((stamp for value in values if (stamp := normalize_timestamp(value))), None)
    return {
        "published_at": first(data.get("published_at"), extra.get("published_at"),
                              extra.get("pixiv_create_date") if source == "pixiv" else None),
        "captured_at": first(data.get("captured_at"), extra.get("captured_at")),
        "uploaded_at": first(data.get("uploaded_at"), extra.get("uploaded_at"),
                             data.get("crawl_time") if source == "upload" else None),
        "scraped_at": first(data.get("scraped_at"), extra.get("scraped_at"),
                            data.get("crawl_time") if source in {"pixiv", "misskey", "x", "fanbox"} else None),
    }


def normalize_source_type(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if not text:
        return None
    aliases = {
        "illust": "illustration",
        "illustrations": "illustration",
        "image": "illustration",
        "ugoira": "ugoira",
        "manga": "manga",
        "novel": "novel",
    }
    return aliases.get(text, re.sub(r"[^a-z0-9_]+", "_", text).strip("_") or None)


def normalize_age_rating(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if not text:
        return None
    normalized = text.replace("_", "-").replace(" ", "-")
    if normalized in {"0", "all-ages", "safe", "general"}:
        return "safe"
    if normalized in {"1", "r18", "r-18"}:
        return "r18"
    if normalized in {"2", "r18g", "r-18g"}:
        return "r18g"
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_") or None


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value > 0
    text = str(value).strip().casefold()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "ai", "generated", "ai_generated"}:
        return True
    if text in {"0", "false", "no", "n", "none"}:
        return False
    return None


def infer_is_animated(
    *,
    explicit: Any = None,
    source_type: str | None = None,
    mime_type: str | None = None,
    original_path: str = "",
    original_filename: str = "",
) -> bool | None:
    explicit_bool = optional_bool(explicit)
    if explicit_bool is not None:
        return explicit_bool
    if normalize_source_type(source_type) == "ugoira":
        return True
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime in _ANIMATED_MIME_TYPES:
        return True
    suffixes = [suffix.casefold() for suffix in Path(original_path or original_filename).suffixes]
    if suffixes[-2:] == [".ugoira", ".zip"] or (suffixes and suffixes[-1] in {".apng", ".gif"}):
        return True
    return None


@dataclass(frozen=True)
class GalleryMetadata:
    source: str
    source_id: str
    title: str
    artist_id: str
    artist_name: str
    original_url: str
    crawl_time: str
    file_sha256: str
    original_filename: str
    original_path: str
    pixiv_tags: tuple[str, ...] = ()
    canonical_tags: tuple[str, ...] = ()
    page_index: int | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    artwork_date: str | None = None
    pixiv_upload_date: str | None = None
    source_type: str | None = None
    age_rating: str | None = None
    is_ai_generated: bool | None = None
    is_animated: bool | None = None
    uploader_user_id: int | None = None
    uploader_username: str | None = None
    deletion_status: str | None = None
    deleted_at: str | None = None
    deleted_by_user_id: int | None = None
    deleted_by_username: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    published_at: str | None = None
    captured_at: str | None = None
    uploaded_at: str | None = None
    scraped_at: str | None = None

    def __post_init__(self) -> None:
        for key, value in asset_timestamps(vars(self)).items():
            object.__setattr__(self, key, value)

    @property
    def asset_key(self) -> str:
        return make_asset_key(self.source, self.source_id, self.page_index)

    @property
    def metadata_group_key(self) -> str:
        return make_metadata_group_key(
            source=self.source,
            artist_id=self.artist_id,
            artist_name=self.artist_name,
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "artist_id": self.artist_id,
            "artist_name": self.artist_name,
            "original_url": self.original_url,
            "crawl_time": self.crawl_time,
            "file_sha256": self.file_sha256,
            "original_filename": self.original_filename,
            "original_path": self.original_path,
            "pixiv_tags": list(self.pixiv_tags),
            "canonical_tags": list(self.canonical_tags),
        }
        optional: dict[str, Any] = {
            **asset_timestamps(vars(self)),
            "page_index": self.page_index,
            "width": self.width,
            "height": self.height,
            "mime_type": self.mime_type,
            "artwork_date": self.artwork_date,
            "pixiv_upload_date": self.pixiv_upload_date,
            "source_type": self.source_type,
            "age_rating": self.age_rating,
            "is_ai_generated": self.is_ai_generated,
            "is_animated": self.is_animated,
            "uploader_user_id": self.uploader_user_id,
            "uploader_username": self.uploader_username,
            "deletion_status": self.deletion_status,
            "deleted_at": self.deleted_at,
            "deleted_by_user_id": self.deleted_by_user_id,
            "deleted_by_username": self.deleted_by_username,
            "extra": self.extra or None,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GalleryMetadata":
        source = str(data["source"])
        original_filename = str(data["original_filename"])
        if source == "upload":
            original_filename = Path(original_filename).stem or original_filename
        extra = dict(data.get("extra") or {})
        parsed_filename = parse_pixiv_filename(original_filename)
        if parsed_filename:
            for key, value in parsed_filename.to_extra().items():
                extra.setdefault(key, value)
        artwork_date = normalize_date_value(
            data.get("artwork_date")
            or extra.get("artwork_date")
            or extra.get("pixiv_create_date")
            or extra.get("create_date")
            or extra.get("filename_date")
            or (parsed_filename.artwork_date if parsed_filename else None)
        )
        pixiv_upload_date = normalize_date_value(
            data.get("pixiv_upload_date")
            or extra.get("pixiv_upload_date")
            or extra.get("upload_date")
            or extra.get("update_date")
        )
        mime_type = data.get("mime_type")
        source_type = normalize_source_type(data.get("source_type") or extra.get("source_type") or extra.get("type"))
        age_rating = normalize_age_rating(data.get("age_rating") or extra.get("age_rating") or extra.get("age"))
        is_ai_generated = optional_bool(data.get("is_ai_generated", extra.get("is_ai_generated", extra.get("AI"))))
        is_animated = infer_is_animated(
            explicit=data.get("is_animated", extra.get("is_animated")),
            source_type=source_type,
            mime_type=mime_type,
            original_path=str(data.get("original_path") or ""),
            original_filename=original_filename,
        )
        return cls(
            **asset_timestamps(data),
            source=source,
            source_id=str(data["source_id"]),
            title=str(data.get("title") or ""),
            artist_id=str(data.get("artist_id") or ""),
            artist_name=str(data.get("artist_name") or ""),
            original_url=str(data.get("original_url") or ""),
            crawl_time=str(data.get("crawl_time") or ""),
            file_sha256=str(data["file_sha256"]),
            original_filename=original_filename,
            original_path=str(data["original_path"]),
            pixiv_tags=tuple(str(tag) for tag in data.get("pixiv_tags", ())),
            canonical_tags=tuple(str(tag) for tag in data.get("canonical_tags", ())),
            page_index=data.get("page_index"),
            width=data.get("width"),
            height=data.get("height"),
            mime_type=mime_type,
            artwork_date=artwork_date,
            pixiv_upload_date=pixiv_upload_date,
            source_type=source_type,
            age_rating=age_rating,
            is_ai_generated=is_ai_generated,
            is_animated=is_animated,
            uploader_user_id=data.get("uploader_user_id"),
            uploader_username=data.get("uploader_username"),
            deletion_status=data.get("deletion_status"),
            deleted_at=data.get("deleted_at"),
            deleted_by_user_id=data.get("deleted_by_user_id"),
            deleted_by_username=data.get("deleted_by_username"),
            extra=extra,
        )
