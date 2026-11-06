"""Application use cases shared by desktop and local API.

Jobs are independent per destination. An upload with an ambiguous result must
never be sent again automatically; a prepared export is never a published post.
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .config import configure_logging, data_path
from .database import Database
from .instance import InstanceLock
from .media import MediaCancelled, MediaService
from .platforms import PLATFORM_NAMES, registry
from .youtube import AuthRequired, UploadCancelled, UploadUncertain, YoutubeClient, validate_metadata

TERMINAL = {"PUBLISHED", "UPLOADED_PRIVATE", "USER_CONFIRMED", "CANCELLED", "USER_CANCELLED"}
RETRYABLE = {"FAILED", "AUTH_REQUIRED", "MISSED_SCHEDULE"}
LOG = logging.getLogger("multipost.service")


def now() -> str:
    return datetime.now(UTC).isoformat()


def utc_time(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Informe data e hora com fuso horário.")
    return parsed.astimezone(UTC).isoformat()


class AppService:
    def __init__(self, data_dir: Path | None = None, youtube=None):
        self.data_dir = Path(data_dir or data_path()).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._instance = InstanceLock(self.data_dir)
        configure_logging(self.data_dir / "logs")
        self.db = Database(self.data_dir / "multipost.sqlite3")
        self.media = MediaService(self.data_dir / "cache")
        self.youtube = youtube or YoutubeClient(self.data_dir)
        self._tick_lock = threading.Lock()
        # Claiming a task and registering cancellation must be one operation
        # relative to cancel()/close(), without locking during heavy I/O.
        self._state_lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._remote_checks: dict[str, float] = {}
        self._closed = False
        self._resources_closed = False
        self._recover()
        LOG.info("application_started")

    def _recover(self):
        with self.db.connection() as connection:
            connection.execute("UPDATE jobs SET status='UNKNOWN_REMOTE_STATUS', "
                               "error='Aplicativo interrompido durante envio. Não reenviar sem verificar.' "
                               "WHERE status='UPLOADING'")
            connection.execute("UPDATE jobs SET status='READY' WHERE status='EXPORTING'")
            cutoff = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
            connection.execute("UPDATE jobs SET status='MISSED_SCHEDULE', "
                               "error='Agendamento vencido. Confirme executar agora.' "
                               "WHERE status='SCHEDULED' AND scheduled_at < ?", (cutoff,))

    def import_video(self, path) -> dict:
        info = self.media.probe(Path(path))
        data = info.as_dict()
        with self.db.connection() as connection:
            existing = connection.execute("SELECT * FROM videos WHERE sha256=?", (info.sha256,)).fetchone()
            if existing:
                connection.execute("UPDATE videos SET path=?,name=?,info=? WHERE id=?",
                                   (str(info.path), Path(info.path).name, json.dumps(data), existing["id"]))
                identity = existing["id"]
            else:
                identity = uuid.uuid4().hex
                connection.execute("INSERT INTO videos VALUES (?,?,?,?,?,?)",
                                   (identity, str(info.path), Path(info.path).name,
                                    info.sha256, json.dumps(data), now()))
        LOG.info("video_imported id=%s", identity)
        return self.video(identity)

    def video(self, identity):
        rows = self.db.rows("SELECT * FROM videos WHERE id=?", (identity,))
        if not rows:
            raise ValueError("Vídeo não encontrado na biblioteca.")
        row = rows[0]
        row["info"] = json.loads(row["info"])
        return row

    def videos(self):
        return [dict(row, info=json.loads(row["info"])) for row in
                self.db.rows("SELECT * FROM videos ORDER BY created_at DESC")]

    def relocate_video(self, identity, path):
        old = self.video(identity)
        info = self.media.probe(path)
        if info.sha256 != old["sha256"]:
            raise ValueError("O arquivo selecionado não é o mesmo vídeo.")
        return self.import_video(path)

    def prepare_video(self, video_id, mode="fit", cancel=None, progress=None):
        video = self.video(video_id)
        output = self.data_dir / "prepared" / f"{uuid.uuid4().hex}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        self.media.convert(video["path"], output, mode=mode, cancel=cancel, progress=progress)
        return self.import_video(output)

    def create_publication(self, video_id, title, caption, platforms, overrides=None,
                           privacy="private", made_for_kids=None, scheduled_at=None,
                           tags=None, category="22"):
        video = self.video(video_id)
        if not Path(video["path"]).is_file():
            raise ValueError("O vídeo foi movido ou removido. Localize-o novamente.")
        if not platforms or any(p not in PLATFORM_NAMES for p in platforms):
            raise ValueError("Selecione pelo menos uma plataforma válida.")
        if not title.strip() or len(title) > 100:
            raise ValueError("Informe título entre 1 e 100 caracteres.")
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Privacidade inválida.")
        if "youtube" in platforms and type(made_for_kids) is not bool:
            raise ValueError("Declare se o conteúdo é destinado a crianças para o YouTube.")
        scheduled_at = utc_time(scheduled_at) if scheduled_at else None
        if scheduled_at and scheduled_at <= now():
            raise ValueError("O agendamento precisa estar no futuro.")
        if not isinstance(category, str) or not category.isascii() or not category.isdecimal():
            raise ValueError("A categoria YouTube deve ser um identificador numérico válido.")
        metadata = {"title": title, "privacy": privacy, "made_for_kids": made_for_kids,
                    "tags": tags or [], "category": category}
        project_id = uuid.uuid4().hex
        identities = []
        with self.db.connection() as connection:
            connection.execute("INSERT INTO projects VALUES (?,?,?)", (project_id, video_id, now()))
            for platform in dict.fromkeys(platforms):
                specific = (overrides or {}).get(platform, caption)
                if platform == "youtube":
                    validate_metadata(metadata | {"description": specific})
                fingerprint = hashlib.sha256(json.dumps(
                    [video["sha256"], platform, title, specific, metadata, scheduled_at],
                    sort_keys=True).encode()).hexdigest()
                previous = connection.execute("SELECT id FROM jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
                if previous:
                    identities.append(previous["id"])
                    continue
                identity = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO jobs(id,project_id,video_id,platform,title,caption,metadata,status,"
                    "fingerprint,scheduled_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (identity, project_id, video_id, platform, title, specific, json.dumps(metadata),
                     "SCHEDULED" if scheduled_at else "READY", fingerprint, scheduled_at, now()))
                connection.execute("INSERT INTO audit_events(job_id,created_at,event) VALUES (?,?,?)",
                                   (identity, now(), "CREATED"))
                identities.append(identity)
        return identities

    def jobs(self):
        return [dict(row, metadata=json.loads(row["metadata"])) for row in
                self.db.rows("SELECT * FROM jobs ORDER BY created_at DESC")]

    def job(self, identity):
        rows = self.db.rows("SELECT * FROM jobs WHERE id=?", (identity,))
        if not rows:
            raise ValueError("Tarefa não encontrada.")
        return dict(rows[0], metadata=json.loads(rows[0]["metadata"]))

    def _update(self, identity, **fields):
        allowed = {"status", "error", "progress", "remote_id", "url", "confirmation", "export_dir",
                   "completed_at", "scheduled_at"}
        if not fields or set(fields) - allowed:
            raise ValueError("Atualização inválida.")
        with self.db.connection() as connection:
            connection.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?",
                               (*fields.values(), identity))
            if "status" in fields:
                connection.execute("INSERT INTO audit_events(job_id,created_at,event) VALUES (?,?,?)",
                                   (identity, now(), fields["status"]))
        if "status" in fields:
            LOG.info("job_state id=%s status=%s", identity, fields["status"])

    def tick(self):
        if self._closed or not self._tick_lock.acquire(blocking=False):
            return
        identity = None
        acknowledged_upload = None
        try:
            if self.settings().get("paused", False):
                return
            # Read-only reconciliation is throttled and round-robin. A remote video
            # may take hours to process and must not starve independent exports.
            processing = self.db.rows("SELECT id FROM jobs WHERE status='PROCESSING'")
            if processing:
                candidate = min(processing, key=lambda item: self._remote_checks.get(item["id"], 0))
                checked_at = self._remote_checks.get(candidate["id"], 0)
                if time.monotonic() - checked_at >= 30:
                    self._remote_checks[candidate["id"]] = time.monotonic()
                    try:
                        self.reconcile(candidate["id"])
                    except Exception as error:
                        # Read failure does not change an acknowledged remote state.
                        LOG.warning("remote_check_failed id=%s type=%s", candidate["id"], type(error).__name__)
            with self._state_lock:
                if self._closed:
                    return
                with self.db.connection() as connection:
                    row = connection.execute("SELECT * FROM jobs WHERE status='READY' OR "
                                             "(status='SCHEDULED' AND scheduled_at<=?) ORDER BY created_at LIMIT 1",
                                             (now(),)).fetchone()
                    if not row:
                        return
                    job = dict(row)
                    identity = job["id"]
                    state = "UPLOADING" if job["platform"] == "youtube" else "EXPORTING"
                    claimed = connection.execute("UPDATE jobs SET status=?,attempts=attempts+1,error='' "
                                                 "WHERE id=? AND status=?", (state, identity, job["status"]))
                    if claimed.rowcount != 1:
                        return
                    connection.execute("INSERT INTO attempts(job_id,created_at,outcome) VALUES (?,?,?)",
                                       (identity, now(), "STARTED"))
                cancel = threading.Event()
                self._cancel_events[identity] = cancel
            video = self.video(job["video_id"])
            # Recheck content before side effects; replaced source files must not be published.
            fresh = self.media.probe(video["path"])
            if fresh.sha256 != video["sha256"]:
                raise ValueError("O conteúdo do vídeo mudou. Importe e revise novamente.")
            if cancel.is_set():
                raise UploadCancelled("Cancelado antes do envio.")
            if job["platform"] == "youtube":
                metadata = json.loads(job["metadata"])
                metadata["description"] = job["caption"]
                acknowledged_upload = self.youtube.upload(video["path"], metadata, cancel,
                                                          lambda p: self._update(identity, progress=p))
                self._update(identity, status="PROCESSING", remote_id=acknowledged_upload["remote_id"],
                             url=acknowledged_upload["url"], progress=1.0)
            else:
                folder = self._export(job, video, cancel)
                with self._state_lock:
                    if cancel.is_set():
                        raise UploadCancelled("Preparação cancelada.")
                    self._update(identity, status="WAITING_USER", export_dir=str(folder), progress=1.0)
        except AuthRequired:
            if identity:
                self._update(identity, status="AUTH_REQUIRED", error="Conecte novamente o YouTube.")
        except (UploadCancelled, MediaCancelled):
            if identity:
                # YoutubeClient uses UploadCancelled only before any remote send;
                # cancellation after a request starts is UploadUncertain instead.
                self._update(identity, status="CANCELLED")
        except UploadUncertain:
            if identity:
                self._update(identity, status="UNKNOWN_REMOTE_STATUS",
                             error="Resultado remoto incerto. Verifique o YouTube Studio; reenvio bloqueado.")
        except Exception as error:
            if identity:
                # Do not log remote exception text: it can contain OAuth headers or URLs.
                safe = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else (
                    "Falha na operação. Verifique conexão, arquivo, permissões e diagnóstico.")
                if acknowledged_upload is not None:
                    self._update(identity, status="UNKNOWN_REMOTE_STATUS",
                                 remote_id=acknowledged_upload.get("remote_id"),
                                 url=acknowledged_upload.get("url"),
                                 error="YouTube recebeu o envio; falha ao registrar confirmação. "
                                       "Verifique o Studio antes de continuar.")
                else:
                    self._update(identity, status="FAILED", error=safe)
                LOG.warning("job_failed id=%s type=%s", identity, type(error).__name__)
        finally:
            try:
                if identity:
                    with self._state_lock:
                        self._cancel_events.pop(identity, None)
                    with self.db.connection() as connection:
                        connection.execute("UPDATE attempts SET outcome=? WHERE id=(SELECT MAX(id) FROM attempts "
                                           "WHERE job_id=?)", (self.job(identity)["status"], identity))
            finally:
                self._tick_lock.release()

    def _export(self, job, video, cancel):
        if cancel.is_set():
            raise UploadCancelled("Preparação cancelada.")
        folder = self.data_dir / "exports" / job["project_id"] / job["platform"]
        folder.mkdir(parents=True, exist_ok=True)
        # One immutable prepared copy per content hash; target folders point to that copy.
        shared = self.data_dir / "exports" / "media"
        shared.mkdir(parents=True, exist_ok=True)
        target = shared / f"{video['sha256']}.mp4"
        if not target.exists():
            if (video["info"]["video_codec"] == "h264"
                    and video["info"]["audio_codec"] in {None, "aac"}
                    and Path(video["path"]).suffix.lower() == ".mp4"):
                self._copy_media(Path(video["path"]), target, cancel)
            else:
                self.media.convert(video["path"], target, cancel=cancel)
        destination = folder / "video.mp4"
        if not destination.exists():
            try:
                destination.hardlink_to(target)
            except OSError:
                self._copy_media(target, destination, cancel)
        if cancel.is_set():
            raise UploadCancelled("Preparação cancelada.")
        (folder / "legenda.txt").write_text(job["caption"], encoding="utf-8")
        connector = registry()[job["platform"]]
        (folder / "INSTRUCOES.txt").write_text(
            f"{PLATFORM_NAMES[job['platform']]}\n{connector.instructions}\n{connector.official_url}\n"
            "Revise vídeo, direitos de uso, música e público antes de publicar no aplicativo oficial.\n"
            "Este pacote não confirma publicação. Após publicar, confirme manualmente no MultiPost.\n",
            encoding="utf-8")
        return folder

    @staticmethod
    def _copy_media(source, target, cancel):
        """A cancelled copy cannot become a reusable shared export artifact."""
        descriptor, temporary = tempfile.mkstemp(suffix=".partial", dir=target.parent)
        partial = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as output, Path(source).open("rb") as original:
                while True:
                    if cancel.is_set():
                        raise UploadCancelled("Cópia cancelada.")
                    chunk = original.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if cancel.is_set():
                raise UploadCancelled("Cópia cancelada.")
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

    def cancel(self, identity):
        with self._state_lock:
            job = self.job(identity)
            if job["status"] in TERMINAL:
                raise ValueError("Esta tarefa já foi concluída.")
            if job["status"] in {"PROCESSING", "UNKNOWN_REMOTE_STATUS"}:
                raise ValueError("Operação remota já iniciada. Verifique ou remova o vídeo no YouTube Studio.")
            if identity in self._cancel_events:
                self._cancel_events[identity].set()
            else:
                self._update(identity, status="CANCELLED")

    def retry(self, identity):
        with self._state_lock:
            job = self.job(identity)
            if job["status"] not in RETRYABLE or job["remote_id"]:
                raise ValueError("Reenvio bloqueado para evitar duplicação. Verifique o estado remoto.")
            self._update(identity, status="READY", scheduled_at=None, error="", progress=0)

    def reschedule(self, identity, scheduled_at):
        with self._state_lock:
            job = self.job(identity)
            if job["status"] not in {"READY", "SCHEDULED", "MISSED_SCHEDULE"}:
                raise ValueError("Somente tarefas pendentes podem ser reagendadas.")
            date = utc_time(scheduled_at)
            if date <= now():
                raise ValueError("Escolha uma data futura.")
            self._update(identity, status="SCHEDULED", scheduled_at=date, error="")

    def reconcile(self, identity, remote_id=None):
        job = self.job(identity)
        if job["platform"] != "youtube" or job["status"] not in {
                "PROCESSING", "UNKNOWN_REMOTE_STATUS", "UPLOADED_PRIVATE"}:
            raise ValueError("Esta tarefa não aguarda verificação remota.")
        remote_id = remote_id or job["remote_id"]
        if not remote_id:
            raise ValueError("Consulte o YouTube Studio e informe o ID do vídeo enviado para reconciliar.")
        result = self.youtube.check_status(remote_id)
        status = result["status"]
        self._update(identity, status=status, remote_id=remote_id, url=result.get("url", job["url"]),
                     confirmation="API" if status in {"PUBLISHED", "UPLOADED_PRIVATE"} else None,
                     completed_at=now() if status in TERMINAL else None,
                     error="O YouTube rejeitou o processamento." if status == "FAILED" else "")

    def confirm_manual(self, identity, url=""):
        with self._state_lock:
            job = self.job(identity)
            if job["status"] != "WAITING_USER" or job["platform"] == "youtube":
                raise ValueError("Somente uma publicação assistida preparada pode ser confirmada.")
            if url:
                parsed = urlparse(url)
                hosts = {"instagram": ("instagram.com",), "facebook": ("facebook.com", "fb.watch"),
                         "tiktok": ("tiktok.com",), "kwai": ("kwai.com", "kw.ai")}[job["platform"]]
                if parsed.scheme != "https" or not any(parsed.hostname == h or
                        (parsed.hostname or "").endswith("." + h) for h in hosts):
                    raise ValueError("Informe um link HTTPS da plataforma selecionada.")
            self._update(identity, status="USER_CONFIRMED", url=url, confirmation="USER", completed_at=now())

    def stats(self):
        jobs = self.jobs()
        return {"videos": len(self.videos()), "completed": sum(j["status"] in TERMINAL - {"CANCELLED"} for j in jobs),
                "waiting": sum(j["status"] == "WAITING_USER" for j in jobs),
                "failed": sum(j["status"] in {"FAILED", "UNKNOWN_REMOTE_STATUS"} for j in jobs),
                "pending": sum(j["status"] in {"READY", "SCHEDULED", "PROCESSING"} for j in jobs)}

    def settings(self):
        return self.db.setting("preferences", {"theme": "dark", "paused": False})

    def save_settings(self, values):
        settings = self.settings() | values
        if settings.get("theme") not in {"dark", "light", "system"}:
            raise ValueError("Tema inválido.")
        self.db.save_setting("preferences", settings)

    def save_draft(self, draft):
        self.db.save_setting("draft", draft)

    def load_draft(self):
        return self.db.setting("draft", {})

    def request_stop(self):
        """Prevent new claims and signal cancellation without blocking the caller."""
        with self._state_lock:
            self._closed = True
            for event in self._cancel_events.values():
                event.set()

    def close(self):
        self.request_stop()
        # Caller must finish its worker before disposing database and releasing writer lock.
        with self._tick_lock:
            if self._resources_closed:
                return
            self.db.close()
            self._instance.close()
            self._resources_closed = True
