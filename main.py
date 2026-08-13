"""Watch a folder and upload new images/videos to a Zipline instance.
"""

import logging
import sys
import webbrowser
from collections import OrderedDict
from mimetypes import guess_type
from os import getenv
from os.path import basename, dirname, exists, getsize, isfile, join, splitext
from queue import Queue
from threading import Event, Lock, Thread, Timer
from time import monotonic, sleep
from typing import Dict, List
from urllib.parse import urlparse

import pyperclip
import requests
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

VALID_EXTENSIONS: List[str] = [".png", ".jpg", ".jpeg", ".mov"]
VALID_EXTENSIONS_SET = {ext.lower() for ext in VALID_EXTENSIONS}  # .PNG, .Mov, etc.
MAX_FILE_SIZE_MB: int = 40

# created + a burst of modified while the OS is still writing (screenshots, .mov).
STABLE_QUIET_S: float = 0.4
STABLE_TIMEOUT_S: float = 120  # long screen recordings
RECENT_COOLDOWN_S: float = 2.0  # Finder/Spotlight often touch the file again after save
UPLOAD_TIMEOUT_FLOOR_S: float = 30.0
UPLOAD_BYTES_PER_S: float = 256 * 1024
UPLOAD_ATTEMPTS: int = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}

# https://zipline.diced.sh/docs/guides/upload-options
UPLOAD_OPTIONS: Dict[str, str] = {
    "x-zipline-format": "random",
    "x-zipline-original-name": "false",
}

ENV_PATH = join(dirname(__file__), ".env")
load_dotenv(ENV_PATH)  # no-op if missing; _require() is what fails

log = logging.getLogger("zipline")

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GRAY = "\033[38;5;244m"
_VIOLET = "\033[38;2;167;139;250m"
_CYAN = "\033[38;2;103;232;249m"
_GREEN = "\033[38;2;52;211;153m"
_AMBER = "\033[38;2;251;191;36m"
_ROSE = "\033[38;2;251;113;133m"
_BLUE = "\033[38;2;147;197;253m"

_LEVEL_STYLE = {
    logging.DEBUG: (_BLUE, "DEBUG"),
    logging.INFO: (_GREEN, " INFO"),
    logging.WARNING: (_AMBER, " WARN"),
    logging.ERROR: (_ROSE, "ERROR"),
    logging.CRITICAL: (_ROSE, "ERROR"),
}


