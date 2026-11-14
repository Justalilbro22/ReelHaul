"""ReelHaul download engine.

Drives the official standalone yt-dlp.exe binary from a subprocess. Using the
official binary means a packaged ReelHaul can update itself with one command
(``yt-dlp --update``) and needs no Python on the target machine.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Union

from PIL import Image, ImageDraw

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
AUDIO_QUALITIES = {"mp3-320": "mp3", "m4a": "m4a"}
SPONSOR_CATEGORIES = [
    "sponsor",
    "selfpromo",
    "intro",
    "outro",
    "interaction",
    "music_offtopic",
]
YT_DLP_EXE = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"

# info fields (vcodec/acodec/title) come last-ish; the free-text title is the
# final field so a '|' or newline inside it cannot break the other columns.
DL_TEMPLATE = (
    "TGP|%(info.vcodec)s|%(info.acodec)s|%(progress.status)s"
    "|%(progress.downloaded_bytes)s|%(progress.total_bytes)s"
    "|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s"
    "|%(progress.filename)s|%(info.title)s"
)
PP_TEMPLATE = "TPP|%(progress.postprocessor)s|%(progress.status)s"


class EngineError(Exception):
    """A failure with a message that is safe to show to a person."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


class DownloadCancelled(Exception):
    """Raised when the user cancels a running download."""


# ------------------------------------------------------------- environment --

def packaged_dirs() -> list[str]:
    """Folders that may hold bundled tools when ReelHaul runs as a frozen exe."""
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(meipass)
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir:
            candidates.append(exe_dir)
            # A plain PyInstaller build (dist\ReelHaul) keeps the bundled tools
            # in the repo root next to dist\, so search two levels up too.
            parent = os.path.dirname(exe_dir)
            if parent:
                candidates.append(parent)
                grandparent = os.path.dirname(parent)
                if grandparent:
                    candidates.append(grandparent)
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    seen: set[str] = set()
    unique: list[str] = []
    for folder in candidates:
        key = os.path.normcase(os.path.abspath(folder))
        if folder and key not in seen:
            seen.add(key)
            unique.append(folder)
    return unique


def find_ytdlp() -> Optional[str]:
    """Locate the yt-dlp binary (bundled first, then PATH)."""
    for folder in packaged_dirs():
        for relative in ("ytdlp", os.path.join("bundled", "ytdlp"), ""):
            path = os.path.join(folder, relative, YT_DLP_EXE)
            if os.path.isfile(path):
                return path
    return shutil.which("yt-dlp")


def find_ffmpeg() -> Optional[str]:
    """Return the folder containing ffmpeg.exe, or None."""
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
        os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
        r"C:\ffmpeg\bin",
    ]
    for folder in packaged_dirs():
        for relative in (
            "ffmpeg",
            os.path.join("bundled", "ffmpeg", "bin"),
            os.path.join("ffmpeg", "bin"),
            "",
        ):
            candidates.append(os.path.join(folder, relative))
    for folder in candidates:
        if folder and os.path.isfile(os.path.join(folder, "ffmpeg.exe")):
            return folder
    return None


def detect_js_runtimes() -> dict:
    """Pick a JavaScript runtime for YouTube's challenge solving.

    A runtime bundled with ReelHaul (deno.exe next to the app) is preferred so
    4K/8K formats work on machines without any dev tools installed.
    """
    for folder in packaged_dirs():
        for name, relative in (
            ("deno", os.path.join("runtime", "deno.exe")),
            ("node", os.path.join("runtime", "node.exe")),
            ("deno", os.path.join("bundled", "runtime", "deno.exe")),
            ("node", os.path.join("bundled", "runtime", "node.exe")),
            ("deno", "deno.exe"),
            ("node", "node.exe"),
        ):
            path = os.path.join(folder, relative)
            if os.path.isfile(path):
                return {name: {"path": path}}
    for name, exe in (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs")):
        if shutil.which(exe):
            return {name: {}}
    return {}


def _js_runtime_args() -> list[str]:
    args: list[str] = []
    for name, config in detect_js_runtimes().items():
        path = (config or {}).get("path")
        args += ["--js-runtimes", f"{name}:{path}" if path else name]
    return args


def _run_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


_version_cache = ""


def engine_version() -> str:
    """Version reported by the yt-dlp binary (cached)."""
    global _version_cache
    if _version_cache:
        return _version_cache
    version = "unknown"
    exe = find_ytdlp()
    if exe:
        try:
            proc = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=_run_flags(),
            )
            version = (proc.stdout or "").strip() or "unknown"
        except Exception:  # noqa: BLE001
            pass
    _version_cache = version
    return version


