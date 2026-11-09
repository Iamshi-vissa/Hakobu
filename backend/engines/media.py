"""Audio and video via FFmpeg.

* Streams whose codec the target container already supports are stream-copied
  (``-c copy``); only incompatible streams are re-encoded.
* H.264 uses a hardware encoder when one is usable (NVENC / Quick Sync / VAAPI),
  probed once; otherwise libx264 with ``-preset veryfast``.
* Progress comes from ``-progress pipe:1`` against the probed duration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from engines.base import (
    ConversionError,
    ConversionOptions,
    CorruptInputError,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
    run_subprocess,
)

AUDIO = ("mp3", "wav", "aac", "m4a", "ogg", "flac", "opus")
VIDEO = ("mp4", "mov", "mkv", "webm", "avi")
H264_ENV = "HAKOBU_H264_ENCODER"  # set by the worker after probing, inherited by children
PROBE_TIMEOUT = 30

# Codecs each container can hold without re-encoding (None = anything).
VIDEO_CODECS: dict[str, frozenset[str] | None] = {
    "mp4": frozenset({"h264", "hevc", "av1", "mpeg4"}),
    "mov": frozenset({"h264", "hevc", "mpeg4", "prores", "mjpeg"}),
    "mkv": None,
    "webm": frozenset({"vp8", "vp9", "av1"}),
    "avi": frozenset({"mpeg4", "h264", "mjpeg"}),
}
AUDIO_CODECS: dict[str, frozenset[str] | None] = {
    "mp4": frozenset({"aac", "mp3", "alac", "ac3", "opus"}),
    "mov": frozenset({"aac", "mp3", "alac", "ac3", "pcm_s16le"}),
    "mkv": None,
    "webm": frozenset({"opus", "vorbis"}),
    "avi": frozenset({"mp3", "ac3", "pcm_s16le"}),
    "mp3": frozenset({"mp3"}),
    "wav": frozenset({"pcm_s16le", "pcm_s24le", "pcm_f32le"}),
    "aac": frozenset({"aac"}),
    "m4a": frozenset({"aac", "alac"}),
    "ogg": frozenset({"vorbis", "opus"}),
    "flac": frozenset({"flac"}),
    "opus": frozenset({"opus"}),
}
# Encoders used when a stream must be re-encoded.
AUDIO_ENCODER = {
    "mp3": "libmp3lame",
    "wav": "pcm_s16le",
    "aac": "aac",
    "m4a": "aac",
    "ogg": "libvorbis",
    "flac": "flac",
    "opus": "libopus",
    "mp4": "aac",
    "mov": "aac",
    "mkv": "aac",
    "webm": "libopus",
    "avi": "libmp3lame",
}
LOSSLESS_AUDIO = frozenset({"wav", "flac"})
GIF_DEFAULT_WIDTH = 480
GIF_FPS = 12


@dataclass(frozen=True, slots=True)
class Probe:
    duration: float
    video: str | None
    audio: str | None


def probe(path: Path) -> Probe:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            timeout=PROBE_TIMEOUT,
            check=True,
        )
        info = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise CorruptInputError("This media file couldn't be read.") from exc
    streams = info.get("streams", [])

    def first(kind: str) -> str | None:
        for stream in streams:
            # Cover art is a "video" stream inside audio files; ignore it.
            if stream.get("codec_type") == kind and not stream.get("disposition", {}).get("attached_pic"):
                return stream.get("codec_name")
        return None

    try:
        duration = float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    if not streams:
        raise CorruptInputError("This media file has no audio or video.")
    return Probe(duration=duration, video=first("video"), audio=first("audio"))


@dataclass(frozen=True, slots=True)
class VideoEncoder:
    codec: tuple[str, ...]
    quality: tuple[str, ...]
    filters: tuple[str, ...] = ()  # appended after scaling (e.g. GPU upload)
    device: tuple[str, ...] = ()  # global options placed before the input


H264_ENCODERS: dict[str, VideoEncoder] = {
    "libx264": VideoEncoder(("-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"), ("-crf", "23")),
    "h264_nvenc": VideoEncoder(("-c:v", "h264_nvenc", "-preset", "p4"), ("-cq", "23")),
    "h264_qsv": VideoEncoder(("-c:v", "h264_qsv", "-preset", "veryfast"), ("-global_quality", "23")),
    "h264_vaapi": VideoEncoder(
        (
            "-c:v",
            "h264_vaapi",
        ),
        ("-qp", "23"),
        ("format=nv12", "hwupload"),
        ("-vaapi_device", "/dev/dri/renderD128"),
    ),
}
OTHER_ENCODERS: dict[str, VideoEncoder] = {
    "webm": VideoEncoder(
        ("-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1"), ("-crf", "33", "-b:v", "0")
    ),
    "avi": VideoEncoder(("-c:v", "mpeg4"), ("-q:v", "4")),
}


def _encoder_works(encoder: VideoEncoder) -> bool:
    filters = ["-vf", ",".join(encoder.filters)] if encoder.filters else []
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                *encoder.device,
                "-f",
                "lavfi",
                "-i",
                "color=s=256x256:d=0.2",
                "-frames:v",
                "2",
                *filters,
                *encoder.codec,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


@lru_cache
def detect_h264_encoder() -> str:
    """The best working H.264 encoder (probed once per process, or inherited via env)."""
    if cached := os.environ.get(H264_ENV):
        return cached
    if get_settings().ffmpeg_hwaccel != "off":
        for name, encoder in H264_ENCODERS.items():
            if name != "libx264" and _encoder_works(encoder):
                return name
    return "libx264"


def video_encoder(dst: str) -> VideoEncoder:
    return OTHER_ENCODERS.get(dst) or H264_ENCODERS[detect_h264_encoder()]


def _video_encode_args(encoder: VideoEncoder, options: ConversionOptions) -> list[str]:
    quality = ["-b:v", options.bitrate] if options.bitrate else list(encoder.quality)
    # Cap the width if asked; always keep dimensions even (required by 4:2:0 encoders).
    scale = f"scale='min({options.width},iw)':-2" if options.width else "scale='trunc(iw/2)*2':'trunc(ih/2)*2'"
    return [*encoder.codec, *quality, "-vf", ",".join((scale, *encoder.filters))]


def _audio_encode_args(dst: str, options: ConversionOptions) -> list[str]:
    args = ["-c:a", AUDIO_ENCODER[dst]]
    if dst not in LOSSLESS_AUDIO:
        args += ["-b:a", options.bitrate if dst in AUDIO and options.bitrate else "192k"]
    return args


def _compatible(codec: str | None, allowed: frozenset[str] | None) -> bool:
    return codec is not None and (allowed is None or codec in allowed)


def build_command(src_path: Path, out: Path, src: str, dst: str, info: Probe, options: ConversionOptions) -> list[str]:
    """Assemble the FFmpeg argv for one conversion (pure; unit-tested directly)."""
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    encoder = video_encoder(dst) if dst in VIDEO else None
    if encoder:
        args += encoder.device
    trimming = options.trim_start is not None or options.trim_end is not None
    if options.trim_start:
        args += ["-ss", f"{options.trim_start:.3f}"]
    args += ["-i", str(src_path)]
    if options.trim_end is not None:
        args += ["-t", f"{max(options.trim_end - (options.trim_start or 0), 0.001):.3f}"]

    if dst == "gif":
        width = options.width or GIF_DEFAULT_WIDTH
        args += [
            "-an",
            "-vf",
            (
                f"fps={GIF_FPS},scale='min({width},iw)':-2:flags=lanczos,"
                "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
            ),
            "-loop",
            "0",
        ]
    elif dst in AUDIO:
        if info.audio is None:
            raise ConversionError("This file has no audio track to extract.")
        args += ["-vn", "-sn", "-dn", "-map", "0:a:0"]
        reencode = trimming or options.bitrate or options.sample_rate or not _compatible(info.audio, AUDIO_CODECS[dst])
        args += _audio_encode_args(dst, options) if reencode else ["-c:a", "copy"]
        if options.sample_rate:
            args += ["-ar", str(options.sample_rate)]
    else:
        args += ["-sn", "-dn", "-map", "0:v:0?", "-map", "0:a?"]
        changed = trimming or options.width or options.bitrate
        copy_video = not changed and src != "gif" and _compatible(info.video, VIDEO_CODECS[dst])
        args += ["-c:v", "copy"] if copy_video else _video_encode_args(encoder, options)
        if info.audio:
            copy_audio = not trimming and _compatible(info.audio, AUDIO_CODECS[dst])
            args += ["-c:a", "copy"] if copy_audio else _audio_encode_args(dst, options)
        if dst in ("mp4", "mov"):
            args += ["-movflags", "+faststart"]
    return [*args, "-progress", "pipe:1", "-nostats", str(out)]


GIF_TO_VIDEO = ("mp4", "webm", "mov", "mkv")


class MediaEngine(Engine):
    name = "ffmpeg"
    transforms = frozenset((*AUDIO, *VIDEO))
    # Never chain into these: a GIF-turned-video has no audio, an image-turned-GIF isn't footage.
    entry_only_pairs = pairs(("gif",), GIF_TO_VIDEO) | pairs(VIDEO, AUDIO)

    def supported_pairs(self) -> frozenset[Pair]:
        return (
            pairs(AUDIO, AUDIO)
            | pairs(VIDEO, VIDEO)
            | pairs(VIDEO, AUDIO)
            | pairs(VIDEO, ("gif",))
            | pairs(("gif",), GIF_TO_VIDEO)
        )

    def available(self) -> bool:
        return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        src, dst = formats_of(input_path, output_path)
        info = probe(input_path)
        start = options.trim_start or 0.0
        end = min(options.trim_end, info.duration) if options.trim_end and info.duration else info.duration
        if options.trim_end is not None and options.trim_end <= start:
            raise ConversionError("Trim end must be after trim start.")
        span = max(end - start, 0.0)

        def on_line(line: str) -> None:
            key, _, value = line.partition("=")
            if progress and span and key == "out_time_us" and value.isdigit():
                progress(min(int(value) / 1_000_000 / span, 1.0))

        run_subprocess(build_command(input_path, output_path, src, dst, info, options), on_line=on_line)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ConversionError("FFmpeg produced an empty file.")
        return [output_path]
