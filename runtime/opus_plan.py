"""OpusPlan — token optimization strategies for budget-constrained subscription tiers.

Users on Free or Pro plans have limited token throughput.  OpusPlan configures
aggressive context compression, model routing, and agent limits so they get
the most value from each session without burning through their budget.

Provider capabilities are tracked per-provider so the setup wizard can show
what each provider offers and configure OMG accordingly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hooks.policy_engine import PolicyDecision, allow, ask, deny
from runtime.canonical_taxonomy import SUBSCRIPTION_TIERS
from runtime.router_selector import select_target


@dataclass(frozen=True)
class OpusPlanConfig:
    """Per-tier optimization configuration."""

    enabled: bool
    max_parallel_agents: int
    context_compression: str  # "aggressive" | "moderate" | "none"
    warning_threshold_pct: int
    prefer_escalate_over_ccg: bool
    budget_multiplier: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_parallel_agents": self.max_parallel_agents,
            "context_compression": self.context_compression,
            "warning_threshold_pct": self.warning_threshold_pct,
            "prefer_escalate_over_ccg": self.prefer_escalate_over_ccg,
            "budget_multiplier": self.budget_multiplier,
        }


@dataclass(frozen=True)
class ProviderPlanSpec:
    """Capabilities of a specific provider + plan combination."""

    provider: str
    plan: str
    max_context_tokens: int
    models_available: tuple[str, ...]
    rate_limit_desc: str
    supports_agents: bool
    monthly_cost_usd: float | None  # None = API-usage-based

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "plan": self.plan,
            "max_context_tokens": self.max_context_tokens,
            "models_available": list(self.models_available),
            "rate_limit_desc": self.rate_limit_desc,
            "supports_agents": self.supports_agents,
            "monthly_cost_usd": self.monthly_cost_usd,
        }


# ── Provider × Plan capabilities ───────────────────────────────────────────

PROVIDER_PLAN_SPECS: dict[str, dict[str, ProviderPlanSpec]] = {
    "claude": {
        "free": ProviderPlanSpec(
            provider="claude",
            plan="free",
            max_context_tokens=200_000,
            models_available=("haiku", "sonnet"),
            rate_limit_desc="Limited messages/day",
            supports_agents=False,
            monthly_cost_usd=0,
        ),
        "pro": ProviderPlanSpec(
            provider="claude",
            plan="pro",
            max_context_tokens=200_000,
            models_available=("haiku", "sonnet", "opus"),
            rate_limit_desc="45 msgs/5hrs on Opus, higher on Sonnet",
            supports_agents=True,
            monthly_cost_usd=20,
        ),
        "max": ProviderPlanSpec(
            provider="claude",
            plan="max",
            max_context_tokens=1_000_000,
            models_available=("haiku", "sonnet", "opus"),
            rate_limit_desc="5-20x Pro usage, 1M context on Opus",
            supports_agents=True,
            monthly_cost_usd=100,
        ),
        "team": ProviderPlanSpec(
            provider="claude",
            plan="team",
            max_context_tokens=200_000,
            models_available=("haiku", "sonnet", "opus"),
            rate_limit_desc="Higher team limits, admin controls",
            supports_agents=True,
            monthly_cost_usd=25,
        ),
        "enterprise_tier": ProviderPlanSpec(
            provider="claude",
            plan="enterprise_tier",
            max_context_tokens=1_000_000,
            models_available=("haiku", "sonnet", "opus"),
            rate_limit_desc="Custom limits, SLA, SSO",
            supports_agents=True,
            monthly_cost_usd=None,
        ),
    },
    "codex": {
        "free": ProviderPlanSpec(
            provider="codex",
            plan="free",
            max_context_tokens=128_000,
            models_available=("gpt-4.1",),
            rate_limit_desc="Limited usage",
            supports_agents=False,
            monthly_cost_usd=0,
        ),
        "pro": ProviderPlanSpec(
            provider="codex",
            plan="pro",
            max_context_tokens=128_000,
            models_available=("gpt-4.1", "o3", "o4-mini"),
            rate_limit_desc="ChatGPT Plus rate limits",
            supports_agents=True,
            monthly_cost_usd=20,
        ),
        "team": ProviderPlanSpec(
            provider="codex",
            plan="team",
            max_context_tokens=128_000,
            models_available=("gpt-4.1", "o3", "o4-mini"),
            rate_limit_desc="Higher team limits",
            supports_agents=True,
            monthly_cost_usd=25,
        ),
    },
    "gemini": {
        "free": ProviderPlanSpec(
            provider="gemini",
            plan="free",
            max_context_tokens=1_000_000,
            models_available=("gemini-2.5-pro", "gemini-2.5-flash"),
            rate_limit_desc="Free tier rate limits, 1M context",
            supports_agents=True,
            monthly_cost_usd=0,
        ),
        "pro": ProviderPlanSpec(
            provider="gemini",
            plan="pro",
            max_context_tokens=1_000_000,
            models_available=("gemini-2.5-pro", "gemini-2.5-flash"),
            rate_limit_desc="Higher limits, priority access",
            supports_agents=True,
            monthly_cost_usd=20,
        ),
    },
    "kimi": {
        "free": ProviderPlanSpec(
            provider="kimi",
            plan="free",
            max_context_tokens=128_000,
            models_available=("kimi-latest",),
            rate_limit_desc="API-based, pay per token",
            supports_agents=False,
            monthly_cost_usd=None,
        ),
    },
}


def get_provider_plans(provider: str) -> dict[str, ProviderPlanSpec]:
    """Return all plan specs for a provider, empty dict if unknown."""
    return PROVIDER_PLAN_SPECS.get(provider, {})


def get_provider_plan(provider: str, plan: str) -> ProviderPlanSpec | None:
    """Return the spec for a specific provider + plan combination."""
    return PROVIDER_PLAN_SPECS.get(provider, {}).get(plan)


def resolve_effective_tier(provider_plans: dict[str, str]) -> str:
    """Given a mapping of {provider: plan}, return the most capable effective tier.

    The effective tier is the highest tier across all providers the user has.
    This determines overall OpusPlan behaviour.
    """
    tier_rank = {t: i for i, t in enumerate(SUBSCRIPTION_TIERS)}
    best_tier = "free"
    for plan in provider_plans.values():
        normalized = plan.strip().lower()
        # Map provider-specific plan names to canonical tiers
        if normalized in tier_rank and tier_rank.get(normalized, -1) > tier_rank.get(
            best_tier, -1
        ):
            best_tier = normalized
    return best_tier


def format_provider_capabilities(provider: str, plan: str) -> str:
    """Return a human-readable summary of what a provider+plan combination offers."""
    spec = get_provider_plan(provider, plan)
    if spec is None:
        return f"  {provider} ({plan}): unknown plan"
    ctx_k = spec.max_context_tokens // 1000
    models = ", ".join(spec.models_available)
    cost = (
        f"${spec.monthly_cost_usd}/mo"
        if spec.monthly_cost_usd is not None
        else "API usage"
    )
    agents = "yes" if spec.supports_agents else "no"
    return (
        f"  {provider} ({plan}): {ctx_k}K context | models: {models} | "
        f"agents: {agents} | {cost} | {spec.rate_limit_desc}"
    )


# ── Strategy table ──────────────────────────────────────────────────────────
#
# free/pro  → OpusPlan active: fewer agents, earlier warnings, prefer escalate
# max+      → OpusPlan inactive: full capabilities

OPUS_PLAN_CONFIGS: dict[str, OpusPlanConfig] = {
    "free": OpusPlanConfig(
        enabled=True,
        max_parallel_agents=1,
        context_compression="aggressive",
        warning_threshold_pct=30,
        prefer_escalate_over_ccg=True,
        budget_multiplier=0.5,
    ),
    "pro": OpusPlanConfig(
        enabled=True,
        max_parallel_agents=2,
        context_compression="moderate",
        warning_threshold_pct=40,
        prefer_escalate_over_ccg=True,
        budget_multiplier=0.8,
    ),
    "max": OpusPlanConfig(
        enabled=False,
        max_parallel_agents=5,
        context_compression="none",
        warning_threshold_pct=50,
        prefer_escalate_over_ccg=False,
        budget_multiplier=1.0,
    ),
    "team": OpusPlanConfig(
        enabled=False,
        max_parallel_agents=8,
        context_compression="none",
        warning_threshold_pct=50,
        prefer_escalate_over_ccg=False,
        budget_multiplier=1.0,
    ),
    "enterprise_tier": OpusPlanConfig(
        enabled=False,
        max_parallel_agents=20,
        context_compression="none",
        warning_threshold_pct=50,
        prefer_escalate_over_ccg=False,
        budget_multiplier=1.0,
    ),
}

# Model routing for token-constrained tiers.
# Maps (task_type) → preferred model name.
_MODEL_ROUTING_CONSTRAINED: dict[str, str] = {
    "explore": "haiku",
    "search": "haiku",
    "implement": "sonnet",
    "review": "sonnet",
    "security": "opus",
    "architecture": "opus",
    "critical": "opus",
}

_MODEL_ROUTING_DEFAULT: dict[str, str] = {
    "explore": "sonnet",
    "search": "sonnet",
    "implement": "opus",
    "review": "opus",
    "security": "opus",
    "architecture": "opus",
    "critical": "opus",
}


def get_opus_plan(tier: str) -> OpusPlanConfig:
    """Return the OpusPlan config for *tier*, defaulting to free."""
    return OPUS_PLAN_CONFIGS.get(tier, OPUS_PLAN_CONFIGS["free"])


def get_tier_config() -> dict[str, str]:
    """Return tier-aware config for prompt-enhancer model hints.

    Reads the current tier from environment or defaults to 'max',
    and returns a dict with 'model_hint' key for prompt injection.
    """
    import os

    tier = os.environ.get("OMG_SUBSCRIPTION_TIER", "max").lower()
    config = get_opus_plan(tier)
    if config.enabled and config.context_compression == "aggressive":
        return {"model_hint": "sonnet", "tier": tier}
    return {"model_hint": "opus", "tier": tier}


def get_model_routing(tier: str, task_type: str) -> str:
    """Return preferred model for *task_type* given the subscription *tier*.

    Token-constrained tiers (free/pro) route cheap tasks to haiku,
    balanced tasks to sonnet, and reserve opus for critical decisions.
    """
    config = get_opus_plan(tier)
    if config.enabled:
        return _MODEL_ROUTING_CONSTRAINED.get(task_type, "sonnet")
    return _MODEL_ROUTING_DEFAULT.get(task_type, "opus")


def should_prefer_escalate(tier: str) -> bool:
    """Return ``True`` when ``/OMG:escalate`` should be suggested over ``/OMG:ccg``.

    CCG (tri-model) is expensive.  On constrained tiers, single-model
    escalation is more token-efficient.
    """
    return get_opus_plan(tier).prefer_escalate_over_ccg


def format_opus_plan_summary(tier: str) -> str:
    """Return a human-readable summary of OpusPlan settings for *tier*."""
    config = get_opus_plan(tier)
    if not config.enabled:
        return f"  OpusPlan: inactive (tier={tier} has sufficient token budget)"

    lines = [
        f"  OpusPlan: ACTIVE (tier={tier})",
        f"    Max parallel agents: {config.max_parallel_agents}",
        f"    Context compression: {config.context_compression}",
        f"    Budget warnings at: {config.warning_threshold_pct}%",
        f"    Prefer /OMG:escalate over /OMG:ccg: yes",
        f"    Budget multiplier: {config.budget_multiplier}x",
        "    Model routing: haiku(explore) → sonnet(implement) → opus(critical)",
    ]
    return "\n".join(lines)


_PLAN_STATE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class GovernedTaskCheckpoint:
    decision: str
    risk_level: str
    reason: str
    controls: tuple[str, ...] = ()

    @classmethod
    def from_policy_decision(cls, decision: PolicyDecision) -> "GovernedTaskCheckpoint":
        controls = tuple(str(control) for control in (decision.controls or []))
        return cls(
            decision=decision.action,
            risk_level=decision.risk_level,
            reason=decision.reason,
            controls=controls,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "controls": list(self.controls),
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_dependencies(raw_dependencies: object) -> list[str]:
    if not isinstance(raw_dependencies, list):
        return []
    dependencies: list[str] = []
    for dep in raw_dependencies:
        dep_id = str(dep or "").strip()
        if dep_id and dep_id not in dependencies:
            dependencies.append(dep_id)
    return dependencies


def _risk_policy_for_task(description: str) -> PolicyDecision:
    lowered = description.lower()
    if any(
        token in lowered
        for token in ("delete", "drop", "remove", "destructive", "force push")
    ):
        return deny(
            "Task contains destructive mutation markers and requires redesign.",
            "high",
            ["plan-redesign", "manual-approval"],
        )
    if any(
        token in lowered
        for token in ("deploy", "release", "production", "credential", "secret")
    ):
        return ask(
            "Task touches production/security surface and needs explicit checkpoint approval.",
            "high",
            ["manual-approval", "evidence-required"],
        )
    if any(
        token in lowered
        for token in ("edit", "write", "refactor", "migration", "schema")
    ):
        return ask(
            "Task mutates code or state; proceed with governed review.",
            "med",
            ["review-required"],
        )
    return allow("Task is planning/discovery scoped and allowed.")


def _default_task_breakdown(objective: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "task-1",
            "description": f"Analyze constraints for objective: {objective}",
            "dependencies": [],
        },
        {
            "id": "task-2",
            "description": "Design governed implementation approach and checkpoints",
            "dependencies": ["task-1"],
        },
        {
            "id": "task-3",
            "description": "Implement, verify, and capture evidence artifacts",
            "dependencies": ["task-2"],
        },
    ]


def _normalize_tasks(
    raw_tasks: list[dict[str, Any]] | list[str] | None,
) -> list[dict[str, Any]]:
    if not raw_tasks:
        return []
    normalized: list[dict[str, Any]] = []
    for index, task in enumerate(raw_tasks, start=1):
        if isinstance(task, str):
            description = task.strip()
            if not description:
                continue
            normalized.append(
                {"id": f"task-{index}", "description": description, "dependencies": []}
            )
            continue
        if not isinstance(task, dict):
            continue
        description = str(task.get("description", "") or "").strip()
        if not description:
            continue
        task_id = str(task.get("id", "") or f"task-{index}").strip() or f"task-{index}"
        normalized.append(
            {
                "id": task_id,
                "description": description,
                "dependencies": _normalize_dependencies(task.get("dependencies")),
            }
        )
    return normalized


def _plan_storage_path(project_dir: str, plan_id: str) -> Path:
    return Path(project_dir) / ".omg" / "plans" / f"{plan_id}.json"


def generate_governed_deep_plan(
    objective: str,
    *,
    tasks: list[dict[str, Any]] | list[str] | None = None,
    tier: str = "max",
    project_dir: str = ".",
    plan_id: str | None = None,
    budget_remaining_ratio: float | None = None,
    latency_sensitive: bool | None = None,
) -> dict[str, Any]:
    normalized_objective = str(objective or "").strip()
    if not normalized_objective:
        raise ValueError("objective is required")

    normalized_tasks = _normalize_tasks(tasks)
    if not normalized_tasks:
        normalized_tasks = _default_task_breakdown(normalized_objective)

    model_target = select_target(
        normalized_objective,
        "governed planning",
        budget_remaining_ratio=budget_remaining_ratio,
        latency_sensitive=latency_sensitive,
    )
    suggested_model = str(
        model_target.get("model") or get_model_routing(tier, "architecture")
    )

    plan_tasks: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    for task in normalized_tasks:
        policy = _risk_policy_for_task(task["description"])
        checkpoint = GovernedTaskCheckpoint.from_policy_decision(policy).to_dict()
        plan_task = {
            "id": task["id"],
            "description": task["description"],
            "dependencies": _normalize_dependencies(task.get("dependencies")),
            "governance_checkpoint": checkpoint,
        }
        plan_tasks.append(plan_task)
        checkpoints.append({"task_id": plan_task["id"], **checkpoint})

    timestamp = _utc_now_iso()
    normalized_plan_id = str(plan_id or f"plan-{uuid4()}")
    return {
        "schema": "OMGGovernedPlan",
        "schema_version": _PLAN_STATE_SCHEMA_VERSION,
        "id": normalized_plan_id,
        "version": 1,
        "objective": normalized_objective,
        "objectives": [normalized_objective],
        "tasks": plan_tasks,
        "governance_checkpoints": checkpoints,
        "routing": {
            "tier": tier,
            "strategy": model_target,
            "planning_model": suggested_model,
        },
        "bundle": "plan-council",
        "created_at": timestamp,
        "updated_at": timestamp,
        "plan_path": str(_plan_storage_path(project_dir, normalized_plan_id)),
    }


def persist_governed_plan(
    plan: dict[str, Any], *, project_dir: str = "."
) -> dict[str, Any]:
    plan_id = str(plan.get("id", "")).strip()
    if not plan_id:
        raise ValueError("plan.id is required")

    plan_path = _plan_storage_path(project_dir, plan_id)
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] | None = None
    if plan_path.exists():
        try:
            existing_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(existing_payload, dict):
                existing = existing_payload
        except (OSError, json.JSONDecodeError):
            existing = None

    next_plan = dict(plan)
    now = _utc_now_iso()
    history: list[dict[str, Any]] = []
    if existing is None:
        next_plan["version"] = int(next_plan.get("version", 1) or 1)
        next_plan["created_at"] = str(next_plan.get("created_at") or now)
    else:
        prior_version = int(existing.get("version", 1) or 1)
        next_plan["version"] = prior_version + 1
        next_plan["created_at"] = str(existing.get("created_at") or now)
        prior_history = existing.get("history")
        if isinstance(prior_history, list):
            history.extend(prior_history)
        frozen_previous = dict(existing)
        frozen_previous.pop("history", None)
        history.append(frozen_previous)
    next_plan["updated_at"] = now
    if history:
        next_plan["history"] = history

    temp_path = plan_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(next_plan, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    os.replace(temp_path, plan_path)
    return next_plan


def diff_plans(plan_v1: dict[str, Any], plan_v2: dict[str, Any]) -> dict[str, Any]:
    def _task_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
        tasks = plan.get("tasks")
        if not isinstance(tasks, list):
            return {}
        mapped: dict[str, dict[str, Any]] = {}
        for row in tasks:
            if not isinstance(row, dict):
                continue
            task_id = str(row.get("id", "")).strip()
            if task_id:
                mapped[task_id] = row
        return mapped

    t1 = _task_map(plan_v1)
    t2 = _task_map(plan_v2)

    added = [t2[task_id] for task_id in t2.keys() - t1.keys()]
    removed = [t1[task_id] for task_id in t1.keys() - t2.keys()]
    modified: list[dict[str, Any]] = []
    for task_id in t1.keys() & t2.keys():
        if t1[task_id] != t2[task_id]:
            modified.append(
                {
                    "id": task_id,
                    "before": t1[task_id],
                    "after": t2[task_id],
                }
            )

    return {
        "plan_id": str(plan_v2.get("id") or plan_v1.get("id") or ""),
        "from_version": int(plan_v1.get("version", 0) or 0),
        "to_version": int(plan_v2.get("version", 0) or 0),
        "added": added,
        "removed": removed,
        "modified": modified,
        "changed_tasks": added + removed + modified,
    }


# Validate that every canonical tier has a config entry
if set(OPUS_PLAN_CONFIGS.keys()) != set(SUBSCRIPTION_TIERS):
    raise ValueError(
        f"OPUS_PLAN_CONFIGS keys {set(OPUS_PLAN_CONFIGS.keys())} "
        f"must exactly match SUBSCRIPTION_TIERS {set(SUBSCRIPTION_TIERS)}"
    )
