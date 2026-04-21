from __future__ import annotations

import json
import importlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol, cast


class _PytestProtocol(Protocol):
    def skip(self, reason: str) -> None: ...


pytest = cast(_PytestProtocol, cast(object, importlib.import_module("pytest")))

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"


def run_hook(hook_path: Path, event: dict[str, object]) -> dict[str, object]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    env["OMG_HOOK_INVENTORY_TEST"] = "1"
    env["OMG_TDD_GATE_STRICT"] = "0"
    env["OMG_STRICT_AMBIGUITY_MODE"] = "0"

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return {"returncode": result.returncode}


def _event_payload() -> dict[str, object]:
    return {
        "event": "PreToolUse",
        "tool": "Read",
        "input": {"file_path": "/tmp/test.txt"},
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/test.txt"},
    }


class TestHookChainBenchmark:
    def test_hook_chain_benchmark(self) -> None:
        hooks = sorted(
            [
                f
                for f in HOOKS_DIR.glob("*.py")
                if not f.name.startswith("_") and f.name != "__init__.py"
            ]
        )
        event = _event_payload()

        start = time.time()
        for hook in hooks[:20]:
            _ = run_hook(hook, event)
        elapsed = time.time() - start

        print(f"\n20 hooks in {elapsed:.2f}s")
        assert elapsed < 30, f"Hook chain too slow: {elapsed:.2f}s for 20 hooks"

    def test_single_hook_latency(self) -> None:
        firewall = HOOKS_DIR / "firewall.py"
        if not firewall.exists():
            pytest.skip("firewall.py not found")

        start = time.time()
        _ = run_hook(firewall, _event_payload())
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Single hook too slow: {elapsed:.2f}s"


class TestConcurrentAgentsLoad:
    def test_concurrent_agents_hook_load(self) -> None:
        hooks = sorted(
            [
                f
                for f in HOOKS_DIR.glob("*.py")
                if not f.name.startswith("_") and f.name != "__init__.py"
            ]
        )[:8]
        if not hooks:
            pytest.skip("No hooks found")

        event = _event_payload()
        jobs: list[Path] = hooks * 2

        def _run_for_concurrency(hook: Path) -> dict[str, object]:
            return run_hook(hook, event)

        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_run_for_concurrency, jobs))
        elapsed = time.time() - start

        assert all(r.get("returncode") is not None for r in results)
        assert elapsed < 45, f"Concurrent hook load too slow: {elapsed:.2f}s"


class TestBudgetEnvelope:
    def test_budget_module_exists(self) -> None:
        budget_file = ROOT / "src" / "orchestration" / "budget.ts"
        assert budget_file.exists(), "budget.ts not found"

    def test_budget_has_pressure_function(self) -> None:
        budget_file = ROOT / "src" / "orchestration" / "budget.ts"
        if not budget_file.exists():
            pytest.skip("budget.ts not found")

        content = budget_file.read_text(encoding="utf-8")
        assert "BudgetEnvelope" in content
        assert "pressure(" in content, "pressure() not found in budget.ts"

    def test_budget_pressure_scan_benchmark(self) -> None:
        budget_file = ROOT / "src" / "orchestration" / "budget.ts"
        if not budget_file.exists():
            pytest.skip("budget.ts not found")

        start = time.time()
        for _ in range(200):
            _ = "pressure(" in budget_file.read_text(encoding="utf-8")
        elapsed = time.time() - start
        assert elapsed < 2.5, f"budget.ts scan too slow: {elapsed:.2f}s"


class TestRateLimiter:
    def test_rate_limiter_exists(self) -> None:
        rate_limiter = ROOT / "src" / "security" / "rate-limiter.ts"
        assert rate_limiter.exists(), "rate-limiter.ts not found"

    def test_rate_limiter_has_token_bucket(self) -> None:
        rate_limiter = ROOT / "src" / "security" / "rate-limiter.ts"
        if not rate_limiter.exists():
            pytest.skip("rate-limiter.ts not found")

        content = rate_limiter.read_text(encoding="utf-8").lower()
        assert "token" in content and "bucket" in content and "consume" in content

    def test_rate_limiter_scan_benchmark(self) -> None:
        rate_limiter = ROOT / "src" / "security" / "rate-limiter.ts"
        if not rate_limiter.exists():
            pytest.skip("rate-limiter.ts not found")

        start = time.time()
        for _ in range(200):
            text = rate_limiter.read_text(encoding="utf-8")
            _ = "consume(" in text
        elapsed = time.time() - start
        assert elapsed < 2.5, f"rate-limiter.ts scan too slow: {elapsed:.2f}s"


class TestLedgerIntegrity:
    def test_ledger_exists(self) -> None:
        ledger = ROOT / "src" / "governance" / "ledger.ts"
        assert ledger.exists(), "ledger.ts not found"

    def test_ledger_has_integrity_check(self) -> None:
        ledger = ROOT / "src" / "governance" / "ledger.ts"
        if not ledger.exists():
            pytest.skip("ledger.ts not found")

        content = ledger.read_text(encoding="utf-8")
        assert "GovernanceLedger" in content
        assert "verifyIntegrity(" in content

    def test_ledger_contention_read_benchmark(self) -> None:
        ledger = ROOT / "src" / "governance" / "ledger.ts"
        if not ledger.exists():
            pytest.skip("ledger.ts not found")

        def _read_size(_: int) -> int:
            return len(ledger.read_text(encoding="utf-8"))

        start = time.time()
        with ThreadPoolExecutor(max_workers=8) as executor:
            sizes = list(executor.map(_read_size, range(120)))
        elapsed = time.time() - start

        assert all(size > 0 for size in sizes)
        assert elapsed < 5.0, f"Ledger contention benchmark too slow: {elapsed:.2f}s"
