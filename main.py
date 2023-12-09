from mimetypes import guess_type
from os.path import basename, isfile, splitext, getsize, exists
from time import sleep

from pyperclip import copy
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


def upload_file(path):
    # Upload the file to Zipline
    try:
        headers = {"Authorization": f"{USER_ACCESS_TOKEN}"}
        files = {
            "file": (
                basename(path),
                open(path, "rb"),
                guess_type(path)[0],
            )
        }
        response = post(API_UPLOAD_URL, headers=headers, files=files, timeout=10)

        if response.status_code == 200:
            print(f"File uploaded successfully: {response.json()['files'][0]}")
            # Copy the URL to the clipboard
            copy(response.json()["files"][0])
        elif response.status_code == 401:
            print("Authentication failed. Please check your USER_ACCESS_TOKEN.")
        else:
            print(f"File upload failed. Status code: {response.status_code}")
    except PermissionError as error:
        print(error)
        return


def validate_file(path):
    # Return if the file is not a valid file
    if not isfile(path):
        return

    # Return if the file does not have an acceptable file type
    if splitext(path)[1] not in VALID_EXTENSIONS:
        print(f"Error: {basename(path)} has an unsupported file extension. "
              f"Allowed extensions: {', '.join(VALID_EXTENSIONS)}")
        return

    # Return if file size is greater than 40MB
    if getsize(path) >= MAX_FILE_SIZE_MB * (1 << 20):
        print(f"Error: {basename(path)} exceeds the permitted file size limit "
              f"({getsize(path) / (1 << 20):.2f}MB > 40MB).")
        return


class MonitorFolder(FileSystemEventHandler):
    def on_created(self, event):
        validate_file(event.src_path)

        sleep(0.02)

        upload_file(event.src_path)


if __name__ == "__main__":
    # Check if the path exists
    if not exists(MONITOR_FOLDER_PATH):
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
