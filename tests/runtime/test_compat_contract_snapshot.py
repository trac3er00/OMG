"""Contract snapshot drift protection for compatibility mapping."""
from __future__ import annotations

import json
from pathlib import Path

from runtime.compat import CONTRACT_SNAPSHOT_VERSION, build_contract_snapshot_payload, list_compat_skill_contracts


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "runtime" / "omg_compat_contract_snapshot.json"


def test_compat_contract_snapshot_exists():
    assert SNAPSHOT.exists(), "Missing runtime/omg_compat_contract_snapshot.json"


def test_compat_contract_snapshot_matches_runtime_contracts():
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["schema"] == "OalCompatContractSnapshot"
    assert payload["contract_version"] == CONTRACT_SNAPSHOT_VERSION

    contracts = list_compat_skill_contracts()
    assert payload["count"] == len(contracts)
    assert payload["contracts"] == contracts


def test_runtime_snapshot_payload_shape():
    payload = build_contract_snapshot_payload(include_generated_at=False)
    assert payload["schema"] == "OalCompatContractSnapshot"
    assert payload["contract_version"] == CONTRACT_SNAPSHOT_VERSION
    assert payload["count"] == len(payload["contracts"])
