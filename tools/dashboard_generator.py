#!/usr/bin/env python3
"""
HTML Dashboard Generator for OMG

Generates a single self-contained HTML dashboard with Chart.js (CDN)
from tool-ledger.jsonl and cost-ledger.jsonl data.

Feature flag: SESSION_ANALYTICS (default: False)
Pure stdlib — no external dependencies.
"""

import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Lazy import for feature flag helper
_get_feature_flag = None

_logger = logging.getLogger(__name__)
logger = _logger


def _ensure_imports():
    """Lazy import feature flag helper."""
    global _get_feature_flag
    if _get_feature_flag is None:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            from hooks._common import get_feature_flag as _gff
            _get_feature_flag = _gff
        except ImportError:
            # Fallback: always return default
            _get_feature_flag = None


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read JSONL file and return list of parsed entries.

    Skips malformed lines gracefully. Returns empty list if file missing.
    """
    if not os.path.exists(path):
        return []

    entries: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        _logger.debug("Failed to read JSONL dashboard source", exc_info=True)

    return entries


def _aggregate_tool_usage(tool_entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count tool invocations by tool name."""
    counts: Dict[str, int] = Counter()
    for entry in tool_entries:
        tool = entry.get("tool", "unknown")
        if isinstance(tool, str) and tool:
            counts[tool] += 1
    return dict(counts)


