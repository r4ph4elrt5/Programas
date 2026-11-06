"""Local video inspection and conversion; originals are always read-only."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass
from typing import Callable


class MediaError(RuntimeError):
    """An invalid video, unavailable tool, or failed media operation."""


class MediaCancelled(MediaError):
    """The user cancelled processing; no output was published."""


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    size: int
    sha256: str
    thumbnail: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise MediaError(f"{name} não encontrado. Instale FFmpeg e adicione-o ao PATH.")
    return resolved


def _run(args: list[str], timeout: int = 60) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("Não foi possível executar a ferramenta de vídeo.") from exc
    if result.returncode:
        raise MediaError("Arquivo inválido ou processamento de vídeo rejeitado pelo FFmpeg.")
    return result.stdout


def _positive_number(value: object) -> float:
    try:
        number = float(str(value))
    except (ValueError, TypeError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


class MediaService:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def probe(self, path: str | Path) -> VideoInfo:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise MediaError("Vídeo não encontrado. Localize novamente o arquivo.")
        raw = _run([
            _tool("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe", "-print_format", "json",
            "-show_format", "-show_streams", str(source),
        ])
        try:
            data = json.loads(raw)
            streams = data.get("streams", [])
            video = next(s for s in streams if s.get("codec_type") == "video"
                         and not s.get("disposition", {}).get("attached_pic"))
            audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
            width, height = int(video["width"]), int(video["height"])
            duration = _positive_number(data.get("format", {}).get("duration"))
            if not duration:
                duration = _positive_number(video.get("duration"))
            numerator, denominator = video.get("avg_frame_rate", "0/1").split("/")
            fps = _positive_number(numerator) / (_positive_number(denominator) or 1)
            rotation = video.get("tags", {}).get("rotate", 0)
            for item in video.get("side_data_list", []):
                if "rotation" in item:
                    rotation = item["rotation"]
            if int(float(rotation)) % 180:
                width, height = height, width
            if duration <= 0 or width <= 0 or height <= 0:
                raise ValueError("Missing video dimensions/duration")
        except (ValueError, TypeError, KeyError, StopIteration, AttributeError) as exc:
            raise MediaError("O arquivo não contém um vídeo válido com duração conhecida.") from exc
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        checksum = digest.hexdigest()
        thumbnail = self.thumbnail(source, checksum)
        return VideoInfo(
            str(source), duration, width, height, fps, video.get("codec_name", "unknown"),
            audio.get("codec_name"), source.stat().st_size, checksum, str(thumbnail),
        )

    def thumbnail(self, path: str | Path, checksum: str) -> Path:
        # Only a digest may become a cache filename; no external path fragments.
        if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise MediaError("Identificador de cache inválido.")
        target = self.cache_dir / f"{checksum}.jpg"
        if target.is_file():
            return target
        descriptor, temporary = tempfile.mkstemp(suffix=".jpg", dir=self.cache_dir)
        os.close(descriptor)
        temp = Path(temporary)
        try:
            _run([
                _tool("ffmpeg"), "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i",
                str(Path(path).resolve()), "-frames:v", "1", "-vf", "scale=320:-2",
                str(temp),
            ])
            os.replace(temp, target)
            return target
        finally:
            temp.unlink(missing_ok=True)

    def convert(
        self, path: str | Path, output: str | Path, mode: str = "fit",
        cancel: threading.Event | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Path:
        if mode not in {"fit", "crop"}:
            raise MediaError("Modo inválido. Escolha fit (margens) ou crop (corte central).")
        cancel = cancel if cancel is not None else threading.Event()
        if cancel.is_set():
            raise MediaCancelled("Conversão cancelada.")
        source, target = Path(path).resolve(), Path(output).resolve()
        if source == target or target.exists():
            raise MediaError("O destino já existe. O vídeo original nunca será sobrescrito.")
        if target.suffix.lower() != ".mp4":
            raise MediaError("A versão preparada deve usar extensão .mp4.")
        info = self.probe(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(suffix=".mp4", dir=target.parent)
        os.close(descriptor)
        temp = Path(temporary)
        if mode == "fit":
            sizing = (
                "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            )
        else:
            sizing = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        args = [
            _tool("ffmpeg"), "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?", "-vf", sizing + ",setsar=1",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "2",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags",
            "+faststart", "-progress", "pipe:1", str(temp),
        ]
        process = None
        events: queue.Queue[str | None] = queue.Queue()
        try:
            with tempfile.TemporaryFile(mode="w+b") as errors:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, text=True)

                def read_progress() -> None:
                    assert process is not None and process.stdout is not None
                    for line in process.stdout:
                        events.put(line.strip())
                    events.put(None)

                reader = threading.Thread(target=read_progress, daemon=True)
                reader.start()
                while True:
                    if cancel.is_set():
                        raise MediaCancelled("Conversão cancelada.")
                    try:
                        line = events.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    if line.startswith("out_time_us=") and progress:
                        elapsed = _positive_number(line.split("=", 1)[1]) / 1_000_000
                        progress(min(0.99, elapsed / info.duration))
                if process.wait() != 0:
                    raise MediaError("FFmpeg não conseguiu preparar o vídeo. Verifique o arquivo e o espaço livre.")
                if cancel.is_set():
                    raise MediaCancelled("Conversão cancelada.")
                # Exclusive creation prevents a racing operation from replacing a user file.
                try:
                    os.link(temp, target)
                except FileExistsError as exc:
                    raise MediaError("O destino foi criado durante o processamento; escolha outro nome.") from exc
                if progress:
                    progress(1.0)
                return target
        except OSError as exc:
            raise MediaError("Falha ao gravar o vídeo preparado. Verifique permissões e espaço livre.") from exc
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout:
                    process.stdout.close()
            temp.unlink(missing_ok=True)


def validate_short(info: VideoInfo) -> list[str]:
    """Recommendations only: each destination remains the authority on eligibility."""
    warnings = []
    if info.width >= info.height:
        warnings.append("Vídeo horizontal ou quadrado: confira a prévia e o enquadramento vertical.")
    if info.duration > 180:
        warnings.append("Mais de 3 minutos: confira os limites atuais de cada plataforma e do YouTube Shorts.")
    if info.video_codec != "h264" or info.audio_codec not in {"aac", None}:
        warnings.append("Considere preparar uma cópia MP4 com H.264/AAC para maior compatibilidade.")
    if min(info.width, info.height) < 720:
        warnings.append("Resolução baixa: converter não recupera detalhes ausentes do original.")
    return warnings
