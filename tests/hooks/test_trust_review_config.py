"""Tests for trust review config discovery integration."""

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure tools/ is on sys.path so config_discovery can be imported for patching
_tools_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

import config_discovery  # noqa: E402

from hooks.trust_review import (
    _validate_config_security,
    _log_config_import,
    review_discovered_configs,
)

# === _validate_config_security tests =========================================


class TestValidateConfigSecurity:
    """Tests for the _validate_config_security helper."""

    def test_clean_config_returns_safe(self, tmp_path: Path):
        """Clean config with no suspicious patterns is safe."""
        config = tmp_path / "CLAUDE.md"
        config.write_text("# My project rules\nUse TypeScript.")
        result = _validate_config_security(str(config), config.read_text())
        assert result["safe"] is True
        assert result["issues"] == []
        assert result["warnings"] == []

    def test_eval_pattern_rejected(self, tmp_path: Path):
        """Config containing eval( is flagged as unsafe."""
        config = tmp_path / "rules.md"
        config.write_text("Run this: eval('code')")
        result = _validate_config_security(str(config), config.read_text())
        assert result["safe"] is False
        assert any("eval" in issue for issue in result["issues"])

    def test_exec_pattern_rejected(self, tmp_path: Path):
        """Config containing exec( is flagged as unsafe."""
        config = tmp_path / "rules.md"
        config.write_text("exec(compile('x', 'y', 'exec'))")
        result = _validate_config_security(str(config), config.read_text())
        assert result["safe"] is False
        assert any("exec" in issue for issue in result["issues"])

    def test_import_pattern_rejected(self, tmp_path: Path):
        """Config containing __import__( is flagged as unsafe."""
        content = "__import__('os').system('rm -rf /')"
        config = tmp_path / "bad.md"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is False
        assert any("__import__" in issue for issue in result["issues"])

    def test_subprocess_pattern_rejected(self, tmp_path: Path):
        """Config mentioning subprocess is flagged."""
        content = "import subprocess\nsubprocess.run(['ls'])"
        config = tmp_path / "script.md"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is False
        assert any("subprocess" in issue for issue in result["issues"])

    def test_os_system_pattern_rejected(self, tmp_path: Path):
        """Config with os.system( is flagged."""
        content = "os.system('echo hello')"
        config = tmp_path / "run.md"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is False
        assert any("os\\.system" in issue for issue in result["issues"])

    def test_credential_pattern_warns_not_blocks(self, tmp_path: Path):
        """Credential patterns produce warnings but config remains safe."""
        content = "Set your api_key in .env and secret token"
        config = tmp_path / "setup.md"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is True
        assert len(result["warnings"]) >= 1
        assert any("api_key" in w for w in result["warnings"])

    def test_password_pattern_warns(self, tmp_path: Path):
        """Password pattern produces a warning."""
        content = "password: changeme123"
        config = tmp_path / "config.yaml"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is True
        assert any("password" in w for w in result["warnings"])

    def test_large_file_warns(self, tmp_path: Path):
        """Files over 100KB produce a size warning."""
        config = tmp_path / "big.md"
        config.write_text("x" * (101 * 1024))  # 101KB
        result = _validate_config_security(str(config), "x" * 100)
        assert result["safe"] is True
        assert any("large" in w for w in result["warnings"])

    def test_multiple_dangerous_patterns(self, tmp_path: Path):
        """Multiple dangerous patterns all get reported."""
        content = "eval('a')\nexec('b')\nsubprocess.call([])"
        config = tmp_path / "multi.md"
        config.write_text(content)
        result = _validate_config_security(str(config), content)
        assert result["safe"] is False
        assert len(result["issues"]) >= 3

    def test_empty_content_is_safe(self, tmp_path: Path):
        """Empty content is safe."""
        config = tmp_path / "empty.md"
        config.write_text("")
        result = _validate_config_security(str(config), "")
        assert result["safe"] is True
        assert result["issues"] == []

    def test_nonexistent_path_no_crash(self):
        """Non-existent path doesn't crash (size check handles OSError)."""
        result = _validate_config_security("/nonexistent/path.md", "clean content")
        assert result["safe"] is True


# === _log_config_import tests ================================================


