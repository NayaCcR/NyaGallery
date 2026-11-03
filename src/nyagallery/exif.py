"""Best-effort photo metadata; originals are never modified."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from io import BytesIO
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_timezone(value: str) -> tzinfo:
    if value == "UTC":
        return timezone.utc
    if re.fullmatch(r"[+-]\d{2}:\d{2}", value):
        hours, minutes = map(int, value[1:].split(":"))
        if hours <= 23 and minutes <= 59:
            return timezone(timedelta(minutes=(hours * 60 + minutes) * (-1 if value[0] == "-" else 1)))
    else:
        try:
            return ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    raise ValueError(f"Invalid EXIF timezone: {value!r}; use UTC, +08:00 or an installed IANA timezone")


def validate_timezone(value: str) -> str:
    parse_timezone(value)
    return value


def browser_mtime(value: str | None) -> str | None:
    """Accept integer Unix milliseconds, 1980-01-01 through tomorrow.

    The lower bound also rejects contemporary Unix seconds passed as milliseconds.
    """
    if value is None:
        return None
    if not re.fullmatch(r"\d{12,13}", value):
        raise ValueError("last_modified_ms must be integer Unix milliseconds")
    milliseconds = int(value)
    if not 315532800000 <= milliseconds <= int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp() * 1000):
        raise ValueError("last_modified_ms must be between 1980-01-01 and tomorrow")
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()


def file_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        return None


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace").strip("\x00 ")
    return str(value or "").strip("\x00 ")


def _ifd(raw, tag: int) -> dict:
    try:
        return dict(raw.get_ifd(tag))
    except Exception:
        return {}


def _coordinate(gps: dict, tag: int, ref_tag: int, positive: str, negative: str, limit: int) -> float | None:
    try:
        degrees, minutes, seconds = (float(value) for value in gps[tag])
        ref = _text(gps[ref_tag]).upper()
        if ref not in (positive, negative) or not all(math.isfinite(v) for v in (degrees, minutes, seconds)):
            return None
        if not (0 <= degrees <= limit and 0 <= minutes < 60 and 0 <= seconds < 60):
            return None
        result = degrees + minutes / 60 + seconds / 3600
        if result > limit:
            return None
        return -result if ref == negative else result
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def extract_photo_metadata(path: Path, *, default_timezone: str = "UTC", fallback_time: str | None = None, fallback_source: str = "file_mtime") -> dict[str, object]:
    try:
        from PIL import Image
        with Image.open(path) as image:
            return _extract_photo_metadata_from_image(image, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)
    except Exception:
        return _extract_photo_metadata_values({}, {}, {}, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)


def extract_photo_metadata_bytes(content: bytes, *, default_timezone: str = "UTC", fallback_time: str | None = None, fallback_source: str = "file_mtime") -> dict[str, object]:
    try:
        from PIL import Image
        with Image.open(BytesIO(content)) as image:
            return _extract_photo_metadata_from_image(image, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)
    except Exception:
        return _extract_photo_metadata_values({}, {}, {}, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)


def _extract_photo_metadata_from_image(image: object, *, default_timezone: str, fallback_time: str | None, fallback_source: str) -> dict[str, object]:
    raw = image.getexif()
    root = dict(raw)
    exif = {**root, **_ifd(raw, 34665)}
    gps = _ifd(raw, 34853)
    return _extract_photo_metadata_values(root, exif, gps, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)


def _extract_photo_metadata_values(root: dict[object, object], exif: dict[object, object], gps: dict[object, object], *, default_timezone: str, fallback_time: str | None, fallback_source: str) -> dict[str, object]:
    extra: dict[str, object] = {}
    make, model = _text(root.get(271)), _text(root.get(272))
    if make or model:
        extra["camera"] = {"make": make, "model": model}
    for tag, offset_tag, subsecond_tag, name in (
        (36867, 36881, 37521, "DateTimeOriginal"),
        (36868, 36882, 37522, "DateTimeDigitized"),
        (306, 36880, 37520, "DateTime"),
    ):
        try:
            captured = datetime.strptime(_text(exif.get(tag)), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
        offset = _text(exif.get(offset_tag))
        try:
            zone = parse_timezone(offset) if re.fullmatch(r"[+-]\d{2}:\d{2}", offset) else None
        except ValueError:
            zone = None
        zone_source = "exif_offset" if zone is not None else "configured_default"
        zone = zone or parse_timezone(default_timezone)
        subseconds = _text(exif.get(subsecond_tag))
        if subseconds.isdigit():
            captured = captured.replace(microsecond=int(subseconds[:6].ljust(6, "0")))
        timestamp = captured.replace(tzinfo=zone).isoformat()
        extra.update(captured_at=timestamp, captured_at_source=f"exif:{name}", exif_captured_at=timestamp,
                     captured_at_timezone_source=zone_source)
        break

    coordinates = {}
    for key, tag, ref_tag, positive, negative, limit in (
        ("latitude", 2, 1, "N", "S", 90), ("longitude", 4, 3, "E", "W", 180),
    ):
        coordinate = _coordinate(gps, tag, ref_tag, positive, negative, limit)
        if coordinate is not None:
            coordinates[key] = coordinate
    if coordinates:
        extra["gps"] = coordinates
    if "captured_at" not in extra and fallback_time is not None:
        extra.update(captured_at=fallback_time, captured_at_source=fallback_source)
    return extra
