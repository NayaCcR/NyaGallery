from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
from typing import Callable
import time
import zipfile

from nyagallery.config import MediaConfig
from nyagallery.metadata import GalleryMetadata
from nyagallery.storage import GalleryStorage


ProgressCallback = Callable[[dict[str, object]], None]
MiB = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


def _positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def _bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value or default)))
    except (TypeError, ValueError):
        return default


MAX_FRAME_PIXELS = _env_int("NYAGALLERY_MEDIA_MAX_FRAME_PIXELS", 50_000_000)
MAX_IMAGE_PIXELS = _env_int("NYAGALLERY_MEDIA_MAX_IMAGE_PIXELS", 100_000_000)
MAX_ANIMATION_FRAMES = _env_int("NYAGALLERY_MEDIA_MAX_ANIMATION_FRAMES", 500)
MAX_ZIP_UNCOMPRESSED_BYTES = _env_int("NYAGALLERY_MEDIA_MAX_ZIP_UNCOMPRESSED_BYTES", 512 * MiB)
MAX_ZIP_FRAME_BYTES = _env_int("NYAGALLERY_MEDIA_MAX_ZIP_FRAME_BYTES", 64 * MiB)
MAX_VIDEO_BYTES = _env_int("NYAGALLERY_MEDIA_MAX_VIDEO_BYTES", 128 * MiB)
DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS = _env_int(
    "NYAGALLERY_MEDIA_GENERATION_TIMEOUT_SECONDS",
    _env_int("NYAGALLERY_MEDIA_TASK_TIMEOUT_SECONDS", 300),
)


@dataclass(frozen=True)
class MediaLimits:
    max_frame_pixels: int = MAX_FRAME_PIXELS
    max_image_pixels: int = MAX_IMAGE_PIXELS
    max_animation_frames: int = MAX_ANIMATION_FRAMES
    max_zip_uncompressed_bytes: int = MAX_ZIP_UNCOMPRESSED_BYTES
    max_zip_frame_bytes: int = MAX_ZIP_FRAME_BYTES
    max_video_bytes: int = MAX_VIDEO_BYTES
    generation_timeout_seconds: int = DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS
    preview_max_edge: int = 1800
    thumb_max_edge: int = 420
    avif_quality: int = 82
    webp_quality: int = 82


def media_limits_from_config(config: MediaConfig | None = None) -> MediaLimits:
    if config is None:
        return MediaLimits()
    return MediaLimits(
        max_frame_pixels=_positive_int(config.max_frame_pixels, MAX_FRAME_PIXELS),
        max_image_pixels=_positive_int(config.max_image_pixels, MAX_IMAGE_PIXELS),
        max_animation_frames=_positive_int(config.max_animation_frames, MAX_ANIMATION_FRAMES),
        max_zip_uncompressed_bytes=_positive_int(config.max_zip_uncompressed_bytes, MAX_ZIP_UNCOMPRESSED_BYTES),
        max_zip_frame_bytes=_positive_int(config.max_zip_frame_bytes, MAX_ZIP_FRAME_BYTES),
        max_video_bytes=_positive_int(config.max_video_bytes, MAX_VIDEO_BYTES),
        generation_timeout_seconds=_positive_int(config.generation_timeout_seconds, DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS),
        preview_max_edge=_positive_int(config.preview_max_edge, 1800),
        thumb_max_edge=_positive_int(config.thumb_max_edge, 420),
        avif_quality=_bounded_int(config.avif_quality, 82, minimum=1, maximum=100),
        webp_quality=_bounded_int(config.webp_quality, 82, minimum=1, maximum=100),
    )


@dataclass(frozen=True)
class GeneratedMedia:
    asset_key: str
    preview_path: str | None
    thumb_path: str | None
    kind: str


class MediaGenerationError(RuntimeError):
    pass


class MediaGenerationTimeout(MediaGenerationError):
    pass


