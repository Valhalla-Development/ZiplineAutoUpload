"""Exercise upload behavior with temporary files and mocked external services."""

import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
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


class TestCase(unittest.TestCase):
    def start_patch(self, context):
        result = context.start()
        self.addCleanup(context.stop)
        return result


class UploadTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "image.png"
        self.path.write_bytes(b"image data")
        self.log = self.start_patch(patch.object(main, "log"))
        self.post = self.start_patch(patch.object(main.requests, "post"))
        self.clipboard = self.start_patch(patch.object(main.pyperclip, "copy"))
        self.browser = self.start_patch(patch.object(main.webbrowser, "open"))
        self.start_patch(patch.object(main, "wait_until_stable", return_value=True))
        self.start_patch(patch.object(main, "OPEN_URL_IN_BROWSER", False))

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

    def drain(self, monitor):
        with monitor._queue.all_tasks_done:
            self.assertTrue(monitor._queue.all_tasks_done.wait_for(
                lambda: monitor._queue.unfinished_tasks == 0, timeout=3,
            ), "upload queue did not finish")

    def test_deleted_file_does_not_kill_worker(self):
        self.post.return_value = self.response()
        monitor = self.monitor()
        monitor._queue.put(str(self.path.with_name("deleted.png")))
        monitor._queue.put(str(self.path))
        self.drain(monitor)
        self.assertTrue(monitor._worker.is_alive())
        self.assertEqual(self.post.call_count, 1)
        self.clipboard.assert_called_once_with("https://example.test/u/image.png")

    def test_unexpected_error_does_not_kill_worker(self):
        monitor = self.monitor()
        with patch.object(monitor, "upload_file", side_effect=[RuntimeError("failed"), None]) as upload:
            monitor._queue.put(str(self.path))
            monitor._queue.put(str(self.path))
            self.drain(monitor)
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
        monitor = self.monitor()
        with patch.object(monitor._stop, "wait", return_value=False) as wait:
            monitor.upload_file(str(self.path))
        self.assertEqual(self.post.call_count, 2)
        wait.assert_called_once_with(1)
        self.clipboard.assert_called_once()

    def test_authentication_failure_does_not_retry(self):
        self.post.return_value = self.response(401)
        self.monitor().upload_file(str(self.path))
        self.post.assert_called_once()
        self.clipboard.assert_not_called()

    def test_clipboard_failure_does_not_repeat_successful_upload(self):
        self.post.return_value = self.response()
        self.clipboard.side_effect = main.pyperclip.PyperclipException("clipboard unavailable")
        monitor = self.monitor()
        monitor._process(str(self.path))
        self.drain(monitor)
        monitor._process(str(self.path))
        self.drain(monitor)
        self.post.assert_called_once()

    def test_permission_error_is_reported_without_post(self):
        monitor = self.monitor()
        with patch("builtins.open", side_effect=PermissionError("access denied")):
            self.assertFalse(monitor.upload_file(str(self.path)))
        self.post.assert_not_called()
        self.log.error.assert_called_once()

    def test_duplicate_paths_are_not_queued_while_active(self):
        monitor = self.monitor()
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def blocked_upload(path, expected=None):
            started.set()
            if not release.wait(3):
                raise RuntimeError("test upload was not released")
            return True

        other = self.path.with_name("other.png")
        other.write_bytes(b"other image")
        with patch.object(monitor, "upload_file", side_effect=blocked_upload) as upload, \
                patch.object(monitor, "_schedule") as schedule:
            monitor._process(str(self.path))
            self.assertTrue(started.wait(3))
            monitor._process(str(other))
            monitor._process(str(other))
            monitor._process(str(self.path))
            self.assertEqual(monitor._queue.qsize(), 1)
            release.set()
            self.drain(monitor)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(schedule.call_count, 2)

    def test_unchanged_successful_file_is_not_uploaded_again(self):
        self.post.return_value = self.response()
        monitor = self.monitor()
        monitor._process(str(self.path))
        self.drain(monitor)
        monitor._process(str(self.path))
        self.drain(monitor)
        self.post.assert_called_once()

    def test_failed_upload_can_be_retried_by_later_event(self):
        self.post.side_effect = [self.response(400), self.response()]
        monitor = self.monitor()
        monitor._process(str(self.path))
        self.drain(monitor)
        monitor._process(str(self.path))
        self.drain(monitor)
        self.assertEqual(self.post.call_count, 2)
        self.clipboard.assert_called_once()

    def test_changed_file_is_uploaded_again(self):
        self.post.return_value = self.response()
        monitor = self.monitor()
        monitor._process(str(self.path))
        self.drain(monitor)
        self.path.write_bytes(b"changed image data")
        monitor._process(str(self.path))
        self.drain(monitor)
        self.assertEqual(self.post.call_count, 2)

    def test_change_during_upload_is_rescheduled(self):
        monitor = self.monitor()

        def modify_source(*args, **kwargs):
            self.path.write_bytes(b"new contents")
            monitor._schedule(str(self.path))
            return self.response()

        self.post.side_effect = modify_source
        with patch.object(monitor, "_schedule", wraps=monitor._schedule) as schedule:
            monitor._process(str(self.path))
            self.drain(monitor)
            # One event while active and one follow-up after completing the snapshot.
            self.assertEqual(schedule.call_count, 2)
        self.assertIn(str(self.path), monitor._pending)
        self.assertEqual(self.post.call_args.kwargs["files"]["file"][1], b"image data")

    def test_rename_and_close_events_schedule_destination(self):
        monitor = self.monitor()
        with patch.object(monitor, "_schedule") as schedule:
            monitor.on_any_event(SimpleNamespace(
                event_type="moved", is_directory=False,
                src_path=str(self.path.with_name(".temporary")), dest_path=str(self.path),
            ))
            monitor.on_any_event(SimpleNamespace(
                event_type="closed", is_directory=False, src_path=str(self.path),
            ))
        self.assertEqual(schedule.call_count, 2)
        schedule.assert_called_with(str(self.path))

    def test_old_timer_cannot_remove_replacement(self):
        monitor = self.monitor()
        old, replacement = Mock(), Mock()
        monitor._pending[str(self.path)] = replacement
        monitor._process(str(self.path), old)
        self.assertIs(monitor._pending[str(self.path)], replacement)
        self.assertTrue(monitor._queue.empty())

    def test_oversized_queued_file_is_not_uploaded(self):
        monitor = self.monitor()
        with self.path.open("wb") as file:
            file.truncate(main.MAX_FILE_SIZE_MB * (1 << 20))
        monitor._process(str(self.path))
        self.drain(monitor)
        self.post.assert_not_called()

    def test_file_changed_before_snapshot_is_not_uploaded(self):
        expected = main.file_signature(str(self.path))
        self.path.write_bytes(b"replacement contents")
        self.assertFalse(self.monitor().upload_file(str(self.path), expected))
        self.post.assert_not_called()

    def test_retries_send_original_snapshot(self):
        def first_attempt(*args, **kwargs):
            self.path.unlink()
            return self.response(503)

        monitor = self.monitor()
        def post(*args, **kwargs):
            if self.post.call_count == 1:
                return first_attempt(*args, **kwargs)
            return self.response()

        self.post.side_effect = post
        with patch.object(monitor._stop, "wait", return_value=False):
            self.assertTrue(monitor.upload_file(str(self.path)))
        for call in self.post.call_args_list:
            self.assertEqual(call.kwargs["files"]["file"][1], b"image data")

    def test_stop_cancels_queue_and_finishes_active_request(self):
        started, release, finished = Event(), Event(), Event()
        self.addCleanup(release.set)
        monitor = self.monitor()

        def post(*args, **kwargs):
            started.set()
            if not release.wait(3):
                raise RuntimeError("test upload was not released")
            return self.response()

        self.post.side_effect = post
        monitor._process(str(self.path))
        self.assertTrue(started.wait(3))
        other = self.path.with_name("other.png")
        other.write_bytes(b"other image")
        monitor._process(str(other))

        def stop():
            monitor.stop()
            finished.set()

        stopper = Thread(target=stop)
        stopper.start()
        self.assertTrue(monitor._stop.wait(3))
        self.assertFalse(finished.is_set())
        release.set()
        stopper.join(3)
        self.assertTrue(finished.is_set())
        self.assertFalse(monitor._worker.is_alive())
        self.assertEqual(monitor._queue.unfinished_tasks, 0)
        self.post.assert_called_once()
        monitor._schedule(str(self.path))
        self.assertFalse(monitor._pending)

    def test_shutdown_interrupts_retry_delay(self):
        monitor = self.monitor()

        def post(*args, **kwargs):
            monitor._stop.set()
            return self.response(503)

        self.post.side_effect = post
        self.assertFalse(monitor.upload_file(str(self.path)))
        self.post.assert_called_once()
        # stop() normally sets this flag and enqueues the sentinel together.
        monitor._stop.clear()


