import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime.operate import check_health, setup_monitoring, update_deployment


class TestSetupMonitoring(unittest.TestCase):
    def test_setup_monitoring_uses_existing_deploy_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / ".omg" / "deploy"
            manifest_path.mkdir(parents=True, exist_ok=True)
            (manifest_path / "latest.json").write_text(
                json.dumps({"target": "vercel", "url": "https://demo.vercel.app"}),
                encoding="utf-8",
            )

            result = setup_monitoring(temp_dir)

            self.assertTrue(result["monitoring_enabled"])
            self.assertEqual(
                result["health_check_url"], "https://demo.vercel.app/health"
            )
            self.assertTrue((Path(temp_dir) / ".omg" / "monitoring.json").exists())


class TestCheckHealth(unittest.TestCase):
    @patch("runtime.operate.urlopen")
    def test_check_health_success(self, mock_urlopen):
        response = MagicMock()
        response.status = 200
        mock_urlopen.return_value.__enter__.return_value = response

        result = check_health("https://example.com/health")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 200)


class TestUpdateDeployment(unittest.TestCase):
    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_dry_run(self, mock_changes, mock_tests, mock_deploy):
        mock_changes.return_value = ["src/app.ts"]
        mock_tests.return_value = {
            "success": True,
            "status": "passed",
            "command": ["bun", "test"],
        }
        mock_deploy.return_value = {
            "success": True,
            "message": "Dry run: would execute vercel deploy --prod --yes",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "vercel.json").write_text("{}\n", encoding="utf-8")

            result = update_deployment(temp_dir, dry_run=True)

            self.assertTrue(result["success"])
            self.assertEqual(result["target"], "vercel")
            self.assertEqual(result["changed_files"], ["src/app.ts"])
            self.assertTrue(result["rollback_available"])
            mock_deploy.assert_called_once()

    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_aborts_on_failed_tests(
        self, mock_changes, mock_tests, mock_deploy
    ):
        mock_changes.return_value = ["src/app.ts"]
        mock_tests.return_value = {
            "success": False,
            "status": "failed",
            "command": ["bun", "test"],
            "exit_code": 1,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "fly.toml").write_text("app = \"demo\"\n", encoding="utf-8")

            result = update_deployment(temp_dir, dry_run=True)

            self.assertFalse(result["success"])
            self.assertEqual(result["target"], "fly")
            self.assertIn("Tests failed", result["message"])
            mock_deploy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