def is_cover_only_original(metadata: GalleryMetadata) -> bool:
    """Video originals cannot be decoded here; their cache comes from a cover frame written at sync time."""
    return str(metadata.mime_type or "").casefold().startswith("video/")


def _emit_progress(callback: ProgressCallback | None, **payload: object) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        pass


class MediaGenerator:
    def __init__(
        self,
        storage: GalleryStorage,
        *,
        preview_max_edge: int = 1800,
        thumb_max_edge: int = 420,
        avif_quality: int = 82,
        webp_quality: int = 82,
        timeout_seconds: int = DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS,
        limits: MediaLimits | None = None,
    ) -> None:
        self.limits = limits or MediaLimits(
            generation_timeout_seconds=_positive_int(timeout_seconds, DEFAULT_MEDIA_GENERATION_TIMEOUT_SECONDS),
            preview_max_edge=_positive_int(preview_max_edge, 1800),
            thumb_max_edge=_positive_int(thumb_max_edge, 420),
            avif_quality=_bounded_int(avif_quality, 82, minimum=1, maximum=100),
            webp_quality=_bounded_int(webp_quality, 82, minimum=1, maximum=100),
        )
        self.storage = storage
        self.preview_max_edge = self.limits.preview_max_edge
        self.thumb_max_edge = self.limits.thumb_max_edge
        self.avif_quality = self.limits.avif_quality
        self.webp_quality = self.limits.webp_quality
        self.timeout_seconds = self.limits.generation_timeout_seconds

    def generate_all(self) -> list[GeneratedMedia]:
        return [
            self.generate_for_metadata(metadata)
            for metadata in self.storage.iter_metadata()
            if not is_cover_only_original(metadata)
        ]

    def generate_for_asset_key(
        self,
        asset_key: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> GeneratedMedia:
        return self.generate_for_metadata(self.storage.read_metadata(asset_key), progress=progress)

    def generate_for_metadata(
        self,
        metadata: GalleryMetadata,
        *,
        progress: ProgressCallback | None = None,
    ) -> GeneratedMedia:
        deadline = time.monotonic() + self.timeout_seconds
        self.storage.ensure()
        if is_cover_only_original(metadata):
            raise MediaGenerationError(
                f"video original is cached from its cover frame, not decoded here: {metadata.asset_key}"
            )
        original_path = self.storage.resolve_relative_path(metadata.original_path)
        if not original_path.exists():
            raise MediaGenerationError(f"original file does not exist: {original_path}")
        _check_deadline(deadline)
        _emit_progress(progress, stage="starting", progress=0.0, message="starting media cache generation")
        if original_path.suffix.lower() == ".zip" or metadata.mime_type == "application/zip":
            return self._generate_ugoira(metadata, original_path, progress=progress, deadline=deadline)
        if is_animated_raster(original_path, limits=self.limits):
            return self._generate_animated_raster(metadata, original_path, progress=progress, deadline=deadline)
        return self._generate_static(metadata, original_path, progress=progress, deadline=deadline)

    def generate_from_cover(
        self,
        metadata: GalleryMetadata,
        cover: bytes,
        *,
        progress: ProgressCallback | None = None,
    ) -> GeneratedMedia:
        """Builds the cache from a cover frame for originals Pillow cannot decode, such as archived X videos."""
        Image, ImageOps, _ = _load_pillow(self.limits)
        self.storage.ensure()
        deadline = time.monotonic() + self.timeout_seconds
        _emit_progress(progress, stage="starting", progress=0.0, message="starting cover cache generation")
        with Image.open(BytesIO(cover)) as source:
            _validate_frame_size(source.size, label="cover", limits=self.limits)
            image = ImageOps.exif_transpose(source)
            _validate_frame_size(image.size, label="cover", limits=self.limits)
            _check_deadline(deadline)
            preview_path = self.storage.preview_path(metadata.asset_key, ".avif")
            thumb_path = self.storage.thumb_path(metadata.asset_key, ".avif")
            _remove_if_exists(self.storage.preview_path(metadata.asset_key, ".webp"))
            _emit_progress(progress, stage="encoding_preview", progress=65.0, message="encoding preview")
            _save_avif(_fit_image(image, self.preview_max_edge), preview_path, self.avif_quality)
            _emit_progress(progress, stage="encoding_thumb", progress=85.0, message="encoding thumbnail")
            _check_deadline(deadline)
            _save_avif(_fit_image(image, self.thumb_max_edge), thumb_path, self.avif_quality)
        return GeneratedMedia(
            asset_key=metadata.asset_key,
            preview_path=self.storage.cache_relative_path(preview_path),
            thumb_path=self.storage.cache_relative_path(thumb_path),
            kind="cover",
        )

    def _generate_static(
        self,
        metadata: GalleryMetadata,
        original_path: Path,
        *,
        progress: ProgressCallback | None = None,
        deadline: float | None = None,
    ) -> GeneratedMedia:
        Image, ImageOps, _ = _load_pillow(self.limits)
        _check_deadline(deadline)
        with Image.open(original_path) as source:
            _validate_frame_size(source.size, label="image", limits=self.limits)
            _emit_progress(progress, stage="reading_image", progress=20.0, message="reading image")
            image = ImageOps.exif_transpose(source)
            _validate_frame_size(image.size, label="image", limits=self.limits)
            _write_media_metadata_if_changed(self.storage, metadata, image.size, is_animated=False)
            _check_deadline(deadline)
            preview = _fit_image(image, self.preview_max_edge)
            thumb = _fit_image(image, self.thumb_max_edge)
            preview_path = self.storage.preview_path(metadata.asset_key, ".avif")
            thumb_path = self.storage.thumb_path(metadata.asset_key, ".avif")
            _remove_if_exists(self.storage.preview_path(metadata.asset_key, ".webp"))
            _emit_progress(progress, stage="encoding_preview", progress=65.0, message="encoding preview")
            _check_deadline(deadline)
            _save_avif(preview, preview_path, self.avif_quality)
            _emit_progress(progress, stage="encoding_thumb", progress=85.0, message="encoding thumbnail")
            _check_deadline(deadline)
            _save_avif(thumb, thumb_path, self.avif_quality)
        return GeneratedMedia(
            asset_key=metadata.asset_key,
            preview_path=self.storage.cache_relative_path(preview_path),
            thumb_path=self.storage.cache_relative_path(thumb_path),
            kind="static",
        )

    def _generate_animated_raster(
        self,
        metadata: GalleryMetadata,
        original_path: Path,
        *,
        progress: ProgressCallback | None = None,
        deadline: float | None = None,
    ) -> GeneratedMedia:
        Image, ImageOps, ImageSequence = _load_pillow(self.limits)
        _check_deadline(deadline)
        with Image.open(original_path) as source:
            frames = []
            durations = []
            first_frame_size: tuple[int, int] | None = None
            total_frames = max(1, int(getattr(source, "n_frames", 1) or 1))
            if total_frames > self.limits.max_animation_frames:
                raise MediaGenerationError(
                    f"animated image has too many frames: {total_frames} > {self.limits.max_animation_frames}"
                )
            start = time.perf_counter()
            last_emit = 0.0
            for index, frame in enumerate(ImageSequence.Iterator(source), 1):
                _check_deadline(deadline)
                if index > self.limits.max_animation_frames:
                    raise MediaGenerationError(
                        f"animated image has too many frames: {index} > {self.limits.max_animation_frames}"
                    )
                _validate_frame_size(frame.size, label=f"frame {index}", limits=self.limits)
                image = ImageOps.exif_transpose(frame)
                _validate_frame_size(image.size, label=f"frame {index}", limits=self.limits)
                if first_frame_size is None:
                    first_frame_size = image.size
                frames.append(_fit_image(image.convert("RGBA"), self.preview_max_edge))
                durations.append(max(20, int(frame.info.get("duration") or source.info.get("duration") or 100)))
                now = time.perf_counter()
                if index == 1 or index == total_frames or now - last_emit >= 0.75:
                    elapsed = max(0.001, now - start)
                    _emit_progress(
                        progress,
                        stage="reading_frames",
                        progress=min(85.0, 5.0 + 75.0 * index / total_frames),
                        message="reading animated frames",
                        frames_done=index,
                        frames_total=total_frames,
                        frames_per_second=index / elapsed,
                    )
                    last_emit = now
            loop = int(source.info.get("loop") or 0)

        if not frames:
            raise MediaGenerationError(f"animated image has no frames: {original_path}")
        if first_frame_size:
            _write_media_metadata_if_changed(self.storage, metadata, first_frame_size, is_animated=True)

        preview_path = self.storage.preview_path(metadata.asset_key, ".webp")
        thumb_path = self.storage.thumb_path(metadata.asset_key, ".avif")
        _remove_if_exists(self.storage.preview_path(metadata.asset_key, ".avif"))
        _check_deadline(deadline)
        _emit_progress(
            progress,
            stage="encoding_webp",
            progress=90.0,
            message="encoding animated preview",
            frames_done=len(frames),
            frames_total=len(frames),
        )
        _save_animated_webp(frames, durations, preview_path, self.webp_quality, loop=loop)
        _emit_progress(progress, stage="encoding_thumb", progress=96.0, message="encoding thumbnail")
        _check_deadline(deadline)
        _save_avif(_fit_image(frames[0], self.thumb_max_edge), thumb_path, self.avif_quality)
        return GeneratedMedia(
            asset_key=metadata.asset_key,
            preview_path=self.storage.cache_relative_path(preview_path),
            thumb_path=self.storage.cache_relative_path(thumb_path),
            kind="animated",
        )

    def _generate_ugoira(
        self,
        metadata: GalleryMetadata,
        original_path: Path,
        *,
        progress: ProgressCallback | None = None,
        deadline: float | None = None,
    ) -> GeneratedMedia:
        Image, _, _ = _load_pillow(self.limits)
        _check_deadline(deadline)
        frame_specs = metadata.extra.get("ugoira_frames") or []
        frames_by_name = {
            str(frame.get("file")): int(frame.get("delay") or 100)
            for frame in frame_specs
            if isinstance(frame, dict) and str(frame.get("file") or "").strip()
        }
        with zipfile.ZipFile(original_path) as archive:
            image_infos = _validate_ugoira_zip_archive(archive, limits=self.limits)
            infos_by_name = {info.filename: info for info in image_infos}
            if not infos_by_name:
                raise MediaGenerationError(f"ugoira zip has no image frames: {original_path}")
            ordered_names = [name for name in frames_by_name if name in infos_by_name] or sorted(infos_by_name)
            if len(ordered_names) > self.limits.max_animation_frames:
                raise MediaGenerationError(
                    f"ugoira zip has too many frames: {len(ordered_names)} > {self.limits.max_animation_frames}"
                )
            frames = []
            durations = []
            first_frame_size: tuple[int, int] | None = None
            total_frames = max(1, len(ordered_names))
            total_uncompressed_read = 0
            start = time.perf_counter()
            last_emit = 0.0
            for index, name in enumerate(ordered_names, 1):
                _check_deadline(deadline)
                info = infos_by_name[name]
                _validate_zip_frame_info(info, limits=self.limits)
                with archive.open(info) as file:
                    frame_bytes = _read_limited(file, self.limits.max_zip_frame_bytes, label=f"ugoira frame {name}")
                total_uncompressed_read += len(frame_bytes)
                if total_uncompressed_read > self.limits.max_zip_uncompressed_bytes:
                    raise MediaGenerationError(
                        "ugoira zip total uncompressed image data is too large: "
                        f"{total_uncompressed_read} > {self.limits.max_zip_uncompressed_bytes}"
                    )
                with Image.open(BytesIO(frame_bytes)) as frame_source:
                    _validate_frame_size(frame_source.size, label=f"frame {index}", limits=self.limits)
                    frame = frame_source.convert("RGBA")
                _validate_frame_size(frame.size, label=f"frame {index}", limits=self.limits)
                if first_frame_size is None:
                    first_frame_size = frame.size
                frames.append(_fit_image(frame, self.preview_max_edge))
                durations.append(frames_by_name.get(name, 100))
                now = time.perf_counter()
                if index == 1 or index == total_frames or now - last_emit >= 0.75:
                    elapsed = max(0.001, now - start)
                    _emit_progress(
                        progress,
                        stage="reading_frames",
                        progress=min(85.0, 5.0 + 75.0 * index / total_frames),
                        message="reading ugoira frames",
                        frames_done=index,
                        frames_total=total_frames,
                        frames_per_second=index / elapsed,
                    )
                    last_emit = now
        if first_frame_size:
            _write_media_metadata_if_changed(self.storage, metadata, first_frame_size, is_animated=True)

        preview_path = self.storage.preview_path(metadata.asset_key, ".webp")
        _remove_if_exists(self.storage.preview_path(metadata.asset_key, ".avif"))
        _check_deadline(deadline)
        _emit_progress(
            progress,
            stage="encoding_webp",
            progress=90.0,
            message="encoding ugoira preview",
            frames_done=len(frames),
            frames_total=len(frames),
        )
        frames[0].save(
            preview_path,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            quality=self.webp_quality,
            method=6,
        )
        thumb = _fit_image(frames[0], self.thumb_max_edge)
        thumb_path = self.storage.thumb_path(metadata.asset_key, ".avif")
        _emit_progress(progress, stage="encoding_thumb", progress=96.0, message="encoding thumbnail")
        _check_deadline(deadline)
        _save_avif(thumb, thumb_path, self.avif_quality)
        return GeneratedMedia(
            asset_key=metadata.asset_key,
            preview_path=self.storage.cache_relative_path(preview_path),
            thumb_path=self.storage.cache_relative_path(thumb_path),
            kind="ugoira",
        )


def probe_media_size(
    path: Path,
    *,
    mime_type: str | None = None,
    limits: MediaLimits | None = None,
) -> tuple[int | None, int | None]:
    active_limits = limits or MediaLimits()
    try:
        if path.suffix.lower() == ".zip" or mime_type == "application/zip":
            return _probe_ugoira_size(path, limits=active_limits)
        return _probe_static_size(path, limits=active_limits)
    except Exception:
        return (None, None)


def is_animated_raster(path: Path, *, limits: MediaLimits | None = None) -> bool:
    try:
        Image, _, _ = _load_pillow(limits)
        with Image.open(path) as source:
            return bool(getattr(source, "is_animated", False) and getattr(source, "n_frames", 1) > 1)
    except Exception:
        return False


def _load_pillow(limits: MediaLimits | None = None):
    try:
        import pillow_avif  # noqa: F401
        from PIL import Image, ImageOps, ImageSequence
    except ImportError as exc:
        raise MediaGenerationError(
            'Install media support with: python -m pip install -e ".[media]"'
        ) from exc
    active_limits = limits or MediaLimits()
    Image.MAX_IMAGE_PIXELS = active_limits.max_image_pixels
    return Image, ImageOps, ImageSequence


def _probe_static_size(path: Path, *, limits: MediaLimits) -> tuple[int | None, int | None]:
    Image, ImageOps, _ = _load_pillow(limits)
    with Image.open(path) as source:
        _validate_frame_size(source.size, label="image", limits=limits)
        image = ImageOps.exif_transpose(source)
        _validate_frame_size(image.size, label="image", limits=limits)
        return image.size


def _probe_ugoira_size(path: Path, *, limits: MediaLimits) -> tuple[int | None, int | None]:
    Image, _, _ = _load_pillow(limits)
    with zipfile.ZipFile(path) as archive:
        image_infos = _validate_ugoira_zip_archive(archive, limits=limits)
        for info in sorted(image_infos, key=lambda item: item.filename):
            _validate_zip_frame_info(info, limits=limits)
            with archive.open(info) as file:
                frame_bytes = _read_limited(file, limits.max_zip_frame_bytes, label=f"ugoira frame {info.filename}")
            with Image.open(BytesIO(frame_bytes)) as image:
                _validate_frame_size(image.size, label="frame", limits=limits)
                return image.size
    return (None, None)


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise MediaGenerationTimeout("media generation timed out")


def _validate_frame_size(size: tuple[int, int], *, label: str, limits: MediaLimits) -> None:
    width, height = int(size[0] or 0), int(size[1] or 0)
    if width <= 0 or height <= 0:
        raise MediaGenerationError(f"{label} has invalid size: {width}x{height}")
    pixels = width * height
    if pixels > limits.max_frame_pixels:
        raise MediaGenerationError(
            f"{label} is too large: {width}x{height} ({pixels} pixels) > {limits.max_frame_pixels}"
        )


def _validate_ugoira_zip_archive(archive: zipfile.ZipFile, *, limits: MediaLimits) -> list[zipfile.ZipInfo]:
    entries = [info for info in archive.infolist() if not info.is_dir()]
    total_uncompressed = 0
    for info in entries:
        total_uncompressed += max(0, int(info.file_size or 0))
        if total_uncompressed > limits.max_zip_uncompressed_bytes:
            raise MediaGenerationError(
                "ugoira zip total uncompressed size is too large: "
                f"{total_uncompressed} > {limits.max_zip_uncompressed_bytes}"
            )
    image_infos = [info for info in entries if _is_image_name(info.filename)]
    if len(image_infos) > limits.max_animation_frames:
        raise MediaGenerationError(
            f"ugoira zip has too many image frames: {len(image_infos)} > {limits.max_animation_frames}"
        )
    for info in image_infos:
        _validate_zip_frame_info(info, limits=limits)
    return image_infos


def _validate_zip_frame_info(info: zipfile.ZipInfo, *, limits: MediaLimits) -> None:
    frame_size = max(0, int(info.file_size or 0))
    if frame_size > limits.max_zip_frame_bytes:
        raise MediaGenerationError(
            f"ugoira frame is too large: {info.filename} ({frame_size} bytes) > {limits.max_zip_frame_bytes}"
        )


def _read_limited(file, max_bytes: int, *, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.read(min(MiB, max(1, max_bytes - total + 1)))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise MediaGenerationError(f"{label} is too large: {total} bytes > {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def _write_media_metadata_if_changed(
    storage: GalleryStorage,
    metadata: GalleryMetadata,
    size: tuple[int, int],
    *,
    is_animated: bool,
) -> None:
    width, height = size
    if metadata.width == width and metadata.height == height and metadata.is_animated == is_animated:
        return
    updated = metadata.__class__(
        **{
            **metadata.to_dict(),
            "width": width,
            "height": height,
            "is_animated": is_animated,
        }
    )
    storage.write_metadata(updated, replace=True)


def _fit_image(image, max_edge: int):
    fitted = image.copy()
    if fitted.mode not in ("RGB", "RGBA"):
        fitted = fitted.convert("RGBA")
    fitted.thumbnail((max_edge, max_edge))
    return fitted


def _save_avif(image, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="AVIF", quality=quality)


def _save_animated_webp(frames, durations: list[int], path: Path, quality: int, *, loop: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        path,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=loop,
        quality=quality,
        method=6,
    )


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
