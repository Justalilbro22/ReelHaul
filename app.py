"""ReelHaul — a free 4K/8K video and audio downloader for Windows.

A friendly desktop front-end for yt-dlp. No accounts, no ads, no limits.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

import engine

APP_NAME = "ReelHaul"
BASE_DIR = Path(__file__).resolve().parent
ASSETS = BASE_DIR / "assets"
DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "ReelHaul"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

if os.name == "nt":
    try:
        import ctypes

        # Claim a Windows AppUserModelID so the taskbar shows the app's own
        # icon instead of the Python logo when running from source.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"Justalilbro22.{APP_NAME}"
        )
    except Exception:  # noqa: BLE001
        pass

# ---------------------------------------------------------------- palette ---
BG = "#0A0C11"
CARD = "#11151D"
CARD_2 = "#161C26"
CARD_3 = "#0C1017"
BORDER = "#232A38"
TEXT = "#EEF2F9"
MUTED = "#8A93A6"
DIM = "#5D6678"
ACCENT = "#FF2E4D"
ACCENT_HOVER = "#E01F3C"
GREEN = "#3DDC97"
RED = "#FF6B6B"
YELLOW = "#F5B84B"

COOKIE_CHOICES = ["Off", "Firefox", "Chrome", "Edge", "Brave", "Opera", "Vivaldi"]
CONTAINER_CHOICES = ["MP4", "MKV"]

HEIGHT_LABELS = {
    4320: "4320p — 8K",
    2160: "2160p — 4K",
    1440: "1440p — 2K",
    1080: "1080p — Full HD",
    720: "720p — HD",
    480: "480p",
    360: "360p",
    240: "240p",
    144: "144p",
}

DEFAULT_SETTINGS = {
    "outdir": str(Path.home() / "Downloads" / "ReelHaul"),
    "container": "MP4",
    "cookies": "Off",
    "subs": False,
    "thumb": False,
    "meta": True,
    "sponsor": False,
    "playlist": False,
    "h264": False,
    "quality": "best",
    "geometry": "",
}

log = logging.getLogger("reelhaul")


def setup_logging() -> None:
    handler = logging.FileHandler(DATA_DIR / "reelhaul.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_FILE.exists():
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update({k: v for k, v in loaded.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        log.exception("Could not read settings")
    return settings


def human_bytes(value: float | int | None) -> str:
    if not value:
        return ""
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float | int | None) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def short_title(text: str, limit: int = 88) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def absolute_url(text: str) -> str | None:
    """Normalise a pasted link or bare video id."""
    text = text.strip().strip('"').strip("'")
    if not text:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return f"https://www.youtube.com/watch?v={text}"
    if text.startswith(("http://", "https://")):
        return text
    if re.match(r"^(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com|m\.youtube\.com)/", text):
        return "https://" + text
    if "." in text and " " not in text:
        return "https://" + text
    return None


@dataclass
class Job:
    id: str
    url: str
    title: str
    options: engine.DownloadOptions
    status: str = "Queued"
    pct: float = 0.0
    detail: str = ""
    error: str = ""
    filepaths: list[str] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    row: object = None
    widgets: dict = field(default_factory=dict)
    last_ui: float = 0.0


class ReelHaul(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)

        self.settings = load_settings()
        self.ffmpeg_location = engine.find_ffmpeg() or ""
        self.version = engine.engine_version()
        self.jobs: list[Job] = []
        self.ui_queue: queue.Queue = queue.Queue()
        self.dl_queue: queue.Queue = queue.Queue()
        self._closing = False

        self.title(f"{APP_NAME} — 4K YouTube Downloader")
        self.minsize(940, 720)
        self._restore_geometry()

        try:
            self.iconbitmap(str(ASSETS / "icon.ico"))
        except Exception:  # noqa: BLE001 - icon is cosmetic
            log.debug("icon not available", exc_info=True)

        self._make_fonts()
        self._load_logo()
        self._build_ui()
        self._restore_controls()
        self.bind("<Control-Return>", lambda _e: self.start_downloads())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        for index in range(2):
            threading.Thread(
                target=self._download_worker, name=f"download-{index}", daemon=True
            ).start()

        self.after(60, self._drain_ui)
        self._update_queue_count()
        if not self.ffmpeg_location:
            self._set_status("ffmpeg was not found — 4K merging may fail.", YELLOW)

    # ------------------------------------------------------------- visuals --
    def _make_fonts(self) -> None:
        self.f_brand = ctk.CTkFont("Segoe UI", 22, "bold")
        self.f_h1 = ctk.CTkFont("Segoe UI", 15, "bold")
        self.f_title = ctk.CTkFont("Segoe UI", 14, "bold")
        self.f_body = ctk.CTkFont("Segoe UI", 13)
        self.f_small = ctk.CTkFont("Segoe UI", 12)
        self.f_tiny = ctk.CTkFont("Segoe UI", 11)
        self.f_section = ctk.CTkFont("Segoe UI", 10, "bold")
        self.f_mono = ctk.CTkFont("Consolas", 12)

    def _load_logo(self) -> None:
        self.logo_ctk = None
        self.logo_small_ctk = None
        try:
            from PIL import Image

            logo = Image.open(ASSETS / "logo.png")
            self.logo_ctk = ctk.CTkImage(logo, logo, size=(42, 42))
            self.logo_small_ctk = ctk.CTkImage(logo, logo, size=(40, 40))
        except Exception:  # noqa: BLE001
            log.debug("logo not available", exc_info=True)

    def _restore_geometry(self) -> None:
        geometry = self.settings.get("geometry") or ""
        if re.fullmatch(r"\d+x\d+\+-?\d+\+-?\d+", geometry):
            try:
                self.geometry(geometry)
                return
            except tk.TclError:
                pass
        width, height = 1080, 880
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 24)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _section(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master, text=text, font=self.f_section, text_color=DIM, anchor="w"
        )

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_source_card()
        self._build_options_card()
        self._build_queue_card()
        self._build_footer()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        header.grid_columnconfigure(1, weight=1)

        if self.logo_ctk is not None:
            logo = ctk.CTkLabel(header, text="", image=self.logo_ctk)
            logo.grid(row=0, column=0, rowspan=2, padx=(0, 12))

        title = ctk.CTkLabel(
            header, text=APP_NAME, font=self.f_brand, text_color=TEXT, anchor="w"
        )
        title.grid(row=0, column=1, sticky="sw")
        subtitle = ctk.CTkLabel(
            header,
            text="Free 4K · 8K video & audio downloader",
            font=self.f_small,
            text_color=MUTED,
            anchor="w",
        )
        subtitle.grid(row=1, column=1, sticky="nw", pady=(1, 0))

        status = f"yt-dlp {self.version}"
        status += "   ·   ffmpeg ✓" if self.ffmpeg_location else "   ·   ffmpeg missing"
        self.engine_label = ctk.CTkLabel(
            header,
            text=status,
            font=self.f_tiny,
            text_color=MUTED if self.ffmpeg_location else RED,
            anchor="e",
        )
        self.engine_label.grid(row=0, column=2, sticky="e", padx=(12, 0))

        self.update_btn = ctk.CTkButton(
            header,
            text="Update engine",
            width=104,
            height=26,
            corner_radius=8,
            fg_color="transparent",
            hover_color=CARD_2,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=self.f_tiny,
            command=self.update_engine,
        )
        self.update_btn.grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(4, 0))

    def _build_source_card(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        head.grid_columnconfigure(1, weight=1)
        self._section(head, "LINKS").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text="one per line  ·  videos, playlists & 1000+ other sites",
            font=self.f_tiny,
            text_color=DIM,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.url_box = ctk.CTkTextbox(
            card,
            height=62,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            fg_color=CARD_3,
            text_color=TEXT,
            font=self.f_body,
            wrap="none",
            activate_scrollbars=True,
        )
        self.url_box.grid(row=1, column=0, sticky="ew", padx=18)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 0))
        buttons.grid_columnconfigure(2, weight=1)

        paste = ctk.CTkButton(
            buttons,
            text="Paste",
            width=78,
            height=34,
            corner_radius=9,
            fg_color=CARD_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=self.f_small,
            command=self.paste_link,
        )
        paste.grid(row=0, column=0, sticky="w")

        self.analyze_btn = ctk.CTkButton(
            buttons,
            text="Analyze",
            width=96,
            height=34,
            corner_radius=9,
            fg_color=CARD_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=self.f_small,
            command=self.analyze,
        )
        self.analyze_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.download_btn = ctk.CTkButton(
            buttons,
            text="Download",
            width=170,
            height=36,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            command=self.start_downloads,
        )
        self.download_btn.grid(row=0, column=3, sticky="e")

        preview = ctk.CTkFrame(card, fg_color="transparent")
        preview.grid(row=3, column=0, sticky="ew", padx=18, pady=(12, 16))
        preview.grid_columnconfigure(1, weight=1)

        holder = ctk.CTkFrame(
            preview,
            width=178,
            height=100,
            fg_color=CARD_3,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        holder.grid(row=0, column=0, rowspan=3, sticky="nw")
        holder.grid_propagate(False)
        self.thumb_label = ctk.CTkLabel(
            holder, text="", image=self.logo_small_ctk if self.logo_small_ctk else None
        )
        self.thumb_label.place(relx=0.5, rely=0.5, anchor="center")

        self.preview_title = ctk.CTkLabel(
            preview,
            text="Nothing loaded yet",
            font=self.f_title,
            text_color=TEXT,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.preview_title.grid(row=0, column=1, sticky="ew", padx=(16, 0))
        self.preview_meta = ctk.CTkLabel(
            preview,
            text="Paste a link above and press Analyze — or just hit Download.",
            font=self.f_small,
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.preview_meta.grid(row=1, column=1, sticky="ew", padx=(16, 0), pady=(3, 0))
        self.preview_chips = ctk.CTkLabel(
            preview,
            text="",
            font=self.f_tiny,
            text_color=ACCENT,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.preview_chips.grid(row=2, column=1, sticky="ew", padx=(16, 0), pady=(5, 0))

    def _build_options_card(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        self._section(card, "DOWNLOAD OPTIONS").grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 6)
        )

        menus = ctk.CTkFrame(card, fg_color="transparent")
        menus.grid(row=1, column=0, sticky="ew", padx=18)
        menus.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(menus, text="Quality", font=self.f_small, text_color=MUTED).grid(
            row=0, column=0, padx=(0, 8)
        )
        self.quality_map = {label: value for value, label in engine.QUALITY_CHOICES}
        self.quality_menu = self._menu(
            menus, list(self.quality_map), "Best available (up to 8K)", width=212
        )
        self.quality_menu.grid(row=0, column=1, padx=(0, 18))
        self.quality_menu.configure(command=self._on_option_changed)

        ctk.CTkLabel(menus, text="Container", font=self.f_small, text_color=MUTED).grid(
            row=0, column=2, padx=(0, 8)
        )
        self.container_menu = self._menu(menus, CONTAINER_CHOICES, "MP4", width=88)
        self.container_menu.grid(row=0, column=3, padx=(0, 18))
        self.container_menu.configure(command=self._on_option_changed)

        ctk.CTkLabel(menus, text="Cookies", font=self.f_small, text_color=MUTED).grid(
            row=0, column=4, padx=(0, 8)
        )
        self.cookies_menu = self._menu(menus, COOKIE_CHOICES, "Off", width=112)
        self.cookies_menu.grid(row=0, column=5, sticky="w")
        self.cookies_menu.configure(command=self._on_option_changed)

        checks = ctk.CTkFrame(card, fg_color="transparent")
        checks.grid(row=2, column=0, sticky="w", padx=18, pady=(10, 0))

        self.var_subs = tk.BooleanVar(value=False)
        self.var_thumb = tk.BooleanVar(value=False)
        self.var_meta = tk.BooleanVar(value=True)
        self.var_sponsor = tk.BooleanVar(value=False)
        self.var_playlist = tk.BooleanVar(value=False)
        self.var_h264 = tk.BooleanVar(value=False)

        check_specs = [
            ("Subtitles (EN)", self.var_subs),
            ("Thumbnail", self.var_thumb),
            ("Metadata", self.var_meta),
            ("SponsorBlock", self.var_sponsor),
            ("Full playlist", self.var_playlist),
            ("H.264 only", self.var_h264),
        ]
        for index, (text, variable) in enumerate(check_specs):
            checkbox = ctk.CTkCheckBox(
                checks,
                text=text,
                variable=variable,
                checkbox_width=17,
                checkbox_height=17,
                corner_radius=5,
                border_width=2,
                border_color=BORDER,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                checkmark_color="#FFFFFF",
                text_color=MUTED,
                font=self.f_small,
                command=self._on_check_changed,
            )
            checkbox.grid(row=0, column=index, padx=(0, 20), sticky="w")

        folder = ctk.CTkFrame(card, fg_color="transparent")
        folder.grid(row=3, column=0, sticky="ew", padx=18, pady=(10, 0))
        folder.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(folder, text="Save to", font=self.f_small, text_color=MUTED).grid(
            row=0, column=0, padx=(0, 8)
        )
        self.folder_var = tk.StringVar(value=self.settings["outdir"])
        self.folder_entry = ctk.CTkEntry(
            folder,
            textvariable=self.folder_var,
            height=32,
            corner_radius=9,
            border_width=1,
            border_color=BORDER,
            fg_color=CARD_3,
            text_color=TEXT,
            font=self.f_small,
        )
        self.folder_entry.grid(row=0, column=1, sticky="ew")

        browse = ctk.CTkButton(
            folder,
            text="Browse",
            width=78,
            height=32,
            corner_radius=9,
            fg_color=CARD_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=self.f_small,
            command=self.browse_folder,
        )
        browse.grid(row=0, column=2, padx=(8, 0))

        open_folder = ctk.CTkButton(
            folder,
            text="Open",
            width=62,
            height=32,
            corner_radius=9,
            fg_color="transparent",
            hover_color=CARD_2,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=self.f_small,
            command=lambda: self.open_folder(self.folder_var.get()),
        )
        open_folder.grid(row=0, column=3, padx=(6, 0))

        self.hint_label = ctk.CTkLabel(
            card, text="", font=self.f_tiny, text_color=DIM, anchor="w"
        )
        self.hint_label.grid(row=4, column=0, sticky="ew", padx=18, pady=(8, 14))
        self._update_hint()

    def _menu(self, master, values, default, width: int) -> ctk.CTkOptionMenu:
        menu = ctk.CTkOptionMenu(
            master,
            values=values,
            width=width,
            height=32,
            corner_radius=9,
            fg_color=CARD_2,
            button_color=CARD_2,
            button_hover_color=BORDER,
            text_color=TEXT,
            dropdown_fg_color=CARD_2,
            dropdown_hover_color=BORDER,
            dropdown_text_color=TEXT,
            font=self.f_small,
            dropdown_font=self.f_small,
            dynamic_resizing=False,
            anchor="w",
        )
        if default in values:
            menu.set(default)
        return menu

    def _build_queue_card(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 4))
        head.grid_columnconfigure(2, weight=1)

        self._section(head, "DOWNLOADS").grid(row=0, column=0, sticky="w")
        self.queue_count = ctk.CTkLabel(
            head, text="0 items", font=self.f_tiny, text_color=DIM, anchor="w"
        )
        self.queue_count.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ctk.CTkButton(
            head,
            text="Open downloads folder",
            width=150,
            height=26,
            corner_radius=8,
            fg_color="transparent",
            hover_color=CARD_2,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=self.f_tiny,
            command=lambda: self.open_folder(self.folder_var.get()),
        ).grid(row=0, column=3, sticky="e")

        self.queue_frame = ctk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=DIM,
        )
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))

        self.empty_label = ctk.CTkLabel(
            self.queue_frame,
            text="Your downloads will appear here.\nPaste a link above — 4K, playlists, MP3 and more.",
            font=self.f_small,
            text_color=DIM,
            justify="center",
        )
        self.empty_label.pack(pady=34)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=28, pady=(0, 10))
        footer.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(
            footer, text="Ready", font=self.f_tiny, text_color=MUTED, anchor="w"
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            footer,
            text="Free · no ads · no limits",
            font=self.f_tiny,
            text_color=DIM,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------- settings --
    def _restore_controls(self) -> None:
        s = self.settings
        if s.get("container") in CONTAINER_CHOICES:
            self.container_menu.set(s["container"])
        if s.get("cookies") in COOKIE_CHOICES:
            self.cookies_menu.set(s["cookies"])
        self.var_subs.set(bool(s.get("subs")))
        self.var_thumb.set(bool(s.get("thumb")))
        self.var_meta.set(bool(s.get("meta")))
        self.var_sponsor.set(bool(s.get("sponsor")))
        self.var_playlist.set(bool(s.get("playlist")))
        self.var_h264.set(bool(s.get("h264")))
        quality = s.get("quality", "best")
        for label, value in self.quality_map.items():
            if value == quality:
                self.quality_menu.set(label)
                break
        self._update_hint()

    def _save_settings(self) -> None:
        values = {
            "outdir": self.folder_var.get().strip(),
            "container": self.container_menu.get(),
            "cookies": self.cookies_menu.get(),
            "subs": self.var_subs.get(),
            "thumb": self.var_thumb.get(),
            "meta": self.var_meta.get(),
            "sponsor": self.var_sponsor.get(),
            "playlist": self.var_playlist.get(),
            "h264": self.var_h264.get(),
            "quality": self._quality_value(),
            "geometry": self.geometry(),
        }
        self.settings.update(values)
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self.settings, indent=2), encoding="utf-8"
            )
        except OSError:
            log.exception("Could not save settings")

    def _on_option_changed(self, _value: str | None = None) -> None:
        self._save_settings()

    def _on_check_changed(self) -> None:
        self._update_hint()
        self._save_settings()

    def _update_hint(self) -> None:
        if self.var_h264.get():
            text = "H.264 stops at 1080p on YouTube. Use it only for old players; " \
                   "leave it off for 4K/8K (VP9/AV1 plays in VLC, MPV, Chrome and Windows 11)."
            color = YELLOW
        elif not self.ffmpeg_location:
            text = "ffmpeg is missing — 4K merging, MP3 conversion and embedding will fail."
            color = RED
        else:
            text = "Tip: if YouTube asks you to sign in or confirms you are not a bot, " \
                   "pick your signed-in browser under Cookies and retry."
            color = DIM
        self.hint_label.configure(text=text, text_color=color)

    # ------------------------------------------------------------- helpers --
    def _quality_value(self) -> str:
        return self.quality_map.get(self.quality_menu.get(), "best")

    def _cookies_value(self) -> str:
        choice = self.cookies_menu.get()
        return "" if choice == "Off" else choice.lower()

    def _current_options(self) -> engine.DownloadOptions:
        outdir = self.folder_var.get().strip().strip('"') or str(
            Path.home() / "Downloads" / "ReelHaul"
        )
        self.folder_var.set(outdir)
        options = engine.DownloadOptions(
            outdir=outdir,
            quality=self._quality_value(),
            container=self.container_menu.get().lower(),
            prefer_h264=self.var_h264.get(),
            embed_subs=self.var_subs.get(),
            embed_thumbnail=self.var_thumb.get(),
            embed_metadata=self.var_meta.get(),
            sponsorblock=self.var_sponsor.get(),
            playlist=self.var_playlist.get(),
            cookies_browser=self._cookies_value(),
            ffmpeg_location=self.ffmpeg_location,
        )
        return options

    def _collect_urls(self) -> list[str]:
        raw = self.url_box.get("1.0", "end").strip()
        if not raw:
            return []
        found: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            urls = re.findall(r"https?://[^\s\"'<>]+", line)
            if urls:
                found.extend(urls)
                continue
            url = absolute_url(line.split()[0])
            if url:
                found.append(url)
        seen: set[str] = set()
        unique: list[str] = []
        for url in found:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    def _set_status(self, text: str, color: str = MUTED) -> None:
        try:
            self.status_label.configure(text=text, text_color=color)
        except tk.TclError:
            pass

    def _post(self, callback, *args) -> None:
        self.ui_queue.put((callback, args))

    def _drain_ui(self) -> None:
        try:
            while True:
                try:
                    callback, args = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    callback(*args)
                except Exception:  # noqa: BLE001 - one bad callback must not stop the loop
                    log.exception("UI callback failed")
        finally:
            if not self._closing:
                try:
                    self.after(60, self._drain_ui)
                except tk.TclError:
                    pass

    def _update_queue_count(self) -> None:
        active = sum(1 for job in self.jobs if job.status in ("Queued", "Downloading"))
        done = sum(1 for job in self.jobs if job.status == "Done")
        if not self.jobs:
            text = "0 items"
        elif active:
            text = f"{active} active · {done} done"
        else:
            text = f"{len(self.jobs)} items"
        try:
            self.queue_count.configure(text=text)
        except tk.TclError:
            pass

    # --------------------------------------------------------------- input --
    def paste_link(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        text = (text or "").strip()
        if not text:
            return
        current = self.url_box.get("1.0", "end").strip()
        if current:
            self.url_box.insert("end", "\n" + text)
        else:
            self.url_box.delete("1.0", "end")
            self.url_box.insert("1.0", text)
        urls = self._collect_urls()
        if not current and len(urls) == 1:
            self.after(50, self.analyze)
        else:
            self._set_status(f"{len(urls)} link(s) ready — press Analyze or Download.")

    def browse_folder(self) -> None:
        initial = self.folder_var.get().strip() or str(Path.home() / "Downloads")
        chosen = filedialog.askdirectory(parent=self, initialdir=initial, title="Choose a download folder")
        if chosen:
            self.folder_var.set(chosen)
            self._save_settings()

    def open_folder(self, folder: str) -> None:
        folder = (folder or "").strip().strip('"')
        if not folder:
            return
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError:
            self._set_status("Could not open that folder.", RED)

    # ------------------------------------------------------------- analyze --
    def analyze(self) -> None:
        urls = self._collect_urls()
        if not urls:
            self._set_status("Paste a video link first.", YELLOW)
            return
        self.analyze_btn.configure(state="disabled", text="Analyzing…")
        self._set_status("Reading video info…")
        threading.Thread(
            target=self._analyze_worker,
            args=(urls[0], self._cookies_value()),
            daemon=True,
        ).start()

    def _analyze_worker(self, url: str, cookies: str) -> None:
        try:
            info = engine.analyze(url, cookies)
            image = engine.fetch_thumbnail(info.get("thumbnail") or "", (356, 200))
            self._post(self._apply_preview, info, image)
        except engine.EngineError as exc:
            self._post(self._analyze_failed, exc.message)
        except Exception as exc:  # noqa: BLE001
            log.exception("Analyze failed")
            self._post(self._analyze_failed, engine.friendly_error(exc))

    def _apply_preview(self, info: dict, image) -> None:
        self.analyze_btn.configure(state="normal", text="Analyze")
        if image is not None:
            self.thumb_image = ctk.CTkImage(image, image, size=(178, 100))
            self.thumb_label.configure(image=self.thumb_image, text="")
        self.preview_title.configure(text=short_title(info["title"], 110))

        meta = []
        if info.get("uploader"):
            meta.append(info["uploader"])
        if info.get("duration"):
            meta.append(human_duration(info["duration"]))
        if info.get("view_count"):
            meta.append(f"{info['view_count']:,} views")
        self.preview_meta.configure(
            text="  ·  ".join(meta) or "Video loaded", text_color=MUTED
        )

        chips = []
        heights = info.get("heights") or []
        if heights:
            chips.append("Available: " + " · ".join(
                "8K" if h >= 4320 else "4K" if h >= 2160 else f"{h}p" for h in heights[:6]
            ))
        if info.get("playlist_count"):
            chips.append(
                f"Playlist · {info['playlist_count']} videos — tick Full playlist to get all"
            )
        self.preview_chips.configure(text="        ".join(chips))

        self._rebuild_quality_menu(heights)
        self._set_status("Video info loaded.")
        self._save_settings()

    def _rebuild_quality_menu(self, heights: list[int]) -> None:
        current = self._quality_value()
        mapping: dict[str, str] = {}
        mapping["Best available (up to 8K)"] = "best"
        if heights:
            for height in heights:
                if height in HEIGHT_LABELS:
                    mapping[f"{HEIGHT_LABELS[height]}"] = str(height)
                elif height > 144:
                    mapping[f"{height}p"] = str(height)
        else:
            for value, label in engine.QUALITY_CHOICES:
                if value.isdigit():
                    mapping[label] = value
        for value, label in engine.QUALITY_CHOICES:
            if value in ("mp3-320", "m4a"):
                mapping[label] = value

        self.quality_map = mapping
        labels = list(mapping)
        self.quality_menu.configure(values=labels)
        chosen = next((label for label, value in mapping.items() if value == current), None)
        self.quality_menu.set(chosen or labels[0])

    def _analyze_failed(self, message: str) -> None:
        self.analyze_btn.configure(state="normal", text="Analyze")
        self.preview_title.configure(text="Couldn't read that link")
        self.preview_meta.configure(text=message, text_color=RED)
        self.preview_chips.configure(text="")
        self._set_status(message, RED)

    # ------------------------------------------------------------ downloads --
    def start_downloads(self) -> None:
        urls = self._collect_urls()
        if not urls:
            self._set_status("Paste a video link first.", YELLOW)
            return
        options = self._current_options()
        try:
            os.makedirs(options.outdir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Folder problem",
                f"Can't create the download folder:\n{options.outdir}\n\n{exc}",
                parent=self,
            )
            return

        for url in urls:
            job = Job(
                id=uuid.uuid4().hex,
                url=url,
                title=short_title(url, 78),
                options=options,
            )
            self._create_row(job)
            self.jobs.append(job)
            self.dl_queue.put(job)

        self._update_queue_count()
        self._set_status(f"Queued {len(urls)} download(s).")
        self._save_settings()

    def _create_row(self, job: Job) -> None:
        self.empty_label.pack_forget()

        row = ctk.CTkFrame(self.queue_frame, fg_color=CARD_2, corner_radius=11)
        row.pack(fill="x", padx=4, pady=4)
        row.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            row,
            text=job.title,
            font=self.f_body,
            text_color=TEXT,
            anchor="w",
            justify="left",
        )
        title.grid(row=0, column=0, sticky="ew", padx=(14, 10), pady=(8, 0))

        pct = ctk.CTkLabel(
            row,
            text="0%",
            width=46,
            font=self.f_small,
            text_color=MUTED,
            anchor="e",
        )
        pct.grid(row=0, column=1, sticky="e", pady=(8, 0))

        action = ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=26,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#2A3140",
            text_color=MUTED,
            font=self.f_small,
            command=lambda: self._row_action(job),
        )
        action.grid(row=0, column=2, padx=(6, 8), pady=(6, 0))

        status = ctk.CTkLabel(
            row,
            text="Queued",
            font=self.f_tiny,
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(14, 8))

        bar = ctk.CTkProgressBar(
            row,
            height=4,
            corner_radius=2,
            fg_color="#242B38",
            progress_color=ACCENT,
        )
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(7, 10))
        bar.set(0)
        bar.configure(mode="determinate")

        job.row = row
        job.widgets = {
            "title": title,
            "pct": pct,
            "action": action,
            "status": status,
            "bar": bar,
        }
        for widget in (row, title, status):
            widget.bind("<Button-1>", lambda _e, j=job: self._show_job_error(j))

    def _download_worker(self) -> None:
        while True:
            job = self.dl_queue.get()
            try:
                if job.cancel.is_set():
                    self._post(self._mark_cancelled, job)
                    continue
                self._post(self._mark_started, job)
                try:
                    paths = engine.download(
                        job.url,
                        job.options,
                        on_progress=lambda payload, j=job: self._on_progress(j, payload),
                        on_status=lambda text, j=job: self._post(self._set_job_status, j, text),
                        on_title=lambda text, j=job: self._post(self._set_job_title, j, text),
                        cancel_event=job.cancel,
                    )
                    self._post(self._mark_done, job, paths)
                except engine.DownloadCancelled:
                    self._post(self._mark_cancelled, job)
                except engine.EngineError as exc:
                    log.warning("Download failed: %s\n%s", exc.message, exc.detail)
                    self._post(self._mark_failed, job, exc.message, exc.detail)
                except Exception as exc:  # noqa: BLE001
                    log.exception("Unexpected download error")
                    message = engine.friendly_error(exc)
                    self._post(self._mark_failed, job, message, traceback.format_exc())
            finally:
                self.dl_queue.task_done()

    def _on_progress(self, job: Job, payload: dict) -> None:
        now = time.monotonic()
        if now - job.last_ui < 0.1:
            return
        job.last_ui = now
        self._post(self._render_progress, job, payload)

    def _render_progress(self, job: Job, payload: dict) -> None:
        if job.status in ("Done", "Failed", "Cancelled"):
            return
        widgets = job.widgets
        if not widgets:
            return
        pct = payload.get("pct")
        if pct is not None:
            pct = max(0.0, min(100.0, float(pct)))
            job.pct = pct
            widgets["bar"].set(pct / 100)
            widgets["pct"].configure(text=f"{pct:.0f}%")

        parts = []
        phase = payload.get("phase")
        if phase == "video":
            parts.append("Video")
        elif phase == "audio":
            parts.append("Audio")
        downloaded = payload.get("downloaded") or 0
        total = payload.get("total") or 0
        if total:
            parts.append(f"{human_bytes(downloaded)} / {human_bytes(total)}")
        speed = payload.get("speed")
        if speed:
            parts.append(f"{human_bytes(speed)}/s")
        eta = payload.get("eta")
        if eta:
            parts.append(f"ETA {human_duration(eta)}")
        widgets["status"].configure(
            text="  ·  ".join(parts) if parts else "Downloading…",
            text_color=MUTED,
        )

    def _set_job_status(self, job: Job, text: str) -> None:
        if job.status in ("Done", "Failed", "Cancelled") or not job.widgets:
            return
        if text == "Processing…":
            job.status = "Downloading"
            job.pct = 100
            job.widgets["bar"].set(1)
            job.widgets["pct"].configure(text="100%")
        job.widgets["status"].configure(text=text, text_color=MUTED)

    def _set_job_title(self, job: Job, title: str) -> None:
        job.title = short_title(title, 78)
        if job.widgets:
            job.widgets["title"].configure(text=job.title)

    def _mark_started(self, job: Job) -> None:
        job.status = "Downloading"
        if job.widgets:
            job.widgets["status"].configure(text="Starting…", text_color=MUTED)
            job.widgets["bar"].configure(progress_color=ACCENT)
        self._update_queue_count()

    def _mark_done(self, job: Job, paths: list[str]) -> None:
        job.status = "Done"
        job.pct = 100
        job.filepaths = [p for p in paths if p and os.path.exists(p)]
        if job.widgets:
            job.widgets["bar"].configure(progress_color=GREEN)
            job.widgets["bar"].set(1)
            job.widgets["pct"].configure(text="100%", text_color=GREEN)
            if job.filepaths:
                if len(job.filepaths) == 1:
                    text = f"Saved  ·  {os.path.basename(job.filepaths[0])}"
                else:
                    text = f"Saved {len(job.filepaths)} files"
            else:
                text = "Finished"
            job.widgets["status"].configure(text=text, text_color=GREEN)
            job.widgets["action"].configure(text="Open", width=50, state="normal")
        self._update_queue_count()
        if not any(j.status in ("Queued", "Downloading") for j in self.jobs):
            self._set_status("All downloads finished.")
            try:
                self.bell()
            except tk.TclError:
                pass

    def _mark_failed(self, job: Job, message: str, detail: str) -> None:
        job.status = "Failed"
        job.error = message
        job.detail = detail
        if job.widgets:
            job.widgets["bar"].configure(progress_color=RED)
            job.widgets["bar"].set(0)
            job.widgets["pct"].configure(text="—", text_color=RED)
            job.widgets["status"].configure(
                text="Failed — click this row for details", text_color=RED
            )
            job.widgets["action"].configure(text="Retry", width=50, state="normal")
        self._set_status(f"Download failed: {message}", RED)
        self._update_queue_count()

    def _mark_cancelled(self, job: Job) -> None:
        if job.status == "Done":
            return
        job.status = "Cancelled"
        if job.widgets:
            job.widgets["bar"].configure(progress_color=DIM)
            job.widgets["bar"].set(0)
            job.widgets["pct"].configure(text="—", text_color=MUTED)
            job.widgets["status"].configure(text="Cancelled", text_color=MUTED)
            job.widgets["action"].configure(text="Retry", width=50, state="normal")
        self._update_queue_count()

    def _row_action(self, job: Job) -> None:
        if job.status in ("Queued", "Downloading"):
            self._cancel_job(job)
        elif job.status == "Done":
            self._open_job(job)
        else:
            self._retry_job(job)

    def _cancel_job(self, job: Job) -> None:
        job.cancel.set()
        if job.status == "Queued":
            self._mark_cancelled(job)
            self._set_status("Download cancelled.")
        else:
            if job.widgets:
                job.widgets["status"].configure(text="Cancelling…", text_color=YELLOW)
            self._set_status("Cancelling…")

    def _retry_job(self, job: Job) -> None:
        job.cancel.clear()
        job.status = "Queued"
        job.pct = 0
        job.error = ""
        job.detail = ""
        job.filepaths = []
        if job.widgets:
            job.widgets["bar"].configure(progress_color=ACCENT)
            job.widgets["bar"].set(0)
            job.widgets["pct"].configure(text="0%", text_color=MUTED)
            job.widgets["status"].configure(text="Queued", text_color=MUTED)
            job.widgets["action"].configure(text="✕", width=28, state="normal")
        self.dl_queue.put(job)
        self._update_queue_count()
        self._set_status("Retrying…")

    def _open_job(self, job: Job) -> None:
        if len(job.filepaths) == 1:
            path = os.path.normpath(job.filepaths[0])
            if os.path.exists(path):
                try:
                    subprocess.Popen(["explorer", f"/select,{path}"])
                    return
                except OSError:
                    pass
        self.open_folder(job.options.outdir)

    def _show_job_error(self, job: Job) -> None:
        if not job.error:
            return
        detail = job.detail.strip()
        message = job.error
        if detail and detail not in message:
            message += "\n\nDetails:\n" + detail[-1200:]
        messagebox.showerror("Download failed", message[:2200], parent=self)

    # -------------------------------------------------------------- updates --
    def update_engine(self) -> None:
        if str(self.update_btn.cget("state")) == "disabled":
            return
        self.update_btn.configure(state="disabled", text="Updating…")
        self._set_status("Updating yt-dlp…")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self) -> None:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            exe = engine.find_ytdlp()
            if exe:
                # The official standalone binary updates itself in place.
                proc = subprocess.run(
                    [exe, "--update"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=flags,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                self._post(self._update_done, proc.returncode == 0, output)
                return
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=600,
                creationflags=flags,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            self._post(self._update_done, proc.returncode == 0, output)
        except subprocess.TimeoutExpired:
            self._post(self._update_done, False, "The update timed out. Check your connection.")
        except Exception as exc:  # noqa: BLE001
            log.exception("Update failed")
            self._post(self._update_done, False, str(exc))

    def _update_done(self, ok: bool, output: str) -> None:
        self.update_btn.configure(state="normal", text="Update engine")
        if not ok:
            self._set_status("Update failed.", RED)
            messagebox.showerror(
                "Update failed",
                (output or "yt-dlp could not update itself.")[-1500:],
                parent=self,
            )
            return
        new_version = engine.refresh_version()
        self.engine_label.configure(
            text=f"yt-dlp {new_version}   ·   " + ("ffmpeg ✓" if self.ffmpeg_location else "ffmpeg missing")
        )
        self._set_status(f"yt-dlp {new_version} installed.")
        if messagebox.askyesno(
            "Engine updated",
            f"yt-dlp {new_version} is installed.\nRestart ReelHaul now to use it?",
            parent=self,
        ):
            self._restart()

    def _restart(self) -> None:
        self._closing = True
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable, str(BASE_DIR / "app.py")])
        finally:
            self.destroy()

    def _on_close(self) -> None:
        active = [j for j in self.jobs if j.status in ("Queued", "Downloading")]
        if active:
            if not messagebox.askyesno(
                "Quit ReelHaul?",
                f"{len(active)} download(s) are still running. Quit anyway?",
                parent=self,
            ):
                return
        self._closing = True
        self._save_settings()
        self.destroy()

    def run(self) -> None:
        self.mainloop()


def run_selftest() -> int:
    """Headless validation used for packaged builds (--selftest)."""
    results = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "engine_exe": engine.find_ytdlp() or "",
        "yt_dlp_version": engine.engine_version(),
        "ffmpeg_dir": engine.find_ffmpeg() or "",
        "js_runtimes": engine.detect_js_runtimes(),
        "gui_ok": False,
        "analyze_ok": False,
        "analyze_blocked": False,
        "heights": [],
        "errors": [],
    }
    try:
        root = ctk.CTk()
        root.withdraw()
        root.update()
        root.destroy()
        results["gui_ok"] = True
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(f"gui: {exc}")
    try:
        info = engine.analyze("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        results["heights"] = info["heights"]
        results["analyze_ok"] = True
    except engine.EngineError as exc:
        if engine.is_bot_check(exc):
            # Datacenter IPs (CI runners) get YouTube's bot check regardless of
            # the build's health - engine mechanics above are already verified.
            results["analyze_blocked"] = True
        else:
            results["errors"].append(f"analyze: {exc}")
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(f"analyze: {exc}")
    try:
        (DATA_DIR / "selftest.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
    healthy = (
        bool(results["engine_exe"])
        and bool(results["ffmpeg_dir"])
        and bool(results["js_runtimes"])
        and results["gui_ok"]
        and (results["analyze_ok"] or results["analyze_blocked"])
    )
    return 0 if healthy else 1


def main() -> int:
    setup_logging()
    if "--selftest" in sys.argv:
        return run_selftest()
    try:
        ReelHaul().run()
        return 0
    except Exception:  # noqa: BLE001 - last resort for a windowless launcher
        log.exception("ReelHaul crashed")
        try:
            messagebox.showerror(
                "ReelHaul crashed",
                "Something went wrong while starting ReelHaul.\n\n"
                + traceback.format_exc(limit=4),
            )
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
