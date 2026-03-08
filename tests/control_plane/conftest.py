from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _strict_tdd_gate_for_mutation_tests(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if "mutation_gate" in request.node.name:
        monkeypatch.setenv("OMG_TDD_GATE_STRICT", "1")
