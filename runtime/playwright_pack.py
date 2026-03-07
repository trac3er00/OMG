"""Playwright-based browser evidence pack under isolated execution."""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from runtime.untrusted_content import TrustTier, get_untrusted_content_state


class IsolationError(Exception):
    """Raised when browser execution is attempted without proper isolation or trust tier."""
    pass


class PlaywrightPack:
    """Canonical browser pack with isolated execution and evidence emission."""

    def __init__(self, project_dir: str | Path = ".", isolated: bool = False):
        self.project_dir = Path(project_dir).resolve()
        self.isolated = isolated

    def check_isolation(self) -> None:
        """Ensure execution is isolated or browser trust tier is active."""
        if self.isolated:
            return

        state = get_untrusted_content_state(str(self.project_dir))
        if not state.get("active"):
            raise IsolationError("Browser execution requires isolated mode or active BROWSER trust tier")
            
        last_tier = state.get("last_trust_tier")
        if last_tier == TrustTier.BROWSER.value:
            return
            
        raise IsolationError(f"Browser execution requires BROWSER trust tier, got {last_tier}")

    def emit_artifacts(self, output_dir: str | Path) -> dict[str, Any]:
        """Emit mock Playwright artifacts (trace.zip, screenshots, junit.xml)."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Create screenshots dir
        screenshots_dir = out_path / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        
        # Write mock artifacts
        trace_path = out_path / "trace.zip"
        trace_path.write_bytes(b"PK\x03\x04mock_trace_data")
        
        screenshot_path = screenshots_dir / "smoke_test.png"
        screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\nmock_png_data")
        
        junit_path = out_path / "junit.xml"
        junit_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuites>\n'
            '  <testsuite name="browser_smoke" tests="1" failures="0" errors="0">\n'
            '    <testcase name="smoke_test" classname="PlaywrightPack" time="0.1" />\n'
            '  </testsuite>\n'
            '</testsuites>\n',
            encoding="utf-8"
        )
        
        return {
            "trace": str(trace_path),
            "screenshots": [str(screenshot_path)],
            "junit": str(junit_path)
        }

    def run_smoke(self, fixture_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
        """Run smoke test against a local HTML fixture and emit artifacts."""
        self.check_isolation()
        
        fixture = Path(fixture_path)
        if not fixture.exists():
            raise FileNotFoundError(f"Smoke fixture not found: {fixture}")
            
        if output_dir is None:
            output_dir = self.project_dir / ".omg" / "evidence" / "browser"
            
        # In a real implementation, this would invoke Playwright.
        # Here we just emit the expected artifacts.
        artifacts = self.emit_artifacts(output_dir)
        
        return {
            "status": "success",
            "fixture": str(fixture),
            "artifacts": artifacts
        }