def refresh_version() -> str:
    """Re-read the yt-dlp version (used after an in-place self-update)."""
    global _version_cache
    _version_cache = ""
    return engine_version()


# ------------------------------------------------------------------ errors --

def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _clean_error(exc: BaseException) -> str:
    text = strip_ansi(str(exc)).strip()
    return text or exc.__class__.__name__


_BOT_MARKERS = (
    "not a bot",
    "sign in to confirm",
    "use --cookies",
    "cookies-from-browser",
    "sign-in check",
    "signed-in browser",
)


def is_bot_check(exc_or_text: Union[BaseException, str]) -> bool:
    """True when YouTube refused us because of a datacenter/anonymous IP."""
    raw = _clean_error(exc_or_text) if isinstance(exc_or_text, BaseException) else str(exc_or_text)
    if isinstance(exc_or_text, EngineError) and exc_or_text.detail:
        raw += " " + exc_or_text.detail
    low = strip_ansi(raw).lower()
    return any(marker in low for marker in _BOT_MARKERS)


def friendly_error(exc_or_text: Union[BaseException, str]) -> str:
    """Turn yt-dlp's raw error into something a person can act on."""
    if isinstance(exc_or_text, BaseException):
        raw = _clean_error(exc_or_text)
    else:
        raw = strip_ansi(str(exc_or_text)).strip()
    raw = re.sub(r"^ERROR:\s*", "", raw, flags=re.I)
    # Multi-line stderr: the last line usually carries the real message.
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if lines:
        raw = lines[-1]
    low = raw.lower()

    if "not a bot" in low or "sign in to confirm" in low or "use --cookies" in low:
        return (
            "YouTube wants a sign-in check for this video. Choose a signed-in browser "
            "under Cookies (Firefox works best) and try again."
        )
    if "age" in low and ("restrict" in low or "confirm" in low):
        return (
            "This video is age-restricted. Pick a browser you are signed in to under "
            "Cookies, then retry."
        )
    if "private video" in low:
        return "This video is private."
    if "members-only" in low or "join this channel" in low:
        return "This video is for channel members only."
    if "video unavailable" in low:
        return "This video is unavailable (removed, region-locked, or blocked)."
    if "ffmpeg" in low and ("not found" in low or "not installed" in low or "not be found" in low):
        return "ffmpeg is missing. It is required to merge 4K video and audio."
    if "unsupported url" in low:
        return "That link is not supported."
    if "timed out" in low or "timeout" in low:
        return "The connection timed out. Check your internet and try again."
    if "http error 403" in low or "forbidden" in low:
        return (
            "YouTube refused the download (HTTP 403). Try again, or choose a browser "
            "under Cookies."
        )
    if "no space" in low or "disk full" in low:
        return "There is not enough free disk space."
    return raw[:400]


# ------------------------------------------------------------------ formats --

# Menu label -> quality value
QUALITY_CHOICES = [
    ("best", "Best available (up to 8K)"),
    ("2160", "2160p — 4K"),
    ("1440", "1440p — 2K"),
    ("1080", "1080p — Full HD"),
    ("720", "720p — HD"),
    ("480", "480p"),
    ("360", "360p"),
    ("mp3-320", "Audio — MP3 320 kbps"),
    ("m4a", "Audio — M4A (AAC)"),
]
QUALITY_LABELS = dict(QUALITY_CHOICES)
QUALITY_VALUES = {label: value for value, label in QUALITY_CHOICES}


@dataclass
class DownloadOptions:
    outdir: str
    quality: str = "best"
    container: str = "mp4"
    prefer_h264: bool = False
    embed_subs: bool = False
    embed_thumbnail: bool = False
    embed_metadata: bool = False
    sponsorblock: bool = False
    playlist: bool = False
    cookies_browser: str = ""
    ffmpeg_location: str = ""


def build_format(quality: str, prefer_h264: bool = False) -> str:
    """Build a yt-dlp format string for a quality preset."""
    if quality in AUDIO_QUALITIES:
        if quality == "m4a":
            return "bestaudio[ext=m4a]/bestaudio/best"
        return "bestaudio/best"

    if prefer_h264:
        if quality == "best":
            return "bv*[vcodec^=avc1]+ba/b[vcodec^=avc1]/bv*+ba/b"
        height = int(quality)
        return (
            f"bv*[height<={height}][vcodec^=avc1]+ba/b[height<={height}]/"
            f"bv*[height<={height}]+ba/b"
        )

    if quality == "best":
        return "bv*+ba/b"
    height = int(quality)
    return f"bv*[height<={height}]+ba/b[height<={height}]"


