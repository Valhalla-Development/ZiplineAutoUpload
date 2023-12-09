import mimetypes
import os.path
from time import sleep

import pyperclip
from requests import post
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Absolute path to the folder to monitor for new files
MONITOR_FOLDER_PATH = "<path>"
# List of valid file extensions that will be considered for upload
VALID_EXTENSIONS = [".png", ".jpg", ".jpeg", ".mov"]
# URL of the API endpoint for uploading files to your Zipline instance
API_UPLOAD_URL = "https://<domain>/api/upload"
# Access token associated with your user account for authentication
USER_ACCESS_TOKEN = "<access_token>"
# Maximum allowable size for an individual file in megabytes
MAX_FILE_SIZE_MB = 40


class MonitorFolder(FileSystemEventHandler):
    def on_created(self, event):
        # Return if the file is not a valid file
        if not os.path.isfile(event.src_path):
            return

        # Return if the file does not have an acceptable file type
        if os.path.splitext(event.src_path)[1] not in VALID_EXTENSIONS:
            print(f"Error: {os.path.basename(event.src_path)} has an unsupported file extension. "
                  f"Allowed extensions: {', '.join(VALID_EXTENSIONS)}")
            return

        # Return if file size is greater than 40MB
        if os.path.getsize(event.src_path) >= MAX_FILE_SIZE_MB * (1 << 20):
            print(f"Error: {os.path.basename(event.src_path)} exceeds the permitted file size limit "
                  f"({os.path.getsize(event.src_path) / (1 << 20):.2f}MB > 40MB).")
            return

        sleep(0.02)

        # Upload the file to Zipline
        try:
            headers = {"Authorization": f"{USER_ACCESS_TOKEN}"}
            files = {
                "file": (
                    os.path.basename(event.src_path),
                    open(event.src_path, "rb"),
                    mimetypes.guess_type(event.src_path)[0],
                )
            }
            response = post(API_UPLOAD_URL, headers=headers, files=files, timeout=10)

            if response.status_code == 200:
                print(f"File uploaded successfully: {response.json()['files'][0]}")
                # Copy the URL to the clipboard
                pyperclip.copy(response.json()["files"][0])
            elif response.status_code == 401:
                print("Authentication failed. Please check your USER_ACCESS_TOKEN.")
            else:
                print(f"File upload failed. Status code: {response.status_code}")
        except PermissionError as error:
            print(error)
            return


if __name__ == "__main__":
    # Check if the path exists
    if not os.path.exists(MONITOR_FOLDER_PATH):
        raise FileNotFoundError(f"The specified path does not exist: {MONITOR_FOLDER_PATH}")

    event_handler = MonitorFolder()
    observer = Observer()
    observer.schedule(event_handler, path=MONITOR_FOLDER_PATH, recursive=True)
    print("Monitoring started")
    observer.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
