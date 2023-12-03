<div align="center">
  <br />
  <p>
    <img src="https://share.valhalladev.org/r/XPk8iq.png" width="550" alt="DiscordGPT" />
  </p>
  <br />
  <p>
  <a href="https://discord.gg/Q3ZhdRJ">
    <img src="https://img.shields.io/discord/495602800802398212.svg?colorB=Blue&logo=discord&label=Support&style=for-the-badge" alt="Support">
  </a>
  <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload">
    <img src="https://img.shields.io/github/languages/top/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge" alt="Language">
  </a>
  <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/issues">
    <img src="https://img.shields.io/github/issues/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge" alt="Issues">
  </a>
  <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/pulls">
    <img src="https://img.shields.io/github/issues-pr/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge" alt="Pull Requests">
  </a>
  <a href="https://app.codacy.com/gh/Valhalla-Development/ZiplineAutoUpload/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade">
    <img src="https://img.shields.io/codacy/grade/cb6c917ff4354eaea13a814e8da7ab80?style=for-the-badge" alt="Codacy Ranking">
  </a>
  </p>
</div>

ZiplineAutoUpload utilizes Python and various libraries
to create a script that monitors a specified folder for new files.
When a new file is detected, the script will upload the file to a Zipline instance using its API.

## Installation

To use this project, you will need to install the following dependencies:

* `watchdog`: A library for monitoring file system events in real-time.
* `requests`: A library for sending HTTP requests in Python.
* `pyperclip`: A library for interacting with the clipboard in Python.

You can install these libraries using pip:
```
pip3 install watchdog requests pyperclip
```
## Usage

To use this project, follow these steps:

1. Replace `<your-domain>` and `<your-api-token>` in the code with your Zipline instance's domain and API token.
2. Replace `<your-absolute-path>` with the absolute path to the folder you want to monitor.
3. Run the script by executing the following command:
```bash
python3 main.py
```
The script will start monitoring the specified folder and upload any new files that are created.
When a file is uploaded successfully, the URL to the uploaded file will be copied to your clipboard.
If there's an error while uploading a file, the error message will be printed to the console.
