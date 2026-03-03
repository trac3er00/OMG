"""Parity tests for Claude/GPT/Local adapter contract."""

from runtime.adapters import get_adapters


def test_adapter_parity_schema_keys():
    adapters = get_adapters()
    idea = {"gomg": "Implement auth middleware"}

    baseline = None
    for name, adapter in adapters.items():
        plan = adapter.plan(idea)
        executed = adapter.execute(plan)
        verified = adapter.verify(executed)
        evidence = adapter.collect_evidence(verified)

        shape = {
            "plan": tuple(sorted(plan.keys())),
            "execute": tuple(sorted(executed.keys())),
            "verify": tuple(sorted(verified.keys())),
            "evidence": tuple(sorted(evidence.keys())),
        }

        if baseline is None:
            baseline = shape
        else:
            assert shape == baseline, f"schema mismatch for adapter: {name}"


def test_adapter_common_error_code_capability():
    adapters = get_adapters()
    # In stub implementation, no errors are emitted; ensure shared errors key exists.
    for adapter in adapters.values():
        executed = adapter.execute({"dummy": True})
        assert "errors" in executed
        assert isinstance(executed["errors"], list)