class TestLogConfigImport:
    """Tests for config import logging."""

    @patch("_common.atomic_json_write")
    def test_log_creates_entry(self, mock_write, tmp_path: Path):
        """Logging creates a properly formatted entry."""
        config = tmp_path / "CLAUDE.md"
        config.write_text("# Rules")
        _log_config_import(str(config), "claude_code", True, project_dir=str(tmp_path))

        assert mock_write.called
        log_path, data = mock_write.call_args[0]
        assert ".omg/trust/config_imports.json" in log_path
        assert len(data) == 1
        entry = data[0]
        assert entry["tool"] == "claude_code"
        assert entry["approved"] is True
        assert "timestamp" in entry
        assert "sha256_hash" in entry
        assert entry["config_path"] == str(config)

    @patch("_common.atomic_json_write")
    def test_log_rejected_entry(self, mock_write, tmp_path: Path):
        """Logging a rejected config records approved=False."""
        config = tmp_path / "bad.md"
        config.write_text("eval('x')")
        _log_config_import(str(config), "cursor", False, project_dir=str(tmp_path))

        assert mock_write.called
        _, data = mock_write.call_args[0]
        assert data[0]["approved"] is False

    @patch("_common.atomic_json_write")
    def test_log_appends_to_existing(self, mock_write, tmp_path: Path):
        """New entries append to existing log file."""
        log_dir = tmp_path / ".omg" / "trust"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "config_imports.json"
        existing = [{"timestamp": "2026-01-01T00:00:00", "config_path": "old.md", "tool": "cursor", "approved": True, "sha256_hash": "abc"}]
        log_file.write_text(json.dumps(existing))

        config = tmp_path / "new.md"
        config.write_text("new content")
        _log_config_import(str(config), "windsurf", True, project_dir=str(tmp_path))

        assert mock_write.called
        _, data = mock_write.call_args[0]
        assert len(data) == 2
        assert data[0]["tool"] == "cursor"
        assert data[1]["tool"] == "windsurf"

    @patch("_common.atomic_json_write")
    def test_log_sha256_hash_computed(self, mock_write, tmp_path: Path):
        """SHA-256 hash is computed correctly."""
        config = tmp_path / "test.md"
        content = "hello world"
        config.write_text(content)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        _log_config_import(str(config), "gemini", True, project_dir=str(tmp_path))

        _, data = mock_write.call_args[0]
        assert data[0]["sha256_hash"] == expected_hash


# === review_discovered_configs tests =========================================


