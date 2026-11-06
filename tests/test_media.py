import hashlib
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from multipost.media import MediaCancelled, MediaError, MediaService, validate_short


@pytest.fixture
def sample(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for integration test")
    path = tmp_path / "vídeo espaço.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "color=c=blue:s=160x90:r=10", "-t", "0.5", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


def test_real_probe_thumbnail_and_validation(sample, tmp_path):
    info = MediaService(tmp_path / "cache").probe(sample)
    assert (info.width, info.height) == (160, 90)
    assert info.duration == pytest.approx(0.5, abs=0.1)
    assert info.fps == pytest.approx(10)
    assert info.video_codec == "h264"
    assert info.sha256 == hashlib.sha256(sample.read_bytes()).hexdigest()
    assert Path(info.thumbnail).stat().st_size > 0
    assert info.as_dict()["path"] == str(sample)
    assert validate_short(info)


def test_conversion_real_does_not_change_original(sample, tmp_path):
    service = MediaService(tmp_path / "cache")
    original_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    updates = []
    output = service.convert(sample, tmp_path / "saída.mp4", progress=updates.append)
    result = service.probe(output)
    assert (result.width, result.height) == (1080, 1920)
    assert result.video_codec == "h264"
    assert updates[-1] == 1
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == original_hash
    with pytest.raises(MediaError, match="destino já existe"):
        service.convert(sample, output)
    with pytest.raises(MediaError, match="destino já existe"):
        service.convert(sample, sample)


def test_cancel_before_processing(sample, tmp_path):
    stop = threading.Event()
    stop.set()
    output = tmp_path / "cancelled.mp4"
    with pytest.raises(MediaCancelled):
        MediaService(tmp_path / "cache").convert(sample, output, cancel=stop)
    assert not output.exists()


def test_cancel_during_processing_cleans_partial_output(sample, tmp_path):
    stop = threading.Event()
    output = tmp_path / "cancelled.mp4"
    service = MediaService(tmp_path / "cache")
    with pytest.raises(MediaCancelled):
        service.convert(sample, output, cancel=stop, progress=lambda _: stop.set())
    assert not output.exists()
    assert sorted(p.name for p in tmp_path.glob("*.mp4")) == [sample.name]


def test_invalid_missing_file_and_invalid_video(tmp_path):
    service = MediaService(tmp_path / "cache")
    with pytest.raises(MediaError, match="não encontrado"):
        service.probe(tmp_path / "missing.mp4")
    invalid = tmp_path / "bad.mp4"
    invalid.write_bytes(b"not a video")
    with pytest.raises(MediaError):
        service.probe(invalid)


def test_invalid_mode_and_cache_identifier(tmp_path):
    service = MediaService(tmp_path / "cache")
    with pytest.raises(MediaError):
        service.convert("source", "output.mp4", mode="stretch")
    with pytest.raises(MediaError):
        service.thumbnail("source", "../../outside")
