from mimetypes import guess_type
from os.path import basename, isfile, splitext, getsize, exists
from time import sleep
from webbrowser import open

from pyperclip import copy
from requests import post
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Absolute path to the folder to monitor for new files
MONITOR_FOLDER_PATH = "<path>"
# List of valid file extensions that will be considered for upload
VALID_EXTENSIONS = [".png", ".jpg", ".jpeg", ".mov"]
# The URL of the API endpoint for uploading files to your Zipline instance
API_UPLOAD_URL = "https://<domain>/api/upload"
# The access token associated with your user account for authentication
USER_ACCESS_TOKEN = "<access_token>"
# The maximum allowable size for an individual file, specified in megabytes
MAX_FILE_SIZE_MB = 40
# A dictionary containing upload options for the Zipline API.
# For detailed information on available options, refer to the official documentation:
# https://zipline.diced.sh/docs/guides/upload-options
UPLOAD_OPTIONS = {"Format": "RANDOM", "Embed": "false"}
# Used to decide if the URL for the uploaded files should open in the browser.
OPEN_URL_IN_BROWSER = False


def validate_file(path):
    """
    Validates a file based on its type and size.

    Parameters:
    - path (str): The absolute path to the file.

    Returns:
    - bool: True if the file is valid, False otherwise.
    """
    if not isfile(path) or basename(path).startswith('.'):
        return False

    if splitext(path)[1] not in VALID_EXTENSIONS:
        print(f"Error: {basename(path)} has an unsupported file extension. "
              f"Allowed extensions: {', '.join(VALID_EXTENSIONS)}")
        return False

    if getsize(path) >= MAX_FILE_SIZE_MB * (1 << 20):
        print(f"Error: {basename(path)} exceeds the permitted file size limit "
              f"({getsize(path) / (1 << 20):.2f}MB > 40MB).")
        return False

    return True


class MonitorFolder(FileSystemEventHandler):
    def __init__(self):
        self.array = []

    def handle_array(self, event):
        """
        Handles an array of files by processing each file in the array and updating the `array` attribute.

        Parameters:
        - self (object): The object handling the array of files.
        - event (event.FileSystemEvent): The event representing the file being processed.

        Returns:
            bool: Whether the function executed successfully or not.
        """
        seen_files = set()
        unique_array = []

        for item in reversed(self.array):  # Loop through the array of files and process each one
            if item['file'] not in seen_files:
                unique_array.append(item)
                seen_files.add(item['file'])

            if item['file'] == event.src_path:
                if item['status'] == 'processed':
                    return False
                item['status'] = 'processed'  # Mark the file as processed

        self.array = unique_array[-10:]  # Keep the last 10 items in the array

        return True

    def upload_file(self, event):
        try:
            if not self.handle_array(event):
                return

            headers = {"Authorization": USER_ACCESS_TOKEN, **UPLOAD_OPTIONS}
            files = {
                "file": (
                    basename(event.src_path),
                    open(event.src_path, "rb"),
                    guess_type(event.src_path)[0],
                )
            }
            response = post(API_UPLOAD_URL, headers=headers, files=files, timeout=10)

            if response.status_code == 200:
                print(f"File uploaded successfully: {response.json()['files'][0]}")
                copy(response.json()["files"][0])  # Copy the URL to the clipboard

                if OPEN_URL_IN_BROWSER:
                    open(response.json()["files"][0])  # Open the uploaded file in the browser if OPEN_URL_IN_BROWSER
            elif response.status_code == 401:
                print("Authentication failed. Please check your USER_ACCESS_TOKEN.")
            else:
                print(f"File upload failed. Status code: {response.status_code}")
        except PermissionError as error:
            print(error)

    def on_any_event(self, event):
        """
        Event handler for created files in the monitored folder.

        Parameters:
        - event (FileSystemEvent): The event object representing the created file.

        Returns:
        None
        """
        if event.event_type not in ['created', 'modified']:
            return

        if not validate_file(event.src_path):
            return  # Exit early if validation fails

        self.array.append({'file': event.src_path, 'status': 'processing'})

        sleep(0.02)  # Apply a small sleep time to allow for system events

        self.upload_file(event)  # Attempt to upload the file


if __name__ == "__main__":
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
