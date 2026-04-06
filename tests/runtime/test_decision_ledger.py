from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.decision_ledger import DECISION_TYPES, Decision, DecisionLedger


def _make_decision(
    type_: str = "tech_choice",
    ctx: str = "PostgreSQL",
    rationale: str = "fast",
    src: str = "user",
) -> Decision:
    return Decision(decision_type=type_, context=ctx, rationale=rationale, source=src)


def test_decision_types_are_supported() -> None:
    assert DECISION_TYPES == (
        "tech_choice",
        "architecture",
        "scope",
        "constraint",
        "preference",
    )


def test_append_and_query(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    decision = _make_decision(ctx="Use JWT", rationale="stateless auth")

    ledger.append(decision)

    results = ledger.query()
    assert len(results) == 1
    assert results[0].context == "Use JWT"


def test_query_by_type(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    ledger.append(_make_decision(type_="tech_choice", ctx="tech1"))
    ledger.append(_make_decision(type_="architecture", ctx="arch1"))

    results = ledger.query(decision_type="tech_choice")

    assert len(results) == 1
    assert results[0].context == "tech1"


def test_query_by_keyword(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    ledger.append(_make_decision(ctx="Use PostgreSQL for storage"))
    ledger.append(_make_decision(ctx="Use Redis for cache"))

    results = ledger.query(keyword="postgresql")

    assert len(results) == 1
    assert "PostgreSQL" in results[0].context


def test_compact_reduces_duplicates(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    for i in range(5):
        ledger.append(_make_decision(ctx="same context", rationale=f"version {i}"))

    stats = ledger.compact()

    assert stats["before"] == 5
    assert stats["after"] < stats["before"]


def test_compact_dry_run_no_changes(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    for i in range(3):
        ledger.append(_make_decision(ctx="same", rationale=f"v{i}"))

    stats_dry = ledger.compact(dry_run=True)
    results_after = ledger.query()

    assert stats_dry["before"] == 3
    assert len(results_after) == 3


def test_decision_persists_to_jsonl(tmp_path: Path) -> None:
    ledger = DecisionLedger(str(tmp_path))
    ledger.append(_make_decision(ctx="persist test"))

    jsonl = (tmp_path / ".omg" / "state" / "ledger" / "decisions.jsonl").read_text(
        encoding="utf-8"
    )
    data = json.loads(jsonl.strip())

    assert data["context"] == "persist test"
    assert "id" in data
    assert "timestamp" in data
