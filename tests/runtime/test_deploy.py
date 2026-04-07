import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from runtime.deploy_integration import (
    PLATFORMS,
    deploy,
    detect_available_platforms,
    _extract_url,
)


class TestDetectAvailablePlatforms(unittest.TestCase):
    @patch("shutil.which", return_value=None)
    def test_no_cli_available(self, mock_which):
        result = detect_available_platforms()
        self.assertEqual(result, [])

    @patch("shutil.which")
    def test_vercel_available(self, mock_which):
        mock_which.side_effect = lambda name: (
            "/usr/bin/vercel" if name == "vercel" else None
        )
        result = detect_available_platforms()
        self.assertIn("vercel", result)
        self.assertNotIn("netlify", result)

    @patch("shutil.which")
    def test_multiple_platforms_available(self, mock_which):
        mock_which.side_effect = lambda name: (
            f"/usr/bin/{name}" if name in ("vercel", "netlify") else None
        )
        result = detect_available_platforms()
        self.assertIn("vercel", result)
        self.assertIn("netlify", result)


class TestDeploy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.which", return_value=None)
    def test_no_cli_returns_install_hint(self, mock_which):
        result = deploy(self.project_dir)
        self.assertFalse(result["deployed"])
        self.assertIsNone(result["platform"])
        self.assertIsNone(result["url"])
        self.assertEqual(result["available_platforms"], [])
        self.assertIn("install", result["message"].lower())

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_successful_vercel_deploy(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: (
            "/usr/bin/vercel" if name == "vercel" else None
        )
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Production: https://my-app.vercel.app\n",
            stderr="",
        )

        result = deploy(self.project_dir, platform="vercel")

        self.assertTrue(result["deployed"])
        self.assertEqual(result["platform"], "vercel")
        self.assertEqual(result["url"], "https://my-app.vercel.app")
        self.assertEqual(result["message"], "Deployed successfully")

        mock_run.assert_called_once_with(
            PLATFORMS["vercel"]["command"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_deploy_autodetects_first_available(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: (
            "/usr/bin/netlify" if name == "netlify" else None
        )
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://my-site.netlify.app\n",
            stderr="",
        )

        result = deploy(self.project_dir)

        self.assertTrue(result["deployed"])
        self.assertEqual(result["platform"], "netlify")
        mock_run.assert_called_once()

    @patch("shutil.which")
    def test_deploy_platform_not_found(self, mock_which):
        mock_which.side_effect = lambda name: (
            "/usr/bin/vercel" if name == "vercel" else None
        )
        result = deploy(self.project_dir, platform="netlify")

        self.assertFalse(result["deployed"])
        self.assertEqual(result["platform"], "netlify")
        self.assertIn("vercel", result["available_platforms"])
        self.assertIn("not found", result["message"].lower())

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_deploy_nonzero_exit(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: (
            "/usr/bin/vercel" if name == "vercel" else None
        )
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: Not authenticated",
        )

        result = deploy(self.project_dir, platform="vercel")

        self.assertFalse(result["deployed"])
        self.assertEqual(result["platform"], "vercel")
        self.assertIn("Not authenticated", result["message"])

    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="vercel", timeout=120),
    )
    @patch("shutil.which")
    def test_deploy_timeout(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: (
            "/usr/bin/vercel" if name == "vercel" else None
        )

        result = deploy(self.project_dir, platform="vercel")

        self.assertFalse(result["deployed"])
        self.assertIn("timed out", result["message"].lower())


class TestExtractUrl(unittest.TestCase):
    def test_extract_vercel_url(self):
        output = (
            "Production: https://my-app.vercel.app\nInspect: https://vercel.com/inspect"
        )
        self.assertEqual(_extract_url(output, "vercel"), "https://my-app.vercel.app")

    def test_extract_netlify_url(self):
        output = "Website URL: https://my-site.netlify.app"
        self.assertEqual(_extract_url(output, "netlify"), "https://my-site.netlify.app")

    def test_no_url_in_output(self):
        self.assertIsNone(_extract_url("Deployed!", "vercel"))

    def test_empty_output(self):
        self.assertIsNone(_extract_url("", "vercel"))


class TestPlatformsConfig(unittest.TestCase):
    def test_all_platforms_have_required_keys(self):
        for name, config in PLATFORMS.items():
            self.assertIn("cli", config, f"{name} missing 'cli'")
            self.assertIn("command", config, f"{name} missing 'command'")
            self.assertIsInstance(
                config["command"], list, f"{name} command should be list"
            )

    def test_known_platforms_exist(self):
        self.assertIn("vercel", PLATFORMS)
        self.assertIn("netlify", PLATFORMS)
        self.assertIn("cloudflare", PLATFORMS)


if __name__ == "__main__":
    unittest.main()