def _use_color() -> bool:
    explicit = (getenv("LOG_COLOR") or "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    if getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _paint(text: str, code: str = "", bold: bool = False) -> str:
    if not _use_color():
        return text
    return f"{_BOLD if bold else ''}{code}{text}{_RESET}"


def _gradient_rule(width: int = 52) -> str:
    if not _use_color():
        return "━" * width
    chunks = []
    for i in range(width):
        t = i / max(width - 1, 1)
        r = int(139 + (34 - 139) * t)
        g = int(92 + (211 - 92) * t)
        b = int(246 + (238 - 246) * t)
        chunks.append(f"\033[38;2;{r};{g};{b}m━")
    return "".join(chunks) + _RESET


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        time = self.formatTime(record, self.datefmt)
        code, label = _LEVEL_STYLE.get(record.levelno, (_GRAY, record.levelname))
        return f"{_paint(time, _GRAY)} {_paint(label, code, bold=True)}  {record.getMessage()}"


def _setup_logging() -> None:
    level_name = (getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO

    plain = logging.Formatter("%(asctime)s %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(_ColorFormatter(datefmt="%H:%M:%S") if _use_color() else plain)

    handlers: List[logging.Handler] = [stream]
    log_file = (getenv("LOG_FILE") or "").strip()
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(plain)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)


_setup_logging()


class ConfigError(SystemExit):
    """Missing/placeholder .env values. Subclasses SystemExit so we skip a traceback."""


def _require(name: str) -> str:
    """Required env var. Rejects empty strings and leftover <placeholders>."""
    raw = getenv(name)
    if raw is None:
        raise ConfigError(
            f"\n  {name} is not set.\n"
            f"  Copy .env.example to .env and fill it in\n"
        )
    value = raw.strip()
    if not value or value.startswith("<") or value.lower() in {"changeme", "your_access_token_here"}:
        raise ConfigError(
            f"\n  {name} still looks like a placeholder ({value!r}).\n"
            f"  Open .env and put the real value in.\n"
        )
    return value


def _truthy(name: str, default: bool = False) -> bool:
    raw = getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _mask(secret: str) -> str:
    """Last 4 chars only"""
    if len(secret) <= 8:
        return "••••"
    return f"••••{secret[-4:]}"


MONITOR_FOLDER_PATH: str = _require("MONITOR_FOLDER_PATH")
API_UPLOAD_URL: str = _require("ZIPLINE_UPLOAD_URL")
USER_ACCESS_TOKEN: str = _require("ZIPLINE_TOKEN")
OPEN_URL_IN_BROWSER: bool = _truthy("OPEN_URL_IN_BROWSER", default=False)


def print_banner() -> None:
    host = urlparse(API_UPLOAD_URL).netloc or API_UPLOAD_URL
    types = ", ".join(ext.lstrip(".") for ext in VALID_EXTENSIONS)
    rule = _gradient_rule()
    config_source = ".env loaded" if exists(ENV_PATH) else "defaults (no .env — copy .env.example)"
    browser = (
        _paint("enabled", _GREEN) if OPEN_URL_IN_BROWSER else _paint("disabled", _AMBER)
    )

    def row(label: str, value: str) -> None:
        print(f"  {_paint(f'{label:<12}', _GRAY)} {value}")

    print()
    print(f"  {_paint('ZIPLINE', _VIOLET, bold=True)} {_paint('auto-upload', _GRAY)}")
    print(f"  {rule}")
    row("Folder", MONITOR_FOLDER_PATH)
    row("Host", _paint(host, _CYAN))
    row("Token", _mask(USER_ACCESS_TOKEN))
    row("Types", types)
    row("Limit", f"{MAX_FILE_SIZE_MB} MB")
    row("Browser", browser)
    row("Config", config_source)
    print(f"  {rule}")
    print(
        f"  {_paint('Ready to upload.', _GREEN, bold=True)} "
        f"{_paint('Ctrl+C to stop · LOG_LEVEL=DEBUG for more detail', _GRAY)}"
    )
    print()


def validate_file(path: str) -> bool:
    """True if this path is a non-hidden file we should upload."""
    # .DS_Store, AppleDouble, screenshot temps
    if not isfile(path) or basename(path).startswith("."):
        return False

    if splitext(path)[1].lower() not in VALID_EXTENSIONS_SET:
        log.warning("%s: unsupported extension (want %s)",
                    basename(path), ", ".join(VALID_EXTENSIONS))
        return False

    # 1 << 20 == 1 MiB. `>=` means exactly MAX_FILE_SIZE_MB is also rejected.
    if getsize(path) >= MAX_FILE_SIZE_MB * (1 << 20):
        log.warning("%s: %.2f MB exceeds %s MB limit",
                    basename(path), getsize(path) / (1 << 20), MAX_FILE_SIZE_MB)
        return False

    return True


def wait_until_stable(path: str) -> bool:
    """True once size is unchanged for STABLE_QUIET_S. False if it vanishes or times out."""
    deadline = monotonic() + STABLE_TIMEOUT_S
    last_size = -1
    last_change = monotonic()
    while monotonic() < deadline:
        if not isfile(path):
            return False
        try:
            size = getsize(path)
        except OSError:
            return False  # deleted / not yet readable
        now = monotonic()
        if size != last_size:
            last_size = size
            last_change = now
        elif now - last_change >= STABLE_QUIET_S:
            return True
        sleep(0.05)  # keep this well under STABLE_QUIET_S
    log.warning("%s never settled (still growing, vanished, or hit %ss)",
                basename(path), int(STABLE_TIMEOUT_S))
    return False


def upload_timeout_s(path: str) -> float:
    """HTTP timeout from file size so a 40MB .mov isn't killed at 10s."""
    try:
        size = getsize(path)
    except OSError:
        return UPLOAD_TIMEOUT_FLOOR_S
    return max(UPLOAD_TIMEOUT_FLOOR_S, size / UPLOAD_BYTES_PER_S + 15.0)


def _body_snippet(response: requests.Response) -> str:
    text = (response.text or "").strip().replace("\n", " ")
    if len(text) > 300:
        text = text[:297] + "..."
    return text or "(empty body)"


def _file_url(response: requests.Response):
    """Pull files[0].url out of a Zipline upload JSON, or None if the shape is wrong."""
    try:
        data = response.json()
    except ValueError:
        log.error("upload got non-JSON (%s): %s", response.status_code, _body_snippet(response))
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list) or not files:
        log.error("unexpected upload response (%s): %s", response.status_code, _body_snippet(response))
        return None
    first = files[0]
    url = first.get("url") if isinstance(first, dict) else None
    if not url:
        log.error("upload response had no file URL: %s", _body_snippet(response))
        return None
    return url


def _mime_type(path: str) -> str:
    # guess_type returns None for unknown extensions
    return guess_type(path)[0] or "application/octet-stream"


class MonitorFolder(FileSystemEventHandler):
    def __init__(self):
        self._lock = Lock()
        self._pending: Dict[str, Timer] = {}  # path -> coalescing timer
        self._recent: OrderedDict[str, float] = OrderedDict()  # path -> last upload time
        self._queue: Queue = Queue()
        self._stop = Event()
        self._worker = Thread(target=self._run_worker, name="upload-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        with self._lock:
            for timer in self._pending.values():
                timer.cancel()
            self._pending.clear()
        self._stop.set()
        self._queue.put(None)  # wake the worker
        self._worker.join(timeout=8)

    def _interesting(self, path: str) -> bool:
        """Cheap pre-filter so we don't arm a timer for every Desktop file."""
        if not isfile(path) or basename(path).startswith("."):
            return False
        return splitext(path)[1].lower() in VALID_EXTENSIONS_SET

    def _schedule(self, path: str) -> None:
        # Reset: only the last event in a created/modified burst should fire.
        with self._lock:
            existing = self._pending.pop(path, None)
            if existing is not None:
                existing.cancel()
            timer = Timer(STABLE_QUIET_S, self._process, args=(path,))
            timer.daemon = True  # don't block process exit on ctrl+c
            self._pending[path] = timer
            timer.start()

    def _process(self, path: str) -> None:
        with self._lock:
            self._pending.pop(path, None)
        if not wait_until_stable(path):
            return
        if not validate_file(path):
            return
        now = monotonic()
        with self._lock:
            uploaded_at = self._recent.get(path)
            if uploaded_at is not None and now - uploaded_at < RECENT_COOLDOWN_S:
                return
            # Claim before POST so two timers can't upload the same path.
            self._recent[path] = now
            self._recent.move_to_end(path)
            while len(self._recent) > 32:
                self._recent.popitem(last=False)
        self._queue.put(path)

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            path = self._queue.get()
            if path is None:
                break
            try:
                self.upload_file(path)
            finally:
                self._queue.task_done()

    def upload_file(self, path: str):
        # Raw token, not "Bearer …" — this Zipline version expects it that way.
        headers = {"Authorization": USER_ACCESS_TOKEN, **UPLOAD_OPTIONS}
        timeout = upload_timeout_s(path)
        last_error = None

        for attempt in range(1, UPLOAD_ATTEMPTS + 1):
            try:
                with open(path, "rb") as file:
                    files = {
                        "file": (
                            basename(path),
                            file,
                            _mime_type(path),
                        )
                    }
                    response = requests.post(
                        API_UPLOAD_URL,
                        headers=headers,
                        files=files,
                        timeout=timeout,
                    )
            except PermissionError as e:
                log.error("permission error reading %s: %s", basename(path), e)
                return
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = str(e)
            except requests.exceptions.RequestException as e:
                log.error("upload failed: %s", e)
                return
            else:
                if response.status_code in (401, 403):
                    log.error(
                        "Zipline rejected the token (HTTP %s). Check ZIPLINE_TOKEN in .env. %s",
                        response.status_code,
                        _body_snippet(response),
                    )
                    return
                if response.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {response.status_code} {_body_snippet(response)}"
                elif not response.ok:
                    log.error("upload failed: HTTP %s %s", response.status_code, _body_snippet(response))
                    return
                else:
                    file_url = _file_url(response)
                    if not file_url:
                        return
                    try:
                        size_mb = getsize(path) / (1 << 20)
                    except OSError:
                        size_mb = 0.0
                    log.info("uploaded %s (%.2f MB) -> %s", basename(path), size_mb, file_url)
                    try:
                        pyperclip.copy(file_url)
                    except pyperclip.PyperclipException as e:
                        log.warning("uploaded, but clipboard copy failed: %s", e)
                    if OPEN_URL_IN_BROWSER:
                        webbrowser.open(file_url)
                    return

            if attempt < UPLOAD_ATTEMPTS:
                delay = 2 ** (attempt - 1)  # 1s, then 2s
                log.warning("retry %s/%s in %ss: %s", attempt, UPLOAD_ATTEMPTS, delay, last_error)
                sleep(delay)

        log.error("upload failed after %s attempts: %s", UPLOAD_ATTEMPTS, last_error)

    def on_any_event(self, event):
        if event.event_type not in ["created", "modified"]:
            return
        if event.is_directory:
            return
        path = event.src_path
        if not self._interesting(path):
            return
        log.debug("%s %s", event.event_type, basename(path))
        self._schedule(path)


def main():
    if not exists(MONITOR_FOLDER_PATH):
        raise ConfigError(
            f"\n  MONITOR_FOLDER_PATH does not exist: {MONITOR_FOLDER_PATH}\n"
            f"  Fix the path in .env and try again.\n"
        )

    print_banner()

    event_handler = MonitorFolder()
    observer = Observer()
    observer.schedule(event_handler, path=MONITOR_FOLDER_PATH, recursive=False)
    observer.start()

    try:
        while True:
            sleep(1)  # watchdog runs on its own thread; this just keeps us alive
    except KeyboardInterrupt:
        log.info("stopped")
        event_handler.stop()
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
