"""Real SQLite/media integration with an explicit fake remote YouTube boundary."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading

import pytest

from multipost.service import AppService
from multipost.youtube import AuthRequired, UploadCancelled, UploadUncertain


class FakeYoutube:
    def __init__(self):
        self.uploads = []
        self.checks = []

    def upload(self, path, metadata, cancel, progress):
        self.uploads.append((path, dict(metadata)))
        progress(0.5)
        return {"remote_id": "video123", "url": "https://www.youtube.com/watch?v=video123"}

    def check_status(self, remote_id):
        self.checks.append(remote_id)
        return {"status": "PUBLISHED", "url": f"https://www.youtube.com/watch?v={remote_id}"}


@pytest.fixture
def video_path(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real media integration requires FFmpeg and ffprobe")
    source = tmp_path / "história curta.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=90x160:r=10", "-t", "0.4", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(source),
    ], check=True)
    return source


@pytest.fixture
def app(tmp_path):
    service = AppService(tmp_path / "app", youtube=FakeYoutube())
    yield service
    service.close()


def create(app, video_path, platforms=("instagram",), **kwargs):
    video = app.import_video(video_path)
    return app.create_publication(
        video["id"], "Uma história", "Legenda #história", list(platforms), **kwargs,
    )


def test_video_to_five_destinations_preserves_confirmation_source(app, video_path):
    platforms = ["youtube", "instagram", "facebook", "tiktok", "kwai"]
    identities = create(app, video_path, platforms, made_for_kids=False, privacy="public",
                        overrides={"tiktok": "Legenda TikTok"})
    assert len(identities) == 5
    assert len(set(identities)) == 5
    assert len({job["project_id"] for job in app.jobs()}) == 1
    for _ in range(10):
        app.tick()
    by_platform = {job["platform"]: job for job in app.jobs()}
    youtube = by_platform["youtube"]
    assert youtube["status"] == "PUBLISHED"
    assert youtube["confirmation"] == "API"
    assert youtube["remote_id"] == "video123"
    assert len(app.youtube.uploads) == 1
    assert app.youtube.uploads[0][1]["made_for_kids"] is False
    for platform in platforms[1:]:
        job = by_platform[platform]
        assert job["status"] == "WAITING_USER"
        assert job["confirmation"] is None
        package = Path(job["export_dir"])
        assert (package / "video.mp4").read_bytes() == video_path.read_bytes()
        expected = "Legenda TikTok" if platform == "tiktok" else "Legenda #história"
        assert (package / "legenda.txt").read_text(encoding="utf-8") == expected
        assert (package / "INSTRUCOES.txt").is_file()
        app.confirm_manual(job["id"], f"https://www.{platform}.com/post/123")
        confirmed = app.job(job["id"])
        assert confirmed["status"] == "USER_CONFIRMED"
        assert confirmed["confirmation"] == "USER"
        assert confirmed["completed_at"]
    assert app.stats()["completed"] == 5
    assert len(app.db.rows("SELECT * FROM attempts")) == 5


def test_duplicate_import_and_publication_are_idempotent(app, video_path):
    first = create(app, video_path, ("instagram", "facebook"))
    second = create(app, video_path, ("instagram", "facebook", "instagram"))
    assert second == first
    assert len(app.videos()) == 1
    assert len(app.jobs()) == 2
    app.tick()
    app.tick()
    app.tick()
    assert all(job["status"] == "WAITING_USER" for job in app.jobs())
    assert all(job["attempts"] == 1 for job in app.jobs())
    assert len(app.db.rows("SELECT * FROM attempts")) == 2


def test_scheduling_persists_and_missed_schedule_requires_explicit_retry(app, video_path):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    identity = create(app, video_path, scheduled_at=future)[0]
    app.tick()
    assert app.job(identity)["status"] == "SCHEDULED"
    assert app.job(identity)["attempts"] == 0
    app.save_draft({"caption": "Rascunho persistido"})
    app.save_settings({"theme": "light"})
    app.close()
    reopened = AppService(app.data_dir, youtube=FakeYoutube())
    try:
        assert reopened.job(identity)["scheduled_at"] == future
        assert reopened.settings()["theme"] == "light"
        assert reopened.load_draft()["caption"] == "Rascunho persistido"
        expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        reopened._update(identity, scheduled_at=expired)
    finally:
        reopened.close()
    recovered = AppService(app.data_dir, youtube=FakeYoutube())
    try:
        assert recovered.job(identity)["status"] == "MISSED_SCHEDULE"
        recovered.tick()
        assert recovered.job(identity)["attempts"] == 0
        recovered.retry(identity)
        recovered.tick()
        assert recovered.job(identity)["status"] == "WAITING_USER"
    finally:
        recovered.close()


def test_interrupted_upload_is_not_automatically_retried(app, video_path):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    app._update(identity, status="UPLOADING")
    app.close()
    reopened = AppService(app.data_dir, youtube=FakeYoutube())
    try:
        assert reopened.job(identity)["status"] == "UNKNOWN_REMOTE_STATUS"
        reopened.tick()
        assert reopened.youtube.uploads == []
        with pytest.raises(ValueError, match="Reenvio bloqueado"):
            reopened.retry(identity)
        with pytest.raises(ValueError, match="YouTube Studio"):
            reopened.reconcile(identity)
        reopened.reconcile(identity, remote_id="video123")
        assert reopened.job(identity)["confirmation"] == "API"
        assert reopened.youtube.uploads == []
    finally:
        reopened.close()


def test_cancelling_pending_job_prevents_export(app, video_path):
    identity = create(app, video_path)[0]
    app.cancel(identity)
    app.tick()
    job = app.job(identity)
    assert job["status"] == "CANCELLED"
    assert job["export_dir"] is None
    assert job["attempts"] == 0
    with pytest.raises(ValueError):
        app.retry(identity)
    with pytest.raises(ValueError):
        app.confirm_manual(identity)


def test_cancelling_active_upload_preserves_unknown_remote_state(app, video_path):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    started = threading.Event()

    def upload(path, metadata, cancel, progress):
        started.set()
        if not cancel.wait(timeout=5):
            raise AssertionError("Test never cancelled active upload")
        raise UploadUncertain("Interrupted after remote upload started")

    app.youtube.upload = upload
    thread = threading.Thread(target=app.tick)
    thread.start()
    try:
        assert started.wait(timeout=5)
        app.cancel(identity)
    finally:
        thread.join(timeout=6)
    assert not thread.is_alive()
    assert app.job(identity)["status"] == "UNKNOWN_REMOTE_STATUS"
    with pytest.raises(ValueError):
        app.retry(identity)


@pytest.mark.parametrize("error, expected", [
    (AuthRequired("Reconnect"), "AUTH_REQUIRED"),
    (UploadUncertain("No acknowledgement"), "UNKNOWN_REMOTE_STATUS"),
])
def test_remote_failure_classification_does_not_claim_success(app, video_path, error, expected):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]

    def upload(*args):
        raise error

    app.youtube.upload = upload
    app.tick()
    job = app.job(identity)
    assert job["status"] == expected
    assert job["confirmation"] is None
    app.tick()
    assert app.job(identity)["attempts"] == 1


def test_two_instances_cannot_steal_jobs_and_lock_releases(app):
    with pytest.raises(RuntimeError, match="já está aberto"):
        AppService(app.data_dir, youtube=FakeYoutube())
    app.close()
    other = AppService(app.data_dir, youtube=FakeYoutube())
    other.close()


def test_source_changed_after_import_fails_before_remote_side_effect(app, video_path):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    with video_path.open("ab") as handle:
        handle.write(b"changed since reviewed")
    app.tick()
    assert app.job(identity)["status"] == "FAILED"
    assert "conteúdo do vídeo mudou" in app.job(identity)["error"]
    assert app.youtube.uploads == []


def test_backup_is_consistent_and_never_overwrites(app, video_path, tmp_path):
    identity = create(app, video_path)[0]
    destination = tmp_path / "backup.sqlite3"
    app.db.backup(destination)
    with sqlite3.connect(destination) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT id FROM jobs").fetchone() == (identity,)
        assert connection.execute("SELECT COUNT(*) FROM videos").fetchone() == (1,)
    with pytest.raises(ValueError):
        app.db.backup(destination)
    with pytest.raises(ValueError):
        app.db.backup(app.db.path)


@pytest.mark.parametrize("url", [
    "http://www.instagram.com/post/1", "https://instagram.com.evil.example/1",
    "javascript:alert(1)", "https://www.tiktok.com/1", "file:///etc/passwd",
])
def test_manual_confirmation_rejects_wrong_or_unsafe_platform_urls(app, video_path, url):
    identity = create(app, video_path)[0]
    app.tick()
    with pytest.raises(ValueError, match="link HTTPS"):
        app.confirm_manual(identity, url)
    assert app.job(identity)["status"] == "WAITING_USER"
    assert app.job(identity)["confirmation"] is None


def test_invalid_publication_rolls_back_all_destination_jobs(app, video_path):
    video = app.import_video(video_path)
    with pytest.raises(ValueError, match="crianças"):
        app.create_publication(video["id"], "Title", "caption", ["instagram", "youtube"])
    with pytest.raises(ValueError, match="5.000"):
        app.create_publication(video["id"], "Title", "caption", ["instagram", "youtube"],
                               made_for_kids=False, overrides={"youtube": "é" * 2501})
    assert app.jobs() == []
    assert app.db.rows("SELECT * FROM projects") == []
    assert app.db.rows("SELECT * FROM audit_events") == []


def test_pause_blocks_claiming_without_losing_ready_jobs(app, video_path):
    identity = create(app, video_path)[0]
    app.save_settings({"paused": True})
    app.tick()
    assert app.job(identity)["status"] == "READY"
    assert app.job(identity)["attempts"] == 0
    app.save_settings({"paused": False})
    app.tick()
    assert app.job(identity)["status"] == "WAITING_USER"


def test_cancel_after_export_before_completion_is_not_lost(app, video_path, monkeypatch):
    identity = create(app, video_path)[0]
    prepared = threading.Event()
    release = threading.Event()
    export = app._export

    def delayed_export(*args):
        result = export(*args)
        prepared.set()
        assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(app, "_export", delayed_export)
    worker = threading.Thread(target=app.tick)
    worker.start()
    try:
        assert prepared.wait(timeout=5)
        app.cancel(identity)
    finally:
        release.set()
        worker.join(timeout=6)
    assert not worker.is_alive()
    assert app.job(identity)["status"] == "CANCELLED"
    assert app.job(identity)["export_dir"] is None
    # A completed shared file can safely remain cached; cancellation must not
    # destroy artifacts referenced by other platform jobs.
    media_files = list((app.data_dir / "exports" / "media").glob("*.mp4"))
    assert len(media_files) == 1
    assert media_files[0].read_bytes() == video_path.read_bytes()


def test_cancel_during_claim_waits_for_event_registration(app, video_path, monkeypatch):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    registration_started = threading.Event()
    release_registration = threading.Event()
    cancel_finished = threading.Event()
    original_probe = app.media.probe

    class GatedEvents(dict):
        def __setitem__(self, key, value):
            registration_started.set()
            assert release_registration.wait(timeout=5)
            super().__setitem__(key, value)

    def probe_after_cancel(path):
        assert cancel_finished.wait(timeout=5)
        return original_probe(path)

    def cancel():
        app.cancel(identity)
        cancel_finished.set()

    app._cancel_events = GatedEvents()
    monkeypatch.setattr(app.media, "probe", probe_after_cancel)
    worker = threading.Thread(target=app.tick)
    worker.start()
    cancellation = threading.Thread(target=cancel)
    try:
        assert registration_started.wait(timeout=5)
        cancellation.start()
        assert not cancel_finished.wait(timeout=0.1)
    finally:
        release_registration.set()
        cancellation.join(timeout=6)
        worker.join(timeout=6)
    assert not worker.is_alive()
    assert not cancellation.is_alive()
    assert app.job(identity)["status"] == "CANCELLED"
    assert app.youtube.uploads == []


def test_cancel_mid_copy_cleans_partial_and_preserves_original(app, tmp_path, monkeypatch):
    source = tmp_path / "large.mp4"
    original = b"a" * (2 * 1024 * 1024)
    source.write_bytes(original)
    target = tmp_path / "copy.mp4"
    stop = threading.Event()
    checks = iter([False, True])
    monkeypatch.setattr(stop, "is_set", lambda: next(checks, True))
    with pytest.raises(UploadCancelled):
        app._copy_media(source, target, stop)
    assert not target.exists()
    assert list(tmp_path.glob("*.partial")) == []
    assert source.read_bytes() == original


def test_rescheduling_cannot_overwrite_concurrently_claimed_upload(app, video_path, monkeypatch):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    schedule_read = threading.Event()
    release_schedule = threading.Event()
    tick_finished = threading.Event()
    original_job = app.job
    errors = []

    def gated_job(job_id):
        result = original_job(job_id)
        if threading.current_thread() is scheduler:
            schedule_read.set()
            assert release_schedule.wait(timeout=5)
        return result

    def schedule():
        try:
            app.reschedule(identity, future)
        except Exception as error:
            errors.append(error)

    def tick():
        try:
            app.tick()
        finally:
            tick_finished.set()

    monkeypatch.setattr(app, "job", gated_job)
    scheduler = threading.Thread(target=schedule)
    worker = threading.Thread(target=tick)
    scheduler.start()
    try:
        assert schedule_read.wait(timeout=5)
        worker.start()
        assert not tick_finished.wait(timeout=0.1)
    finally:
        release_schedule.set()
        scheduler.join(timeout=6)
        worker.join(timeout=6)
    assert not scheduler.is_alive()
    assert not worker.is_alive()
    assert not errors
    assert app.job(identity)["status"] == "SCHEDULED"
    assert app.job(identity)["attempts"] == 0
    assert app.youtube.uploads == []


def test_concurrent_retries_cannot_reset_an_already_retried_job(app, video_path, monkeypatch):
    identity = create(app, video_path, ("youtube",), made_for_kids=False)[0]
    app._update(identity, status="FAILED")
    retry_read = threading.Event()
    release_retry = threading.Event()
    second_finished = threading.Event()
    original_job = app.job
    first_errors = []
    second_errors = []

    def gated_job(job_id):
        result = original_job(job_id)
        if threading.current_thread() is first:
            retry_read.set()
            assert release_retry.wait(timeout=5)
        return result

    def retry(errors, done=None):
        try:
            app.retry(identity)
        except Exception as error:
            errors.append(error)
        finally:
            if done:
                done.set()

    monkeypatch.setattr(app, "job", gated_job)
    first = threading.Thread(target=retry, args=(first_errors,))
    second = threading.Thread(target=retry, args=(second_errors, second_finished))
    first.start()
    try:
        assert retry_read.wait(timeout=5)
        second.start()
        assert not second_finished.wait(timeout=0.1)
    finally:
        release_retry.set()
        first.join(timeout=6)
        second.join(timeout=6)
    assert not first.is_alive()
    assert not second.is_alive()
    assert not first_errors
    assert len(second_errors) == 1
    assert isinstance(second_errors[0], ValueError)
    assert app.job(identity)["status"] == "READY"
    app.tick()
    assert len(app.youtube.uploads) == 1
    assert app.job(identity)["status"] == "PROCESSING"
