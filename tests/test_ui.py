"""GUI checks run under a display (Linux CI uses xvfb-run)."""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from multipost.ui import MainWindow, SECTIONS, parse_schedule


def test_schedule_converts_explicit_offset_to_utc():
    future = datetime.now(timezone(timedelta(hours=-4))) + timedelta(days=1)
    result = datetime.fromisoformat(parse_schedule(future.isoformat()))
    assert result.utcoffset() == timedelta(0)
    assert result == future


@pytest.mark.parametrize("text", ["not-a-date", "2020-01-01 12:00"])
def test_schedule_rejects_invalid_or_past_dates(text):
    with pytest.raises(ValueError):
        parse_schedule(text)


def test_blank_schedule_means_immediate():
    assert parse_schedule("  ") is None


@pytest.mark.skipif(sys.platform == "linux" and not os.environ.get("DISPLAY"), reason="GUI requires Xvfb/display")
def test_desktop_navigation_draft_and_threaded_publish(tmp_path, monkeypatch):
    from multipost.service import AppService

    video_path = tmp_path / "vídeo de teste.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x284:d=0.3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path),
    ], check=True, timeout=30)
    service = AppService(tmp_path / "data")
    video = service.import_video(video_path)
    # Merely visiting Accounts must not make synchronous network requests.
    monkeypatch.setattr(service.youtube, "account", lambda: pytest.fail("unexpected network check"))
    monkeypatch.setattr("multipost.ui.messagebox.askyesno", lambda *args, **kwargs: True)
    window = MainWindow(service)
    callback_errors = []
    window.report_callback_exception = lambda *args: callback_errors.append(args)
    try:
        for section in SECTIONS:
            window.show(section)
            window.update_idletasks()
            assert window._heading.cget("text") == section
            assert window._last_render_error is None
        window._selected_video = video["id"]
        window.show("Nova publicação")
        window._title_var.set("Uma publicação real")
        window._caption.insert("1.0", "Legenda geral #teste")
        for platform, var in window._platform_vars.items():
            var.set(platform == "instagram")
        window._override_vars["instagram"].set(True)
        window._override_boxes["instagram"].insert("1.0", "Legenda Instagram")
        window._save_editor()
        saved = service.load_draft()
        assert saved["overrides"]["instagram"] == "Legenda Instagram"
        assert saved["caption"] == "Legenda geral #teste"
        converted_path = tmp_path / "vídeo convertido.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x284:d=0.3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(converted_path),
        ], check=True, timeout=30)
        converted = service.import_video(converted_path)
        monkeypatch.setattr(service, "prepare_video", lambda *args, **kwargs: converted)
        window._convert("fit")
        deadline = time.monotonic() + 5
        while window._selected_video != converted["id"] and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        assert window._selected_video == converted["id"]
        assert service.load_draft()["caption"] == "Legenda geral #teste"
        # Importing while the editor is open must also select the new result.
        monkeypatch.setattr("multipost.ui.filedialog.askopenfilenames", lambda **kwargs: (str(video_path),))
        window._import()
        deadline = time.monotonic() + 5
        while window._selected_video != video["id"] and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        assert window._selected_video == video["id"]
        window._save_editor()
        assert service.load_draft()["video_id"] == video["id"]
        window._create_jobs()
        deadline = time.monotonic() + 5
        while not service.jobs() and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        jobs = service.jobs()
        assert len(jobs) == 1
        assert jobs[0]["platform"] == "instagram"
        assert jobs[0]["caption"] == "Legenda Instagram"
        assert jobs[0]["status"] != "PUBLISHED"
        deadline = time.monotonic() + 8
        while service.job(jobs[0]["id"])["status"] != "WAITING_USER" and time.monotonic() < deadline:
            service.tick()
            window.update()
            time.sleep(0.01)
        window.show("Fila de publicações")
        window.update_idletasks()
        assert service.job(jobs[0]["id"])["status"] == "WAITING_USER"
        assert callback_errors == []
    finally:
        window._close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                if not window.winfo_exists():
                    break
                window.update()
            except Exception:
                break
            time.sleep(0.01)
