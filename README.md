<div align="center">
  <img id="top" src="https://share.valhalladev.org/u/ZiplineAutoUpload.png" width="100%" alt="ZiplineAutoUpload Banner">

# 📤 ZiplineAutoUpload: Your Instant File Sharing Companion! 🚀

  <p>
    <a href="https://discord.gg/Q3ZhdRJ"><img src="https://img.shields.io/discord/495602800802398212.svg?colorB=5865F2&logo=discord&logoColor=white&style=for-the-badge" alt="Discord"></a>
    <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/stargazers"><img src="https://img.shields.io/github/stars/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge&color=yellow" alt="Stars"></a>
    <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/network/members"><img src="https://img.shields.io/github/forks/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge&color=orange" alt="Forks"></a>
    <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/issues"><img src="https://img.shields.io/github/issues/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge&color=red" alt="Issues"></a>
    <a href="https://github.com/Valhalla-Development/ZiplineAutoUpload/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Valhalla-Development/ZiplineAutoUpload.svg?style=for-the-badge&color=blue" alt="License"></a>
    <br>
    <a href="https://app.codacy.com/gh/Valhalla-Development/ZiplineAutoUpload/dashboard"><img src="https://img.shields.io/codacy/grade/cb6c917ff4354eaea13a814e8da7ab80?style=for-the-badge&color=brightgreen" alt="Codacy"></a>
    <a href="https://zipline.diced.sh"><img src="https://img.shields.io/badge/Powered%20by-Zipline-a656f7?style=for-the-badge" alt="Powered by Zipline"></a>
    <a href="https://www.python.org"><img src="https://img.shields.io/badge/Made%20with-Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Made with Python"></a>
  </p>

  <p><em>Because manually uploading files is so last century! 🦕</em></p>
</div>

---
## 🌟 Welcome to the Future of File Sharing!

ZiplineAutoUpload is your personal file-sharing assistant that makes sharing files as easy as dropping them into a folder. Simply save or move a file to your monitored folder, and BOOM! 💥 - the file is automatically uploaded, the link is copied to your clipboard, and you're ready to share in seconds!

## 🎯 Features That'll Make You Feel Like a File-Sharing Wizard

<table>
  <tr>
    <td width="50%">
      <h3>👀 Automatic Monitoring</h3>
      <p>Drop a file and let the magic happen - no clicks required!</p>
    </td>
    <td width="50%">
      <h3>📋 Instant Clipboard Copy</h3>
      <p>Upload links are automatically copied and ready to share!</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🔍 Smart File Filtering</h3>
      <p>Only uploads the file types you want, ignoring the rest!</p>
    </td>
    <td width="50%">
      <h3>🌐 Browser Integration</h3>
      <p>Optionally opens your uploaded files right in your browser!</p>
    </td>
  </tr>
</table>

## 🚀 Requirements

- [Python 3.x](https://python.org/)
- [pip](https://pip.pypa.io/en/stable/installation/) (Python package installer)
- A [Zipline](https://github.com/diced/zipline) instance
- Internet connection (obviously! 😉)

## 🛠️ Installation & Setup

1. Clone this repository or download the source code:
    ```bash
    git clone https://github.com/Valhalla-Development/ZiplineAutoUpload.git
    ```

2. Navigate to the project directory:
    ```bash
    cd ZiplineAutoUpload
    ```

3. Install required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

See the top of `main.py` for all configuration options and their descriptions. The main settings you'll need to configure are:

```python
# The folder to monitor for new files
MONITOR_FOLDER_PATH = "/path/to/your/folder"

# Your Zipline instance URL
API_UPLOAD_URL = "https://your.zipline.instance/api/upload"

# Your Zipline access token
USER_ACCESS_TOKEN = "your_access_token_here"
```

## 🎬 Usage

1. Start the Upload:
   ```bash
   python main.py
   ```

2. Drop files into your monitored folder.

3. Watch the magic happen! Each valid file will be:
   - ✅ Automatically uploaded
   - 📋 URL copied to clipboard
   - 🌐 Opened in browser (if enabled)

## 📊 What to Expect

When running, you'll see:
```
Monitoring started
File uploaded successfully: https://your.zipline.instance/u/filename.png
```

## 🤝 Contributing

Want to make this even more awesome? Here's how:

1. Fork it
2. Create your feature branch:
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m 'Add some amazing feature'
   ```
4. Push to the branch:
   ```bash
   git push origin feature/amazing-feature
   ```
5. Open a Pull Request

## 📜 License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details. (It's mostly "Share the love, and keep it open!")

## 🙏 Acknowledgments

- [Zipline](https://github.com/diced/zipline) for the awesome file hosting service
- [Watchdog](https://pythonhosted.org/watchdog/) for the reliable file monitoring
- All contributors and users who make this project better!

## 📬 Join Our Community

Got questions? Need help? Join our [Discord server](https://discord.gg/Q3ZhdRJ) - where we're always happy to help!

---

<div align="center">

💻 Crafted with ❤️ by [Valhalla-Development](https://github.com/Valhalla-Development)

[🐛 Report Bug](https://github.com/Valhalla-Development/ZiplineAutoUpload/issues/new?assignees=&labels=bug&projects=&template=bug_report.yml&title=%5BBUG%5D+Short+Description) | [💡 Request Feature](https://github.com/Valhalla-Development/ZiplineAutoUpload/issues/new?assignees=&labels=enhancement&projects=&template=feature_request.yml&title=%5BFeature%5D+Short+Description) | [🤔 Need Help?](https://discord.gg/Q3ZhdRJ)

<a href="#top">🔝 Back to Top</a>
</div>
