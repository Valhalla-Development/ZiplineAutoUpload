import os.path
import requests
import mimetypes
import pyperclip
from time import sleep
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
            print(f"Error: {os.path.basename(event.src_path)} has an unsupported file extension. "
                  f"Allowed extensions: {', '.join(valid_extensions)}")
            return

        # Return if file size is greater than 40MB
        if os.path.getsize(event.src_path) >= 40 * (1 << 20):
            print(f"Error: {os.path.basename(event.src_path)} exceeds the permitted file size limit "
                  f"({os.path.getsize(event.src_path) / (1 << 20):.2f}MB > 40MB).")
            return

        sleep(0.02)

        try:
            headers = {"Authorization": f"{access_token}"}
            files = {
                "file": (
                    os.path.basename(event.src_path),
                    open(event.src_path, "rb"),
                    mimetypes.guess_type(event.src_path)[0],
                )
            }
            response = requests.post(api_url, headers=headers, files=files, timeout=10)

            if response.status_code == 200:
                print(f"File Uploaded Successfully: {response.json()['files'][0]}")
                # Copy the URL to the clipboard
                pyperclip.copy(response.json()["files"][0])
            else:
                print(f"File upload failed. Status code: {response.status_code}")
        except PermissionError as error:
            print(error)
            return


if __name__ == "__main__":
    # Absolute path to monitor for new files
    path = "<your-absolute-path>"

    # Check if the path exists
    if not os.path.exists(path):
        raise FileNotFoundError(f"The specified path does not exist: {path}")

    event_handler = MonitorFolder()
    observer = Observer()
    observer.schedule(event_handler, path=path)
    print("Monitoring started")
    observer.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
