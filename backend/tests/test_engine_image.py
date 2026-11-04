from __future__ import annotations

import pytest
from PIL import Image

from engines.image import ImageEngine
from tests.conftest import convert, detected

ENGINE = ImageEngine()
TARGETS = ["png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico"]


@pytest.mark.parametrize("dst", [t for t in TARGETS if t != "png"])
def test_png_to_every_raster(samples, tmp_path, dst: str) -> None:
    [out] = convert(ENGINE, samples.get("png"), dst, tmp_path)
    assert detected(out) == dst


@pytest.mark.parametrize("src", ["jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico", "svg"])
def test_every_source_to_png(samples, tmp_path, src: str) -> None:
    [out] = convert(ENGINE, samples.get(src), "png", tmp_path)
    assert detected(out) == "png"


def test_resize_keeps_aspect_ratio(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("png"), "jpg", tmp_path, width=160)
    assert Image.open(out).size == (160, 100)


def test_quality_changes_size(samples, tmp_path) -> None:
    sizes = []
    for quality in (10, 95):
        folder = tmp_path / str(quality)
        folder.mkdir()
        sizes.append(convert(ENGINE, samples.get("png"), "jpg", folder, quality=quality)[0].stat().st_size)
    assert sizes[0] < sizes[1]


def test_transparency_is_flattened_for_jpeg(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("png"), "jpg", tmp_path)
    assert Image.open(out).mode == "RGB"


def test_strip_metadata(samples, tmp_path) -> None:
    src = tmp_path / "exif.jpg"
    image = Image.open(samples.get("jpg"))
    exif = Image.Exif()
    exif[0x010F] = "HakobuCam"  # Make
    image.save(src, exif=exif)
    (tmp_path / "keep").mkdir()
    (tmp_path / "strip").mkdir()
    kept = convert(ENGINE, src, "webp", tmp_path / "keep")[0]
    stripped = convert(ENGINE, src, "webp", tmp_path / "strip", strip_metadata=True)[0]
    assert Image.open(kept).getexif().get(0x010F) == "HakobuCam"
    assert not Image.open(stripped).getexif()


def test_animated_gif_to_webp_keeps_frames(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("gif"), "webp", tmp_path)
    assert getattr(Image.open(out), "n_frames", 1) == 2


def test_icon_is_square_with_standard_sizes(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("png"), "ico", tmp_path)
    assert (256, 256) in Image.open(out).info["sizes"]


def test_corrupted_input(tmp_path) -> None:
    from engines.base import ConversionError

    bad = tmp_path / "bad.bmp"
    bad.write_bytes(b"BM" + b"\x00" * 50)
    with pytest.raises(ConversionError):
        convert(ENGINE, bad, "png", tmp_path)
