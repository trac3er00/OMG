from __future__ import annotations

from typing import Any


def format_terminal(narrative: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("=== OMG Verdict ===")
    lines.append(narrative.get("verdict_summary", ""))
    lines.append("")

    blockers = narrative.get("blockers_section", [])
    if blockers:
        lines.append("Blockers:")
        for b in blockers:
            lines.append(f"  - {b}")
        lines.append("")

    next_actions = narrative.get("next_actions", [])
    if next_actions:
        lines.append("Next Actions:")
        for a in next_actions:
            lines.append(f"  - {a}")
        lines.append("")

    evidence = narrative.get("evidence_paths_section", [])
    if evidence:
        lines.append("Evidence:")
        for e in evidence:
            lines.append(f"  - {e}")
        lines.append("")

    provenance = narrative.get("provenance_note")
    if provenance:
        lines.append(f"Provenance: {provenance}")
        lines.append("")

    return "\n".join(lines)


def format_markdown(narrative: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("## OMG Verdict")
    lines.append("")
    lines.append(narrative.get("verdict_summary", ""))
    lines.append("")

    blockers = narrative.get("blockers_section", [])
    if blockers:
        lines.append("### Blockers")
        lines.append("")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    next_actions = narrative.get("next_actions", [])
    if next_actions:
        lines.append("### Next Actions")
        lines.append("")
        for a in next_actions:
            lines.append(f"- {a}")
        lines.append("")

    evidence = narrative.get("evidence_paths_section", [])
    if evidence:
        lines.append("### Evidence")
        lines.append("")
        for e in evidence:
            lines.append(f"- `{e}`")
        lines.append("")

    provenance = narrative.get("provenance_note")
    if provenance:
        lines.append(f"*{provenance}*")
        lines.append("")

    return "\n".join(lines)


__all__ = ["format_terminal", "format_markdown"]
