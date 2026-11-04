"""Raster image conversion: pyvips first (fast, streaming), Pillow as fallback."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from engines.base import (
    ConversionError,
    ConversionOptions,
    CorruptInputError,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
)

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

log = logging.getLogger(__name__)

RASTER_IN = ("png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico")
RASTER_OUT = ("png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico")
ANIMATED = frozenset({"gif", "webp"})
NO_ALPHA = frozenset({"jpg", "bmp"})
# Formats libvips can't (reliably) read/write: no ICO support, BMP only via ImageMagick,
# and HEIC encoding needs an HEVC encoder that distro libheif builds often omit.
PILLOW_ONLY_IN = frozenset({"bmp", "ico"})
PILLOW_ONLY_OUT = frozenset({"bmp", "ico", "heic"})
ICO_MAX = 256
ICO_SIZES = (16, 32, 48, 64, 128, 256)
DEFAULT_QUALITY = 85
PILLOW_FORMAT = {
    "png": "PNG", "jpg": "JPEG", "webp": "WEBP", "gif": "GIF", "bmp": "BMP",
    "tiff": "TIFF", "heic": "HEIF", "avif": "AVIF", "ico": "ICO",
}

# pillow-heif must load its bundled libheif (with the HEVC encoder) before libvips
# pulls in the system libheif, otherwise HEIC encoding silently disappears.
from pillow_heif import register_heif_opener

register_heif_opener()

try:
    import pyvips

    VIPS_KEEP_API = pyvips.at_least_libvips(8, 15)
except (ImportError, OSError):  # libvips missing → Pillow only
    pyvips = None
    VIPS_KEEP_API = False


class ImageEngine(Engine):
    name = "image"
    transforms = frozenset(RASTER_OUT)

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs(RASTER_IN, RASTER_OUT) | pairs(("svg",), RASTER_OUT)

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        src, dst = formats_of(input_path, output_path)
        with tempfile.TemporaryDirectory() as tmp:
            if src == "svg":
                input_path, src = _rasterize_svg(input_path, Path(tmp) / "svg.png", options), "png"
            if pyvips is not None and src not in PILLOW_ONLY_IN and dst not in PILLOW_ONLY_OUT:
                try:
                    _convert_vips(input_path, output_path, src, dst, options)
                    return [output_path]
                except pyvips.Error as exc:
                    log.info("libvips could not handle %s→%s, falling back to Pillow: %s", src, dst, exc)
            _convert_pillow(input_path, output_path, src, dst, options)
        return [output_path]


def _rasterize_svg(path: Path, out: Path, options: ConversionOptions) -> Path:
    import cairosvg

    try:
        # unsafe=False (default) blocks external entity and file references.
        cairosvg.svg2png(url=str(path), write_to=str(out),
                         output_width=options.width, output_height=options.height)
    except Exception as exc:  # cairosvg raises many parser-specific types
        raise CorruptInputError("This SVG could not be read.") from exc
    return out


def _convert_vips(src_path: Path, out: Path, src: str, dst: str, options: ConversionOptions) -> None:
    animated = src in ANIMATED and dst in ANIMATED
    if options.width or options.height:
        # thumbnail() shrinks on load, the cheapest way to resize.
        image = pyvips.Image.thumbnail(
            str(src_path), options.width or 100_000, height=options.height or 100_000,
            size="down", option_string="n=-1" if animated else "",
        )
    else:
        image = pyvips.Image.new_from_file(str(src_path), access="sequential", **({"n": -1} if animated else {}))
    if dst in NO_ALPHA and image.hasalpha():
        image = image.flatten(background=[255, 255, 255])
    save_opts: dict[str, object] = {}
    if dst in ("jpg", "webp", "avif"):
        save_opts["Q"] = options.quality or DEFAULT_QUALITY
    if dst == "avif":
        save_opts["compression"] = "av1"
    if options.strip_metadata:
        if VIPS_KEEP_API:
            save_opts["keep"] = 0  # VipsForeignKeep.NONE
        else:
            save_opts["strip"] = True
    image.write_to_file(str(out), **save_opts)


def _convert_pillow(src_path: Path, out: Path, src: str, dst: str, options: ConversionOptions) -> None:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(src_path)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CorruptInputError("This image appears to be corrupted or unreadable.") from exc
    exif = image.info.get("exif")
    image = ImageOps.exif_transpose(image)
    if options.width or options.height:
        image.thumbnail((options.width or 100_000, options.height or 100_000), Image.Resampling.LANCZOS)
    if dst == "ico":
        image = _square_icon(image)
    if dst in NO_ALPHA:
        image = _flatten(image)
    elif image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        image = image.convert("RGBA")
    save_opts: dict[str, object] = {}
    if dst in ("jpg", "webp", "avif", "heic"):
        save_opts["quality"] = options.quality or DEFAULT_QUALITY
    if dst == "ico":
        save_opts["sizes"] = [(s, s) for s in ICO_SIZES if s <= max(image.size)] or [image.size]
    if exif and not options.strip_metadata and dst in ("jpg", "webp", "png", "tiff", "heic", "avif"):
        save_opts["exif"] = exif
    try:
        image.save(out, PILLOW_FORMAT[dst], **save_opts)
    except (OSError, KeyError, ValueError) as exc:
        raise ConversionError(f"Could not write {dst.upper()} image.") from exc


def _square_icon(image: PILImage) -> PILImage:
    """Fit into at most 256×256 and pad to a transparent square, as icons expect."""
    from PIL import Image

    image = image.convert("RGBA")
    image.thumbnail((ICO_MAX, ICO_MAX), Image.Resampling.LANCZOS)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def _flatten(image: PILImage) -> PILImage:
    from PIL import Image

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")