def _aggregate_cost_over_time(cost_entries: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    """Aggregate cost by date (YYYY-MM-DD)."""
    by_date: Dict[str, float] = defaultdict(float)
    for entry in cost_entries:
        ts = entry.get("ts", "")
        cost = entry.get("cost_usd", 0.0)
        if not isinstance(ts, str) or not ts:
            continue
        try:
            cost_val = float(cost)
        except (TypeError, ValueError):
            cost_val = 0.0
        # Extract date portion
        date_str = ts[:10]  # YYYY-MM-DD
        if len(date_str) == 10:
            by_date[date_str] += cost_val

    return sorted(by_date.items())


def _build_session_summary(
    tool_entries: List[Dict[str, Any]],
    cost_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build session summary stats."""
    total_tools = len(tool_entries)
    total_cost = sum(
        float(e.get("cost_usd", 0.0))
        for e in cost_entries
        if isinstance(e.get("cost_usd"), (int, float))
    )
    total_tokens = sum(
        int(e.get("tokens_in", 0)) + int(e.get("tokens_out", 0))
        for e in cost_entries
        if isinstance(e.get("tokens_in"), (int, float))
        and isinstance(e.get("tokens_out"), (int, float))
    )

    return {
        "total_tool_calls": total_tools,
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "cost_entries": len(cost_entries),
    }


def _render_html(
    tool_usage: Dict[str, int],
    cost_over_time: List[Tuple[str, float]],
    session_summary: Dict[str, Any],
    cost_entries: List[Dict[str, Any]],
) -> str:
    """Render a self-contained HTML dashboard with Chart.js CDN."""
    # Prepare JSON data for charts
    tool_labels = json.dumps(list(tool_usage.keys()))
    tool_data = json.dumps(list(tool_usage.values()))

    cost_labels = json.dumps([item[0] for item in cost_over_time])
    cost_data = json.dumps([round(item[1], 6) for item in cost_over_time])

    # Per-entry cost data for detailed chart
    entry_costs = []
    for entry in cost_entries:
        ts = entry.get("ts", "")
        cost = entry.get("cost_usd", 0.0)
        try:
            cost_val = round(float(cost), 6)
        except (TypeError, ValueError):
            cost_val = 0.0
        entry_costs.append({"ts": ts, "cost": cost_val})
    entry_costs_json = json.dumps(entry_costs)

    summary_html = (
        f"<li>Total Tool Calls: <strong>{session_summary['total_tool_calls']}</strong></li>"
        f"<li>Total Cost: <strong>${session_summary['total_cost_usd']}</strong></li>"
        f"<li>Total Tokens: <strong>{session_summary['total_tokens']}</strong></li>"
        f"<li>Cost Entries: <strong>{session_summary['cost_entries']}</strong></li>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OMG Session Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
        h1 {{ text-align: center; margin-bottom: 24px; color: #38bdf8; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; max-width: 1200px; margin: 0 auto; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        .card h2 {{ margin-bottom: 16px; color: #94a3b8; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
        .card.full {{ grid-column: 1 / -1; }}
        canvas {{ max-height: 300px; }}
        ul {{ list-style: none; }}
        ul li {{ padding: 8px 0; border-bottom: 1px solid #334155; font-size: 15px; }}
        ul li strong {{ color: #38bdf8; }}
        .timestamp {{ text-align: center; color: #64748b; margin-top: 24px; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>OMG Session Dashboard</h1>
    <div class="grid">
        <div class="card">
            <h2>Tool Usage</h2>
            <canvas id="toolChart"></canvas>
        </div>
        <div class="card">
            <h2>Cost Over Time</h2>
            <canvas id="costChart"></canvas>
        </div>
        <div class="card full">
            <h2>Session Summary</h2>
            <ul>
                {summary_html}
            </ul>
        </div>
    </div>
    <div class="timestamp">Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</div>
    <script>
        const toolLabels = {tool_labels};
        const toolData = {tool_data};
        const costLabels = {cost_labels};
        const costData = {cost_data};

        new Chart(document.getElementById('toolChart'), {{
            type: 'bar',
            data: {{
                labels: toolLabels,
                datasets: [{{
                    label: 'Tool Calls',
                    data: toolData,
                    backgroundColor: 'rgba(56, 189, 248, 0.7)',
                    borderColor: 'rgba(56, 189, 248, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
                    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
                }}
            }}
        }});

        new Chart(document.getElementById('costChart'), {{
            type: 'line',
            data: {{
                labels: costLabels,
                datasets: [{{
                    label: 'Cost (USD)',
                    data: costData,
                    borderColor: 'rgba(34, 197, 94, 1)',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    fill: true,
                    tension: 0.3
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
                    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>"""


def generate_dashboard(
    project_dir: str,
    output_path: Optional[str] = None,
) -> str:
    """Generate an HTML dashboard from OMG ledger data.

    Reads tool usage stats from {project_dir}/.omg/state/ledger/tool-ledger.jsonl
    and cost data from {project_dir}/.omg/state/ledger/cost-ledger.jsonl.
    Generates a single self-contained HTML file with Chart.js loaded from CDN.

    Args:
        project_dir: Project root directory.
        output_path: Path for the HTML file. Defaults to
                     {project_dir}/.omg/state/dashboard.html.

    Returns:
        The output_path string on success.
    """
    _ensure_imports()

    # Check feature flag — return empty string if disabled
    if _get_feature_flag is not None:
        if not _get_feature_flag("SESSION_ANALYTICS", default=False):
            return ""

    # Resolve default output path
    if output_path is None:
        output_path = os.path.join(project_dir, ".omg", "state", "dashboard.html")

    # Read ledger data
    tool_ledger_path = os.path.join(project_dir, ".omg", "state", "ledger", "tool-ledger.jsonl")
    cost_ledger_path = os.path.join(project_dir, ".omg", "state", "ledger", "cost-ledger.jsonl")

    tool_entries = _read_jsonl(tool_ledger_path)
    cost_entries = _read_jsonl(cost_ledger_path)

    # Aggregate data
    tool_usage = _aggregate_tool_usage(tool_entries)
    cost_over_time = _aggregate_cost_over_time(cost_entries)
    session_summary = _build_session_summary(tool_entries, cost_entries)

    # Render HTML
    html = _render_html(tool_usage, cost_over_time, session_summary, cost_entries)

    # Write file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
