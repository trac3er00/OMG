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
import logging
import os
import time
from pathlib import Path
from typing import Any


_logger = logging.getLogger(__name__)


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


# TODO: wire into stop_dispatcher verification flow so template selection learns from outcomes
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

    entry: dict[str, Any] = {
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
    except Exception as exc:
        _logger.debug(
            "Failed to append prompt outcome at %s: %s", path, exc, exc_info=True
        )


def _load_outcomes(
    project_dir: str | Path, max_age_days: int = 30
) -> list[dict[str, Any]]:
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
    except Exception as exc:
        _logger.debug(
            "Failed to load prompt outcomes from %s: %s", path, exc, exc_info=True
        )
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


# ---------------------------------------------------------------------------
# Cross-provider parity measurement
# ---------------------------------------------------------------------------


class ParityScore:
    """Structural similarity score between prompt outputs (0.0-1.0)."""

    def __init__(self, template_id: str) -> None:
        self.template_id = template_id
        self.scores: dict[str, float] = {}
        self.low_parity_threshold = 0.8

    def add_score(self, provider: str, score: float) -> None:
        self.scores[provider] = score

    @property
    def average_score(self) -> float:
        return sum(self.scores.values()) / len(self.scores) if self.scores else 0.0

    @property
    def is_low_parity(self) -> bool:
        return self.average_score < self.low_parity_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "scores": self.scores,
            "average": self.average_score,
            "low_parity": self.is_low_parity,
        }


def compute_structural_similarity(output_a: str, output_b: str) -> float:
    """Compute structural similarity between two prompt outputs.

    Uses simple heuristics: section count, word overlap, length ratio.
    Returns 0.0-1.0 (1.0 = identical structure).
    """
    # Count sections (lines starting with #)
    sections_a = len([line for line in output_a.split("\n") if line.startswith("#")])
    sections_b = len([line for line in output_b.split("\n") if line.startswith("#")])

    # Word overlap (Jaccard similarity)
    words_a = set(output_a.lower().split())
    words_b = set(output_b.lower().split())
    if not words_a and not words_b:
        return 1.0
    jaccard = len(words_a & words_b) / len(words_a | words_b)

    # Length ratio
    max_len = max(len(output_a), len(output_b))
    len_ratio = min(len(output_a), len(output_b)) / max_len if max_len > 0 else 1.0

    # Section similarity
    section_total = sections_a + sections_b
    section_sim = 1.0 - abs(sections_a - sections_b) / max(section_total, 1)

    return jaccard * 0.5 + len_ratio * 0.3 + section_sim * 0.2


def measure_template_parity(template_id: str, outputs: dict[str, str]) -> ParityScore:
    """Measure parity of a template across multiple provider outputs.

    Args:
        template_id: Identifier for the prompt template.
        outputs: Mapping of provider_name to output_text.

    Returns:
        ParityScore with per-provider similarity against the reference provider.
    """
    score = ParityScore(template_id)
    providers = list(outputs.keys())

    if len(providers) < 2:
        # Single provider: perfect parity by definition
        for p in providers:
            score.add_score(p, 1.0)
        return score

    # Compare each provider against the first (reference)
    reference_provider = providers[0]
    reference_output = outputs[reference_provider]
    score.add_score(reference_provider, 1.0)

    for provider in providers[1:]:
        sim = compute_structural_similarity(reference_output, outputs[provider])
        score.add_score(provider, sim)

    return score


def generate_parity_report(scores: list[ParityScore]) -> dict[str, Any]:
    """Generate parity report with low-parity templates flagged."""
    return {
        "total_templates": len(scores),
        "low_parity_count": sum(1 for s in scores if s.is_low_parity),
        "templates": [s.to_dict() for s in scores],
        "low_parity_templates": [s.template_id for s in scores if s.is_low_parity],
    }


# ---------------------------------------------------------------------------
# Parity enforcement — auto-correction overlays
# ---------------------------------------------------------------------------


class ProviderCorrection:
    """Provider-specific template correction overlay."""

    def __init__(self, provider: str, original_template: str):
        self.provider = provider
        self.original_template = original_template
        self.corrections: list[tuple[str, str]] = []
        self.applied = False

    def add_correction(self, original: str, corrected: str) -> None:
        self.corrections.append((original, corrected))

    def apply(self) -> str:
        """Apply corrections to produce provider-specific template."""
        result = self.original_template
        for original, corrected in self.corrections:
            result = result.replace(original, corrected)
        self.applied = True
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "corrections_count": len(self.corrections),
            "applied": self.applied,
            "corrections": [{"from": o, "to": c} for o, c in self.corrections],
        }


def auto_correct_template(
    template: str,
    provider: str,
    parity_score: float,
    threshold: float = 0.8,
) -> ProviderCorrection:
    """Auto-correct a template when parity is below threshold.

    Returns a ProviderCorrection overlay; original template is unchanged.
    """
    correction = ProviderCorrection(provider=provider, original_template=template)

    if parity_score >= threshold:
        return correction

    provider_hints: dict[str, dict[str, str]] = {
        "claude": {"You are": "As an AI assistant,", "Please": ""},
        "codex": {"explain": "describe", "analyze": "review"},
        "gemini": {"step by step": "systematically", "think": "reason"},
        "kimi": {"output": "result", "generate": "create"},
    }

    hints = provider_hints.get(provider.lower(), {})
    for original, replacement in hints.items():
        if original in template:
            correction.add_correction(original, replacement)

    return correction


def enforce_parity(
    template_id: str,
    template: str,
    parity_scores: dict[str, float],
    threshold: float = 0.8,
) -> dict[str, ProviderCorrection]:
    """Enforce parity by auto-correcting templates below threshold.

    Returns dict of provider -> ProviderCorrection (only for below-threshold providers).
    """
    corrections: dict[str, ProviderCorrection] = {}
    for provider, score in parity_scores.items():
        if score < threshold:
            correction = auto_correct_template(template, provider, score, threshold)
            corrections[provider] = correction
    return corrections
