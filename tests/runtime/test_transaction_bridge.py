"""Integration tests for ConfigTransaction bridge across writers and setup flows.

Proves:
1. A write to a Claude config via the existing public API produces a transaction receipt.
2. A simulated multi-host setup with injected failure on host N rolls back hosts 1..N-1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from runtime.config_transaction import ConfigTransactionError


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Receipt from standalone writer
# ---------------------------------------------------------------------------


class TestWriterReceipt:
    """Standalone writer calls produce a module-level receipt."""

    def test_claude_write_produces_receipt(self, fake_home: Path, tmp_path: Path) -> None:
        _ = fake_home
        from runtime import mcp_config_writers as mod

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        mod.write_claude_mcp_config(str(project_dir), "http://localhost:8765")

        receipt = mod._last_receipt
        assert receipt is not None
        assert receipt["executed"] is True
        config_path = str((project_dir / ".mcp.json").resolve())
        assert any(w["path"] == config_path for w in receipt["planned_writes"])
        assert receipt["verification"][config_path] == "ok"

    def test_codex_stdio_write_produces_receipt(self, fake_home: Path, tmp_path: Path) -> None:
        _ = fake_home
        from runtime import mcp_config_writers as mod

        codex_path = tmp_path / ".codex" / "config.toml"
        mod.write_codex_mcp_stdio_config(
            command="python3",
            args=["-m", "runtime.omg_mcp_server"],
            server_name="omg-control",
            config_path=str(codex_path),
        )

        receipt = mod._last_receipt
        assert receipt is not None
        assert receipt["executed"] is True


# ---------------------------------------------------------------------------
# Multi-host rollback
# ---------------------------------------------------------------------------


class TestMultiHostRollback:
    """configure_mcp failure on host N rolls back hosts 1..N-1."""

    def test_failure_on_host_n_rolls_back_hosts_1_to_n_minus_1(
        self,
        fake_home: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _ = fake_home
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Pre-existing Codex config
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        codex_config = codex_dir / "config.toml"
        codex_original = "# original codex config\n"
        _ = codex_config.write_text(codex_original, encoding="utf-8")

        # Pre-existing Gemini config
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        gemini_config = gemini_dir / "settings.json"
        gemini_original = '{"original": true}\n'
        _ = gemini_config.write_text(gemini_original, encoding="utf-8")

        # Inject write failure for the gemini target (first write only → allow rollback)
        from runtime import config_transaction as ct_mod

        real_write = ct_mod._ATOMIC_WRITE_TEXT_SAFE
        gemini_resolved = gemini_config.resolve()
        hit = {"count": 0}

        def flaky_write(path: Path, content: str, *, mode: int = 0o600) -> None:
            if Path(path).resolve() == gemini_resolved:
                hit["count"] += 1
                if hit["count"] == 1:
                    raise OSError("injected gemini write failure")
            real_write(path, content, mode=mode)

        monkeypatch.setattr(ct_mod, "_ATOMIC_WRITE_TEXT_SAFE", flaky_write)

        from hooks.setup_wizard import configure_mcp

        result = configure_mcp(
            project_dir=str(project_dir),
            detected_clis={
                "codex": {"detected": True},
                "gemini": {"detected": True},
            },
        )

        # Transaction should have failed and rolled back all writes
        assert result["configured"] == []
        assert len(result.get("errors", {})) > 0

        # Claude .mcp.json should not exist (didn't exist before → rollback removed it)
        claude_config_path = project_dir / ".mcp.json"
        assert not claude_config_path.exists()

        # Codex config should be restored to its original content
        assert codex_config.read_text(encoding="utf-8") == codex_original

        # Gemini config should be restored to its original content
        assert gemini_config.read_text(encoding="utf-8") == gemini_original
