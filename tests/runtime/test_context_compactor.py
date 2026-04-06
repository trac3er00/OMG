from __future__ import annotations

from collections.abc import Callable
import importlib
import json
from pathlib import Path
from typing import Protocol, cast


class ContextLike(Protocol):
    decisions: list[str]
    constraints: list[str]
    open_loops: list[str]
    risks: list[str]
    artifacts: list[str]
    next_actions: list[str]

    def to_markdown(self, verbosity: str = "standard") -> str: ...


_module = importlib.import_module("runtime.context_compactor")
CompactedContext = cast(type[object], getattr(_module, "CompactedContext"))
compact_context = cast(Callable[..., ContextLike], getattr(_module, "compact_context"))


def test_compact_context_returns_compacted_context(tmp_path: Path) -> None:
    result = compact_context(project_dir=str(tmp_path))

    assert isinstance(result, CompactedContext)
    assert hasattr(result, "decisions")
    assert hasattr(result, "constraints")
    assert hasattr(result, "open_loops")
    assert hasattr(result, "risks")
    assert hasattr(result, "artifacts")
    assert hasattr(result, "next_actions")


def test_to_markdown_contains_all_sections(tmp_path: Path) -> None:
    ctx = compact_context(project_dir=str(tmp_path))
    md = ctx.to_markdown()

    assert "## Decisions" in md
    assert "## Constraints" in md
    assert "## Open Loops" in md
    assert "## Risks" in md
    assert "## Artifacts" in md
    assert "## Next Actions" in md


def test_compact_context_reads_journal(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(
        json.dumps({"content": "We decided to use PostgreSQL for the database"}) + "\n",
        encoding="utf-8",
    )

    result = compact_context(journal_path=str(journal), project_dir=str(tmp_path))

    assert len(result.decisions) > 0
    assert any("PostgreSQL" in decision for decision in result.decisions)


def test_to_markdown_under_500_lines(tmp_path: Path) -> None:
    ctx = compact_context(project_dir=str(tmp_path))
    md = ctx.to_markdown()

    assert len(md.splitlines()) < 500


def test_compact_context_reads_interaction_journal_directory(tmp_path: Path) -> None:
    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    journal_dir.mkdir(parents=True)
    _ = (journal_dir / "step-1.json").write_text(
        json.dumps({"message": "Need to follow up on flaky session health tests"})
        + "\n",
        encoding="utf-8",
    )

    result = compact_context(project_dir=str(tmp_path))

    assert any("follow up" in item.lower() for item in result.open_loops)
    assert any("follow up" in item.lower() for item in result.next_actions)
