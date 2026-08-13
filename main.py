"""Watch a folder and upload new images/videos to a Zipline instance.
"""

import webbrowser
from collections import OrderedDict
from mimetypes import guess_type
from os import getenv
from os.path import basename, dirname, exists, getsize, isfile, join, splitext
from threading import Lock, Timer
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

# https://zipline.diced.sh/docs/guides/upload-options
UPLOAD_OPTIONS: Dict[str, str] = {
    "x-zipline-format": "random",
    "x-zipline-original-name": "false",
}

ENV_PATH = join(dirname(__file__), ".env")
load_dotenv(ENV_PATH)  # no-op if missing; _require() is what fails


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
    browser = "true" if OPEN_URL_IN_BROWSER else "false"
    line = "─" * 52
    print(
        f"\n{line}\n"
        f"  ZiplineAutoUpload\n"
        f"{line}\n"
        f"  folder    {MONITOR_FOLDER_PATH}\n"
        f"  host      {host}\n"
        f"  token     {_mask(USER_ACCESS_TOKEN)}\n"
        f"  types     {types}\n"
        f"  max size  {MAX_FILE_SIZE_MB} MB\n"
        f"  browser   {browser}\n"
        f"{line}\n"
        f"  watching…  (ctrl+c to stop)\n"
    )


def validate_file(path: str) -> bool:
    """True if this path is a non-hidden file we should upload."""
    # .DS_Store, AppleDouble, screenshot temps
    if not isfile(path) or basename(path).startswith("."):
        return False

    if splitext(path)[1].lower() not in VALID_EXTENSIONS_SET:
        print(f"Error: {basename(path)} has an unsupported file extension. "
              f"Allowed extensions: {', '.join(VALID_EXTENSIONS)}")
        return False

    # 1 << 20 == 1 MiB. `>=` means exactly MAX_FILE_SIZE_MB is also rejected.
    if getsize(path) >= MAX_FILE_SIZE_MB * (1 << 20):
        print(f"Error: {basename(path)} exceeds the permitted file size limit "
              f"({getsize(path) / (1 << 20):.2f}MB > {MAX_FILE_SIZE_MB}MB).")
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
    return False


class MonitorFolder(FileSystemEventHandler):
    def __init__(self):
        self._lock = Lock()
        self._pending: Dict[str, Timer] = {}  # path -> coalescing timer
        self._recent: OrderedDict[str, float] = OrderedDict()  # path -> last upload time

    def stop(self) -> None:
        with self._lock:
            for timer in self._pending.values():
                timer.cancel()
            self._pending.clear()

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
        self.upload_file(path)

    def upload_file(self, path: str):
        headers = {"Authorization": USER_ACCESS_TOKEN, **UPLOAD_OPTIONS}
        try:
            with open(path, "rb") as file:
                files = {
                    "file": (
                        basename(path),
                        file,
                        guess_type(path)[0],
                    )
                }
                response = requests.post(API_UPLOAD_URL, headers=headers, files=files, timeout=10)

            response.raise_for_status()
            response_data = response.json()["files"][0]
            file_url = response_data["url"]
            print(f"File uploaded successfully: {file_url}")
            pyperclip.copy(file_url)

            if OPEN_URL_IN_BROWSER:
                webbrowser.open(file_url)
        except requests.exceptions.RequestException as e:
            print(f"File upload failed: {str(e)}")
        except PermissionError as e:
            print(f"Permission error: {str(e)}")

    def on_any_event(self, event):
        if event.event_type not in ["created", "modified"]:
            return
        if event.is_directory:
            return
        path = event.src_path
        if not self._interesting(path):
            return
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
        event_handler.stop()
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
