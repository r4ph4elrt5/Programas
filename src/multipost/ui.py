"""Desktop presentation. Workers never access Tk; results pass through a queue."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable

import customtkinter as ctk
from PIL import Image

from .media import VideoInfo, validate_short

PLATFORMS = {
    "youtube": "YouTube Shorts",
    "instagram": "Instagram Reels",
    "facebook": "Facebook Reels",
    "tiktok": "TikTok",
    "kwai": "Kwai",
}
DESTINATIONS = {
    "youtube": "https://studio.youtube.com/",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "kwai": "https://www.kwai.com/",
}
SECTIONS = (
    "Dashboard", "Nova publicação", "Biblioteca de vídeos", "Fila de publicações",
    "Agendamentos", "Histórico", "Contas conectadas", "Configurações", "Logs e diagnóstico",
)
LABELS = {
    "READY": "Na fila", "SCHEDULED": "Agendado", "VALIDATING": "Validando",
    "UPLOADING": "Enviando", "PROCESSING": "Processando na plataforma",
    "EXPORTING": "Preparando pacote assistido",
    "PUBLISHED": "Publicação confirmada pela API",
    "UPLOADED_PRIVATE": "Enviado; vídeo privado ou não listado",
    "WAITING_USER": "Aguardando publicação manual", "PREPARED": "Pacote preparado",
    "USER_CONFIRMED": "Publicação declarada pelo usuário",
    "USER_CANCELLED": "Cancelado pelo usuário", "CANCELLED": "Cancelado",
    "FAILED": "Falhou", "AUTH_REQUIRED": "Conecte sua conta",
    "APPROVAL_REQUIRED": "Requer aprovação da plataforma",
    "UNKNOWN_REMOTE_STATUS": "Resultado incerto — verificar antes de reenviar",
    "MISSED_SCHEDULE": "Horário perdido — reagende ou envie agora",
}
TERMINAL = {"PUBLISHED", "USER_CONFIRMED", "UPLOADED_PRIVATE", "CANCELLED", "USER_CANCELLED"}


def open_local(path: str | Path) -> None:
    """Use the registered OS application, with no shell interpolation."""
    target = str(Path(path).expanduser().resolve(strict=True))
    if sys.platform == "win32":
        os.startfile(target)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", target])


def parse_schedule(value: str) -> str | None:
    """Explicit offsets are accepted; naive dates use this machine's local zone."""
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("Use AAAA-MM-DD HH:MM, por exemplo 2026-12-01 18:30.") from exc
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("O agendamento precisa estar no futuro.")
    return parsed.isoformat()