class StabilityTests(TestCase):
    def setUp(self):
        self.time = 0.0
        self.start_patch(patch.object(main, "monotonic", side_effect=lambda: self.time))
        self.start_patch(patch.object(main, "sleep", side_effect=self.tick))
        self.start_patch(patch.object(main, "isfile", return_value=True))
        self.start_patch(patch.object(main, "STABLE_QUIET_S", 0.2))
        self.start_patch(patch.object(main, "STABLE_TIMEOUT_S", 1.0))
        self.start_patch(patch.object(main, "log"))

    def tick(self, seconds):
        self.time += seconds

    def test_same_size_writes_reset_quiet_period(self):
        def signature(path):
            # Only mtime changes, while size and identity remain constant.
            return (1, 2, 10, 100 if self.time < 0.15 else 200)

        with patch.object(main, "file_signature", side_effect=signature):
            self.assertTrue(main.wait_until_stable("image.png"))
        self.assertGreaterEqual(self.time, 0.35)

    def test_unsettled_file_times_out(self):
        with patch.object(main, "file_signature", side_effect=lambda path: (1, 2, 10, self.time)):
            self.assertFalse(main.wait_until_stable("image.png"))

    def test_missing_file_and_shutdown_cancel_readiness(self):
        with patch.object(main, "file_signature", side_effect=FileNotFoundError):
            self.assertFalse(main.wait_until_stable("image.png"))
        stop = Event()
        stop.set()
        self.assertFalse(main.wait_until_stable("image.png", stop))


class LifecycleTests(TestCase):
    def setUp(self):
        self.start_patch(patch.object(main, "isdir", return_value=True))
        self.start_patch(patch.object(main, "print_banner"))
        self.start_patch(patch.object(main, "log"))
        self.observer = self.start_patch(patch.object(main, "Observer")).return_value
        self.monitor = self.start_patch(patch.object(main, "MonitorFolder")).return_value

    def test_monitor_stops_even_if_observer_start_fails(self):
        self.observer.start.side_effect = OSError("cannot watch directory")
        self.observer.is_alive.return_value = False
        with self.assertRaises(OSError):
            main.main()
        self.observer.stop.assert_called_once()
        self.monitor.stop.assert_called_once()

    def test_shutdown_stops_observer_before_upload_worker(self):
        calls = Mock()
        calls.attach_mock(self.observer, "observer")
        calls.attach_mock(self.monitor, "monitor")
        with patch.object(main, "sleep", side_effect=KeyboardInterrupt):
            main.main()
        names = [call[0] for call in calls.mock_calls]
        self.assertLess(names.index("observer.stop"), names.index("observer.join"))
        self.assertLess(names.index("observer.join"), names.index("monitor.stop"))


if __name__ == "__main__":
    unittest.main()
