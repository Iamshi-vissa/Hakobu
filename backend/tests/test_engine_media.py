from __future__ import annotations

import subprocess

import pytest

from engines.base import ConversionError, ConversionOptions
from engines.media import MediaEngine, Probe, build_command
from tests.conftest import convert, detected, requires

pytestmark = requires("ffmpeg", "ffprobe")
ENGINE = MediaEngine()


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


@pytest.mark.parametrize("dst", ["mp3", "ogg", "opus", "flac", "aac", "m4a"])
def test_audio_targets(samples, tmp_path, dst: str) -> None:
    [out] = convert(ENGINE, samples.get("wav"), dst, tmp_path)
    assert detected(out) == dst


@pytest.mark.parametrize("dst", ["mov", "mkv", "webm", "avi", "gif", "mp3", "wav"])
def test_video_targets(samples, tmp_path, dst: str) -> None:
    [out] = convert(ENGINE, samples.get("mp4"), dst, tmp_path)
    assert detected(out) == dst


def test_trim_and_progress(samples, tmp_path) -> None:
    seen: list[float] = []
    out = tmp_path / "out.mp3"
    ENGINE.convert(samples.get("wav"), out, ConversionOptions(trim_start=0.5, trim_end=1.5, bitrate="96k"),
                   progress=seen.append)
    assert 0.9 < _duration(out) < 1.2
    assert seen and max(seen) <= 1.0


def test_trim_end_before_start_is_rejected(samples, tmp_path) -> None:
    with pytest.raises(ConversionError):
        convert(ENGINE, samples.get("wav"), "mp3", tmp_path, trim_start=1.5, trim_end=1.0)


def test_container_change_uses_stream_copy(tmp_path) -> None:
    info = Probe(duration=2, video="h264", audio="aac")
    argv = build_command(tmp_path / "in.mp4", tmp_path / "out.mkv", "mp4", "mkv", info, ConversionOptions())
    assert argv[argv.index("-c:v") + 1] == "copy" and argv[argv.index("-c:a") + 1] == "copy"


def test_incompatible_streams_are_reencoded(tmp_path) -> None:
    info = Probe(duration=2, video="h264", audio="aac")
    argv = build_command(tmp_path / "in.mp4", tmp_path / "out.webm", "mp4", "webm", info, ConversionOptions())
    assert argv[argv.index("-c:v") + 1] == "libvpx-vp9" and argv[argv.index("-c:a") + 1] == "libopus"


def test_h264_uses_veryfast_preset(tmp_path) -> None:
    info = Probe(duration=2, video="vp9", audio="opus")
    argv = build_command(tmp_path / "in.webm", tmp_path / "out.mp4", "webm", "mp4", info, ConversionOptions())
    assert "libx264" in argv and argv[argv.index("-preset") + 1] == "veryfast"


def test_audio_extraction_copies_compatible_audio(tmp_path) -> None:
    info = Probe(duration=2, video="h264", audio="aac")
    argv = build_command(tmp_path / "in.mp4", tmp_path / "out.m4a", "mp4", "m4a", info, ConversionOptions())
    assert "-vn" in argv and argv[argv.index("-c:a") + 1] == "copy"


def test_video_without_audio_cannot_become_audio(tmp_path) -> None:
    with pytest.raises(ConversionError):
        build_command(tmp_path / "a.mp4", tmp_path / "a.mp3", "mp4", "mp3", Probe(2, "h264", None), ConversionOptions())