# ----------------------------------------------------------------- analyze --

def analyze(url: str, cookies_browser: str = "") -> dict:
    """Fetch metadata about a video or playlist (no download)."""
    exe = find_ytdlp()
    if not exe:
        raise EngineError(
            "The download engine (yt-dlp) is missing. Reinstall ReelHaul.", ""
        )

    args = [
        exe,
        "-J",
        "--no-warnings",
        "--color", "never",
        "--playlist-items", "1",
        "--socket-timeout", "30",
        *_js_runtime_args(),
    ]
    if cookies_browser:
        args += ["--cookies-from-browser", cookies_browser]
    args.append(url)

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            creationflags=_run_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("Reading that video took too long. Try again.", "") from exc

    if proc.returncode != 0 or not (proc.stdout or "").strip():
        message = proc.stderr or proc.stdout or "yt-dlp failed"
        raise EngineError(friendly_error(message), strip_ansi(message)[-900:])

    try:
        info = json.loads(proc.stdout)
    except ValueError as exc:
        raise EngineError(
            "The engine returned data that couldn't be read.", proc.stdout[:600]
        ) from exc

    if not info:
        raise EngineError("No video was found at that link.", "")

    playlist_count = None
    if info.get("_type") == "playlist":
        playlist_count = info.get("playlist_count")
        entries = [entry for entry in (info.get("entries") or []) if entry]
        if not entries:
            raise EngineError("That playlist appears to be empty.", "")
        info = entries[0]

    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if height and vcodec not in (None, "none") and fmt.get("ext") != "mhtml":
            try:
                heights.add(int(height))
            except (TypeError, ValueError):
                continue

    return {
        "title": info.get("title") or "Untitled video",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
        "webpage_url": info.get("webpage_url") or url,
        "heights": sorted(heights, reverse=True),
        "playlist_count": playlist_count,
        "view_count": info.get("view_count"),
        "is_live": bool(info.get("is_live")),
        "extractor": info.get("extractor_key") or "",
    }


def fetch_thumbnail(url: str, size: tuple[int, int] = (356, 200)) -> Optional[Image.Image]:
    """Download and round a thumbnail for the preview panel."""
    if not url:
        return None
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ReelHaul"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize(size, Image.LANCZOS)
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), 12, fill=255)
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        return out
    except Exception:  # noqa: BLE001 - preview art is optional
        return None


# ---------------------------------------------------------------- download --

_PP_LABELS = {
    "Merger": "Merging video + audio",
    "MoveFiles": "Finishing up",
    "FFmpegExtractAudio": "Converting audio",
    "FFmpegVideoConvertor": "Converting video",
    "FFmpegMetadata": "Writing metadata",
    "FFmpegEmbedSubtitle": "Embedding subtitles",
    "EmbedThumbnail": "Embedding thumbnail",
    "FFmpegThumbnailsConvertor": "Preparing thumbnail",
    "SponsorBlock": "Checking sponsor segments",
    "ModifyChapters": "Removing sponsor segments",
}


def _phase_of(vcodec: str, acodec: str) -> str:
    if vcodec in ("none", "", "NA", None):
        return "audio"
    if acodec in ("none", "", "NA", None):
        return "video"
    return "media"


def _to_float(text: str) -> Optional[float]:
    if text in ("", "NA", None):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _snapshot(outdir: str) -> dict[str, str]:
    """Map normcase path -> real path for every file under outdir."""
    found: dict[str, str] = {}
    for root, _dirs, files in os.walk(outdir):
        for name in files:
            path = os.path.join(root, name)
            found[os.path.normcase(path)] = path
    return found


def _watch_cancel(proc: subprocess.Popen, cancel_event: threading.Event) -> None:
    while proc.poll() is None:
        if cancel_event.is_set():
            try:
                proc.kill()
            except OSError:
                pass
            return
        time.sleep(0.08)


