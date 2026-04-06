from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

DECISION_TYPES = (
    "tech_choice",
    "architecture",
    "scope",
    "constraint",
    "preference",
)
SOURCES = ("user", "agent", "policy")

_ARCHIVE_DAYS = 90


class DecisionRecord(TypedDict):
    id: str
    decision_type: str
    context: str
    rationale: str
    source: str
    confidence: float
    tags: list[str]
    timestamp: str


def _parse_timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_float(value: object, default: float = 0.8) -> float:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(tag) for tag in cast(list[object], value)]
    return []


@dataclass
class Decision:
    decision_type: str
    context: str
    rationale: str
    source: str
    confidence: float = 0.8
    tags: list[str] = field(default_factory=list)
    id: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if self.decision_type not in DECISION_TYPES:
            raise ValueError(f"Unsupported decision_type: {self.decision_type}")
        if self.source not in SOURCES:
            raise ValueError(f"Unsupported source: {self.source}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.tags = [str(tag) for tag in self.tags]
        if not self.id:
            digest = hashlib.sha256(
                f"{self.context}:{self.rationale}:{time.time()}".encode("utf-8")
            ).hexdigest()
            self.id = digest[:16]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> DecisionRecord:
        return {
            "id": self.id,
            "decision_type": self.decision_type,
            "context": self.context,
            "rationale": self.rationale,
            "source": self.source,
            "confidence": self.confidence,
            "tags": self.tags,
            "timestamp": self.timestamp,
        }


class DecisionLedger:
    def __init__(self, project_dir: str = "."):
        base = Path(project_dir) / ".omg" / "state" / "ledger"
        self._ledger_path: Path = base / "decisions.jsonl"
        self._archive_path: Path = base / "decisions-archive.jsonl"
        base.mkdir(parents=True, exist_ok=True)

    def append(self, decision: Decision) -> None:
        with self._ledger_path.open("a", encoding="utf-8") as handle:
            _ = handle.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")

    def _load_all(self) -> list[Decision]:
        if not self._ledger_path.exists():
            return []

        entries: list[Decision] = []
        for line in self._ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                loaded = cast(object, json.loads(line))
                if not isinstance(loaded, dict):
                    continue
                raw = cast(dict[str, object], loaded)
                entries.append(
                    Decision(
                        decision_type=_as_text(raw.get("decision_type"), "tech_choice"),
                        context=_as_text(raw.get("context")),
                        rationale=_as_text(raw.get("rationale")),
                        source=_as_text(raw.get("source"), "agent"),
                        confidence=_as_float(raw.get("confidence"), 0.8),
                        tags=_as_tags(raw.get("tags")),
                        id=_as_text(raw.get("id")),
                        timestamp=_as_text(raw.get("timestamp")),
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return entries

    def query(
        self,
        decision_type: str | None = None,
        keyword: str | None = None,
        since_days: int | None = None,
        limit: int = 100,
    ) -> list[Decision]:
        entries = self._load_all()

        if decision_type is not None:
            entries = [
                entry for entry in entries if entry.decision_type == decision_type
            ]

        if keyword:
            normalized = keyword.lower()
            entries = [
                entry
                for entry in entries
                if normalized in entry.context.lower()
                or normalized in entry.rationale.lower()
                or any(normalized in tag.lower() for tag in entry.tags)
            ]

        if since_days is not None:
            cutoff = datetime.now(timezone.utc).timestamp() - (since_days * 86400)
            entries = [
                entry
                for entry in entries
                if _parse_timestamp(entry.timestamp) >= cutoff
            ]

        return entries[-limit:]

    def compact(self, dry_run: bool = False) -> dict[str, int]:
        entries = self._load_all()
        before = len(entries)
        cutoff = datetime.now(timezone.utc).timestamp() - (_ARCHIVE_DAYS * 86400)

        to_archive: list[Decision] = []
        deduped: dict[str, Decision] = {}

        for entry in sorted(entries, key=lambda item: item.timestamp):
            entry_ts = _parse_timestamp(entry.timestamp)
            if entry_ts < cutoff:
                to_archive.append(entry)
                continue
            key = f"{entry.decision_type}:{entry.context[:40].strip().lower()}"
            deduped[key] = entry

        to_keep = sorted(deduped.values(), key=lambda item: item.timestamp)
        archived = len(to_archive)
        merged = max(0, before - archived - len(to_keep))

        if not dry_run:
            with self._ledger_path.open("w", encoding="utf-8") as handle:
                for entry in to_keep:
                    _ = handle.write(
                        json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
                    )

            if to_archive:
                with self._archive_path.open("a", encoding="utf-8") as handle:
                    for entry in to_archive:
                        _ = handle.write(
                            json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
                        )

        return {
            "before": before,
            "after": len(to_keep),
            "archived": archived,
            "merged": merged,
        }
