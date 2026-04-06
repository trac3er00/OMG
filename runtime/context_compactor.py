from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
from typing import cast


JsonObject = dict[str, object]


_DEFAULT_JOURNAL_REL = Path(".omg") / "state" / "interaction-journal.jsonl"
_JOURNAL_DIR_REL = Path(".omg") / "state" / "interaction_journal"
_SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "decisions": ("decided", "decision", "chose", "selected", "will use", "going with"),
    "constraints": (
        "must not",
        "cannot",
        "constraint",
        "requirement",
        "must be",
        "should not",
    ),
    "open_loops": ("todo", "pending", "blocked", "waiting", "need to", "follow up"),
    "risks": ("risk", "concern", "warning", "careful", "watch out", "hazard"),
    "next_actions": (
        "next",
        "then",
        "after that",
        "follow-up",
        "follow up",
        "action item",
    ),
}
_VERBOSITY_LIMITS = {"brief": 3, "standard": 10, "detailed": 50}


@dataclass
class CompactedContext:
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    open_loops: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_markdown(self, verbosity: str = "standard") -> str:
        limit = _VERBOSITY_LIMITS.get(verbosity, _VERBOSITY_LIMITS["standard"])
        sections = [
            ("## Decisions", self.decisions),
            ("## Constraints", self.constraints),
            ("## Open Loops", self.open_loops),
            ("## Risks", self.risks),
            ("## Artifacts", self.artifacts),
            ("## Next Actions", self.next_actions),
        ]
        lines = ["# Session Handoff Context", ""]
        for header, items in sections:
            lines.append(header)
            if items:
                for item in items[:limit]:
                    lines.append(f"- {item}")
            else:
                lines.append("- (none)")
            lines.append("")
        return "\n".join(lines)


def compact_context(
    journal_path: str | None = None,
    project_dir: str = ".",
    verbosity: str = "standard",
) -> CompactedContext:
    ctx = CompactedContext()
    root = Path(project_dir).resolve()

    for entry in _load_journal_entries(root, journal_path):
        _classify_entry(ctx, entry)

    ctx.artifacts.extend(_extract_artifacts(root))
    _derive_next_actions(ctx)
    _apply_limits(ctx, verbosity)
    return ctx


def _load_journal_entries(root: Path, journal_path: str | None) -> list[JsonObject]:
    if journal_path:
        journal = Path(journal_path)
        if journal.suffix == ".jsonl":
            return _load_jsonl_entries(journal)
        if journal.is_dir():
            return _load_journal_dir_entries(journal)

    default_jsonl = root / _DEFAULT_JOURNAL_REL
    if default_jsonl.exists():
        return _load_jsonl_entries(default_jsonl)

    journal_dir = root / _JOURNAL_DIR_REL
    if journal_dir.exists():
        return _load_journal_dir_entries(journal_dir)

    return []


def _load_jsonl_entries(path: Path) -> list[JsonObject]:
    entries: list[JsonObject] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            raw_payload = cast(object, json.loads(line))
            payload = _coerce_json_object(raw_payload)
            if payload is not None:
                entries.append(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return entries


def _load_journal_dir_entries(path: Path) -> list[JsonObject]:
    entries: list[JsonObject] = []
    try:
        candidates = sorted(path.glob("*.json"), key=lambda candidate: candidate.name)
    except OSError:
        return []
    for candidate in candidates:
        if candidate.name.endswith(".tmp"):
            continue
        try:
            raw_payload = cast(
                object, json.loads(candidate.read_text(encoding="utf-8"))
            )
            payload = _coerce_json_object(raw_payload)
        except (OSError, json.JSONDecodeError):
            continue
        if payload is not None:
            entries.append(payload)
    return entries


def _classify_entry(ctx: CompactedContext, entry: JsonObject) -> None:
    content = _extract_content(entry)
    if not content:
        return
    normalized = content.lower()
    snippet = _summarize(content)

    matched = False
    for section_name, patterns in _SECTION_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            _append_section(ctx, section_name, snippet)
            matched = True

    if not matched and _looks_like_constraint(entry):
        ctx.constraints.append(snippet)


def _extract_content(entry: JsonObject) -> str:
    for key in ("content", "message", "summary", "text"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = _coerce_json_object(entry.get("metadata"))
    if metadata is not None:
        for key in ("command", "reason", "note"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _looks_like_constraint(entry: JsonObject) -> bool:
    tool = str(entry.get("tool", "")).strip().lower()
    rollback_mode = str(entry.get("rollback_mode", "")).strip().lower()
    return tool in {"write", "edit", "multiedit"} and rollback_mode == "unsupported"


def _summarize(content: str, max_len: int = 200) -> str:
    single_line = " ".join(content.split())
    if len(single_line) <= max_len:
        return single_line
    return single_line[: max_len - 3].rstrip() + "..."


def _extract_artifacts(root: Path) -> list[str]:
    commands = [
        ["git", "status", "--short"],
        ["git", "diff", "--name-only", "HEAD~5", "HEAD"],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=root,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        artifacts = _parse_git_output(command, result.stdout)
        if artifacts:
            return artifacts
    return []


def _parse_git_output(command: list[str], stdout: str) -> list[str]:
    items: list[str] = []
    if command[:3] == ["git", "status", "--short"]:
        for line in stdout.splitlines():
            row = line.rstrip()
            if len(row) < 4:
                continue
            path = row[3:].strip()
            if not path:
                continue
            items.append(f"Changed: {path}")
    else:
        for line in stdout.splitlines():
            path = line.strip()
            if path:
                items.append(f"Modified: {path}")
    return _dedupe(items)


def _derive_next_actions(ctx: CompactedContext) -> None:
    if not ctx.next_actions:
        ctx.next_actions.extend(ctx.open_loops)
    ctx.next_actions = _dedupe(ctx.next_actions)


def _apply_limits(ctx: CompactedContext, verbosity: str) -> None:
    limit = _VERBOSITY_LIMITS.get(verbosity, _VERBOSITY_LIMITS["standard"])
    ctx.decisions = _dedupe(ctx.decisions)[:limit]
    ctx.constraints = _dedupe(ctx.constraints)[:limit]
    ctx.open_loops = _dedupe(ctx.open_loops)[:limit]
    ctx.risks = _dedupe(ctx.risks)[:limit]
    ctx.artifacts = _dedupe(ctx.artifacts)[:limit]
    ctx.next_actions = _dedupe(ctx.next_actions)[:limit]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _append_section(ctx: CompactedContext, section_name: str, item: str) -> None:
    if section_name == "decisions":
        ctx.decisions.append(item)
    elif section_name == "constraints":
        ctx.constraints.append(item)
    elif section_name == "open_loops":
        ctx.open_loops.append(item)
    elif section_name == "risks":
        ctx.risks.append(item)
    elif section_name == "artifacts":
        ctx.artifacts.append(item)
    elif section_name == "next_actions":
        ctx.next_actions.append(item)


def _coerce_json_object(payload: object) -> JsonObject | None:
    if not isinstance(payload, dict):
        return None
    payload_dict = cast(dict[object, object], payload)
    normalized: JsonObject = {}
    for key, value in payload_dict.items():
        if not isinstance(key, str):
            return None
        normalized[key] = value
    return normalized
