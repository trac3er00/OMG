"""Optional adapter for summarizing Playwright artifacts into proof-chain-friendly payloads."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def summarize_playwright_artifacts(
    trace_path: str | None = None,
    junit_path: str | None = None,
    screenshots: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize browser artifacts into a proof-chain-friendly dict.
    
    Returns a dict consumable by proof-gate / claim-judge:
        status     — "ok" or "error"
        artifacts  — {trace, junit, screenshots} (only provided paths)
        metadata   — provided metadata or {}
    """
    if not trace_path and not junit_path and not screenshots:
        return {"status": "error", "reason": "no_artifacts_provided"}

    artifacts: dict[str, Any] = {}
    
    if trace_path:
        artifacts["trace"] = str(Path(trace_path))
        
    if junit_path:
        artifacts["junit"] = str(Path(junit_path))
        
    if screenshots:
        artifacts["screenshots"] = [str(Path(s)) for s in screenshots]

    return {
        "status": "ok",
        "artifacts": artifacts,
        "metadata": metadata or {},
    }
