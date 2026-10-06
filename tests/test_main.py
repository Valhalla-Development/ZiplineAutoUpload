"""Exercise upload behavior with temporary files and mocked external services."""

import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

# Importing the entry point must never read developer credentials or log files.
with patch.dict(os.environ, {
    "MONITOR_FOLDER_PATH": "/tmp",
    "ZIPLINE_UPLOAD_URL": "https://example.test/api/upload",
    "ZIPLINE_TOKEN": "test-token",
    "LOG_COLOR": "false",
}, clear=True), patch("dotenv.load_dotenv", return_value=False):
    main = importlib.import_module("main")


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "image.png"
        self.path.write_bytes(b"image data")
        self.log = self.enterContext(patch.object(main, "log"))
        self.post = self.enterContext(patch.object(main.requests, "post"))
        self.clipboard = self.enterContext(patch.object(main.pyperclip, "copy"))
        self.browser = self.enterContext(patch.object(main.webbrowser, "open"))
        self.enterContext(patch.object(main, "OPEN_URL_IN_BROWSER", False))

    def response(self, status=200, payload=None):
        response = requests.Response()
        response.status_code = status
        response._content = b"mock response"
        response.json = Mock(return_value=payload or {
            "files": [{"url": "https://example.test/u/image.png"}],
        })
        return response

    def monitor(self):
        monitor = main.MonitorFolder()
        self.addCleanup(monitor.stop)
        return monitor

    def test_deleted_file_does_not_kill_worker(self):
        self.post.return_value = self.response()
        monitor = self.monitor()
        monitor._queue.put(str(self.path.with_name("deleted.png")))
        monitor._queue.put(str(self.path))
        monitor._queue.join()
        self.assertTrue(monitor._worker.is_alive())
        self.assertEqual(self.post.call_count, 1)
        self.clipboard.assert_called_once_with("https://example.test/u/image.png")

    def test_unexpected_error_does_not_kill_worker(self):
        monitor = self.monitor()
        with patch.object(monitor, "upload_file", side_effect=[RuntimeError("failed"), None]) as upload:
            monitor._queue.put(str(self.path))
            monitor._queue.put(str(self.path))
            monitor._queue.join()
        self.assertTrue(monitor._worker.is_alive())
        self.assertEqual(upload.call_count, 2)
        self.log.exception.assert_called_once()

    def test_invalid_response_urls_are_rejected(self):
        for url in [123, {}, "", "file:///tmp/image.png", "javascript:alert(1)", "https://"]:
            with self.subTest(url=url):
                response = self.response(payload={"files": [{"url": url}]})
                self.assertIsNone(main._file_url(response))

    def test_malformed_response_is_rejected(self):
        for payload in [[], {"files": []}, {"files": [None]}]:
            with self.subTest(payload=payload):
                response = self.response()
                response.json.return_value = payload
                self.assertIsNone(main._file_url(response))
        response.json.side_effect = ValueError("invalid JSON")
        self.assertIsNone(main._file_url(response))

    def test_retryable_status_retries(self):
        self.post.side_effect = [self.response(503), self.response()]
        with patch.object(main, "sleep") as sleep:
            self.monitor().upload_file(str(self.path))
        self.assertEqual(self.post.call_count, 2)
        sleep.assert_called_once_with(1)
        self.clipboard.assert_called_once()

    def test_authentication_failure_does_not_retry(self):
        self.post.return_value = self.response(401)
        self.monitor().upload_file(str(self.path))
        self.post.assert_called_once()
        self.clipboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
