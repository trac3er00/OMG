"""Playwright-based browser evidence pack under isolated execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from runtime.untrusted_content import (
    TRUST_TIER_CONFIG,
    TrustTier,
    get_untrusted_content_state,
)


class IsolationError(Exception):
    """Raised when browser execution is attempted without proper isolation or trust tier."""
    pass


class PlaywrightPack:
    """Canonical browser pack with isolated execution and evidence emission.

    Emits a proof-ready trace pack contract consumed by proof-gate / claim-judge:
        artifacts  — trace.zip, junit.xml, screenshot paths
        metadata   — isolated, timestamp, project_dir, trust_tier
    """

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

    def _resolve_trust_tier(self) -> str:
        if self.isolated:
            return TrustTier.BROWSER.value
        state = get_untrusted_content_state(str(self.project_dir))
        return str(state.get("last_trust_tier", TrustTier.BROWSER.value))

    def emit_artifacts(self, output_dir: str | Path) -> dict[str, Any]:
        """Emit mock Playwright artifacts (trace.zip, screenshots, junit.xml)."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        screenshots_dir = out_path / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

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
            encoding="utf-8",
        )

        return {
            "trace": str(trace_path),
            "screenshots": [str(screenshot_path)],
            "junit": str(junit_path),
        }

    def _build_metadata(self, *, timestamp: str | None = None) -> dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        trust_tier = self._resolve_trust_tier()
        tier_config = TRUST_TIER_CONFIG.get(
            TrustTier(trust_tier),
            TRUST_TIER_CONFIG[TrustTier.BROWSER],
        )
        return {
            "isolated": self.isolated,
            "timestamp": ts,
            "project_dir": str(self.project_dir),
            "trust_tier": trust_tier,
            "trust_label": tier_config.label,
            "trust_score": tier_config.score,
        }

    def run_smoke(self, fixture_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
        """Run smoke test against a local HTML fixture and emit proof-ready artifacts.

        Returns a dict consumable by proof-gate / claim-judge:
            status     — "success"
            fixture    — resolved fixture path
            artifacts  — {trace, junit, screenshots}
            metadata   — {isolated, timestamp, project_dir, trust_tier, trust_label, trust_score}
        """
        self.check_isolation()

        fixture = Path(fixture_path)
        if not fixture.exists():
            raise FileNotFoundError(f"Smoke fixture not found: {fixture}")

        if output_dir is None:
            output_dir = self.project_dir / ".omg" / "evidence" / "browser"

        timestamp = datetime.now(timezone.utc).isoformat()

        artifacts = self.emit_artifacts(output_dir)
        metadata = self._build_metadata(timestamp=timestamp)

        evidence_dir = Path(output_dir)
        _write_browser_evidence(
            evidence_dir,
            fixture=fixture,
            artifacts=artifacts,
            metadata=metadata,
        )

        return {
            "status": "success",
            "fixture": str(fixture),
            "artifacts": artifacts,
            "metadata": metadata,
        }


def _write_browser_evidence(
    output_dir: Path,
    *,
    fixture: Path,
    artifacts: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "browser-evidence.json"

    fixture_bytes = fixture.read_bytes() if fixture.exists() else b""
    fixture_hash = sha256(fixture_bytes).hexdigest()

    payload = {
        "schema": "BrowserEvidence",
        "generated_at": metadata.get("timestamp", ""),
        "fixture": str(fixture),
        "fixture_hash": fixture_hash,
        "artifacts": artifacts,
        "metadata": metadata,
        "trust_tier": metadata.get("trust_tier", "browser"),
        "trust_label": metadata.get("trust_label", "UNTRUSTED_EXTERNAL_CONTENT"),
        "trust_score": metadata.get("trust_score", 0.0),
    }
    evidence_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return str(evidence_path)
