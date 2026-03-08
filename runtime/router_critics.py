from __future__ import annotations

import os
import re
from typing import Any


_CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\btrust me\b", "contains unsupported confidence phrase 'trust me'"),
    (r"\bimplemented\b", "claims implementation without evidence pointer"),
    (r"\bfixed\b", "claims fix without evidence pointer"),
    (r"\btested\b", "claims testing without evidence pointer"),
)

_EVIDENCE_PATTERNS: tuple[str, ...] = (
    r"\.sisyphus/evidence/",
    r"\.omg/state/",
    r"\bpytest\b",
    r"\bpython3\s+-m\s+pytest\b",
    r"\b[a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+(?::\d+)?\b",
)

_PATH_RE = re.compile(r"\b(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+(?:[:#]L?\d+)?\b")
_FUNC_BACKTICK_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`")
_FUNC_TEXT_RE = re.compile(r"\bfunction\s+([a-zA-Z_][a-zA-Z0-9_]*)\b")
_SYMBOL_TEXT_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")


def _extract_output_text(candidate: dict[str, Any]) -> str:
    value = candidate.get("output", "")
    return value if isinstance(value, str) else str(value)


def _has_evidence_pointer(text: str, context_packet: dict[str, Any]) -> bool:
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in _EVIDENCE_PATTERNS):
        return True
    pointers = context_packet.get("artifact_pointers")
    if isinstance(pointers, list):
        for pointer in pointers:
            if isinstance(pointer, str) and pointer and pointer.lower() in lowered:
                return True
    return False


def _run_skeptic(candidate: dict[str, Any], context_packet: dict[str, Any]) -> dict[str, Any]:
    output_text = _extract_output_text(candidate)
    lowered = output_text.lower()
    findings: list[str] = []
    has_evidence = _has_evidence_pointer(output_text, context_packet)

    for pattern, message in _CLAIM_PATTERNS:
        if re.search(pattern, lowered):
            if "trust me" in pattern or not has_evidence:
                findings.append(message)

    if findings:
        verdict = "fail" if any("trust me" in item for item in findings) else "warn"
        confidence = 0.9 if verdict == "fail" else 0.78
        return {"verdict": verdict, "findings": findings, "confidence": confidence}

    return {
        "verdict": "pass",
        "findings": ["claims include sufficient evidence pointers or are non-assertive"],
        "confidence": 0.83,
    }


def _extract_context_paths(context_packet: dict[str, Any]) -> set[str]:
    known: set[str] = set()
    pointers = context_packet.get("artifact_pointers")
    if isinstance(pointers, list):
        known.update(str(p).strip() for p in pointers if isinstance(p, str) and p.strip())

    for key in ("files", "known_paths", "artifacts"):
        value = context_packet.get(key)
        if isinstance(value, list):
            known.update(str(v).strip() for v in value if isinstance(v, str) and v.strip())

    summary = context_packet.get("summary", "")
    if isinstance(summary, str):
        known.update(match.group(0).strip() for match in _PATH_RE.finditer(summary))

    return {item.lstrip("./") for item in known}


def _extract_context_functions(context_packet: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("functions", "symbols", "known_functions"):
        value = context_packet.get(key)
        if isinstance(value, list):
            names.update(str(v).strip() for v in value if isinstance(v, str) and v.strip())
    summary = context_packet.get("summary", "")
    if isinstance(summary, str):
        for match in _FUNC_BACKTICK_RE.finditer(summary):
            names.add(match.group(1))
        for match in _FUNC_TEXT_RE.finditer(summary):
            names.add(match.group(1))
    return names


def _extract_output_paths(output_text: str) -> set[str]:
    return {match.group(0).split(":", 1)[0].lstrip("./") for match in _PATH_RE.finditer(output_text)}


def _extract_output_functions(output_text: str) -> set[str]:
    functions: set[str] = set()
    for match in _FUNC_BACKTICK_RE.finditer(output_text):
        functions.add(match.group(1))
    for match in _FUNC_TEXT_RE.finditer(output_text):
        functions.add(match.group(1))
    for match in _SYMBOL_TEXT_RE.finditer(output_text):
        token = match.group(1)
        if token not in {"if", "for", "while", "return", "assert"}:
            functions.add(token)
    return functions


def _is_path_verifiable(path: str, known_paths: set[str], project_dir: str) -> bool:
    if path in known_paths:
        return True
    normalized = path.split("#", 1)[0].strip()
    return os.path.exists(os.path.join(project_dir, normalized))


def _run_hallucination_auditor(
    candidate: dict[str, Any],
    context_packet: dict[str, Any],
    project_dir: str,
) -> dict[str, Any]:
    output_text = _extract_output_text(candidate)
    known_paths = _extract_context_paths(context_packet)
    known_functions = _extract_context_functions(context_packet)

    referenced_paths = _extract_output_paths(output_text)
    referenced_functions = _extract_output_functions(output_text)

    findings: list[str] = []

    unknown_paths = [
        path for path in sorted(referenced_paths) if not _is_path_verifiable(path, known_paths, project_dir)
    ]
    unknown_functions = [
        name for name in sorted(referenced_functions) if known_functions and name not in known_functions
    ]

    if unknown_paths:
        findings.append("unverifiable file references: " + ", ".join(unknown_paths[:6]))
    if unknown_functions:
        findings.append("unverifiable function references: " + ", ".join(unknown_functions[:6]))

    if findings and (len(unknown_paths) >= max(1, len(referenced_paths))):
        return {"verdict": "fail", "findings": findings, "confidence": 0.86}
    if findings:
        return {"verdict": "warn", "findings": findings, "confidence": 0.72}

    return {
        "verdict": "pass",
        "findings": ["output references are verifiable against bounded context packet"],
        "confidence": 0.8,
    }


def run_critics(candidate: dict[str, object], context_packet: dict[str, object], project_dir: str) -> dict[str, dict[str, Any]]:
    bounded_context = {
        "summary": context_packet.get("summary", ""),
        "artifact_pointers": context_packet.get("artifact_pointers", []),
        "files": context_packet.get("files", []),
        "known_paths": context_packet.get("known_paths", []),
        "functions": context_packet.get("functions", []),
        "known_functions": context_packet.get("known_functions", []),
    }

    skeptic = _run_skeptic(candidate, bounded_context)
    hallucination_auditor = _run_hallucination_auditor(candidate, bounded_context, project_dir)
    return {
        "skeptic": skeptic,
        "hallucination_auditor": hallucination_auditor,
    }
