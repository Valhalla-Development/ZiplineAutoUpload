"""Verify installed-command configuration using only isolated dummy env files."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.installed = root / "installed"
        self.cwd = root / "working"
        self.installed.mkdir()
        self.cwd.mkdir()
        source = Path(__file__).resolve().parents[1] / "main.py"
        (self.installed / "main.py").write_text(source.read_text())
        self.config = (
            f"MONITOR_FOLDER_PATH={self.cwd}\n"
            "ZIPLINE_UPLOAD_URL=https://example.test/api/upload\n"
            "ZIPLINE_TOKEN=dummy-file-token\n"
            "LOG_COLOR=false\n"
        )

    def run_command(self, env=None, expression=None):
        code = (
            f"import sys; sys.path.insert(0, {str(self.installed)!r}); import main; "
            + (expression or "import json; print(json.dumps([main.USER_ACCESS_TOKEN, main.MONITOR_FOLDER_PATH]))")
        )
        return subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=self.cwd,
            env={"LOG_COLOR": "false", **(env or {})},
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_installed_command_loads_working_directory_env(self):
        (self.cwd / ".env").write_text(self.config)
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["dummy-file-token", str(self.cwd)])

    def test_existing_environment_overrides_env_files(self):
        (self.cwd / ".env").write_text(self.config)
        result = self.run_command({"ZIPLINE_TOKEN": "dummy-environment-token"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0], "dummy-environment-token")

    def test_working_directory_overrides_checkout_fallback(self):
        (self.installed / ".env").write_text(self.config)
        (self.cwd / ".env").write_text("ZIPLINE_TOKEN=dummy-working-token\n")
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["dummy-working-token", str(self.cwd)])

    def test_environment_only_configuration(self):
        result = self.run_command({
            "MONITOR_FOLDER_PATH": str(self.cwd),
            "ZIPLINE_UPLOAD_URL": "https://example.test/api/upload",
            "ZIPLINE_TOKEN": "dummy-environment-token",
        })
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_monitor_path_must_be_a_directory(self):
        path = self.cwd / "image.png"
        path.write_bytes(b"image")
        (self.cwd / ".env").write_text(self.config)
        result = self.run_command({"MONITOR_FOLDER_PATH": str(path)}, "main.main()")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not a directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
