import webbrowser
from mimetypes import guess_type
from os import getenv
from os.path import basename, dirname, exists, getsize, isfile, join, splitext
from time import monotonic, sleep
from typing import Dict, List
from urllib.parse import urlparse

import pyperclip
import requests
from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

VALID_EXTENSIONS: List[str] = [".png", ".jpg", ".jpeg", ".mov"]
MAX_FILE_SIZE_MB: int = 40
STABLE_QUIET_S: float = 0.4
STABLE_TIMEOUT_S: float = 120
# https://zipline.diced.sh/docs/guides/upload-options
UPLOAD_OPTIONS: Dict[str, str] = {
    "x-zipline-format": "random",
    "x-zipline-original-name": "false",
}

ENV_PATH = join(dirname(__file__), ".env")
load_dotenv(ENV_PATH)


class ConfigError(SystemExit):
    """Raised when .env is missing or still full of placeholders."""


def _require(name: str) -> str:
    raw = getenv(name)
    if raw is None:
        raise ConfigError(
            f"\n  {name} is not set.\n"
            f"  Copy .env.example to .env and fill it in — that's the whole setup.\n"
        )
    value = raw.strip()
    if not value or value.startswith("<") or value.lower() in {"changeme", "your_access_token_here"}:
        raise ConfigError(
            f"\n  {name} still looks like a placeholder ({value!r}).\n"
            f"  Open .env and put the real value in. No quotes needed.\n"
        )
    return value


def _truthy(name: str, default: bool = False) -> bool:
    raw = getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _mask(secret: str) -> str:
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
    """
    Validates a file based on its type and size.

    Args:
        path (str): The absolute path to the file.

    Returns:
        bool: True if the file is valid, False otherwise.
    """
    # Check if it's a file and not hidden
    if not isfile(path) or basename(path).startswith('.'):
        return False

    # Check if the file extension is valid
    if splitext(path)[1] not in VALID_EXTENSIONS:
        print(f"Error: {basename(path)} has an unsupported file extension. "
              f"Allowed extensions: {', '.join(VALID_EXTENSIONS)}")
        return False

    # Check if the file size is within the limit
    if getsize(path) >= MAX_FILE_SIZE_MB * (1 << 20):  # Convert MB to bytes
        print(f"Error: {basename(path)} exceeds the permitted file size limit "
              f"({getsize(path) / (1 << 20):.2f}MB > {MAX_FILE_SIZE_MB}MB).")
        return False

    return True


def wait_until_stable(path: str) -> bool:
    deadline = monotonic() + STABLE_TIMEOUT_S
    last_size = -1
    last_change = monotonic()
    while monotonic() < deadline:
        if not isfile(path):
            return False
        try:
            size = getsize(path)
        except OSError:
            return False
        now = monotonic()
        if size != last_size:
            last_size = size
            last_change = now
        elif now - last_change >= STABLE_QUIET_S:
            return True
        sleep(0.05)
    return False


class MonitorFolder(FileSystemEventHandler):
    def __init__(self):
        self.array: List[Dict[str, str]] = []  # Store processed files

    def handle_array(self, event) -> bool:
        """
        Handles an array of files by processing each file in the array and updating the `array` attribute.

        Args:
            event (FileSystemEvent): The event representing the file being processed.

        Returns:
            bool: Whether the function executed successfully or not.
        """
        seen_files = set()
        unique_array = []

        # Process files in reverse order to keep the most recent entries
        for item in reversed(self.array):
            if item['file'] not in seen_files:
                unique_array.append(item)
                seen_files.add(item['file'])

            # Check if the current file has already been processed
            if item['file'] == event.src_path:
                if item['status'] == 'processed':
                    return False
                item['status'] = 'processed'

        # Keep only the last 10 processed files
        self.array = unique_array[-10:]

        return True

    def upload_file(self, event):
        """
        Uploads the file to the specified API endpoint.

        Args:
            event (FileSystemEvent): The event representing the file to be uploaded.
        """
        if not self.handle_array(event):
            return  # File already processed, skip upload

        headers = {"Authorization": USER_ACCESS_TOKEN, **UPLOAD_OPTIONS}
        try:
            with open(event.src_path, "rb") as file:
                files = {
                    "file": (
                        basename(event.src_path),
                        file,
                        guess_type(event.src_path)[0],
                    )
                }
                # Send POST request to upload the file
                response = requests.post(API_UPLOAD_URL, headers=headers, files=files, timeout=10)

            response.raise_for_status()  # Raise an exception for bad responses
            response_data = response.json()["files"][0]
            file_url = response_data["url"]
            print(f"File uploaded successfully: {file_url}")
            pyperclip.copy(file_url)  # Copy the URL to clipboard

            if OPEN_URL_IN_BROWSER:
                webbrowser.open(file_url)  # Open the URL in browser if configured
        except requests.exceptions.RequestException as e:
            print(f"File upload failed: {str(e)}")
        except PermissionError as e:
            print(f"Permission error: {str(e)}")

    def on_any_event(self, event):
        """
        Event handler for created or modified files in the monitored folder.

        Args:
            event (FileSystemEvent): The event object representing the file event.
        """
        if event.event_type not in ['created', 'modified']:
            return

        if event.is_directory:
            return

        if not validate_file(event.src_path):
            return

        if not wait_until_stable(event.src_path):
            return

        if not validate_file(event.src_path):
            return

        self.array.append({'file': event.src_path, 'status': 'processing'})
        self.upload_file(event)


def main():
    """
    Main function to set up and run the file monitoring system.
    """
    if not exists(MONITOR_FOLDER_PATH):
        raise ConfigError(
            f"\n  MONITOR_FOLDER_PATH does not exist: {MONITOR_FOLDER_PATH}\n"
            f"  Fix the path in .env and try again.\n"
        )

    print_banner()

    event_handler = MonitorFolder()
    observer = Observer()
    observer.schedule(event_handler, path=MONITOR_FOLDER_PATH, recursive=True)
    observer.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
