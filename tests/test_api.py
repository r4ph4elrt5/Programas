"""Loopback API checks: authorization, explicit consent and shared use cases."""

import threading

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from multipost.api import create_api, local_api_key


class StubService:
    def __init__(self, path):
        self.data_dir = path
        self.calls = []
        self.draft = {}
        self.ticked = threading.Event()

    def tick(self):
        self.ticked.set()

    def request_stop(self):
        self.calls.append(("request_stop",))

    def videos(self):
        return [{"id": "video-1"}]

    def import_video(self, path):
        self.calls.append(("import", path))
        return {"id": "video-1"}

    def jobs(self):
        return [{"id": "job-1", "status": "WAITING_USER"}]

    def create_publication(self, **values):
        self.calls.append(("create", values))
        return ["job-1"]

    def job(self, identity):
        return {"id": identity}

    def cancel(self, identity):
        self.calls.append(("cancel", identity))

    def retry(self, identity):
        raise ValueError("Reenvio bloqueado para evitar duplicação.")

    def confirm_manual(self, identity, url):
        self.calls.append(("confirm", identity, url))

    def reconcile(self, identity, remote_id):
        self.calls.append(("reconcile", identity, remote_id))

    def save_settings(self, values):
        self.calls.append(("settings", values))

    def load_draft(self):
        return self.draft

    def save_draft(self, values):
        self.draft = values


@pytest.fixture
def api(tmp_path):
    service = StubService(tmp_path)
    with TestClient(create_api(service), base_url="http://127.0.0.1") as client:
        key = (tmp_path / "api-key").read_text()
        client.headers["Authorization"] = "Bearer " + key
        yield client, service, key


def test_private_key_persists_and_denies_symlink(tmp_path):
    key = local_api_key(tmp_path)
    assert len(key) >= 32
    assert local_api_key(tmp_path) == key
    import os
    if os.name != "nt":
        assert (tmp_path / "api-key").stat().st_mode & 0o077 == 0
        (tmp_path / "api-key").chmod(0o644)
        with pytest.raises(RuntimeError, match="0600"):
            local_api_key(tmp_path)


def test_all_routes_require_authentication(api):
    client, service, key = api
    client.headers.pop("Authorization")
    for path in ("/health", "/videos", "/jobs", "/draft"):
        response = client.get(path)
        assert response.status_code == 401
        assert key not in response.text
    assert client.post("/videos", json={"path": "video.mp4"}).status_code == 401
    assert client.put("/draft", json={}).status_code == 401
    assert not service.calls


def test_health_has_no_token_or_fake_authorization(api):
    client, service, key = api
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["capabilities"]["youtube"] == "AUTH_REQUIRED"
    assert response.json()["capabilities"]["kwai"] == "ASSISTED_PUBLISH"
    assert key not in response.text
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert service.ticked.wait(1)


def test_queue_creation_requires_explicit_consent(api):
    client, service, _key = api
    payload = {"video_id": "video-1", "title": "Teste", "caption": "Legenda", "platforms": ["instagram"]}
    assert client.post("/jobs", json=payload).status_code == 400
    assert not service.calls
    assert client.post("/jobs", json=payload | {"approved": "true"}).status_code == 422
    assert client.post("/jobs", json=payload | {"approved": True, "surprise": True}).status_code == 422
    response = client.post("/jobs", json=payload | {"approved": True})
    assert response.status_code == 201
    assert response.json() == {"job_ids": ["job-1"]}
    assert "approved" not in service.calls[0][1]
    assert service.calls[0][1]["privacy"] == "private"


def test_youtube_metadata_is_forwarded_and_bounded(api):
    client, service, _key = api
    payload = {"video_id": "video-1", "title": "Teste", "platforms": ["youtube"],
               "made_for_kids": False, "tags": ["história", "curiosidades"],
               "category": "27", "approved": True}
    assert client.post("/jobs", json=payload).status_code == 201
    assert service.calls[0][1]["tags"] == payload["tags"]
    assert service.calls[0][1]["category"] == "27"
    assert client.post("/jobs", json=payload | {"category": "invalid"}).status_code == 422
    assert client.post("/jobs", json=payload | {"tags": ["x" * 501]}).status_code == 422
    assert client.post("/jobs", json=payload | {"tags": ["x"] * 51}).status_code == 422


def test_actions_and_draft_use_shared_service(api):
    client, service, _key = api
    assert client.post("/videos", json={"path": "C:/vídeos/meu vídeo.mp4"}).status_code == 201
    assert client.get("/videos").json() == [{"id": "video-1"}]
    assert client.get("/jobs").json()[0]["status"] == "WAITING_USER"
    assert client.post("/jobs/job-1/cancel").status_code == 200
    assert client.post("/jobs/job-1/confirm", json={"url": "https://instagram.com/p/one"}).status_code == 200
    assert client.post("/jobs/job-1/reconcile", json={"remote_id": "remote-1"}).status_code == 200
    assert client.post("/queue/pause", json={"paused": True}).json() == {"paused": True}
    assert client.put("/draft", json={"caption": "Legenda"}).status_code == 200
    assert client.get("/draft").json() == {"caption": "Legenda"}
    assert ("confirm", "job-1", "https://instagram.com/p/one") in service.calls


def test_retry_preserves_service_restriction(api):
    client, _service, _key = api
    response = client.post("/jobs/job-1/retry")
    assert response.status_code == 400
    assert "duplicação" in response.json()["detail"]


def test_shutdown_finishes_tick_before_owned_close(tmp_path, monkeypatch):
    from multipost import api as api_module
    service = StubService(tmp_path)
    events = []
    service.close = lambda: events.append("close")
    service.request_stop = lambda: events.append("stop")

    def tick():
        events.append("tick")

    service.tick = tick
    monkeypatch.setattr(api_module, "AppService", lambda: service)
    with TestClient(create_api()):
        pass
    assert events[-1] == "close"
    assert events.count("close") == 1
    assert events.index("stop") < events.index("close")


@pytest.mark.parametrize("status", ["UPLOADING", "EXPORTING"])
def test_shutdown_signals_active_work_without_closing_injected_service(tmp_path, status):
    class ActiveService(StubService):
        def __init__(self, path):
            super().__init__(path)
            self.cancelled = threading.Event()
            self.finished = False

        def tick(self):
            self.ticked.set()
            self.finished = self.cancelled.wait(2)

        def jobs(self):
            return [{"id": "active-job", "status": status},
                    {"id": "remote-job", "status": "PROCESSING"}]

        def request_stop(self):
            self.calls.append(("request_stop",))
            self.cancelled.set()

        def close(self):
            raise AssertionError("An injected service belongs to its caller")

    service = ActiveService(tmp_path)
    with TestClient(create_api(service)):
        assert service.ticked.wait(1)
    assert service.finished
    assert ("request_stop",) in service.calls


def test_shutdown_requests_stop_before_waiting_for_tick(tmp_path):
    class ClaimRaceService(StubService):
        def __init__(self, path):
            super().__init__(path)
            self.allow_claim = threading.Event()
            self.stopping = threading.Event()
            self.claimed = False
            self.finished = False

        def tick(self):
            self.ticked.set()
            if self.allow_claim.wait(2):
                self.claimed = not self.stopping.is_set()
                self.finished = True

        def request_stop(self):
            self.stopping.set()
            self.allow_claim.set()

    service = ClaimRaceService(tmp_path)
    with TestClient(create_api(service)):
        assert service.ticked.wait(1)
    assert not service.claimed
    assert service.finished
