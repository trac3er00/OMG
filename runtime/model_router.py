# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_DEFAULT_SESSION_BUDGET_USD = 5.0
_WARN_THRESHOLD = 0.80
_QUALITY_ORDER = {"medium": 0, "high": 1, "very_high": 2}


@dataclass
class RoutingDecision:
    model_id: str
    provider: str
    complexity: str
    budget_remaining_pct: float
    reasoning: str
    estimated_cost_per_1k: float


@dataclass
class BudgetState:
    session_budget: float = _DEFAULT_SESSION_BUDGET_USD
    consumed_usd: float = 0.0
    api_calls: int = 0
    tokens_used: int = 0

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.session_budget - self.consumed_usd)

    @property
    def remaining_pct(self) -> float:
        if self.session_budget <= 0:
            return 0.0
        return self.remaining_usd / self.session_budget


class ModelRouter:
    def __init__(
        self,
        session_budget: float = _DEFAULT_SESSION_BUDGET_USD,
        project_dir: str = ".",
        registry: dict[str, object] | None = None,
    ):
        self.budget: BudgetState = BudgetState(session_budget=session_budget)
        self.project_dir: str = project_dir
        self._registry: dict[str, object] | None = registry
        self._routing_log: list[dict[str, object]] = []

    def _get_registry(self) -> dict[str, object]:
        if self._registry is None:
            try:
                from .model_registry import load_registry

                self._registry = load_registry()
            except Exception:
                self._registry = {}
        return cast(dict[str, object], self._registry)

    def route(
        self,
        task: dict[str, object] | None = None,
        complexity: str | None = None,
        quality_floor: str = "medium",
    ) -> RoutingDecision:
        resolved_complexity = complexity
        if resolved_complexity is None and task is not None:
            from .complexity_classifier import classify

            resolved_complexity = classify(task).tier
        elif resolved_complexity is None:
            resolved_complexity = "medium"

        mode_reason = ""
        try:
            from .dual_mode import evaluate

            mode_result = evaluate(
                task=task,
                complexity=resolved_complexity,
                project_dir=self.project_dir,
            )
            mode_reason = f"; mode={mode_result.mode} ({mode_result.reason})"
        except Exception:
            mode_reason = ""

        complexity_to_budget = {
            "trivial": "low",
            "simple": "low",
            "medium": "medium",
            "complex": "high",
            "critical": "high",
        }
        complexity_to_quality = {
            "trivial": "medium",
            "simple": "medium",
            "medium": "medium",
            "complex": "high",
            "critical": "very_high",
        }

        budget_level = complexity_to_budget.get(resolved_complexity, "medium")
        auto_quality = complexity_to_quality.get(resolved_complexity, "medium")
        effective_quality = max(
            quality_floor,
            auto_quality,
            key=lambda value: _QUALITY_ORDER.get(value, 0),
        )

        try:
            from .model_registry import get_models_for

            candidates = get_models_for(
                task_type=resolved_complexity,
                budget=budget_level,
                quality_floor=effective_quality,
                registry=self._get_registry(),
            )
        except Exception:
            candidates = []

        if not candidates:
            decision = RoutingDecision(
                model_id="claude-sonnet-4",
                provider="claude",
                complexity=resolved_complexity,
                budget_remaining_pct=self.budget.remaining_pct,
                reasoning=(
                    f"fallback: no candidates found for {resolved_complexity}"
                    f"{mode_reason}"
                ),
                estimated_cost_per_1k=0.003,
            )
        else:
            best = candidates[0]
            decision = RoutingDecision(
                model_id=best.model_id,
                provider=best.provider,
                complexity=resolved_complexity,
                budget_remaining_pct=self.budget.remaining_pct,
                reasoning=(
                    f"{resolved_complexity} task → {best.quality} quality, "
                    f"{best.speed} speed, cheapest qualifying{mode_reason}"
                ),
                estimated_cost_per_1k=best.cost_per_1k_tokens,
            )

        try:
            from .model_toggle import get_mode, get_preferred_model

            toggle_mode = get_mode()
            if toggle_mode != "balanced":
                decision = RoutingDecision(
                    model_id=get_preferred_model(resolved_complexity),
                    provider="claude",
                    complexity=resolved_complexity,
                    budget_remaining_pct=self.budget.remaining_pct,
                    reasoning=(
                        f"toggle override: mode={toggle_mode}, "
                        f"complexity={resolved_complexity}{mode_reason}"
                    ),
                    estimated_cost_per_1k=decision.estimated_cost_per_1k,
                )
        except Exception:
            pass

        self._emit_budget_alerts()
        self._log_decision(decision)
        return decision

    def record_usage(self, tokens_used: int, cost_usd: float | None = None) -> None:
        self.budget.tokens_used += tokens_used
        self.budget.api_calls += 1
        if cost_usd is not None:
            self.budget.consumed_usd += cost_usd
            return
        self.budget.consumed_usd += tokens_used * 0.000003

    def _emit_budget_alerts(self) -> None:
        if self.budget.remaining_pct <= 0.0:
            warnings.warn(
                f"BUDGET EXHAUSTED: session budget of ${self.budget.session_budget:.2f} consumed",
                ResourceWarning,
                stacklevel=3,
            )
            return

        consumed_pct = 1 - self.budget.remaining_pct
        if consumed_pct >= _WARN_THRESHOLD:
            warnings.warn(
                (
                    f"BUDGET WARNING: {consumed_pct * 100:.0f}% of session budget consumed. "
                    f"${self.budget.remaining_usd:.2f} remaining"
                ),
                ResourceWarning,
                stacklevel=3,
            )

    def _log_decision(self, decision: RoutingDecision) -> None:
        entry: dict[str, object] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_id": decision.model_id,
            "provider": decision.provider,
            "complexity": decision.complexity,
            "budget_remaining_pct": round(decision.budget_remaining_pct, 3),
            "estimated_cost_per_1k": round(decision.estimated_cost_per_1k, 6),
            "reasoning": decision.reasoning,
        }
        self._routing_log.append(entry)

        try:
            ledger_dir = Path(self.project_dir) / ".omg" / "state" / "ledger"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            with (ledger_dir / "routing-decisions.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                _ = handle.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def get_routing_log(self) -> list[dict[str, object]]:
        return list(self._routing_log)

    def get_budget_status(self) -> dict[str, float | int]:
        return {
            "session_budget": self.budget.session_budget,
            "consumed_usd": round(self.budget.consumed_usd, 4),
            "remaining_usd": round(self.budget.remaining_usd, 4),
            "remaining_pct": round(self.budget.remaining_pct, 3),
            "api_calls": self.budget.api_calls,
            "tokens_used": self.budget.tokens_used,
        }