class MainWindow(ctk.CTk):
    def __init__(self, service):
        self.service = service
        settings = service.settings()
        ctk.set_appearance_mode(settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("MultiPost Desktop")
        self.geometry("1280x860")
        self.minsize(980, 680)
        self.configure(fg_color=("#F1F5F9", "#0B1120"))
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="multipost-ui")
        self._results = queue.Queue()
        self._closing = False
        self._tick_running = False
        self._busy = 0
        self._draft_after = None
        self._conversion_cancel = threading.Event()
        self._images = []
        self._section = ""
        self._editor_open = False
        self._job_platform = "Todos os destinos"
        self._job_status = "Todos os estados"
        self._last_job_signature = None
        self._last_render_error = None
        self._draft = service.load_draft() or {}
        self._selected_video = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar = ctk.CTkFrame(self, width=225, corner_radius=0,
                                     fg_color=("#FFFFFF", "#111827"))
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        ctk.CTkLabel(self._sidebar, text="MultiPost", font=ctk.CTkFont(size=29, weight="bold"),
                     anchor="w").pack(fill="x", padx=24, pady=(30, 0))
        ctk.CTkLabel(self._sidebar, text="Um vídeo. Cinco destinos.", anchor="w",
                     text_color=("#64748B", "#9CA3AF")).pack(fill="x", padx=24, pady=(4, 25))
        self._nav = {}
        for section in SECTIONS:
            button = ctk.CTkButton(self._sidebar, text=section, height=40, anchor="w",
                                  fg_color="transparent", text_color=("#334155", "#CBD5E1"),
                                  hover_color=("#E2E8F0", "#1F2937"),
                                  command=lambda name=section: self.show(name))
            button.pack(fill="x", padx=14, pady=3)
            self._nav[section] = button
        ctk.CTkLabel(self._sidebar, text="APIs oficiais + publicação assistida\nSeus originais são preservados.",
                     justify="left", text_color=("#64748B", "#9CA3AF"),
                     wraplength=185).pack(side="bottom", padx=20, pady=22)
        self._right = ctk.CTkFrame(self, fg_color="transparent")
        self._right.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        self._right.grid_columnconfigure(0, weight=1)
        self._right.grid_rowconfigure(1, weight=1)
        self._heading = ctk.CTkLabel(self._right, text="", anchor="w",
                                    font=ctk.CTkFont(size=28, weight="bold"))
        self._heading.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self._body = ctk.CTkScrollableFrame(self._right, fg_color="transparent")
        self._body.grid(row=1, column=0, sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)
        self._status = ctk.CTkLabel(self._right, text="Pronto para preparar sua publicação.",
                                   anchor="w", wraplength=800,
                                   text_color=("#475569", "#9CA3AF"))
        self._status.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.show("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain)
        self.after(1500, self._tick)

    def _submit(self, action: Callable, success: Callable | None = None, label="Trabalhando…"):
        if self._closing:
            return
        self._busy += 1
        self._status.configure(text=label)

        def run():
            try:
                result = action()
                self._results.put((success, result, None, True))
            except Exception as exc:
                self._results.put((success, None, exc, True))

        self._pool.submit(run)

    def _drain(self):
        if self._closing:
            return
        try:
            while True:
                callback, result, error, completion = self._results.get_nowait()
                if completion:
                    self._busy = max(0, self._busy - 1)
                if error:
                    self._status.configure(text=f"Não foi possível concluir: {error}")
                    messagebox.showerror("MultiPost", str(error), parent=self)
                else:
                    if completion:
                        self._status.configure(text="Operação concluída.")
                    if callback:
                        callback(result)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _tick(self):
        if self._closing:
            return
        if not self._tick_running:
            self._tick_running = True

            def tick():
                try:
                    self.service.tick()
                except Exception:
                    self._results.put((lambda _: self._status.configure(
                        text="Não foi possível atualizar a fila. Confira os logs e tente novamente."),
                        None, None, False))
                finally:
                    self._results.put((self._tick_done, None, None, False))

            self._pool.submit(tick)
        self.after(2000, self._tick)

    def _tick_done(self, _):
        self._tick_running = False
        if self._section in {"Dashboard", "Fila de publicações", "Agendamentos", "Histórico"}:
            if self._job_signature(self.service.jobs()) != self._last_job_signature:
                fraction = self._body._parent_canvas.yview()[0]
                self.show(self._section)
                self._body._parent_canvas.yview_moveto(fraction)

    @staticmethod
    def _job_signature(jobs):
        return tuple((job["id"], job["status"], job.get("progress"), job.get("error"),
                      job.get("scheduled_at"), job.get("url")) for job in jobs)

    def _clear(self):
        self._images.clear()
        for widget in self._body.winfo_children():
            widget.destroy()

    def show(self, section: str):
        if self._editor_open:
            self._save_editor()
        self._editor_open = False
        if self._draft_after is not None:
            self.after_cancel(self._draft_after)
            self._draft_after = None
        self._section = section
        self._last_render_error = None
        self._heading.configure(text=section)
        for name, button in self._nav.items():
            button.configure(fg_color="#6366F1" if section == name else "transparent",
                             text_color="white" if section == name else ("#334155", "#CBD5E1"))
        self._clear()
        renderers = {
            "Dashboard": self._dashboard, "Nova publicação": self._editor,
            "Biblioteca de vídeos": self._library, "Contas conectadas": self._accounts,
            "Configurações": self._settings, "Logs e diagnóstico": self._diagnostics,
        }
        try:
            renderers.get(section, self._jobs)()
        except Exception as exc:
            self._last_render_error = exc
            self._text(f"Não foi possível carregar esta seção: {exc}")

    def _text(self, text, parent=None, **kwargs):
        max_wrap = kwargs.pop("wraplength", 820)
        label = ctk.CTkLabel(parent or self._body, text=text, anchor="w", justify="left",
                            wraplength=max_wrap, **kwargs)
        label.pack(fill="x", padx=6, pady=7)

        def wrap(event):
            length = max(100, min(max_wrap, event.width - 12))
            if label.cget("wraplength") != length:
                label.configure(wraplength=length)

        # CTkLabel.bind targets its INNER text widget. Measure the fixed-width outer
        # frame instead, so wrapping cannot recursively change its own measurement.
        tk.Misc.bind(label, "<Configure>", wrap, "+")
        return label

    def _card(self, parent=None):
        card = ctk.CTkFrame(parent or self._body, corner_radius=12,
                           fg_color=("#FFFFFF", "#111827"), border_width=1,
                           border_color=("#E2E8F0", "#1F2937"))
        card.pack(fill="x", pady=7, padx=4)
        return card

    def _buttons(self, parent=None):
        bar = ctk.CTkFrame(parent or self._body, fg_color="transparent")
        bar.pack(fill="x", padx=6, pady=10)
        return bar

    def _button(self, parent, text, command, **kwargs):
        button = ctk.CTkButton(parent, text=text, command=command, height=35, **kwargs)
        button.pack(side="left", padx=(0, 8), pady=3)
        return button

    def _dashboard(self):
        jobs = self.service.jobs()
        self._last_job_signature = self._job_signature(jobs)
        videos = self.service.videos()
        self._text("Prepare, acompanhe e confirme suas publicações em um só lugar.",
                   text_color=("#64748B", "#9CA3AF"))
        counts = [
            ("Vídeos na biblioteca", len(videos)),
            ("Confirmadas pela API", sum(j["status"] == "PUBLISHED" for j in jobs)),
            ("Confirmadas por você", sum(j["status"] == "USER_CONFIRMED" for j in jobs)),
            ("Aguardando ação manual", sum(j["status"] == "WAITING_USER" for j in jobs)),
            ("Pendentes / agendadas", sum(j["status"] in {"READY", "SCHEDULED", "UPLOADING", "PROCESSING"} for j in jobs)),
            ("Precisam de atenção", sum(j["status"] in {"FAILED", "AUTH_REQUIRED", "UNKNOWN_REMOTE_STATUS", "MISSED_SCHEDULE"} for j in jobs)),
        ]
        grid = ctk.CTkFrame(self._body, fg_color="transparent")
        grid.pack(fill="x", pady=12)
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="metrics")
        for index, (title, count) in enumerate(counts):
            card = ctk.CTkFrame(grid, fg_color=("#FFFFFF", "#111827"), corner_radius=12)
            card.grid(row=index // 3, column=index % 3, padx=5, pady=5, sticky="nsew")
            ctk.CTkLabel(card, text=str(count), font=ctk.CTkFont(size=32, weight="bold"),
                         text_color=("#4F46E5", "#A5B4FC")).pack(anchor="w", padx=18, pady=(15, 0))
            ctk.CTkLabel(card, text=title, wraplength=210, anchor="w").pack(fill="x", padx=18, pady=(0, 15))
        self._button(self._buttons(), "Criar publicação", lambda: self.show("Nova publicação"))
        self._text("Atividade recente", font=ctk.CTkFont(size=18, weight="bold"))
        if not jobs:
            self._text("Sua fila está vazia. Importe um vídeo e escolha seus destinos para começar.")
        for job in jobs[:5]:
            self._text(f"{PLATFORMS.get(job['platform'], job['platform'])} · {job.get('title', '')}\n"
                       f"{LABELS.get(job['status'], job['status'])}", self._card())

    def _import(self):
        paths = filedialog.askopenfilenames(parent=self, title="Selecionar vídeos",
                                           filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"), ("Todos", "*.*")])
        if not paths:
            return

        def import_all():
            results, failures = [], []
            for path in paths:
                try:
                    results.append(self.service.import_video(path))
                except Exception as exc:
                    failures.append(f"{Path(path).name}: {exc}")
            return results, failures

        def done(value):
            results, failures = value
            if results:
                self._save_editor()
                self._editor_open = False
                self._selected_video = results[-1]["id"]
                self._draft["video_id"] = self._selected_video
            self.show(self._section)
            self._status.configure(text=f"{len(results)} vídeo(s) importado(s).")
            if failures:
                messagebox.showwarning("Arquivos não importados", "\n".join(failures), parent=self)

        self._submit(import_all, done, "Analisando vídeos e gerando miniaturas…")

    def _library(self):
        self._text("Os arquivos originais ficam no seu computador. Conversões geram novos arquivos.")
        self._button(self._buttons(), "Importar vídeos", self._import)
        videos = self.service.videos()
        if not videos:
            self._text("Nenhum vídeo importado. Selecione arquivos MP4, MOV ou outro formato reconhecido pelo FFmpeg.")
        for video in videos:
            card = self._card()
            info = video.get("info", {})
            if isinstance(info, str):
                info = json.loads(info)
            thumb = info.get("thumbnail")
            if thumb and Path(thumb).is_file():
                with Image.open(thumb) as original:
                    preview = original.copy()
                preview.thumbnail((105, 130))
                image = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
                self._images.append(image)
                ctk.CTkLabel(card, image=image, text="").pack(side="left", padx=15, pady=15)
            detail = ctk.CTkFrame(card, fg_color="transparent")
            detail.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            self._text(video.get("name", Path(video["path"]).name), detail,
                       font=ctk.CTkFont(size=17, weight="bold"), wraplength=550)
            self._text(f"{info.get('width', '?')} × {info.get('height', '?')} · "
                       f"{info.get('duration', 0):.1f}s · {info.get('video_codec', '?')} · "
                       f"{info.get('size', 0) / (1024 * 1024):.1f} MB", detail)
            self._text(f"{info.get('fps', 0):.2f} FPS · áudio: {info.get('audio_codec') or 'sem áudio'}\n"
                       f"Importado em: {video.get('created_at', '—')}", detail)
            advice = validate_short(VideoInfo(**info))
            if advice:
                self._text("Revisar compatibilidade: " + " · ".join(advice), detail,
                           wraplength=550, text_color=("#B45309", "#FBBF24"))
            self._text(video["path"] if Path(video["path"]).is_file() else "Arquivo ausente: " + video["path"],
                       detail, wraplength=550, text_color=("#64748B", "#9CA3AF"))
            bar = self._buttons(detail)
            self._button(bar, "Usar vídeo", lambda v=video: self._choose_video(v), width=95)
            self._button(bar, "Abrir prévia", lambda p=video["path"]: self._open(p), width=110)
            if not Path(video["path"]).is_file():
                self._button(self._buttons(detail), "Localizar arquivo novamente",
                             lambda v=video: self._relocate(v), width=180)

    def _relocate(self, video):
        path = filedialog.askopenfilename(parent=self, title="Localizar o mesmo vídeo")
        if path:
            self._submit(lambda: self.service.relocate_video(video["id"], path),
                         lambda _: self.show("Biblioteca de vídeos"), "Verificando identidade do arquivo…")

    def _choose_video(self, video):
        self._selected_video = video["id"]
        self._draft["video_id"] = video["id"]
        self.show("Nova publicação")

    def _open(self, path):
        try:
            open_local(path)
        except Exception as exc:
            messagebox.showerror("Abrir arquivo", str(exc), parent=self)

    def _editor(self):
        videos = self.service.videos()
        self._text("Uma tarefa independente por destino. Você confirma o envio antes de entrar na fila.")
        self._button(self._buttons(), "Importar vídeos", self._import)
        if not videos:
            self._text("Importe um vídeo para começar. O original será preservado.")
            return
        self._video_lookup = {f"{v['id']} · {v.get('name', Path(v['path']).name)}": v for v in videos}
        current_id = self._selected_video or self._draft.get("video_id")
        selected = next((name for name, v in self._video_lookup.items() if v["id"] == current_id),
                        next(iter(self._video_lookup)))
        self._video_var = ctk.StringVar(value=selected)
        ctk.CTkOptionMenu(self._body, variable=self._video_var, values=list(self._video_lookup),
                          command=lambda _: self._video_changed(), width=500).pack(anchor="w", padx=6, pady=8)
        self._video_details = self._text("")
        self._update_video_details()
        conversion = self._buttons()
        self._button(conversion, "Prévia original", lambda: self._open(self._video_lookup[self._video_var.get()]["path"]))
        self._button(conversion, "Gerar vertical com margens", lambda: self._convert("fit"))
        self._button(conversion, "Gerar vertical com corte", lambda: self._convert("crop"))
        self._button(self._buttons(), "Cancelar conversão", self._conversion_cancel.set,
                     fg_color=("#64748B", "#374151"))
        self._text("A conversão vertical gera uma cópia 1080 × 1920. Confira a prévia antes de publicar; "
                   "o corte central pode remover partes da imagem.", text_color=("#64748B", "#9CA3AF"))
        self._title_var = ctk.StringVar(value=self._draft.get("title", ""))
        self._text("Título")
        ctk.CTkEntry(self._body, textvariable=self._title_var, placeholder_text="Título do vídeo").pack(fill="x", padx=6, pady=5)
        self._text("Legenda geral · preserve aqui sua descrição e hashtags")
        self._caption = ctk.CTkTextbox(self._body, height=100)
        self._caption.pack(fill="x", padx=6, pady=5)
        self._caption.insert("1.0", self._draft.get("caption", ""))
        self._caption.bind("<KeyRelease>", lambda _: self._schedule_save())
        self._caption_count = self._text("")
        self._text("Destinos", font=ctk.CTkFont(size=18, weight="bold"))
        self._platform_vars = {}
        self._override_boxes = {}
        self._override_vars = {}
        chosen = self._draft.get("platforms", list(PLATFORMS))
        tabs = ctk.CTkTabview(self._body, height=225)
        tabs.pack(fill="x", padx=6, pady=8)
        for platform, label in PLATFORMS.items():
            tab = tabs.add(label)
            var = ctk.BooleanVar(value=platform in chosen)
            self._platform_vars[platform] = var
            ctk.CTkCheckBox(tab, text="Incluir este destino", variable=var,
                            command=self._schedule_save).pack(anchor="w", padx=5, pady=5)
            custom = ctk.BooleanVar(value=platform in self._draft.get("overrides", {}))
            self._override_vars[platform] = custom
            ctk.CTkCheckBox(tab, text="Usar legenda específica (desmarque para usar a geral)",
                            variable=custom, command=self._schedule_save).pack(anchor="w", padx=5, pady=5)
            box = ctk.CTkTextbox(tab, height=80)
            box.pack(fill="x", padx=5, pady=5)
            box.insert("1.0", self._draft.get("override_texts", {}).get(
                platform, self._draft.get("overrides", {}).get(platform, "")))
            box.bind("<KeyRelease>", lambda _: self._schedule_save())
            self._override_boxes[platform] = box
            self._button(self._buttons(tab), "Copiar legenda", lambda p=platform: self._copy(self._caption_for(p)), width=130)
        self._text("Instagram pessoal, Facebook pessoal, TikTok e Kwai: pacotes assistidos. "
                   "Você conclui a publicação no site ou app oficial.", text_color=("#64748B", "#9CA3AF"))
        youtube = self._card()
        self._text("Opções do YouTube", youtube, font=ctk.CTkFont(size=17, weight="bold"))
        options = self._buttons(youtube)
        self._privacy_var = ctk.StringVar(value=self._draft.get("privacy", "private"))
        ctk.CTkOptionMenu(options, values=["private", "unlisted", "public"], variable=self._privacy_var,
                          command=lambda _: self._schedule_save()).pack(side="left", padx=4)
        kids = self._draft.get("made_for_kids")
        self._kids_var = ctk.StringVar(value="Sim" if kids is True else "Não" if kids is False else "Escolha a classificação")
        ctk.CTkOptionMenu(options, values=["Escolha a classificação", "Sim", "Não"], variable=self._kids_var,
                          command=lambda _: self._schedule_save(), width=220).pack(side="left", padx=8)
        self._text("O conteúdo é destinado a crianças? Escolha Sim ou Não. Privado é o padrão. "
                   "Vídeos verticais não têm classificação Shorts garantida.", youtube)
        self._tags_var = ctk.StringVar(value=self._draft.get("tags_text", ""))
        self._category_var = ctk.StringVar(value=self._draft.get("category", "22"))
        self._text("Tags opcionais separadas por vírgula · categoria numérica (22: Pessoas e blogs)", youtube)
        advanced = self._buttons(youtube)
        ctk.CTkEntry(advanced, textvariable=self._tags_var, width=360,
                     placeholder_text="história, curiosidades").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(advanced, textvariable=self._category_var, width=80).pack(side="left")
        self._text("Agendamento opcional · horário deste computador")
        self._schedule_var = ctk.StringVar(value=self._draft.get("schedule_text", ""))
        ctk.CTkEntry(self._body, textvariable=self._schedule_var,
                     placeholder_text="AAAA-MM-DD HH:MM · deixe vazio para iniciar agora").pack(fill="x", padx=6, pady=5)
        self._text("O aplicativo precisa permanecer aberto. Para destinos assistidos, o horário prepara "
                   "o pacote e a conclusão continua sendo manual.", text_color=("#64748B", "#9CA3AF"))
        bar = self._buttons()
        self._button(bar, "Revisar e criar tarefas", self._create_jobs, fg_color="#6366F1")
        self._button(bar, "Salvar rascunho", self._save_editor, fg_color=("#64748B", "#374151"))
        self._editor_open = True
        for variable in [self._title_var, self._schedule_var, self._tags_var, self._category_var]:
            variable.trace_add("write", lambda *_: self._schedule_save())
        self._update_count()

    def _caption_for(self, platform):
        if self._override_vars[platform].get():
            return self._override_boxes[platform].get("1.0", "end-1c")
        return self._caption.get("1.0", "end-1c")

    def _update_video_details(self):
        video = self._video_lookup[self._video_var.get()]
        info = video["info"]
        advice = validate_short(VideoInfo(**info))
        detail = (f"{info['width']} × {info['height']} · {info['duration']:.1f}s · "
                  f"{info['video_codec']} · {info['fps']:.1f} FPS")
        if advice:
            detail += "\nRevisar antes de publicar: " + " · ".join(advice)
        detail += "\nCompatibilidade final e classificação do vídeo dependem das regras de cada plataforma."
        self._video_details.configure(text=detail)

    def _video_changed(self):
        self._update_video_details()
        self._schedule_save()

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status.configure(text="Legenda copiada.")

    def _update_count(self):
        if self._editor_open:
            self._caption_count.configure(text=f"Título: {len(self._title_var.get())}/100 caracteres · "
                                          f"Legenda geral: {len(self._caption.get('1.0', 'end-1c'))} caracteres")

    def _schedule_save(self):
        if self._draft_after:
            self.after_cancel(self._draft_after)
        self._update_count()
        self._draft_after = self.after(800, self._autosave)

    def _autosave(self):
        self._draft_after = None
        self._save_editor()

    def _save_editor(self):
        if not self._editor_open:
            return
        video = self._video_lookup.get(self._video_var.get())
        self._selected_video = video["id"] if video else None
        self._draft = {
            "video_id": video["id"] if video else None,
            "title": self._title_var.get(), "caption": self._caption.get("1.0", "end-1c"),
            "platforms": [p for p, variable in self._platform_vars.items() if variable.get()],
            "overrides": {p: box.get("1.0", "end-1c") for p, box in self._override_boxes.items()
                          if self._override_vars[p].get()},
            "override_texts": {p: box.get("1.0", "end-1c") for p, box in self._override_boxes.items()},
            "privacy": self._privacy_var.get(),
            "tags_text": self._tags_var.get(), "category": self._category_var.get(),
            "made_for_kids": True if self._kids_var.get() == "Sim" else False if self._kids_var.get() == "Não" else None,
            "schedule_text": self._schedule_var.get(),
        }
        self.service.save_draft(self._draft)

    def _convert(self, mode):
        video = self._video_lookup[self._video_var.get()]
        if mode == "crop" and not messagebox.askyesno("Confirmar corte", "O corte central pode remover "
                                                     "conteúdo das bordas. Gerar uma cópia?", parent=self):
            return
        self._save_editor()
        self._conversion_cancel.clear()

        started = time.monotonic()
        last_report = [0.0]

        def progress(*args):
            elapsed = time.monotonic() - started
            if elapsed - last_report[0] < 0.5:
                return
            last_report[0] = elapsed
            amount = float(args[0]) if args and isinstance(args[0], (float, int)) else 0
            percent = max(0, min(amount * 100 if amount <= 1 else amount, 100))
            eta = f" · restante ~{elapsed * (100 - percent) / percent:.0f}s" if percent > 0 else ""
            text = f"Convertendo · {percent:.0f}% · decorrido {elapsed:.0f}s{eta}"
            self._results.put((lambda _: self._status.configure(text=text), None, None, False))

        def done(result):
            self._save_editor()
            self._editor_open = False
            self._selected_video = result["id"]
            self._draft["video_id"] = result["id"]
            self.show("Nova publicação")
            self._status.configure(text="Cópia convertida. Abra a prévia para conferir o resultado.")

        self._submit(lambda: self.service.prepare_video(video["id"], mode=mode,
                                                        cancel=self._conversion_cancel, progress=progress),
                     done, "Convertendo sem alterar o original…")

    def _create_jobs(self):
        self._save_editor()
        draft = self._draft.copy()
        try:
            scheduled = parse_schedule(draft["schedule_text"])
            if not draft["platforms"]:
                raise ValueError("Selecione ao menos um destino.")
            if "youtube" in draft["platforms"] and draft["made_for_kids"] is None:
                raise ValueError("Informe se o vídeo do YouTube é destinado a crianças.")
        except ValueError as exc:
            messagebox.showerror("Revise a publicação", str(exc), parent=self)
            return
        destinations = ", ".join(PLATFORMS[p] for p in draft["platforms"])
        prompt = f"Título: {draft['title']}\nDestinos: {destinations}\n"
        if "youtube" in draft["platforms"]:
            prompt += f"YouTube: envio oficial com privacidade {draft['privacy']}.\n"
        prompt += "Os outros destinos gerarão pacotes para publicação manual.\n"
        prompt += f"Horário: {scheduled or 'iniciar agora'}.\n\nCriar as tarefas e autorizar este envio?"
        if not messagebox.askyesno("Confirmar publicação", prompt, parent=self):
            return

        def create():
            return self.service.create_publication(
                draft["video_id"], draft["title"], draft["caption"], draft["platforms"], draft["overrides"],
                privacy=draft["privacy"], made_for_kids=draft["made_for_kids"], scheduled_at=scheduled,
                tags=[tag.strip() for tag in draft["tags_text"].split(",") if tag.strip()],
                category=draft["category"].strip(),
            )

        def done(ids):
            self.show("Agendamentos" if scheduled else "Fila de publicações")
            self._status.configure(text=f"{len(ids)} tarefa(s) criada(s). Acompanhe cada destino na fila.")

        self._submit(create, done, "Validando e salvando tarefas…")

    def _jobs(self):
        jobs = self.service.jobs()
        self._last_job_signature = self._job_signature(jobs)
        bar = self._buttons()
        platform_values = ["Todos os destinos", *PLATFORMS.values()]

        def filter_platform(value):
            self._job_platform = value
            self.show(self._section)

        def filter_status(value):
            self._job_status = value
            self.show(self._section)

        ctk.CTkOptionMenu(bar, values=platform_values, variable=ctk.StringVar(value=self._job_platform),
                          command=filter_platform, width=185).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(bar, values=["Todos os estados", *LABELS],
                          variable=ctk.StringVar(value=self._job_status), command=filter_status,
                          width=190).pack(side="left", padx=(0, 8))
        paused = self.service.settings().get("paused", False)

        def pause():
            self.service.save_settings({"paused": not paused})
            self.show(self._section)

        self._button(bar, "Retomar fila" if paused else "Pausar fila", pause, width=115)
        self._text("Fila pausada: tarefas em execução continuam até terminar ou serem canceladas."
                   if paused else "Fila ativa: tarefas autorizadas são processadas em sequência.",
                   text_color=("#64748B", "#9CA3AF"))
        if self._job_platform != "Todos os destinos":
            jobs = [j for j in jobs if PLATFORMS.get(j["platform"]) == self._job_platform]
        if self._job_status != "Todos os estados":
            jobs = [j for j in jobs if j["status"] == self._job_status]
        if self._section == "Agendamentos":
            jobs = [j for j in jobs if j.get("scheduled_at") and j["status"] not in TERMINAL]
            self._text("Horários persistidos em UTC. O computador e o MultiPost precisam estar ligados. "
                       "Horários perdidos exigem sua revisão antes de enviar.")
        elif self._section == "Histórico":
            jobs = [j for j in jobs if j["status"] in TERMINAL | {"FAILED", "UNKNOWN_REMOTE_STATUS"}]
            self._text("Confirmações da API e confirmações declaradas por você aparecem com rótulos diferentes.")
        else:
            jobs = [j for j in jobs if j["status"] not in TERMINAL]
            self._text("O preparo assistido não publica automaticamente. Abra o pacote, publique no destino "
                       "oficial e confirme a conclusão aqui.")
        if not jobs:
            self._text("Nenhuma tarefa nesta seção.")
        for job in jobs:
            card = self._card()
            self._text(f"{PLATFORMS.get(job['platform'], job['platform'])} · {job.get('title', '')}",
                       card, font=ctk.CTkFont(size=17, weight="bold"))
            status = job["status"]
            self._text(f"#{job['id']} · {LABELS.get(status, status)}", card,
                       text_color=("#4F46E5", "#A5B4FC"))
            if job.get("scheduled_at"):
                try:
                    local = datetime.fromisoformat(job["scheduled_at"]).astimezone().strftime("%d/%m/%Y %H:%M %Z")
                except ValueError:
                    local = job["scheduled_at"]
                self._text("Horário: " + local, card)
            if job.get("error"):
                self._text(job["error"], card, text_color=("#B45309", "#FBBF24"))
            if status in {"UPLOADING", "PROCESSING", "VALIDATING"}:
                progress = ctk.CTkProgressBar(card)
                progress.pack(fill="x", padx=12, pady=8)
                value = float(job.get("progress") or 0)
                progress.set(value / 100 if value > 1 else value)
            if job.get("url"):
                self._button(self._buttons(card), "Abrir publicação", lambda url=job["url"]: webbrowser.open(url))
            actions = self._buttons(card)
            if status in {"WAITING_USER", "PREPARED", "USER_CONFIRMED"}:
                self._button(actions, "Copiar legenda", lambda caption=job.get("caption", ""): self._copy(caption), width=115)
                if job.get("export_dir"):
                    self._button(actions, "Abrir pacote", lambda path=job["export_dir"]: self._open(path), width=110)
                self._button(actions, "Destino oficial", lambda p=job["platform"]: webbrowser.open(DESTINATIONS[p]), width=120)
                if status != "USER_CONFIRMED":
                    self._button(self._buttons(card), "Confirmar que publiquei manualmente",
                                 lambda j=job: self._confirm(j), width=280)
            if status in {"FAILED", "AUTH_REQUIRED", "MISSED_SCHEDULE"}:
                self._button(actions, "Tentar agora", lambda j=job: self._retry(j), width=110)
            if status in {"UNKNOWN_REMOTE_STATUS", "PROCESSING"} and job["platform"] == "youtube":
                self._button(actions, "Consultar YouTube", lambda j=job: self._reconcile(j), width=145)
            if status in {"READY", "SCHEDULED", "MISSED_SCHEDULE"}:
                self._button(actions, "Reagendar", lambda j=job: self._reschedule(j), width=100)
            if status not in TERMINAL and status not in {"UNKNOWN_REMOTE_STATUS", "PROCESSING"}:
                self._button(actions, "Cancelar", lambda j=job: self._job_action(self.service.cancel, j["id"]),
                             width=85, fg_color=("#64748B", "#374151"))

    def _job_action(self, action, job_id):
        self._submit(lambda: action(job_id), lambda _: self.show(self._section), "Atualizando tarefa…")

    def _retry(self, job):
        if messagebox.askyesno("Confirmar nova tentativa", "Executar esta tarefa agora? "
                               "Revise a conta, a privacidade e o conteúdo antes de continuar.", parent=self):
            self._job_action(self.service.retry, job["id"])

    def _reschedule(self, job):
        text = simpledialog.askstring("Reagendar tarefa", "Novo horário local: AAAA-MM-DD HH:MM", parent=self)
        if text is None:
            return
        try:
            scheduled = parse_schedule(text)
            if not scheduled:
                raise ValueError("Informe um horário futuro.")
        except ValueError as exc:
            messagebox.showerror("Agendamento", str(exc), parent=self)
            return
        self._submit(lambda: self.service.reschedule(job["id"], scheduled),
                     lambda _: self.show(self._section), "Salvando agendamento…")

    def _reconcile(self, job):
        remote_id = job.get("remote_id")
        if not remote_id:
            remote_id = simpledialog.askstring("Verificar resultado incerto", "Abra o YouTube Studio e "
                                               "localize o vídeo. Informe o ID do vídeo enviado "
                                               "(a parte após v= na URL). Não será feito um novo upload.", parent=self)
            if not remote_id:
                return
        self._submit(lambda: self.service.reconcile(job["id"], remote_id=remote_id.strip()),
                     lambda _: self.show(self._section), "Consultando processamento no YouTube…")

    def _confirm(self, job):
        if not messagebox.askyesno("Confirmação manual", "Você concluiu a publicação no aplicativo ou site oficial? "
                                   "O histórico registrará sua declaração, sem confirmação da API.", parent=self):
            return
        url = simpledialog.askstring("Link da publicação", "Cole o link público, se disponível (opcional):", parent=self)
        if url is not None:
            self._submit(lambda: self.service.confirm_manual(job["id"], url.strip()),
                         lambda _: self.show(self._section))

    def _accounts(self):
        self._text("Nunca digite a senha de uma rede social no MultiPost. O YouTube abre a autorização oficial no navegador.")
        card = self._card()
        self._text("YouTube · integração oficial OAuth 2.0", card, font=ctk.CTkFont(size=18, weight="bold"))
        account_label = self._text("Use Verificar conexão para consultar a conta autorizada.", card)

        def check_account():
            def done(account):
                if account_label.winfo_exists():
                    account_label.configure(text=("Conta conectada: " + account.get("title", "YouTube"))
                                            if account else "Conta não conectada. Importe um cliente OAuth desktop.")
            self._submit(self.service.youtube.account, done, "Verificando a autorização YouTube…")
        self._text("1. Ative a YouTube Data API v3 no Google Cloud.\n"
                   "2. Configure o consentimento e inclua seu usuário de teste, quando aplicável.\n"
                   "3. Crie um cliente OAuth para computador e baixe o JSON.\n"
                   "4. Use Conectar e escolha o arquivo. Autorize no navegador.\n"
                   "Tokens serão guardados no cofre seguro do sistema, nunca no banco ou nos logs.", card)
        bar = self._buttons(card)
        self._button(bar, "Conectar YouTube", self._connect)
        self._button(bar, "Verificar conexão", check_account)
        self._button(bar, "Desconectar", self._disconnect, fg_color=("#64748B", "#374151"))
        self._text("O envio pode ficar restrito a privado em projetos não auditados pelo YouTube. "
                   "A classificação como Short é decidida pela plataforma.", card)
        descriptions = {
            "instagram": "Sua conta pessoal usa publicação assistida. A API de publicação exige conta profissional elegível.",
            "facebook": "Seu perfil pessoal usa publicação assistida. A publicação oficial por API é para Páginas elegíveis.",
            "tiktok": "Publicação assistida. A Content Posting API requer autorização e aprovação do aplicativo e do caso de uso.",
            "kwai": "Publicação assistida. Não há acesso oficial de publicação validado para sua conta brasileira.",
        }
        for platform, description in descriptions.items():
            card = self._card()
            self._text(PLATFORMS[platform] + " · ASSISTED_PUBLISH", card,
                       font=ctk.CTkFont(size=16, weight="bold"))
            self._text(description + " Nenhum login adicional é armazenado pelo MultiPost.", card)
            self._button(self._buttons(card), "Abrir site oficial", lambda p=platform: webbrowser.open(DESTINATIONS[p]))

    def _connect(self):
        path = filedialog.askopenfilename(parent=self, title="Configuração OAuth do Google",
                                         filetypes=[("JSON OAuth para computador", "*.json")])
        if path:
            self._submit(lambda: self.service.youtube.connect(path), lambda _: self.show("Contas conectadas"),
                         "Autorize no navegador oficial. Aguardando retorno do Google…")

    def _disconnect(self):
        if messagebox.askyesno("Desconectar YouTube", "Revogar o acesso e remover as credenciais locais?", parent=self):
            self._submit(self.service.youtube.disconnect, lambda _: self.show("Contas conectadas"))

    def _settings(self):
        self._text("Preferências locais. As alterações são salvas no diretório persistente do aplicativo.")
        card = self._card()
        self._text("Aparência", card, font=ctk.CTkFont(size=18, weight="bold"))
        var = ctk.StringVar(value=self.service.settings().get("theme", "dark"))

        def change(value):
            ctk.set_appearance_mode(value)
            settings = self.service.settings()
            settings["theme"] = value
            self.service.save_settings(settings)

        ctk.CTkOptionMenu(card, values=["dark", "light", "system"], variable=var,
                          command=change).pack(anchor="w", padx=12, pady=12)
        card = self._card()
        self._text("Armazenamento", card, font=ctk.CTkFont(size=18, weight="bold"))
        self._text(str(self.service.data_dir), card)
        self._text("Faça backup deste diretório com o MultiPost fechado. O cofre de credenciais do sistema "
                   "não é incluído no backup: reconecte o YouTube após trocar de computador.", card)
        self._button(self._buttons(card), "Abrir pasta de dados", lambda: self._open(self.service.data_dir))
        self._text("Privacidade: nenhuma senha de rede social é solicitada. Os vídeos originais não são "
                   "sobrescritos. Um pacote assistido só aparece como concluído após sua confirmação.")

    def _diagnostics(self):
        from multipost import __version__

        self._text("Diagnóstico local sem tokens, senhas ou conteúdo das credenciais.")
        data = {
            "aplicativo": __version__, "python": sys.version.split()[0], "sistema": sys.platform,
            "ffmpeg_disponivel": bool(shutil.which("ffmpeg")),
            "ffprobe_disponivel": bool(shutil.which("ffprobe")),
            "diretorio_dados": str(self.service.data_dir),
            "tarefas": len(self.service.jobs()), "videos": len(self.service.videos()),
            "redes_assistidas": ["instagram", "facebook", "tiktok", "kwai"],
            "validacao_remota": "Consulte Contas e o status individual das tarefas; não testado por este relatório.",
        }
        for name, value in data.items():
            self._text(f"{name}: {value}", self._card())

        def export():
            path = filedialog.asksaveasfilename(parent=self, title="Exportar diagnóstico",
                                                defaultextension=".json", initialfile="multipost-diagnostico.json",
                                                filetypes=[("JSON", "*.json")])
            if path:
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self._status.configure(text="Diagnóstico exportado. Revise os caminhos locais antes de compartilhar.")

        bar = self._buttons()
        self._button(bar, "Exportar diagnóstico", export)
        self._button(bar, "Abrir pasta de logs", lambda: self._open(self.service.data_dir / "logs"))

    def _close(self):
        if self._closing:
            return
        if self._busy and not messagebox.askyesno("Encerrar MultiPost", "Há uma operação em andamento. "
                                                  "Solicitar cancelamento e encerrar com segurança?", parent=self):
            return
        if self._editor_open:
            self._save_editor()
        self._closing = True
        self._conversion_cancel.set()
        self._status.configure(text="Encerrando operações com segurança. Aguarde…")
        self.service.request_stop()
        stopped = threading.Event()

        def finish():
            try:
                self._pool.shutdown(wait=True, cancel_futures=True)
                self.service.close()
            finally:
                stopped.set()

        threading.Thread(target=finish, name="multipost-shutdown", daemon=True).start()

        def wait_for_shutdown():
            if stopped.is_set():
                self.destroy()
            else:
                self.after(100, wait_for_shutdown)

        self.after(100, wait_for_shutdown)


def launch(data_dir: Path | None = None, smoke_test: bool = False):
    from multipost.service import AppService

    service = AppService(data_dir)
    window = MainWindow(service)
    if smoke_test:
        failures = []

        def visit(index=0):
            if index >= len(SECTIONS):
                window._close()
                return
            window.show(SECTIONS[index])
            if window._last_render_error:
                failures.append((SECTIONS[index], type(window._last_render_error).__name__))
            window.update_idletasks()
            window.after(80, lambda: visit(index + 1))
        window.after(100, visit)
    window.mainloop()
    if smoke_test and failures:
        raise RuntimeError(f"Falhas ao iniciar telas: {failures}")
