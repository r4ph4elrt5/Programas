"""Scoped bridge: pairing, declarations, isolation and no remote side effects."""

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from multipost.companion import CompanionBridge, CompanionSession, create_companion_api
from multipost.media import VideoInfo
from multipost.service import AppService

CLIENT = "a" * 32
HEADERS = {"X-MultiPost-Extension": CLIENT, "Origin": "chrome-extension://" + CLIENT}


@pytest.fixture
def app(tmp_path):
    source = tmp_path / "meu vídeo.mp4"
    source.write_bytes(b"local fixture; media decoding is exercised separately")
    service = AppService(tmp_path / "data", youtube=MagicMock())
    service.media.probe = MagicMock(return_value=VideoInfo(
        str(source), 10, 1080, 1920, 30, "h264", "aac", source.stat().st_size, "a" * 64))
    video = service.import_video(source)
    identities = service.create_publication(video["id"], "Título", "Legenda #teste",
                                            ["tiktok", "instagram"])
    for _ in range(2):
        service.tick()
    session = CompanionSession()
    with TestClient(create_companion_api(service, session), base_url="http://127.0.0.1:8765") as client:
        client.headers.update(HEADERS)
        yield service, session, client, identities
    service.close()


def pair(session, client):
    code = session.pairing_code()
    response = client.post("/companion/pair", json={"code": code})
    assert response.status_code == 200
    token = response.json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    return code, token


def test_pairing_one_time_and_only_tiktok_scope(app):
    service, session, client, identities = app
    assert client.get("/companion/jobs").status_code == 401
    code, token = pair(session, client)
    tasks = client.get("/companion/jobs").json()
    assert tasks["mode"] == "ASSISTED_PUBLISH"
    assert [job["id"] for job in tasks["jobs"]] == [identities[0]]
    job = tasks["jobs"][0]
    assert job["caption"] == "Legenda #teste"
    assert Path(job["video_path"]).is_file()
    assert "metadata" not in job
    assert token not in json.dumps(tasks)
    assert client.post("/companion/pair", json={"code": code}).status_code == 401
    for route in ("/videos", "/jobs", "/draft", "/health", "/docs", "/openapi.json"):
        assert client.get(route).status_code == 404
    assert client.post(f"/companion/jobs/{identities[1]}/confirm", json={"outcome": "published"}).status_code == 403
    service.youtube.upload.assert_not_called()


def test_bad_origin_host_and_identity_rejected_before_pairing(app):
    _service, session, client, _identities = app
    code = session.pairing_code()
    for headers in ({"Origin": "https://www.tiktok.com"}, {"Host": "evil.example:8765"},
                    {"X-MultiPost-Extension": "b" * 32}):
        assert client.post("/companion/pair", json={"code": code}, headers=headers).status_code == 403
    pair(session, client)
    # Browser extension GETs may omit Origin; the stable client ID must remain bound.
    client.headers.pop("Origin")
    assert client.get("/companion/jobs").status_code == 200
    client.headers["X-MultiPost-Extension"] = "b" * 32
    assert client.get("/companion/jobs").status_code == 401


def test_wrong_pairing_rate_limit_expiry_and_revocation(app, monkeypatch):
    _service, session, client, _identities = app
    code = session.pairing_code()
    wrong = "00000000" if code != "00000000" else "11111111"
    for _ in range(5):
        assert client.post("/companion/pair", json={"code": wrong}).status_code == 401
    assert client.post("/companion/pair", json={"code": code}).status_code == 429
    code = session.pairing_code()
    session._code_deadline = 0
    assert client.post("/companion/pair", json={"code": code}).status_code == 401
    pair(session, client)
    session._token_deadline = 0
    assert client.get("/companion/jobs").status_code == 401
    pair(session, client)
    assert client.post("/companion/disconnect").status_code == 200
    assert client.get("/companion/jobs").status_code == 401


