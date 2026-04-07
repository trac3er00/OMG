import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from runtime.demo_ux import _detect_project_type, preview


class TestDemoUX(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_project_type_static(self):
        with open(os.path.join(self.project_dir, "index.html"), "w") as f:
            f.write("<html></html>")

        self.assertEqual(_detect_project_type(self.project_dir), "static")

    def test_detect_project_type_nextjs(self):
        with open(os.path.join(self.project_dir, "next.config.js"), "w") as f:
            f.write("module.exports = {}")

        self.assertEqual(_detect_project_type(self.project_dir), "nextjs")

    def test_detect_project_type_unknown(self):
        self.assertEqual(_detect_project_type(self.project_dir), "unknown")

    @patch("subprocess.Popen")
    @patch("urllib.request.urlopen")
    @patch("runtime.demo_ux._find_free_port")
    def test_preview_returns_url(self, mock_find_port, mock_urlopen, mock_popen):
        mock_find_port.return_value = 8080
        mock_popen.return_value = MagicMock(pid=1234)

        with open(os.path.join(self.project_dir, "index.html"), "w") as f:
            f.write("<html></html>")

        result = preview(self.project_dir, timeout_sec=1)

        self.assertIn("url", result)
        self.assertTrue(result["url"].startswith("http://localhost:8080"))
        self.assertEqual(result["server_pid"], 1234)

    @patch("subprocess.Popen")
    @patch("urllib.request.urlopen")
    @patch("runtime.demo_ux._find_free_port")
    def test_preview_returns_project_type(
        self, mock_find_port, mock_urlopen, mock_popen
    ):
        mock_find_port.return_value = 8080
        mock_popen.return_value = MagicMock(pid=1234)

        with open(os.path.join(self.project_dir, "index.html"), "w") as f:
            f.write("<html></html>")

        result = preview(self.project_dir, timeout_sec=1)

        self.assertIn("project_type", result)
        self.assertEqual(result["project_type"], "static")


if __name__ == "__main__":
    unittest.main()
