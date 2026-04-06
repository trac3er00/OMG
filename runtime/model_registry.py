# pyright: reportAny=false, reportExplicitAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

"""Model capability registry for the OMG Model Router.

Provides a query API for selecting the best model based on:
- Task type and complexity
- Budget constraints
- Quality requirements
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml


_DEFAULT_REGISTRY_PATH = (
    Path(__file__).parent.parent / "config" / "model-capabilities.yaml"
)
_QUALITY_ORDER = {"low": 0, "medium": 1, "high": 2, "very_high": 3}

BUDGET_LEVELS = ("low", "medium", "high", "unlimited")
QUALITY_FLOORS = ("medium", "high", "very_high")


@dataclass
class ModelCapability:
    model_id: str
    provider: str
    speed: str
    quality: str
    cost_per_1k_tokens: float
    context_window: int
    specialties: list[str] = field(default_factory=list)


def load_registry(path: str | Path | None = None) -> dict[str, ModelCapability]:
    """Load model registry from YAML file. Returns dict of model_id → ModelCapability."""
    registry_path = Path(path) if path else _DEFAULT_REGISTRY_PATH
    try:
        raw_data = yaml.safe_load(registry_path.read_text())
        if not isinstance(raw_data, dict):
            return {}
        data = cast(dict[str, object], raw_data)
        models: dict[str, ModelCapability] = {}
        raw_models = data.get("models")
        if not isinstance(raw_models, dict):
            return {}
        for model_id, attrs in cast(dict[object, object], raw_models).items():
            if not isinstance(model_id, str) or not isinstance(attrs, dict):
                continue
            typed_attrs = cast(dict[str, object], attrs)
            models[model_id] = ModelCapability(
                model_id=model_id,
                provider=str(typed_attrs.get("provider", "unknown")),
                speed=str(typed_attrs.get("speed", "medium")),
                quality=str(typed_attrs.get("quality", "medium")),
                cost_per_1k_tokens=float(typed_attrs.get("cost_per_1k_tokens", 0.005)),
                context_window=int(typed_attrs.get("context_window", 128000)),
                specialties=list(typed_attrs.get("specialties", [])),
            )
        return models
    except Exception:
        return {}


def get_models_for(
    task_type: str = "general",
    budget: str = "medium",
    quality_floor: str = "medium",
    registry: dict[str, ModelCapability] | None = None,
) -> list[ModelCapability]:
    """Get sorted model candidates for a given task.

    Returns models sorted by cost-effectiveness (cheapest qualifying model first).
    """
    if registry is None:
        registry = load_registry()

    min_quality = _QUALITY_ORDER.get(quality_floor, 1)

    budget_limits = {
        "low": 0.001,
        "medium": 0.005,
        "high": 0.020,
        "unlimited": float("inf"),
    }
    max_cost = budget_limits.get(budget, 0.005)

    candidates: list[tuple[ModelCapability, bool]] = []
    task_type_lower = task_type.lower()
    for model in registry.values():
        quality_score = _QUALITY_ORDER.get(model.quality, 0)
        if quality_score < min_quality:
            continue
        if model.cost_per_1k_tokens > max_cost:
            continue
        specialty_match = task_type_lower in [s.lower() for s in model.specialties]
        candidates.append((model, specialty_match))

    candidates.sort(key=lambda x: (not x[1], x[0].cost_per_1k_tokens))
    return [m for m, _ in candidates]
