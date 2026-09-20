from __future__ import annotations

from pathlib import Path
from io import BytesIO
import zipfile

import pytest

from nyagallery.config import MediaConfig
from nyagallery.media import MediaGenerator, MediaLimits, _save_animated_webp, media_limits_from_config, resolve_media_concurrency


def test_animation_defaults_and_concurrency(monkeypatch):
    limits = media_limits_from_config(MediaConfig())
    assert limits.webp_quality == 75
    assert limits.max_concurrency == 0
    monkeypatch.setattr("nyagallery.media.os.cpu_count", lambda: 20)
    assert resolve_media_concurrency(0) == 4
    assert resolve_media_concurrency(1) == 1
    assert resolve_media_concurrency(3) == 3


def test_animated_webp_uses_quality_and_fast_method(tmp_path: Path, monkeypatch):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is not installed")

    calls: dict[str, object] = {}
    original_save = Image.Image.save

    def capture(self, fp, *args, **kwargs):
        calls.update(kwargs)
        return original_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", capture)
    frames = [Image.new("RGBA", (8, 8), color=color) for color in ("red", "blue")]
    output = tmp_path / "preview.webp"
    _save_animated_webp(frames, [80, 120], output, 75, loop=2)
    assert output.exists()
    assert calls["quality"] == 75
    assert calls["method"] == 4


def test_animation_fixtures_preserve_delays_and_loop(tmp_path: Path, monkeypatch):
    pil = pytest.importorskip("PIL.Image")
    Image = pil
    frames = [Image.new("RGBA", (8, 8), color=color) for color in ("red", "blue", "green")]

    apng = tmp_path / "fixture.apng"
    frames[0].save(apng, format="PNG", save_all=True, append_images=frames[1:], duration=[40, 80, 120], loop=2)
    with Image.open(apng) as source:
        assert source.n_frames == 3
        assert source.info.get("loop") == 2
        durations = []
        for index in range(source.n_frames):
            source.seek(index)
            durations.append(source.info.get("duration"))
        assert durations == [40, 80, 120]

    ugoira = tmp_path / "fixture.ugoira.zip"
    with zipfile.ZipFile(ugoira, "w") as archive:
        for index, frame in enumerate(frames):
            payload = BytesIO()
            frame.save(payload, format="PNG")
            archive.writestr(f"{index:06d}.png", payload.getvalue())
    with zipfile.ZipFile(ugoira) as archive:
        assert sorted(archive.namelist()) == ["000000.png", "000001.png", "000002.png"]

    calls: dict[str, object] = {}
    original_save = Image.Image.save

    def capture(self, fp, *args, **kwargs):
        calls.update(kwargs)
        return original_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", capture)
    output = tmp_path / "fixture.webp"
    _save_animated_webp(frames, [40, 80, 120], output, 75, loop=2)
    assert calls["duration"] == [40, 80, 120]
    with Image.open(output) as preview:
        assert preview.n_frames == 3
        assert preview.info.get("loop") == 2