def test_declaration_of_scheduling_is_not_a_published_post(app):
    service, session, client, identities = app
    pair(session, client)
    identity = identities[0]
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = client.post(f"/companion/jobs/{identity}/confirm",
                           json={"outcome": "scheduled", "scheduled_at": future})
    assert response.json() == {"id": identity, "status": "USER_SCHEDULED", "confirmation": "USER"}
    job = service.job(identity)
    assert job["metadata"]["tiktok_scheduled_at"] == future
    assert job["scheduled_at"] is None  # local preparation schedule was not overwritten
    assert service.stats()["completed"] == 0
    assert service.stats()["user_scheduled"] == 1
    assert client.get("/companion/jobs").json()["jobs"][0]["browser_confirmation"] == future
    with pytest.raises(ValueError):
        service.retry(identity)
    # Time alone cannot promote this task. A fresh explicit declaration can.
    service.tick()
    assert service.job(identity)["status"] == "USER_SCHEDULED"
    assert client.post(f"/companion/jobs/{identity}/confirm", json={"outcome": "published"}).status_code == 200
    assert service.job(identity)["status"] == "USER_CONFIRMED"
    assert service.job(identity)["confirmation"] == "USER"
    service.youtube.upload.assert_not_called()


@pytest.mark.parametrize("body", [
    {"outcome": "scheduled"},
    {"outcome": "scheduled", "scheduled_at": "2020-01-01T12:00:00+00:00"},
    {"outcome": "scheduled", "scheduled_at": "2030-01-01T12:00:00"},
    {"outcome": "published", "url": "https://tiktok.com.evil.example/video/1"},
    {"outcome": "published", "url": "https://user:password@www.tiktok.com/video/1"},
    {"outcome": "published", "scheduled_at": "2030-01-01T12:00:00+00:00"},
])
def test_invalid_declarations_preserve_waiting_state(app, body):
    service, session, client, identities = app
    pair(session, client)
    assert client.post(f"/companion/jobs/{identities[0]}/confirm", json=body).status_code == 400
    assert service.job(identities[0])["status"] == "WAITING_USER"


def test_manual_publication_remains_a_user_declaration(app):
    service, session, client, identities = app
    pair(session, client)
    response = client.post(f"/companion/jobs/{identities[0]}/confirm", json={
        "outcome": "published", "url": "https://www.tiktok.com/@example/video/123"})
    assert response.json()["status"] == "USER_CONFIRMED"
    assert service.job(identities[0])["confirmation"] == "USER"
    assert service.job(identities[0])["remote_id"] is None


def test_schedule_declaration_persists_and_is_never_resent(app):
    service, _session, _client, identities = app
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    service.confirm_tiktok_schedule(identities[0], future)
    directory = service.data_dir
    service.close()
    recovered = AppService(directory, youtube=MagicMock())
    try:
        recovered.tick()
        assert recovered.job(identities[0])["status"] == "USER_SCHEDULED"
        assert recovered.job(identities[0])["metadata"]["tiktok_scheduled_at"] == future
        recovered.youtube.upload.assert_not_called()
    finally:
        recovered.close()


def test_bridge_stops_server_without_stopping_application(app):
    service, _session, _client, _identities = app
    bridge = CompanionBridge(service)
    bridge.start()
    try:
        assert bridge.running
        assert len(bridge.pairing_code()) == 8
        bridge.start()  # idempotent
        second = CompanionBridge(service)
        with pytest.raises(ValueError, match="8765"):
            second.start()
    finally:
        bridge.stop()
    assert not bridge.running
    assert not service._closed
    assert service.videos()


def test_only_one_concurrent_pairing_consumes_code():
    session = CompanionSession()
    code = session.pairing_code()
    results = []
    def attempt():
        try:
            results.append(session.pair(code, CLIENT))
        except Exception:
            results.append(None)
    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert sum(result is not None for result in results) == 1
