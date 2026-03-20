"""Lightweight prompt compiler — learn from outcomes and optimize prompts.

Tracks which prompt patterns lead to successful verifications and auto-selects
the best prompt template for each task type. Lightweight DSPy alternative with
zero external dependencies.

Workflow:
    1. Before execution: select_template(task_type) → best preamble for this task type
    2. After verification: record_outcome(task_type, template_id, success) → update stats
    3. Over time: templates with higher success rates get selected more often
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Template Library — curated prompt preambles indexed by task type
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "bugfix": [
        {
            "id": "bugfix-reproduce-first",
            "preamble": (
                "@strategy: Reproduce the bug first. "
                "1) Read the relevant code. 2) Write a failing test. "
                "3) Fix the code. 4) Verify the test passes. "
                "Do NOT guess — confirm the root cause before changing code."
            ),
            "tags": ["tdd", "defensive"],
        },
        {
            "id": "bugfix-trace-backwards",
            "preamble": (
                "@strategy: Trace the error backwards from the symptom. "
                "1) Find the exact error location. 2) Follow the call chain upward. "
                "3) Identify the root cause. 4) Fix at the root, not the symptom."
            ),
            "tags": ["root-cause", "systematic"],
        },
    ],
    "feature": [
        {
            "id": "feature-plan-first",
            "preamble": (
                "@strategy: Plan before coding. "
                "1) Identify all files that need changes. 2) Define the interface first. "
                "3) Implement incrementally. 4) Test each component. "
                "Keep changes minimal and focused."
            ),
            "tags": ["planned", "incremental"],
        },
        {
            "id": "feature-test-driven",
            "preamble": (
                "@strategy: Test-driven feature development. "
                "1) Write acceptance test first. 2) Implement minimum code to pass. "
                "3) Refactor if needed. 4) Verify all tests pass."
            ),
            "tags": ["tdd", "minimal"],
        },
    ],
    "refactor": [
        {
            "id": "refactor-safe-steps",
            "preamble": (
                "@strategy: Refactor in safe steps. "
                "1) Ensure tests pass before starting. 2) Make ONE change at a time. "
                "3) Run tests after each change. 4) Never change behavior and structure simultaneously."
            ),
            "tags": ["safe", "incremental"],
        },
    ],
    "security": [
        {
            "id": "security-audit-first",
            "preamble": (
                "@strategy: Security-first approach. "
                "1) Identify the threat model. 2) Check OWASP Top 10 applicability. "
                "3) Fix vulnerabilities before adding features. "
                "4) Run /OMG:security-check after changes."
            ),
            "tags": ["defensive", "owasp"],
        },
    ],
    "docs": [
        {
            "id": "docs-verify-accuracy",
            "preamble": (
                "@strategy: Documentation accuracy. "
                "1) Read the actual code before writing docs. "
                "2) Include working examples. 3) Never document behavior you haven't verified."
            ),
            "tags": ["accurate", "examples"],
        },
    ],
}

# Default template when no history exists
_DEFAULT_TEMPLATE: dict[str, Any] = {
    "id": "generic-systematic",
    "preamble": (
        "@strategy: Systematic approach. "
        "1) Understand the problem fully before acting. "
        "2) Make the smallest change that works. "
        "3) Verify your changes."
    ),
    "tags": ["generic"],
}


# ---------------------------------------------------------------------------
# Outcome tracking
# ---------------------------------------------------------------------------

def _outcomes_path(project_dir: str | Path) -> str:
    """Path to the prompt outcomes ledger."""
    return os.path.join(str(project_dir), ".omg", "state", "prompt-outcomes.jsonl")


def record_outcome(
    project_dir: str | Path,
    task_type: str,
    template_id: str,
    success: bool,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Record the outcome of a prompt template selection.

    Args:
        project_dir: Project directory
        task_type: Task classification (bugfix, feature, etc.)
        template_id: Which template was used
        success: Whether verification passed
        context: Optional metadata (prompt hash, duration, etc.)
    """
    path = _outcomes_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    entry = {
        "ts": time.time(),
        "task_type": task_type,
        "template_id": template_id,
        "success": success,
    }
    if context:
        entry["context"] = context

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass  # never crash on tracking


def _load_outcomes(project_dir: str | Path, max_age_days: int = 30) -> list[dict[str, Any]]:
    """Load recent outcomes from the ledger."""
    path = _outcomes_path(project_dir)
    if not os.path.exists(path):
        return []

    cutoff = time.time() - (max_age_days * 86400)
    outcomes: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("ts", 0) >= cutoff:
                        outcomes.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return outcomes


# ---------------------------------------------------------------------------
# Template selection
# ---------------------------------------------------------------------------

def _compute_template_scores(
    task_type: str,
    outcomes: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute success rate for each template of the given task type."""
    scores: dict[str, dict[str, int]] = {}  # template_id → {wins, total}

    for outcome in outcomes:
        if outcome.get("task_type") != task_type:
            continue
        tid = outcome.get("template_id", "")
        if tid not in scores:
            scores[tid] = {"wins": 0, "total": 0}
        scores[tid]["total"] += 1
        if outcome.get("success"):
            scores[tid]["wins"] += 1

    # Convert to success rates with Laplace smoothing (prior: 1 win, 2 total)
    rates: dict[str, float] = {}
    for tid, stats in scores.items():
        rates[tid] = (stats["wins"] + 1) / (stats["total"] + 2)
    return rates


def select_template(
    task_type: str,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Select the best prompt template for a task type.

    Uses outcome history to pick the template with the highest success rate.
    Falls back to the first template if no history exists.

    Args:
        task_type: Task classification
        project_dir: Project directory (for outcome history)

    Returns:
        Template dict with keys: id, preamble, tags
    """
    templates = _TEMPLATES.get(task_type, [])
    if not templates:
        return _DEFAULT_TEMPLATE

    if project_dir is None:
        return templates[0]

    outcomes = _load_outcomes(project_dir)
    if not outcomes:
        return templates[0]

    scores = _compute_template_scores(task_type, outcomes)
    if not scores:
        return templates[0]

    # Pick template with highest success rate
    best_template = templates[0]
    best_score = -1.0
    for tmpl in templates:
        rate = scores.get(tmpl["id"], 0.5)  # default 50% for untried
        if rate > best_score:
            best_score = rate
            best_template = tmpl

    return best_template


def get_compiled_preamble(
    task_type: str,
    project_dir: str | Path | None = None,
) -> str:
    """Get the compiled preamble for a task type.

    Convenience wrapper: selects best template and returns just the preamble string.
    """
    template = select_template(task_type, project_dir)
    return template.get("preamble", "")


def get_available_task_types() -> list[str]:
    """Return all task types that have templates."""
    return list(_TEMPLATES.keys())
