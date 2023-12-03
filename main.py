import os.path
import time
import requests
import mimetypes
import pyperclip
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class MonitorFolder(FileSystemEventHandler):
    def on_created(self, event):
        # Array of valid file types
        valid_extensions = [".png", ".jpg", ".jpeg", ".mov"]
        # API URL for your Zipline instance
        api_url = "https://<your-domain>/api/upload"
        # Access token for your account
        access_token = "<your-api-token>"

        # Return if the file is not a valid file
        if not os.path.isfile(event.src_path):
            return

        # Return if the file does not have an acceptable file type
        if os.path.splitext(event.src_path)[1] not in valid_extensions:
            return

        # Return if file size is greater than 40MB
        if os.path.getsize(event.src_path) >= 40 * 1 << 20:
            return

        headers = {"Authorization": f"{access_token}"}
        files = {
            "file": (
                os.path.basename(event.src_path),
                open(event.src_path, "rb"),
                mimetypes.guess_type(event.src_path)[0],
            )
        }
        response = requests.post(api_url, headers=headers, files=files)

        if response.status_code == 200:
            print("File Uploaded Successfully.")
            # Copy the URL to the clipboard
            pyperclip.copy(response.json()["files"][0])
        else:
            print("Failed to upload file with status code:", response.status_code)


if __name__ == "__main__":
    # Absolute path to monitor for new files
    path = "<your-absolute-path>"

    event_handler = MonitorFolder()
    observer = Observer()
    observer.schedule(event_handler, path=path)
    print("Monitoring started")
    observer.start()

    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
