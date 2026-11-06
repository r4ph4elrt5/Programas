"""A scoped, loopback bridge for the user-operated browser companion.

This is deliberately separate from the full local API. The companion can only
read prepared TikTok tasks and record explicit user declarations. It has no
access to OAuth credentials, arbitrary files, queue creation or remote posting.
"""

import hmac
import re
import secrets
import socket
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ORIGIN = re.compile(r"chrome-extension://[a-p]{32}")
PORT = 8765


class CompanionSession:
    """In-memory, rate-limited pairing. Neither code nor token is logged/saved."""

    def __init__(self):
        self._lock = threading.Lock()
        self._code = ""
        self._code_deadline = 0.0
        self._attempts = 0
        self._token_digest = b""
        self._token_deadline = 0.0
        self._origin = None

    def pairing_code(self):
        with self._lock:
            self._code = f"{secrets.randbelow(100_000_000):08d}"
            self._code_deadline = time.monotonic() + 300
            self._attempts = 0
            return self._code

    def pair(self, code, origin=None):
        import hashlib
        with self._lock:
            if self._attempts >= 5:
                raise HTTPException(429, "Gere outro código no MultiPost antes de tentar novamente.")
            self._attempts += 1
            if not self._code or time.monotonic() >= self._code_deadline:
                raise HTTPException(401, "Código expirado. Gere outro no MultiPost.")
            if not hmac.compare_digest(code, self._code):
                raise HTTPException(401, "Código inválido.")
            self._code = ""
            token = secrets.token_urlsafe(48)
            self._token_digest = hashlib.sha256(token.encode()).digest()
            self._token_deadline = time.monotonic() + 8 * 3600
            self._origin = origin
            return {"token": token, "expires_at": (datetime.now(UTC) + timedelta(hours=8)).isoformat()}

    def authorize(self, authorization, origin=None):
        import hashlib
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        with self._lock:
            valid = (token and self._token_digest and time.monotonic() < self._token_deadline
                     and hmac.compare_digest(hashlib.sha256(token.encode()).digest(), self._token_digest)
                     and origin == self._origin)
        if not valid:
            raise HTTPException(401, "Conecte a extensão ao MultiPost novamente.")

    @property
    def connected(self):
        with self._lock:
            return bool(self._token_digest and time.monotonic() < self._token_deadline)

    def disconnect(self):
        with self._lock:
            self._token_digest = b""
            self._token_deadline = 0.0
            self._origin = None
            self._code = ""


class PairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[0-9]{8}$")


class ConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["published", "scheduled"]
    url: str = Field(default="", max_length=2048)
    scheduled_at: str | None = Field(default=None, max_length=64)


def create_companion_api(service, session: CompanionSession):
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            session.disconnect()

    app = FastAPI(title="MultiPost Companion", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origin_regex=ORIGIN.pattern,
                       allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type", "X-MultiPost-Extension"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Reject DNS rebinding and requests from web pages, even if a browser
        # would allow the request to be sent before checking CORS response headers.
        if request.headers.get("host") != f"127.0.0.1:{PORT}":
            return JSONResponse(status_code=403, content={"detail": "Use apenas a ponte local do MultiPost."})
        origin = request.headers.get("origin")
        if origin and not ORIGIN.fullmatch(origin):
            return JSONResponse(status_code=403, content={"detail": "Origem não autorizada."})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(Exception)
    async def failed(_request, _error):
        return JSONResponse(status_code=500, content={"detail": "Operação local não concluída. Consulte o MultiPost."})

    async def authorized(request: Request, authorization: Annotated[str | None, Header()] = None):
        session.authorize(authorization, client_id(request))

    def client_id(request):
        identity = request.headers.get("x-multipost-extension", "")
        if not re.fullmatch("[a-p]{32}", identity):
            raise HTTPException(403, "Identificador da extensão inválido.")
        origin = request.headers.get("origin")
        if origin and origin != "chrome-extension://" + identity:
            raise HTTPException(403, "Origem da extensão inválida.")
        return identity

    @app.post("/companion/pair")
    def pair(body: PairInput, request: Request):
        return session.pair(body.code, client_id(request))

    @app.get("/companion/jobs", dependencies=[Depends(authorized)])
    def jobs():
        tasks = []
        for job in service.jobs():
            if job["platform"] != "tiktok" or job["status"] not in {
                    "WAITING_USER", "USER_CONFIRMED", "USER_SCHEDULED"}:
                continue
            video = service.video(job["video_id"])
            tasks.append({"id": job["id"], "title": job["title"], "caption": job["caption"],
                          "status": job["status"], "video_name": video["name"],
                          "video_path": str(Path(job["export_dir"]) / "video.mp4") if job["export_dir"] else "",
                          "scheduled_at": job["scheduled_at"], "confirmation": job["confirmation"],
                          "browser_confirmation": job["metadata"].get("tiktok_scheduled_at"), "url": job["url"]})
        return {"jobs": tasks, "mode": "ASSISTED_PUBLISH"}

    @app.post("/companion/jobs/{identity}/confirm", dependencies=[Depends(authorized)])
    def confirm(identity: str, body: ConfirmationInput):
        job = service.job(identity)
        if job["platform"] != "tiktok":
            raise HTTPException(403, "A extensão só pode confirmar tarefas TikTok.")
        if body.outcome == "scheduled":
            service.confirm_tiktok_schedule(identity, body.scheduled_at, body.url)
        else:
            if body.scheduled_at:
                raise ValueError("Uma publicação concluída não deve ter data de agendamento.")
            service.confirm_manual(identity, body.url)
        updated = service.job(identity)
        return {"id": identity, "status": updated["status"], "confirmation": updated["confirmation"]}

    @app.post("/companion/disconnect", dependencies=[Depends(authorized)])
    def disconnect():
        session.disconnect()
        return {"disconnected": True}

    return app


class CompanionBridge:
    """Explicitly enabled UI server sharing its service, with no second worker."""

    def __init__(self, service):
        self.service = service
        self.session = CompanionSession()
        self._server = None
        self._thread = None
        self._socket = None

    @property
    def running(self):
        return bool(self._server and self._server.started and self._thread and self._thread.is_alive())

    @property
    def connected(self):
        return self.running and self.session.connected

    def start(self):
        if self.running:
            return
        import uvicorn
        from uvicorn.config import LOGGING_CONFIG
        import copy
        # Uvicorn access logging is off; pairing codes are never URL parameters.
        # Filter defaults to a basic formatter without request bodies or headers.
        log_config = copy.deepcopy(LOGGING_CONFIG)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Windows must never allow a second listener to steal the port.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", PORT))
            sock.listen(16)
        except OSError:
            sock.close()
            raise ValueError("A porta local 8765 está em uso. Feche a API separada ou outra ponte antes de ativar.") from None
        self._socket = sock
        config = uvicorn.Config(create_companion_api(self.service, self.session), host="127.0.0.1",
                                port=PORT, access_log=False, log_level="error", log_config=log_config)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, kwargs={"sockets": [sock]},
                                        name="multipost-companion", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 5
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() >= deadline:
                self.stop()
                raise ValueError("Não foi possível iniciar a ponte local. Verifique o diagnóstico.")
            time.sleep(0.02)

    def pairing_code(self):
        if not self.running:
            raise ValueError("Ative a ponte antes de conectar a extensão.")
        return self.session.pairing_code()

    def stop(self):
        self.session.disconnect()
        if self._server:
            self._server.should_exit = True
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise RuntimeError("A ponte ainda está encerrando. Tente novamente em instantes.")
        if self._socket:
            self._socket.close()
        self._socket = None
        self._server = None
        self._thread = None
