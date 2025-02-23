import webbrowser
from mimetypes import guess_type
from os.path import basename, isfile, splitext, getsize, exists
from time import sleep
from typing import List, Dict

import pyperclip
import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Configuration
# Absolute path to the folder to monitor for new files
MONITOR_FOLDER_PATH: str = "<path>"
# List of valid file extensions that will be considered for upload
VALID_EXTENSIONS: List[str] = [".png", ".jpg", ".jpeg", ".mov"]
# The URL of the API endpoint for uploading files to your Zipline instance
API_UPLOAD_URL: str = "https://<domain>/api/upload"
# The access token associated with your user account for authentication
USER_ACCESS_TOKEN: str = "<access_token>"
# The maximum allowable size for an individual file, specified in megabytes
MAX_FILE_SIZE_MB: int = 40
# A dictionary containing upload options for the Zipline API.
# For detailed information on available options, refer to the official documentation:
# https://zipline.diced.sh/docs/guides/upload-options
UPLOAD_OPTIONS: Dict[str, str] = {
    "x-zipline-format": "random", 
    "x-zipline-original-name": "false"
}
# Used to decide if the URL for the uploaded files should open in the browser.
OPEN_URL_IN_BROWSER: bool = False


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
            return  # Ignore events other than file creation or modification

        if not validate_file(event.src_path):
            return  # Skip invalid files

        self.array.append({'file': event.src_path, 'status': 'processing'})

        sleep(0.02)  # Small delay to allow for system events

        self.upload_file(event)  # Attempt to upload the file


def main():
    """
    Main function to set up and run the file monitoring system.
    """
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


if __name__ == "__main__":
    main()
