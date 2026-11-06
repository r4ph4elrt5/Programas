"""Authenticated loopback-only API for local integrations.

The desktop and API share use cases, never credential contents. Start the API
through ``python -m multipost --api``; it binds only to 127.0.0.1.
"""

import asyncio
import hmac
import logging
import os
import secrets
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import __version__
from .platforms import registry
from .service import AppService

LOG = logging.getLogger("multipost.api")
Platform = Literal["youtube", "instagram", "facebook", "tiktok", "kwai"]


def local_api_key(directory: Path) -> str:
    """Create one private local bearer credential; never return it over HTTP."""
    path = directory / "api-key"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Arquivo de autorização local inválido.") from None
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RuntimeError("O arquivo api-key precisa ter permissão 0600.")
        value = path.read_text(encoding="utf-8").strip()
        if len(value) < 32 or len(value) > 256:
            raise RuntimeError("Arquivo de autorização local inválido.")
        return value
    value = secrets.token_urlsafe(48)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    return value


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportVideo(InputModel):
    path: str = Field(min_length=1, max_length=32767)


class CreatePublication(InputModel):
    video_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=100)
    caption: str = Field(default="", max_length=10000)
    platforms: list[Platform] = Field(min_length=1, max_length=5)
    overrides: dict[Platform, Annotated[str, Field(max_length=10000)]] = Field(default_factory=dict)
    privacy: Literal["private", "unlisted", "public"] = "private"
    made_for_kids: StrictBool | None = None
    tags: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=50)
    category: str = Field(default="22", pattern=r"^[0-9]{1,10}$")
    scheduled_at: str | None = Field(default=None, max_length=64)
    approved: StrictBool = False


class ManualConfirmation(InputModel):
    url: str = Field(default="", max_length=2048)


class Reconciliation(InputModel):
    remote_id: str | None = Field(default=None, min_length=1, max_length=128)


class PauseQueue(InputModel):
    paused: StrictBool


async def _authenticate(request: Request, authorization: Annotated[str | None, Header()] = None):
    prefix = "Bearer "
    provided = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ""
    key = request.app.state.api_key
    if not provided or not hmac.compare_digest(provided.encode(), key.encode()):
        raise HTTPException(status_code=401, detail="Autorização local necessária.",
                            headers={"WWW-Authenticate": "Bearer"})


def create_api(service: AppService | None = None) -> FastAPI:
    """Create an API. An injected service remains owned by its caller."""
    @asynccontextmanager
    async def lifespan(app):
        current = service or AppService()
        owned = service is None
        try:
            app.state.service = current
            app.state.api_key = local_api_key(current.data_dir)
            stop = asyncio.Event()

            async def run_queue():
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(current.tick)
                    except Exception as error:
                        LOG.warning("queue_tick_failed type=%s", type(error).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=2)
                    except TimeoutError:
                        continue

            queue_task = asyncio.create_task(run_queue())
            try:
                yield
            finally:
                stop.set()
                # Atomically prevent new job claims and signal active work
                # before waiting. Disposal remains the injected caller's job.
                await asyncio.to_thread(current.request_stop)
                await queue_task
        finally:
            if owned:
                await asyncio.to_thread(current.close)

    app = FastAPI(title="MultiPost local API", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None,
                  dependencies=[Depends(_authenticate)])

    @app.exception_handler(ValueError)
    async def invalid_input(_request, error):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(FileNotFoundError)
    async def missing_file(_request, _error):
        return JSONResponse(status_code=400, content={"detail": "Arquivo não encontrado."})

    @app.exception_handler(Exception)
    async def operation_failed(_request, error):
        LOG.warning("api_operation_failed type=%s", type(error).__name__)
        return JSONResponse(status_code=500, content={"detail": "Operação não concluída. Consulte o diagnóstico."})

    def current(request: Request) -> AppService:
        return request.app.state.service

    @app.get("/health")
    def health():
        return {"application": "MultiPost", "version": __version__, "capabilities": {
            key: connector.capability.value for key, connector in registry().items()
        }, "youtube": "A autorização deve ser verificada no aplicativo; nenhum token é exposto."}

    @app.get("/videos")
    def videos(request: Request):
        return current(request).videos()

    @app.post("/videos", status_code=201)
    def import_video(body: ImportVideo, request: Request):
        return current(request).import_video(body.path)

    @app.get("/jobs")
    def jobs(request: Request):
        return current(request).jobs()

    @app.post("/jobs", status_code=201)
    def create_jobs(body: CreatePublication, request: Request):
        if not body.approved:
            raise HTTPException(400, "Confirme approved=true para autorizar a fila desta publicação.")
        identities = current(request).create_publication(**body.model_dump(exclude={"approved"}))
        return {"job_ids": identities}

    @app.post("/jobs/{identity}/cancel")
    def cancel(identity: str, request: Request):
        current(request).cancel(identity)
        return current(request).job(identity)

    @app.post("/jobs/{identity}/retry")
    def retry(identity: str, request: Request):
        current(request).retry(identity)
        return current(request).job(identity)

    @app.post("/jobs/{identity}/confirm")
    def confirm(identity: str, body: ManualConfirmation, request: Request):
        current(request).confirm_manual(identity, body.url)
        return current(request).job(identity)

    @app.post("/jobs/{identity}/reconcile")
    def reconcile(identity: str, body: Reconciliation, request: Request):
        current(request).reconcile(identity, body.remote_id)
        return current(request).job(identity)

    @app.post("/queue/pause")
    def pause(body: PauseQueue, request: Request):
        current(request).save_settings({"paused": body.paused})
        return {"paused": body.paused}

    @app.get("/draft")
    def draft(request: Request):
        return current(request).load_draft()

    @app.put("/draft")
    def save_draft(body: dict, request: Request):
        # Bound the persisted document; this is local authenticated user content.
        import json
        if len(json.dumps(body, ensure_ascii=False).encode()) > 100_000:
            raise HTTPException(413, "Rascunho excede 100 KB.")
        current(request).save_draft(body)
        return {"saved": True}

    return app
