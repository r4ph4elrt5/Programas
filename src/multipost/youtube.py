"""Official desktop OAuth and resumable YouTube uploads; never simulate success."""

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
SERVICE = "MultiPost Desktop"
USER = "youtube-oauth"


class YoutubeError(RuntimeError):
    """A safe, user-facing integration error, without raw response bodies."""


class AuthRequired(YoutubeError):
    pass


class UploadUncertain(YoutubeError):
    """Remote outcome is unknown; a fresh upload could duplicate a video."""


class UploadCancelled(YoutubeError):
    pass


class CredentialStore:
    """Only OS-backed vaults; refuse plaintext and fallback backends."""

    def _backend(self):
        import keyring

        backend = keyring.get_keyring()
        module = type(backend).__module__
        allowed = ("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService")
        if not module.startswith(allowed) or backend.priority <= 0:
            raise AuthRequired(
                "Cofre seguro indisponível. Use o Windows Credential Manager "
                "(ou um cofre nativo suportado); tokens não serão salvos em texto."
            )
        return backend

    def load(self):
        value = self._backend().get_password(SERVICE, USER)
        return json.loads(value) if value else None

    def save(self, value):
        self._backend().set_password(SERVICE, USER, json.dumps(value))

    def delete(self):
        backend = self._backend()
        if backend.get_password(SERVICE, USER):
            backend.delete_password(SERVICE, USER)


def validate_metadata(metadata: dict) -> dict:
    result = dict(metadata)
    title = result.get("title", "")
    description = result.get("description", "")
    if not isinstance(title, str) or not title.strip() or len(title) > 100:
        raise ValueError("O título YouTube deve ter entre 1 e 100 caracteres.")
    if not isinstance(description, str) or len(description.encode("utf-8")) > 5000:
        raise ValueError("A descrição YouTube deve ter até 5.000 bytes UTF-8.")
    if any(character in title + description for character in "<>"):
        raise ValueError("YouTube não aceita < ou > no título ou descrição.")
    if type(result.get("made_for_kids")) is not bool:
        raise ValueError("Informe explicitamente se o conteúdo é destinado a crianças.")
    if result.get("privacy", "private") not in ("private", "unlisted", "public"):
        raise ValueError("Privacidade YouTube inválida.")
    tags = result.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("Tags devem ser uma lista de textos.")
    if sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(0, len(tags) - 1) > 500:
        raise ValueError("As tags excedem o limite de 500 caracteres do YouTube.")
    if result.get("publish_at"):
        when = datetime.fromisoformat(result["publish_at"].replace("Z", "+00:00"))
        if when.tzinfo is None or when <= datetime.now(timezone.utc):
            raise ValueError("O agendamento YouTube deve ser futuro e incluir fuso horário.")
        if result.get("privacy", "private") != "private":
            raise ValueError("Agendamento remoto YouTube exige privacidade private.")
    return result


