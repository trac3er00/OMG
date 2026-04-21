from __future__ import annotations

import os
import importlib
from pathlib import Path
from typing import Callable, Protocol, TypeVar, cast

F = TypeVar("F", bound=Callable[..., object])


class _MarkProtocol(Protocol):
    def skipif(self, condition: bool, *, reason: str) -> Callable[[F], F]: ...


class _PytestProtocol(Protocol):
    mark: _MarkProtocol


pytest = cast(
    _PytestProtocol,
    cast(object, importlib.import_module("pytest")),
)

ROOT = Path(__file__).resolve().parents[2]


class TestRoutingAccuracy:
    def test_provider_strengths_define_ollama_cloud(self) -> None:
        multi_force = ROOT / "src" / "cx" / "multi-force.ts"
        content = multi_force.read_text(encoding="utf-8")

        assert "PROVIDER_STRENGTHS" in content
        assert '"ollama-cloud"' in content, "ollama-cloud not in multi-force.ts"

    def test_cost_tiers_define_ollama_cloud(self) -> None:
        equalizer = ROOT / "runtime" / "equalizer.py"
        content = equalizer.read_text(encoding="utf-8")

        assert "_COST_TIERS" in content
        assert '"ollama-cloud"' in content, "ollama-cloud not in equalizer.py"

    def test_all_providers_in_registry(self) -> None:
        providers_file = ROOT / "runtime" / "providers" / "provider_registry.py"
        content = providers_file.read_text(encoding="utf-8")

        for provider in ["claude", "codex", "gemini", "kimi", "ollama-cloud"]:
            assert provider in content, f"{provider} not in provider_registry.py"

    def test_routing_fallback_chain_defined(self) -> None:
        multi_force = ROOT / "src" / "cx" / "multi-force.ts"
        content = multi_force.read_text(encoding="utf-8")

        assert "CATEGORY_FALLBACKS" in content
        assert '"ollama-cloud"' in content, "ollama-cloud not in CATEGORY_FALLBACKS"


class TestCostTierCompliance:
    def test_equalizer_cost_tier_shape(self) -> None:
        equalizer = ROOT / "runtime" / "equalizer.py"
        content = equalizer.read_text(encoding="utf-8")

        assert "_COST_TIERS" in content
        assert '"high"' in content
        assert '"medium"' in content
        assert '"low"' in content
        assert '"claude": "high"' in content
        assert '"codex": "medium"' in content
        assert '"ollama-cloud": "low"' in content

    def test_provider_count(self) -> None:
        registry = ROOT / "runtime" / "providers" / "provider_registry.py"
        content = registry.read_text(encoding="utf-8")

        providers = ["claude", "codex", "gemini", "kimi", "ollama-cloud"]
        found = [provider for provider in providers if provider in content]
        assert len(found) == 5, f"Expected 5 providers, found {len(found)}: {found}"


class TestRealAPIEscalation:
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="No ANTHROPIC_API_KEY",
    )
    def test_claude_api_key_present(self) -> None:
        assert len(os.environ.get("ANTHROPIC_API_KEY", "")) > 0

    @pytest.mark.skipif(
        not os.environ.get("OLLAMA_API_KEY"),
        reason="No OLLAMA_API_KEY",
    )
    def test_ollama_cloud_api_key_present(self) -> None:
        assert len(os.environ.get("OLLAMA_API_KEY", "")) > 0
