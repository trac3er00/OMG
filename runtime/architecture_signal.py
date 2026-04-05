"""Bounded architecture signal artifacts for context-engine consumers.

Produces a compact summary of dependency graph and LSP diagnostics.
Raw data stays in artifact files; only bounded summaries plus artifact
pointers enter later context-engine consumers.

Crash-isolated: ``build_architecture_signal`` never raises.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

_SUMMARY_MAX_CHARS = 500
_STATE_REL = Path(".omg") / "state" / "architecture_signal"
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature flag helper
# ---------------------------------------------------------------------------

def _get_feature_flag(name: str, default: bool = False) -> bool:
    """Check feature flag via env var first, then hooks._common."""
    env_key = f"OMG_{name.upper()}_ENABLED"
    env_val = os.environ.get(env_key, "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    try:
        from hooks._common import get_feature_flag as _gff
        return _gff(name, default)
    except Exception as exc:
        _logger.debug("Failed to resolve feature flag %s via hooks: %s", name, exc, exc_info=True)
        return default


# ---------------------------------------------------------------------------
# Graph summary (reads graph_builder output, never modifies it)
# ---------------------------------------------------------------------------

def _build_graph_summary(project_dir: str) -> tuple[str | None, dict[str, Any], float]:
    """Build dependency graph summary when CODEBASE_VIZ is enabled.

    Returns ``(artifact_path_or_none, metrics_dict, elapsed_ms)``.
    """
    t0 = time.monotonic()

    if not _get_feature_flag("CODEBASE_VIZ", default=False):
        return None, {}, (time.monotonic() - t0) * 1000

    try:
        from plugins.viz.graph_builder import build_project_graph
        result = build_project_graph(project_dir)
    except Exception as exc:
        _logger.debug("Failed to build dependency graph summary: %s", exc, exc_info=True)
        return None, {}, (time.monotonic() - t0) * 1000

    raw_metrics = result.get("metrics", {})
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}

    # Persist raw graph as a side artifact (never injected into prompts)
    artifact_path = Path(project_dir) / _STATE_REL / "dependency-graph-raw.json"
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = artifact_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
        os.rename(tmp, artifact_path)
    except Exception as exc:
        _logger.debug("Failed to persist architecture graph artifact to %s: %s", artifact_path, exc, exc_info=True)

    elapsed = (time.monotonic() - t0) * 1000
    return str(artifact_path), metrics, elapsed


# ---------------------------------------------------------------------------
# LSP diagnostics summary (file-path scan, no live LSP required)
# ---------------------------------------------------------------------------

def _build_lsp_summary(project_dir: str) -> tuple[str | None, dict[str, int], float]:
    """Collect LSP diagnostic counts from evidence artifact if available.

    Returns ``(artifact_path_or_none, severity_counts, elapsed_ms)``.
    """
    t0 = time.monotonic()

    lsp_path = Path(project_dir) / ".omg" / "evidence" / "lsp-diagnostics.json"
    if not lsp_path.exists():
        return None, {}, (time.monotonic() - t0) * 1000

    try:
        data = json.loads(lsp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger.debug("Failed to parse LSP diagnostics from %s: %s", lsp_path, exc, exc_info=True)
        return None, {}, (time.monotonic() - t0) * 1000

    # Normalize: accept both list-of-diagnostics and {diagnostics: [...]}
    diagnostics: list[Any] = data if isinstance(data, list) else (
        data.get("diagnostics", []) if isinstance(data, dict) else []
    )

    counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0, "hint": 0, "total": 0}
    if isinstance(diagnostics, list):
        for d in diagnostics:
            if isinstance(d, dict):
                sev = str(d.get("severity", "info")).lower()
                if sev in counts:
                    counts[sev] += 1
                counts["total"] += 1

    elapsed = (time.monotonic() - t0) * 1000
    return str(lsp_path), counts, elapsed


# ---------------------------------------------------------------------------
# Summary formatter
# ---------------------------------------------------------------------------

def _format_summary(
    graph_metrics: dict[str, Any],
    lsp_counts: dict[str, int],
    fallback: bool,
) -> str:
    """Format a bounded summary string (max ``_SUMMARY_MAX_CHARS`` chars)."""
    if fallback:
        return "no architecture signals available"

    parts: list[str] = []

    if graph_metrics:
        mc = graph_metrics.get("module_count", 0)
        ec = graph_metrics.get("edge_count", 0)
        md = graph_metrics.get("max_depth", 0)
        cs = graph_metrics.get("coupling_score", 0.0)
        cycles = graph_metrics.get("circular_deps", [])
        parts.append(f"graph: {mc} modules, {ec} edges, depth={md}, coupling={cs:.2f}")
        if cycles:
            parts.append(f"  cycles: {len(cycles)}")

    if lsp_counts and lsp_counts.get("total", 0) > 0:
        parts.append(
            f"lsp: {lsp_counts.get('error', 0)} errors, "
            f"{lsp_counts.get('warning', 0)} warnings, "
            f"{lsp_counts.get('total', 0)} total"
        )

    if not parts:
        return "no architecture signals available"

    return "\n".join(parts)[:_SUMMARY_MAX_CHARS]


# ---------------------------------------------------------------------------
# State persistence (follows runtime_contracts.write_run_state pattern)
# ---------------------------------------------------------------------------

def _write_state(project_dir: str, payload: dict[str, Any]) -> None:
    """Write state atomically to ``latest.json`` under architecture_signal."""
    state_dir = Path(project_dir) / _STATE_REL
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        latest = state_dir / "latest.json"
        tmp = latest.with_name("latest.json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        os.rename(tmp, latest)
    except Exception as exc:
        _logger.debug("Failed to persist architecture signal state: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_FALLBACK_RESULT: dict[str, Any] = {
    "summary": "no architecture signals available",
    "artifacts": {
        "dependency_graph": None,
        "lsp_diagnostics": None,
    },
    "perf": {
        "graph_ms": 0.0,
        "lsp_ms": 0.0,
    },
    "fallback": True,
}


def build_architecture_signal(project_dir: str) -> dict[str, Any]:
    """Build bounded architecture signal for context-engine consumers.

    Always returns a dict with keys:
      - ``summary``: bounded text (<=500 chars)
      - ``artifacts``: ``{dependency_graph: path|None, lsp_diagnostics: path|None}``
      - ``perf``: ``{graph_ms: float, lsp_ms: float}``
      - ``fallback``: ``bool`` — True when no signals were available

    Degrades gracefully when graph plugin or LSP evidence is unavailable.
    Never raises.
    """
    try:
        graph_path, graph_metrics, graph_ms = _build_graph_summary(project_dir)
        lsp_path, lsp_counts, lsp_ms = _build_lsp_summary(project_dir)

        fallback = graph_path is None and lsp_path is None
        summary = _format_summary(graph_metrics, lsp_counts, fallback)

        result: dict[str, Any] = {
            "summary": summary,
            "artifacts": {
                "dependency_graph": graph_path,
                "lsp_diagnostics": lsp_path,
            },
            "perf": {
                "graph_ms": round(graph_ms, 3),
                "lsp_ms": round(lsp_ms, 3),
            },
            "fallback": fallback,
        }

        _write_state(project_dir, result)
        return result

    except Exception as exc:
        _logger.warning("Architecture signal build failed; using fallback: %s", exc, exc_info=True)
        # Crash isolation: never raise to caller
        return dict(_FALLBACK_RESULT)
