from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.canonical_taxonomy import CANONICAL_PRESETS, RELEASE_CHANNELS, SUBSCRIPTION_TIERS
from runtime.subscription_tiers import TIER_REGISTRY, detect_tier


def _raising_detector(message: str, *, exc_type: type[Exception] = RuntimeError):
    def _detector(provider: str) -> str:
        raise exc_type(message)

    return _detector


def test_detect_tier_returns_required_result_shape() -> None:
    result = detect_tier("codex")

    assert set(result.keys()) >= {
        "tier",
        "provenance",
        "confidence",
        "budget_usd_per_session",
        "max_parallel_agents",
    }
    assert result["tier"] in SUBSCRIPTION_TIERS
    assert result["provenance"] in {"provider_api", "local_config", "cache", "default"}
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["budget_usd_per_session"] > 0
    assert result["max_parallel_agents"] >= 1


def test_provider_failure_falls_back_to_local_and_records_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "runtime.subscription_tiers._detect_provider_tier",
        _raising_detector("provider_api: 429 rate limit"),
    )

    settings = {
        "_omg": {
            "subscription_tier": "team",
        }
    }
    _ = (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    result = detect_tier("codex", project_dir=str(tmp_path))

    assert result["tier"] == "team"
    assert result["provenance"] == "local_config"
    assert "reason" in result
    assert "429" in str(result["reason"])


def test_provider_failure_falls_back_to_cache_and_records_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "runtime.subscription_tiers._detect_provider_tier",
        _raising_detector("provider_api: network unreachable", exc_type=ConnectionError),
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    cache_path = tmp_path / ".omg" / "state"
    cache_path.mkdir(parents=True, exist_ok=True)
    _ = (cache_path / "tier-cache.json").write_text(
        json.dumps({"tier": "pro", "timestamp": 4_102_444_800}),
        encoding="utf-8",
    )

    result = detect_tier("claude", project_dir=str(tmp_path / "project"))

    assert result["tier"] == "pro"
    assert result["provenance"] == "cache"
    assert "reason" in result
    assert "network" in str(result["reason"])


def test_provider_failure_falls_back_to_default_and_records_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "runtime.subscription_tiers._detect_provider_tier",
        _raising_detector("provider_api: auth expired"),
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    result = detect_tier("gemini", project_dir=str(tmp_path / "project"))

    assert result["tier"] == "free"
    assert result["provenance"] == "default"
    assert result["budget_usd_per_session"] == 5.0
    assert "reason" in result
    assert "auth expired" in str(result["reason"])


def test_subscription_tiers_are_disjoint_from_presets_and_channels() -> None:
    tier_ids = set(TIER_REGISTRY.keys())
    assert tier_ids.isdisjoint(set(CANONICAL_PRESETS))
    assert tier_ids.isdisjoint(set(RELEASE_CHANNELS))


def test_registry_covers_all_canonical_subscription_tiers() -> None:
    assert set(TIER_REGISTRY.keys()) == set(SUBSCRIPTION_TIERS)


def test_detect_tier_preserves_cached_or_default_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "runtime.subscription_tiers._detect_provider_tier",
        _raising_detector("provider_api: 429"),
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _ = (state_dir / "tier-cache.json").write_text(
        json.dumps({"tier": "enterprise_tier", "timestamp": 4_102_444_800}),
        encoding="utf-8",
    )

    result = detect_tier("codex", project_dir=str(tmp_path / "project"))
    assert result["tier"] != "free"
    assert result["tier"] == "enterprise_tier"
