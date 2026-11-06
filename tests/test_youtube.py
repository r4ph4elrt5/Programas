from threading import Event
from unittest.mock import MagicMock

import pytest

from multipost.youtube import (
    AuthRequired, CredentialStore, UploadCancelled, UploadUncertain, YoutubeClient,
    validate_metadata,
)


def metadata(**kwargs):
    return {"title": "História", "description": "Uma legenda", "made_for_kids": False, **kwargs}


@pytest.mark.parametrize("updates", [
    {"title": ""}, {"title": "t" * 101}, {"description": "á" * 2501},
    {"made_for_kids": None}, {"made_for_kids": "false"}, {"privacy": "friends"},
    {"tags": "tag"}, {"tags": ["t" * 501]}, {"title": "<história>"},
    {"publish_at": "2035-01-01T12:00:00", "privacy": "private"},
    {"publish_at": "2035-01-01T12:00:00Z", "privacy": "public"},
])
def test_metadata_rejects_invalid_data(updates):
    with pytest.raises(ValueError):
        validate_metadata(metadata(**updates))


def test_utf8_boundary_and_explicit_children_setting():
    assert validate_metadata(metadata(description="á" * 2500))["made_for_kids"] is False


def test_plaintext_keyring_refused(monkeypatch):
    import keyring

    backend_type = type("PlaintextKeyring", (), {"priority": 1})
    backend_type.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(keyring, "get_keyring", backend_type)
    with pytest.raises(AuthRequired, match="Cofre seguro"):
        CredentialStore().load()


def test_missing_auth_reports_none(tmp_path):
    store = MagicMock()
    store.load.return_value = None
    assert YoutubeClient(tmp_path, store=store).account() is None


def test_resumable_upload_waits_for_processing(tmp_path):
    source = tmp_path / "vídeo.mp4"
    source.write_bytes(b"fixture")
    service = MagicMock()
    request = service.videos.return_value.insert.return_value
    request.next_chunk.side_effect = [(None, None), (None, {"id": "abc123"})]
    client = YoutubeClient(tmp_path, service=service)
    result = client.upload(str(source), metadata(), Event())
    assert result["status"] == "PROCESSING"
    assert result["remote_id"] == "abc123"
    body = service.videos.return_value.insert.call_args.kwargs["body"]
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert service.videos.return_value.insert.call_args.kwargs["media_body"].resumable()


def test_network_ambiguity_never_starts_another_upload(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"fixture")
    service = MagicMock()
    request = service.videos.return_value.insert.return_value
    request.next_chunk.side_effect = OSError("network unavailable")
    with pytest.raises(UploadUncertain):
        YoutubeClient(tmp_path, service=service).upload(str(source), metadata(), Event())
    service.videos.return_value.insert.assert_called_once()
    request.next_chunk.assert_called_once_with(num_retries=0)


def test_server_retry_reuses_resumable_request(tmp_path):
    import httplib2
    from googleapiclient.errors import HttpError

    source = tmp_path / "video.mp4"
    source.write_bytes(b"fixture")
    service = MagicMock()
    request = service.videos.return_value.insert.return_value
    request.next_chunk.side_effect = [
        HttpError(httplib2.Response({"status": "503"}), b'{"error":{"message":"busy"}}'),
        (None, {"id": "abc"}),
    ]
    cancel = MagicMock()
    cancel.is_set.return_value = False
    cancel.wait.return_value = False
    result = YoutubeClient(tmp_path, service=service).upload(str(source), metadata(), cancel)
    assert result["remote_id"] == "abc"
    service.videos.return_value.insert.assert_called_once()
    cancel.wait.assert_called_once_with(2)


def test_cancellation_before_upload_makes_no_remote_call(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"fixture")
    cancel = Event()
    cancel.set()
    service = MagicMock()
    with pytest.raises(UploadCancelled):
        YoutubeClient(tmp_path, service=service).upload(str(source), metadata(), cancel)
    service.videos.assert_not_called()


@pytest.mark.parametrize(("processing", "upload", "privacy", "expected"), [
    ("succeeded", "processed", "public", "PUBLISHED"),
    ("succeeded", "processed", "private", "UPLOADED_PRIVATE"),
    ("succeeded", "processed", "unlisted", "UPLOADED_PRIVATE"),
    ("processing", "uploaded", "public", "PROCESSING"),
    ("succeeded", "uploaded", "public", "PROCESSING"),
    ("failed", "uploaded", "public", "FAILED"),
    ("processing", "rejected", "public", "FAILED"),
])
def test_remote_confirmation_required(tmp_path, processing, upload, privacy, expected):
    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {"items": [{
        "status": {"uploadStatus": upload, "privacyStatus": privacy},
        "processingDetails": {"processingStatus": processing},
    }]}
    assert YoutubeClient(tmp_path, service=service).check_status("id")["status"] == expected


def test_missing_remote_video_is_unknown_not_success(tmp_path):
    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {"items": []}
    assert YoutubeClient(tmp_path, service=service).check_status("id")["status"] == "UNKNOWN_REMOTE_STATUS"
