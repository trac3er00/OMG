from __future__ import annotations

import json
import time
from pathlib import Path

from runtime import contract_compiler


def _write_cache(root: Path, payload: dict[str, object]) -> None:
    cache_path = root / ".omg" / "cache" / "release-readiness-identity.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _stub_release_checks(monkeypatch) -> None:
    monkeypatch.setattr(contract_compiler, "_check_recent_evidence", lambda *_args, **_kwargs: {"status": "ok", "blockers": [], "run_id": ""})
    monkeypatch.setattr(contract_compiler, "_check_doctor_output", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_eval_gate", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_proof_chain", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_execution_primitives", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_claim_judge_compliance", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_proof_surface", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_same_machine_scope", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_packaged_install_smoke", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "check_package_parity", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_plugin_command_paths", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_version_identity_drift", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_provider_host_parity", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_host_semantic_parity", lambda *_args, **_kwargs: {"status": "ok", "blockers": []})
    monkeypatch.setattr(contract_compiler, "_check_mcp_fabric", lambda *_args, **_kwargs: {"ready": True})
    monkeypatch.setattr(contract_compiler, "_provider_statuses", lambda: {host: {"ready": True, "source": "test"} for host in contract_compiler.SUPPORTED_HOSTS})


def test_build_release_readiness_cache_hit_returns_early(tmp_path: Path, monkeypatch) -> None:
    _write_cache(
        tmp_path,
        {
            "schema": "OmgReleaseReadinessResult",
            "status": "ok",
            "channel": "public",
            "version": contract_compiler.CANONICAL_VERSION,
            "cached_at": time.time(),
            "blockers": [],
            "checks": {"cache": "hit"},
        },
    )

    def _unexpected_validate(_root):
        raise AssertionError("full readiness checks should not run on cache hit")

    monkeypatch.setattr(contract_compiler, "validate_contract_registry", _unexpected_validate)

    result = contract_compiler.build_release_readiness(root_dir=tmp_path, output_root=tmp_path, channel="public")

    assert result["cache_hit"] is True
    assert result["checks"]["cache"] == "hit"


def test_build_release_readiness_cache_version_mismatch_runs_checks(tmp_path: Path, monkeypatch) -> None:
    _write_cache(
        tmp_path,
        {
            "schema": "OmgReleaseReadinessResult",
            "status": "ok",
            "channel": "public",
            "version": "0.0.0-mismatch",
            "cached_at": time.time(),
            "blockers": [],
            "checks": {"cache": "stale"},
        },
    )

    calls = {"validate": 0}

    def _validate(_root):
        calls["validate"] += 1
        return {"status": "ok", "errors": []}

    monkeypatch.setattr(contract_compiler, "validate_contract_registry", _validate)
    _stub_release_checks(monkeypatch)

    result = contract_compiler.build_release_readiness(root_dir=tmp_path, output_root=tmp_path, channel="public")

    assert calls["validate"] == 1
    assert result["cache_hit"] is False


def test_build_release_readiness_returns_early_on_stalled_worker(tmp_path: Path, monkeypatch) -> None:
    class _StalledWatchdog:
        @staticmethod
        def get_stalled_workers() -> list[dict[str, object]]:
            return [{"run_id": "run-stalled-1", "status": "alive"}]

    monkeypatch.setattr(contract_compiler, "get_worker_watchdog", lambda *_args, **_kwargs: _StalledWatchdog())

    def _unexpected_validate(_root):
        raise AssertionError("readiness should return before full checks on stalled workers")

    monkeypatch.setattr(contract_compiler, "validate_contract_registry", _unexpected_validate)

    result = contract_compiler.build_release_readiness(root_dir=tmp_path, output_root=tmp_path, channel="public")

    assert result["status"] == "error"
    assert result["cache_hit"] is False
    assert any("worker_watchdog_stalled:" in blocker for blocker in result["blockers"])
    assert result["checks"]["worker_watchdog"]["status"] == "error"