class TestReviewDiscoveredConfigs:
    """Tests for the main review_discovered_configs function."""

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "false"}, clear=False)
    def test_feature_flag_disabled_returns_skipped(self):
        """When feature flag is disabled, returns skipped result."""
        result = review_discovered_configs(".")
        assert result["skipped"] is True
        assert result["reason"] == "feature disabled"

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "0"}, clear=False)
    def test_feature_flag_zero_returns_skipped(self):
        """Env var '0' means disabled."""
        result = review_discovered_configs(".")
        assert result["skipped"] is True

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_clean_configs_approved(self, mock_log, tmp_path: Path):
        """Clean discovered configs are approved."""
        # Create a clean config file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        claude_md = tmp_path / ".claude" / "CLAUDE.md"
        claude_md.write_text("# Project rules\nUse TypeScript.")

        mock_discovery = {
            "discovered": [
                {"tool": "claude_code", "paths": [".claude/CLAUDE.md"], "format": "markdown", "size_bytes": 30, "readable": True}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["skipped"] is False
        assert len(result["approved"]) == 1
        assert result["approved"][0]["tool"] == "claude_code"
        assert len(result["rejected"]) == 0

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_dangerous_config_rejected(self, mock_log, tmp_path: Path):
        """Config with eval( is rejected."""
        bad_file = tmp_path / ".cursorrules"
        bad_file.write_text("eval('malicious code')")

        mock_discovery = {
            "discovered": [
                {"tool": "cursor", "paths": [".cursorrules"], "format": "unknown", "size_bytes": 25, "readable": True}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["skipped"] is False
        assert len(result["rejected"]) == 1
        assert result["rejected"][0]["tool"] == "cursor"
        assert "eval" in result["rejected"][0]["reason"]
        assert len(result["approved"]) == 0

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_credential_warning_still_approved(self, mock_log, tmp_path: Path):
        """Config with credential patterns gets warnings but is still approved."""
        config = tmp_path / "CLAUDE.md"
        config.write_text("Set your api_key and token in environment")

        mock_discovery = {
            "discovered": [
                {"tool": "claude_code", "paths": ["CLAUDE.md"], "format": "markdown", "size_bytes": 40, "readable": True}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["skipped"] is False
        assert len(result["approved"]) == 1
        assert len(result["warnings"]) >= 1
        assert any("api_key" in w for w in result["warnings"])

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_mixed_configs_sorted(self, mock_log, tmp_path: Path):
        """Mix of clean and dangerous configs are properly sorted."""
        clean = tmp_path / "CLAUDE.md"
        clean.write_text("# Clean rules")
        dangerous = tmp_path / ".cursorrules"
        dangerous.write_text("exec('rm -rf /')")

        mock_discovery = {
            "discovered": [
                {"tool": "claude_code", "paths": ["CLAUDE.md"], "format": "markdown", "size_bytes": 13, "readable": True},
                {"tool": "cursor", "paths": [".cursorrules"], "format": "unknown", "size_bytes": 17, "readable": True},
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert len(result["approved"]) == 1
        assert len(result["rejected"]) == 1
        assert result["approved"][0]["tool"] == "claude_code"
        assert result["rejected"][0]["tool"] == "cursor"

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_no_discovered_configs(self, mock_log, tmp_path: Path):
        """Empty discovery result returns empty lists."""
        mock_discovery = {
            "discovered": [],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["skipped"] is False
        assert result["approved"] == []
        assert result["rejected"] == []
        assert result["warnings"] == []

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_unreadable_config_handled(self, mock_log, tmp_path: Path):
        """Unreadable config (readable=False) is handled gracefully."""
        mock_discovery = {
            "discovered": [
                {"tool": "windsurf", "paths": [".windsurfrules"], "format": "unknown", "size_bytes": 0, "readable": False}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        # Unreadable config with empty content → safe (no dangerous patterns in empty string)
        assert result["skipped"] is False
        assert len(result["approved"]) == 1

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_import_logging_called(self, mock_log, tmp_path: Path):
        """Import logging is called for each discovered config."""
        config = tmp_path / "CLAUDE.md"
        config.write_text("# Clean")

        mock_discovery = {
            "discovered": [
                {"tool": "claude_code", "paths": ["CLAUDE.md"], "format": "markdown", "size_bytes": 7, "readable": True}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        # _log_config_import should have been called
        assert mock_log.called
        call_args = mock_log.call_args
        assert call_args[0][0] == "CLAUDE.md"  # config_path
        assert call_args[0][1] == "claude_code"  # tool
        assert call_args[1]["approved"] is True  # approved (keyword arg)

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_result_includes_scan_metadata(self, mock_log, tmp_path: Path):
        """Result includes scan_dir and timestamp from discovery."""
        mock_discovery = {
            "discovered": [],
            "scan_dir": "/some/project",
            "timestamp": "2026-03-02T12:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["scan_dir"] == "/some/project"
        assert result["timestamp"] == "2026-03-02T12:00:00"

    @patch.dict(os.environ, {"OMG_CONFIG_DISCOVERY_ENABLED": "true"}, clear=False)
    @patch("hooks.trust_review._log_config_import")
    def test_config_with_empty_paths_skipped(self, mock_log, tmp_path: Path):
        """Config entry with empty paths list is skipped."""
        mock_discovery = {
            "discovered": [
                {"tool": "unknown_tool", "paths": [], "format": "unknown", "size_bytes": 0, "readable": False}
            ],
            "scan_dir": str(tmp_path),
            "timestamp": "2026-03-02T10:00:00",
        }

        with patch.object(config_discovery, "discover_configs", return_value=mock_discovery):
            result = review_discovered_configs(str(tmp_path))

        assert result["approved"] == []
        assert result["rejected"] == []


# === Existing trust_review functions still work ==============================


class TestExistingTrustReviewUnchanged:
    """Verify existing functions remain intact after extension."""

    def test_review_config_change_still_works(self):
        """Original review_config_change function is unbroken."""
        from hooks.trust_review import review_config_change

        old = {"permissions": {"allow": ["Read"]}}
        new = {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}
        review = review_config_change("settings.json", old, new)
        assert review["verdict"] == "deny"
        assert review["risk_score"] >= 80

    def test_write_trust_manifest_still_works(self, tmp_path: Path):
        """Original write_trust_manifest function is unbroken."""
        from hooks.trust_review import review_config_change, write_trust_manifest

        review = review_config_change("settings.json", {}, {"hooks": {"PreToolUse": []}})
        path = write_trust_manifest(str(tmp_path), review)
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["version"] == "omg-v1"

    def test_format_review_summary_still_works(self):
        """Original format_review_summary function is unbroken."""
        from hooks.trust_review import format_review_summary

        review = {"verdict": "allow", "risk_score": 5, "risk_level": "low", "reasons": ["test"]}
        summary = format_review_summary(review)
        assert "Trust Review" in summary
        assert "allow" in summary
