import sqlite3
from unittest.mock import MagicMock

import pytest

from multipost.media import VideoInfo
from multipost.service import AppService
from multipost.youtube import UploadUncertain, YoutubeError


@pytest.fixture
def service(tmp_path):
    source = tmp_path / "vídeo.mp4"
    source.write_bytes(b"mock media for queue-only tests")
    app = AppService(tmp_path / "data", youtube=MagicMock())
    app.media.probe = MagicMock(return_value=VideoInfo(
        str(source), 5, 1080, 1920, 30, "h264", "aac", source.stat().st_size, "abc123",
    ))
    video = app.import_video(source)
    yield app, video
    app.close()


def create(app, video, platforms):
    return app.create_publication(video["id"], "Título", "Legenda", platforms, made_for_kids=False)


def test_youtube_invalid_metadata_is_rejected_before_queue_creation(service):
    app, video = service
    with pytest.raises(ValueError, match="YouTube"):
        app.create_publication(video["id"], "<Título>", "Legenda", ["youtube"], made_for_kids=False)
    assert app.jobs() == []
    app.youtube.upload.assert_not_called()


def test_processing_youtube_does_not_starve_other_destinations(service):
    app, video = service
    youtube, instagram = create(app, video, ["youtube", "instagram"])
    app._update(youtube, status="PROCESSING", remote_id="remote123")
    app.youtube.check_status.return_value = {"status": "PROCESSING", "url": "https://www.youtube.com/watch?v=remote123"}
    app.tick()
    assert app.job(instagram)["status"] == "WAITING_USER"
    assert app.job(youtube)["status"] == "PROCESSING"
    app.youtube.upload.assert_not_called()


def test_failed_status_read_preserves_remote_state_and_advances_export(service):
    app, video = service
    youtube, instagram = create(app, video, ["youtube", "instagram"])
    app._update(youtube, status="PROCESSING", remote_id="remote123")
    app.youtube.check_status.side_effect = YoutubeError("Unavailable")
    app.tick()
    assert app.job(youtube)["status"] == "PROCESSING"
    assert app.job(youtube)["remote_id"] == "remote123"
    assert app.job(instagram)["status"] == "WAITING_USER"
    with pytest.raises(ValueError, match="bloqueado"):
        app.retry(youtube)


def test_persistence_failure_after_remote_success_never_enables_retry(service, monkeypatch):
    app, video = service
    identity, = create(app, video, ["youtube"])
    app.youtube.upload.return_value = {
        "status": "PROCESSING", "remote_id": "ack123", "url": "https://www.youtube.com/watch?v=ack123",
    }
    original_update = app._update

    def intermittent_database_failure(identity, **fields):
        if fields.get("status") == "PROCESSING":
            raise sqlite3.OperationalError("database is locked")
        return original_update(identity, **fields)

    monkeypatch.setattr(app, "_update", intermittent_database_failure)
    app.tick()
    result = app.job(identity)
    assert result["status"] == "UNKNOWN_REMOTE_STATUS"
    assert result["remote_id"] == "ack123"
    with pytest.raises(ValueError, match="bloqueado"):
        app.retry(identity)
    app.tick()
    app.youtube.upload.assert_called_once()


def test_ambiguous_remote_result_never_retries(service):
    app, video = service
    identity, = create(app, video, ["youtube"])
    app.youtube.upload.side_effect = UploadUncertain("Network interrupted")
    app.tick()
    app.tick()
    assert app.job(identity)["status"] == "UNKNOWN_REMOTE_STATUS"
    app.youtube.upload.assert_called_once()


def test_processing_checks_are_round_robin(service):
    app, video = service
    first, = create(app, video, ["youtube"])
    second, = app.create_publication(video["id"], "Segundo", "Outra legenda", ["youtube"], made_for_kids=False)
    for identity in (first, second):
        app._update(identity, status="PROCESSING", remote_id=identity)
    app.youtube.check_status.side_effect = lambda remote: {"status": "PROCESSING"}
    app.tick()
    app.tick()
    assert {call.args[0] for call in app.youtube.check_status.call_args_list} == {first, second}


def test_private_video_can_be_reconciled_after_remote_publication(service):
    app, video = service
    identity, = create(app, video, ["youtube"])
    app._update(identity, status="UPLOADED_PRIVATE", remote_id="known")
    app.youtube.check_status.return_value = {"status": "PUBLISHED"}
    app.reconcile(identity)
    assert app.job(identity)["status"] == "PUBLISHED"
    assert app.job(identity)["confirmation"] == "API"