class YoutubeClient:
    def __init__(self, data_dir: Path, *, store=None, service=None):
        self.data_dir = Path(data_dir)
        self.store = store or CredentialStore()
        self._service = service

    def _credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        try:
            value = self.store.load()
            if not value:
                raise AuthRequired("Conecte sua conta YouTube em Contas conectadas.")
            credentials = Credentials.from_authorized_user_info(value, SCOPES)
            if credentials.expired and credentials.refresh_token:
                class TimedRequest(Request):
                    def __call__(self, *args, **kwargs):
                        kwargs.setdefault("timeout", 30)
                        return super().__call__(*args, **kwargs)

                credentials.refresh(TimedRequest())
                self.store.save(json.loads(credentials.to_json()))
            if not credentials.valid:
                raise AuthRequired("Credenciais YouTube inválidas; reconecte sua conta.")
            return credentials
        except AuthRequired:
            raise
        except Exception:
            raise AuthRequired("Não foi possível acessar ou renovar a autorização YouTube.") from None

    def _api(self):
        if self._service is not None:
            return self._service
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        return build(
            "youtube", "v3", cache_discovery=False,
            http=AuthorizedHttp(self._credentials(), http=httplib2.Http(timeout=30)),
        )

    def connect(self, client_json_path):
        from google_auth_oauthlib.flow import InstalledAppFlow

        self.store._backend()  # Ensure a safe vault exists before opening consent.
        path = Path(client_json_path).expanduser().resolve(strict=True)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            if "installed" not in config:
                raise ValueError("Escolha credenciais OAuth do tipo Aplicativo para computador.")
            installed = config["installed"]
            if (
                installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
                or installed.get("token_uri") != "https://oauth2.googleapis.com/token"
                or not installed.get("client_id", "").endswith(".apps.googleusercontent.com")
            ):
                raise ValueError("Importe o arquivo OAuth desktop original do Google Cloud.")
            flow = InstalledAppFlow.from_client_config(config, SCOPES)
            credentials = flow.run_local_server(
                host="localhost", port=0, open_browser=True, access_type="offline",
                prompt="consent", timeout_seconds=180,
                success_message="MultiPost autorizado. Você pode fechar esta janela.",
            )
            self.store.save(json.loads(credentials.to_json()))
            return self.account()
        except (ValueError, AuthRequired):
            raise
        except Exception:
            raise AuthRequired("Autorização não concluída. Confira o projeto OAuth e tente novamente.") from None

    def account(self):
        try:
            result = self._api().channels().list(part="snippet", mine=True).execute(num_retries=0)
            items = result.get("items", [])
            if not items:
                raise AuthRequired("A conta autorizada não possui um canal YouTube disponível.")
            return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}
        except AuthRequired:
            return None
        except Exception:
            raise YoutubeError("Não foi possível verificar o canal YouTube.") from None

    def disconnect(self):
        """Revoke remotely first, retain credentials if revocation cannot be confirmed."""
        import requests

        value = self.store.load()
        if value:
            token = value.get("refresh_token") or value.get("token")
            try:
                response = requests.post(
                    "https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=30,
                )
                if response.status_code != 200:
                    raise YoutubeError("Revogação não confirmada. Remova o acesso também na conta Google.")
            except requests.RequestException:
                raise YoutubeError("Sem conexão para revogar. Tente novamente ou remova o acesso no Google.") from None
        self.store.delete()
        self._service = None

    def upload(self, path: str, metadata: dict, cancel: Event, progress: Callable | None = None):
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        metadata = validate_metadata(metadata)
        source = Path(path).expanduser().resolve(strict=True)
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("Vídeo ausente ou vazio.")
        body = {
            "snippet": {
                "title": metadata["title"], "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []), "categoryId": metadata.get("category", "22"),
            },
            "status": {
                "privacyStatus": metadata.get("privacy", "private"),
                "selfDeclaredMadeForKids": metadata["made_for_kids"],
            },
        }
        if metadata.get("publish_at"):
            body["status"]["publishAt"] = metadata["publish_at"]
        if cancel.is_set():
            raise UploadCancelled("Envio cancelado antes de começar.")
        # Construct the authorized service before claiming an upload attempt started.
        api = self._api()
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        if not mime.startswith("video/"):
            mime = "application/octet-stream"
        media = MediaFileUpload(str(source), mimetype=mime, chunksize=8 * 1024 * 1024, resumable=True)
        try:
            request = api.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            transient_failures = 0
            while response is None:
                if cancel.is_set():
                    raise UploadUncertain(
                        "Envio interrompido após iniciar. Verifique o YouTube Studio antes de reenviar."
                    )
                try:
                    status, response = request.next_chunk(num_retries=0)
                    transient_failures = 0
                except HttpError as error:
                    # Reuse the same resumable request/session. The Google client
                    # probes its offset on the next call after a server error.
                    if error.resp.status not in (429, 500, 502, 503, 504) or transient_failures >= 3:
                        raise
                    transient_failures += 1
                    if cancel.wait(2 ** transient_failures):
                        raise UploadUncertain(
                            "Envio interrompido. Confira o YouTube Studio antes de reenviar."
                        ) from None
                    continue
                if status is not None and progress:
                    progress(status.progress())
            remote_id = response.get("id")
            if not remote_id:
                raise UploadUncertain("Resposta sem ID. Verifique o YouTube Studio antes de reenviar.")
            return {"remote_id": remote_id, "url": f"https://www.youtube.com/watch?v={remote_id}", "status": "PROCESSING"}
        except HttpError as error:
            if error.resp.status == 401:
                raise AuthRequired("YouTube recusou a autorização. Reconecte sua conta.") from None
            if error.resp.status in (400, 403, 404):
                raise YoutubeError(
                    "YouTube recusou o envio. Confira dados, permissões, quota e políticas no console."
                ) from None
            raise UploadUncertain("Falha remota durante o envio. Confira o Studio antes de reenviar.") from None
        except (UploadUncertain, UploadCancelled, AuthRequired, YoutubeError):
            raise
        except Exception:
            raise UploadUncertain("Conexão interrompida durante o envio. Confira o Studio antes de reenviar.") from None
        finally:
            stream = media.stream()
            if stream:
                stream.close()

    def check_status(self, remote_id: str):
        try:
            response = self._api().videos().list(
                part="status,processingDetails", id=remote_id,
            ).execute(num_retries=0)
            items = response.get("items", [])
            if not items:
                return {"status": "UNKNOWN_REMOTE_STATUS", "remote_id": remote_id}
            item = items[0]
            state = item.get("status", {})
            processing = item.get("processingDetails", {}).get("processingStatus")
            upload = state.get("uploadStatus")
            if processing in ("failed", "terminated") or upload in ("failed", "rejected", "deleted"):
                result = "FAILED"
            elif processing == "succeeded" and upload == "processed":
                result = "PUBLISHED" if state.get("privacyStatus") == "public" else "UPLOADED_PRIVATE"
            else:
                result = "PROCESSING"
            return {"remote_id": remote_id, "url": f"https://www.youtube.com/watch?v={remote_id}", "status": result}
        except AuthRequired:
            raise
        except Exception:
            raise YoutubeError("Não foi possível verificar o processamento. Nenhum reenvio foi feito.") from None
