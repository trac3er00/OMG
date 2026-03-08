from __future__ import annotations

from pathlib import Path

from runtime.omg_browser_cli import (
    ensure_playwright_cli,
    resolve_playwright_command,
    run_browser_cli,
)


def test_resolve_playwright_command_prefers_native_playwright() -> None:
    def fake_which(name: str) -> str | None:
        if name == "playwright":
            return "/usr/local/bin/playwright"
        if name == "npx":
            return "/usr/local/bin/npx"
        return None

    assert resolve_playwright_command(which=fake_which) == ["playwright"]


def test_resolve_playwright_command_falls_back_to_playwright_cli() -> None:
    def fake_which(name: str) -> str | None:
        if name == "playwright-cli":
            return "/usr/local/bin/playwright-cli"
        return None

    assert resolve_playwright_command(which=fake_which) == ["playwright-cli"]


def test_ensure_playwright_cli_detects_missing_binary(tmp_path: Path) -> None:
    result = ensure_playwright_cli(project_dir=tmp_path, which=lambda _name: None)

    assert result["status"] == "missing"
    assert "playwright" in result["remediation"].lower()
    assert "npx playwright" in result["remediation"]


def test_run_browser_cli_normalizes_artifacts_into_omg_evidence(tmp_path: Path) -> None:
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    trace_path = external_dir / "trace.zip"
    trace_path.write_bytes(b"PK\x03\x04mock_trace")
    junit_path = external_dir / "junit.xml"
    junit_path.write_text("<testsuites></testsuites>", encoding="utf-8")
    screenshot_path = external_dir / "shot.png"
    screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\nmock_png")

    def fake_runner(*, command: list[str], cwd: str, goal: str) -> dict[str, object]:
        assert command == ["playwright"]
        assert cwd == str(tmp_path)
        assert goal == "capture login flow"
        return {
            "returncode": 0,
            "trace_path": str(trace_path),
            "junit_path": str(junit_path),
            "screenshots": [str(screenshot_path)],
            "metadata": {"tool": "playwright", "goal": goal},
        }

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/playwright" if name == "playwright" else None

    result = run_browser_cli(
        goal="capture login flow",
        project_dir=tmp_path,
        which=fake_which,
        runner=fake_runner,
        isolated=True,
    )

    assert result["status"] == "success"
    artifacts = result["artifacts"]
    assert artifacts["trace"].startswith(str(tmp_path / ".omg" / "evidence" / "browser"))
    assert artifacts["junit"].startswith(str(tmp_path / ".omg" / "evidence" / "browser"))
    assert artifacts["screenshots"][0].startswith(str(tmp_path / ".omg" / "evidence" / "browser" / "screenshots"))
    assert (tmp_path / ".omg" / "evidence" / "browser" / "browser-evidence.json").exists()
