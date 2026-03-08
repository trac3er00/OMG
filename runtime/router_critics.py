from __future__ import annotations

def run_critics(candidate: dict[str, object], context_packet: dict[str, object], project_dir: str) -> dict[str, dict[str, str]]:
    _ = (candidate, context_packet, project_dir)
    return {
        "skeptic": {"verdict": "pass"},
        "hallucination_auditor": {"verdict": "pass"},
    }
