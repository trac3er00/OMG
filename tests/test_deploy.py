"""Tests for deploy target detection, monitoring setup, and update flow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from runtime.operate import check_health, setup_monitoring, update_deployment


class TestSetupMonitoring:
    """Tests for setup_monitoring function."""

    def test_setup_monitoring_returns_dict(self, tmp_path: Path) -> None:
        """Verify setup_monitoring returns dict with required keys."""
        result = setup_monitoring(str(tmp_path))

        assert isinstance(result, dict)
        assert "health_check_url" in result
        assert "monitoring_enabled" in result
        assert "dashboard_url" in result
        assert result["monitoring_enabled"] is True
        assert isinstance(result["health_check_url"], str)
        assert isinstance(result["dashboard_url"], str)

    def test_setup_monitoring_with_existing_deploy_url(self, tmp_path: Path) -> None:
        """Verify setup_monitoring uses existing deploy URL for health check."""
        manifest_path = tmp_path / ".omg" / "deploy"
        manifest_path.mkdir(parents=True, exist_ok=True)
        (manifest_path / "latest.json").write_text(
            json.dumps({"target": "vercel", "url": "https://myapp.vercel.app"}),
            encoding="utf-8",
        )

        result = setup_monitoring(str(tmp_path))

        assert result["health_check_url"] == "https://myapp.vercel.app/health"
        assert result["dashboard_url"] == "https://myapp.vercel.app/monitoring"


class TestCheckHealth:
    """Tests for check_health function."""

    def test_check_health_unreachable(self) -> None:
        """Verify check_health handles unreachable URL gracefully."""
        with patch("runtime.operate.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")

            result = check_health("http://localhost:9999/health")

            assert isinstance(result, dict)
            assert result["ok"] is False
            assert result["status_code"] is None
            assert "error" in result
            assert result["url"] == "http://localhost:9999/health"
            assert "response_time_ms" in result

    @patch("runtime.operate.urlopen")
    def test_check_health_success(self, mock_urlopen: MagicMock) -> None:
        """Verify check_health returns correct data on success."""
        response = MagicMock()
        response.status = 200
        mock_urlopen.return_value.__enter__.return_value = response

        result = check_health("https://example.com/health")

        assert result["ok"] is True
        assert result["status_code"] == 200
        assert result["url"] == "https://example.com/health"


class TestUpdateDeployment:
    """Tests for update_deployment function."""

    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_dry_run(
        self,
        mock_changes: MagicMock,
        mock_tests: MagicMock,
        mock_deploy: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify dry_run=True doesn't actually deploy."""
        mock_changes.return_value = ["src/index.ts", "package.json"]
        mock_tests.return_value = {
            "success": True,
            "status": "passed",
            "command": ["bun", "test"],
        }
        mock_deploy.return_value = {
            "success": True,
            "message": "Dry run: would execute vercel deploy --prod --yes",
        }

        (tmp_path / "vercel.json").write_text("{}\n", encoding="utf-8")

        result = update_deployment(str(tmp_path), dry_run=True)

        assert result["success"] is True
        assert result["target"] == "vercel"
        assert "Dry run" in result["message"]
        mock_deploy.assert_called_once()
        call_args = mock_deploy.call_args
        assert call_args[0][2] is True  # dry_run argument

    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_detects_changes(
        self,
        mock_changes: MagicMock,
        mock_tests: MagicMock,
        mock_deploy: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify change detection works."""
        changed_files = ["src/app.ts", "src/utils.ts", "config.json"]
        mock_changes.return_value = changed_files
        mock_tests.return_value = {
            "success": True,
            "status": "passed",
            "command": ["pytest", "tests"],
        }
        mock_deploy.return_value = {
            "success": True,
            "message": "Deployment completed for fly.",
        }

        (tmp_path / "fly.toml").write_text('app = "demo"\n', encoding="utf-8")

        result = update_deployment(str(tmp_path), dry_run=True)

        assert result["changed_files"] == changed_files
        assert len(result["changed_files"]) == 3
        assert result["target"] == "fly"

    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_no_changes(
        self,
        mock_changes: MagicMock,
        mock_tests: MagicMock,
        mock_deploy: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify no deploy happens when no changes detected."""
        mock_changes.return_value = []

        result = update_deployment(str(tmp_path), dry_run=True)

        assert result["success"] is True
        assert result["changed_files"] == []
        assert "No changed files" in result["message"]
        mock_deploy.assert_not_called()

    @patch("runtime.operate._run_deploy")
    @patch("runtime.operate._run_pre_deploy_tests")
    @patch("runtime.operate._collect_changed_files")
    def test_update_deployment_failed_tests_aborts(
        self,
        mock_changes: MagicMock,
        mock_tests: MagicMock,
        mock_deploy: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify deployment aborts when tests fail."""
        mock_changes.return_value = ["src/app.ts"]
        mock_tests.return_value = {
            "success": False,
            "status": "failed",
            "command": ["pytest", "tests"],
            "exit_code": 1,
            "message": "AssertionError",
        }

        (tmp_path / "netlify.toml").write_text("[build]\n", encoding="utf-8")

        result = update_deployment(str(tmp_path), dry_run=True)

        assert result["success"] is False
        assert "Tests failed" in result["message"]
        mock_deploy.assert_not_called()