def download(
    url: str,
    options: DownloadOptions,
    *,
    on_progress: Optional[Callable[[dict], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
    on_title: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[str]:
    """Download one URL. Returns the final file paths (may be empty)."""
    cancel_event = cancel_event or threading.Event()
    exe = find_ytdlp()
    if not exe:
        raise EngineError(
            "The download engine (yt-dlp) is missing. Reinstall ReelHaul.", ""
        )

    outdir = os.path.abspath(options.outdir)
    os.makedirs(outdir, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="reelhaul-")
    ffmpeg = options.ffmpeg_location or find_ffmpeg() or ""
    before = _snapshot(outdir)

    args = [
        exe,
        "--newline",
        "--no-warnings",
        "--color", "never",
        "--format", build_format(options.quality, options.prefer_h264),
        "--paths", f"home:{outdir}",
        "--paths", f"temp:{tmpdir}",
        "--trim-filenames", "180",
        "--concurrent-fragments", "4",
        "--retries", "10",
        "--fragment-retries", "10",
        "--socket-timeout", "30",
        "--merge-output-format", options.container,
        "--progress-template", f"download:{DL_TEMPLATE}",
        "--progress-template", f"postprocess:{PP_TEMPLATE}",
        *_js_runtime_args(),
    ]
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    if options.cookies_browser:
        args += ["--cookies-from-browser", options.cookies_browser]

    if options.playlist:
        args.append("--yes-playlist")
    else:
        args += ["--playlist-items", "1"]

    if options.quality in AUDIO_QUALITIES:
        codec = AUDIO_QUALITIES[options.quality]
        args += ["--extract-audio", "--audio-format", codec]
        if codec == "mp3":
            args += ["--audio-quality", "320K"]
    if options.embed_metadata:
        args.append("--embed-metadata")
    if options.embed_thumbnail:
        args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    if options.embed_subs:
        args += ["--embed-subs", "--write-auto-subs", "--sub-langs", "en.*"]
    if options.sponsorblock:
        args += ["--sponsorblock-remove", ",".join(SPONSOR_CATEGORIES)]

    args.append(url)

    # Video and audio arrive as separate files. Track both so the bar shows one
    # steady job percentage instead of resetting to zero for the audio stream.
    phase_stats: dict[str, dict[str, float]] = {}

    def report(payload: dict, finished: bool = False) -> None:
        stats = phase_stats.setdefault(payload["phase"], {"downloaded": 0.0, "total": 0.0})
        stats["downloaded"] = float(payload["downloaded"] or 0)
        if payload["total"]:
            stats["total"] = float(payload["total"])
        if finished:
            stats["total"] = max(stats["total"], stats["downloaded"])
            stats["downloaded"] = stats["total"]
        total = sum(entry["total"] for entry in phase_stats.values())
        got = sum(entry["downloaded"] for entry in phase_stats.values())
        if total:
            payload["pct"] = max(0.0, min(100.0, got / total * 100.0))
        elif finished:
            payload["pct"] = 100.0
        if on_progress:
            on_progress(payload)

    def handle_download(fields: list[str]) -> None:
        vcodec, acodec, status = fields[1], fields[2], fields[3]
        downloaded = _to_float(fields[4]) or 0.0
        total = _to_float(fields[5]) or _to_float(fields[6]) or 0.0
        speed = _to_float(fields[7])
        eta = _to_float(fields[8])
        title = fields[10]
        payload = {
            "phase": _phase_of(vcodec, acodec),
            "downloaded": downloaded,
            "total": total,
            "speed": speed,
            "eta": eta,
            "pct": None,
        }
        report(payload, finished=status == "finished")
        if on_title and title not in ("", "NA"):
            on_title(title)

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_run_flags(),
        )
    except OSError as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise EngineError(friendly_error(exc), str(exc)) from exc

    watcher = threading.Thread(target=_watch_cancel, args=(proc, cancel_event), daemon=True)
    watcher.start()

    last_error = ""
    try:
        stream = proc.stdout
        assert stream is not None
        for raw in stream:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("TGP|"):
                fields = line.split("|", 10)
                if len(fields) >= 11:
                    try:
                        handle_download(fields)
                    except (ValueError, IndexError):
                        pass
            elif line.startswith("TPP|"):
                fields = line.split("|", 2)
                if len(fields) >= 3:
                    name, status = fields[1], fields[2]
                    if status == "started" and on_status:
                        on_status(_PP_LABELS.get(name, f"Processing ({name})"))
            elif line.startswith("ERROR:"):
                last_error = line[len("ERROR:"):].strip()
    finally:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        watcher.join(timeout=2)
        shutil.rmtree(tmpdir, ignore_errors=True)

    if cancel_event.is_set():
        raise DownloadCancelled()

    if proc.returncode != 0:
        message = last_error or f"yt-dlp exited with code {proc.returncode}"
        raise EngineError(friendly_error(message), message[-900:])

    after_map = _snapshot(outdir)
    real = [after_map[key] for key in sorted(set(after_map) - set(before))]
    return [os.path.normpath(path) for path in real]
