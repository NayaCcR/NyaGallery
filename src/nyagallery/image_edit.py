"""Server-side image edits for user uploads."""
from __future__ import annotations

from io import BytesIO

from nyagallery.exif import extract_photo_metadata_bytes


class ImageEditError(ValueError):
    pass


def edit_uploaded_image(
    content: bytes,
    *,
    mime_type: str | None,
    rotation: int = 0,
    crop_left: float = 0,
    crop_top: float = 0,
    crop_right: float = 0,
    crop_bottom: float = 0,
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    exif_policy: str = "keep",
    default_timezone: str = "UTC",
    fallback_time: str | None = None,
    fallback_source: str = "file_mtime",
    max_pixels: int = 100_000_000,
) -> tuple[bytes, dict[str, object]]:
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime not in {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}:
        raise ImageEditError("image editing supports JPEG, PNG, WebP, TIFF, and BMP uploads")
    if rotation not in {0, 90, 180, 270}:
        raise ImageEditError("rotation must be 0, 90, 180, or 270 degrees")
    if exif_policy not in {"keep", "strip"}:
        raise ImageEditError("EXIF policy must be keep or strip")
    if min(crop_left, crop_top, crop_right, crop_bottom) < 0 or max(crop_left, crop_top, crop_right, crop_bottom) > 45:
        raise ImageEditError("crop insets must be between 0 and 45 percent")
    if crop_left + crop_right >= 100 or crop_top + crop_bottom >= 100:
        raise ImageEditError("crop area is empty")

    metadata = extract_photo_metadata_bytes(content, default_timezone=default_timezone, fallback_time=fallback_time, fallback_source=fallback_source)
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required for upload editing; install the media extra") from exc

    try:
        with Image.open(BytesIO(content)) as source:
            if getattr(source, "n_frames", 1) > 1:
                raise ImageEditError("animated images cannot be edited during upload")
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > max_pixels:
                raise ImageEditError("image exceeds the configured pixel limit")
            exif = source.getexif()
            image = ImageOps.exif_transpose(source).copy()
            left = round(image.width * crop_left / 100)
            top = round(image.height * crop_top / 100)
            right = image.width - round(image.width * crop_right / 100)
            bottom = image.height - round(image.height * crop_bottom / 100)
            if left or top or right != image.width or bottom != image.height:
                image = image.crop((left, top, right, bottom))
            if rotation:
                image = image.rotate(-rotation, expand=True)
            if flip_horizontal:
                image = ImageOps.mirror(image)
            if flip_vertical:
                image = ImageOps.flip(image)
            if image.width * image.height > max_pixels:
                raise ImageEditError("edited image exceeds the configured pixel limit")
            output = BytesIO()
            image_format = source.format or "JPEG"
            save_options: dict[str, object] = {}
            if exif_policy == "keep":
                try:
                    exif[274] = 1
                    save_options["exif"] = exif.tobytes()
                except Exception:
                    pass
            if image_format == "JPEG":
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                save_options.update(quality=95, optimize=True)
            image.save(output, format=image_format, **save_options)
            return output.getvalue(), metadata
    except ImageEditError:
        raise
    except Exception as exc:
        raise ImageEditError(f"could not edit uploaded image: {exc}") from exc
