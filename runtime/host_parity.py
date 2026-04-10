from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.canonical_surface import get_canonical_hosts
from runtime.providers.provider_registry import generate_parity_report, get_registry


_logger = logging.getLogger(__name__)


_IGNORED_SEMANTIC_KEYS = {
    "host",
    "model",
    "model_name",
    "provider",
    "timestamp",
    "run_id",
    "id",
    "latency_ms",
    "duration_ms",
    "token_usage",
    "usage",
    "raw",
}

_TOKEN_RE = re.compile(r"[a-z0-9_\-]+")
_KV_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_\- ]+):\s*(.+?)\s*$")
_REAL_PARITY_SOURCE_KINDS = {
    "compiled_artifact",
    "compiled_output",
    "replayed_output",
    "replayed_artifact",
}

_PROVIDER_PARITY_STUBS = tuple(entry.name for entry in get_registry())


@dataclass
class ParityCheckResult:
    passed: bool
    host_results: dict[str, dict[str, Any]]
    drift_detected: bool
    drift_details: list[str]


@dataclass
class HostParityReport:
    run_id: str
    timestamp: str
    canonical_hosts: list[str]
    parity_results: dict[str, Any]
    overall_status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_host(host: str) -> str:
    return str(host).strip().lower()


def _source_metadata(payload: dict[str, Any]) -> tuple[str, str]:
    raw_source = payload.get("source")
    if not isinstance(raw_source, dict):
        return "", ""

    source: dict[str, Any] = raw_source
    source_kind = str(source.get("kind", "")).strip().lower()
    source_path = ""
    for key in ("artifact_path", "replay_path", "compiled_path", "output_path", "path"):
        value = str(source.get(key, "")).strip()
        if value:
            source_path = value
            break
    return source_kind, source_path


def is_synthetic(payload: dict[str, Any]) -> bool:
    source_kind, source_path = _source_metadata(payload)
    if not source_kind:
        return True
    if source_kind not in _REAL_PARITY_SOURCE_KINDS:
        return True
    if not source_path:
        return True
    return False


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            key_str = str(key)
            if key_str in _IGNORED_SEMANTIC_KEYS:
                continue
            out[key_str] = _canonicalize(value[key])
        return out
    if isinstance(value, list):
        canonical_items = [_canonicalize(item) for item in value]
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in canonical_items):
            return sorted(canonical_items, key=lambda item: repr(item))
        return canonical_items
    if isinstance(value, str):
        return value.strip()
    return value


def _tokenize(text: str) -> list[str]:
    return sorted(set(_TOKEN_RE.findall(text.lower())))


def _parse_json_blob(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        _logger.debug("Primary JSON parse failed for host parity payload: %s", exc, exc_info=True)

    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", stripped, flags=re.IGNORECASE)
    if fence:
        candidate = fence.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            _logger.debug("Fenced JSON parse failed for host parity payload: %s", exc, exc_info=True)

    decoder = json.JSONDecoder()
    for start in range(len(stripped)):
        if stripped[start] not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stripped[start:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def _coerce_scalar(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    if re.fullmatch(r"-?\d+\.\d+", value.strip()):
        return float(value.strip())
    return value.strip()


def _parse_structured_text(text: str) -> dict[str, Any]:
    structured: dict[str, Any] = {}
    for line in text.splitlines():
        match = _KV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        if "," in value:
            structured[key] = [_coerce_scalar(part) for part in value.split(",") if part.strip()]
        else:
            structured[key] = _coerce_scalar(value)
    return structured


def _build_semantic_content(host: str, output_value: Any) -> dict[str, Any]:
    if isinstance(output_value, (dict, list)):
        return {"structured": _canonicalize(output_value)}

    output_text = str(output_value or "").strip()
    parsed = _parse_json_blob(output_text)
    if parsed is not None:
        return {"structured": _canonicalize(parsed)}

    if host == "gemini":
        structured = _parse_structured_text(output_text)
        if structured:
            return {"structured": _canonicalize(structured)}

    tokens = _tokenize(output_text)
    return {
        "text": {
            "tokens": tokens[:64],
            "token_count": len(tokens),
        }
    }


def _jaccard_similarity(a_tokens: list[str], b_tokens: list[str]) -> float:
    a_set = set(a_tokens)
    b_set = set(b_tokens)
    if not a_set and not b_set:
        return 1.0
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


class HostParityNormalizer:
    def __init__(self, canonical_hosts: list[str] | None = None, text_similarity_threshold: float = 0.55):
        self.canonical_hosts = [_normalize_host(host) for host in (canonical_hosts or get_canonical_hosts())]
        self.text_similarity_threshold = max(0.0, min(1.0, float(text_similarity_threshold)))

    def normalize_output(self, host: str, raw_output: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = context
        host_name = _normalize_host(host)
        payload = raw_output if isinstance(raw_output, dict) else {"output": raw_output}
        source_kind, source_path = _source_metadata(payload)

        exit_code_raw = payload.get("exit_code", 0)
        try:
            exit_code = int(exit_code_raw)
        except Exception as exc:
            _logger.debug("Failed to coerce host exit code for %s: %s", host_name, exc, exc_info=True)
            exit_code = 0

        error = str(payload.get("error", "")).strip()
        status = "error" if error or exit_code != 0 else "ok"
        fallback = str(payload.get("fallback", "")).strip()
        semantic_content = _build_semantic_content(host_name, payload.get("output", ""))

        normalized = {
            "host": host_name,
            "status": status,
            "exit_code": exit_code,
            "exit_code_class": "success" if exit_code == 0 else "error",
            "fallback": fallback,
            "error": error,
            "error_class": "none" if not error else "provider-error",
            "source_kind": source_kind or "synthetic",
            "source_path": source_path,
            "source_class": "compiled_or_replayed" if not is_synthetic(payload) else "synthetic",
            "semantic": semantic_content,
        }
        return normalized

    def _is_semantically_equivalent(self, left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, str]:
        if left.get("status") != right.get("status"):
            return False, "status mismatch"

        left_semantic = left.get("semantic", {}) if isinstance(left.get("semantic"), dict) else {}
        right_semantic = right.get("semantic", {}) if isinstance(right.get("semantic"), dict) else {}

        left_structured = left_semantic.get("structured")
        right_structured = right_semantic.get("structured")
        if left_structured is not None and right_structured is not None:
            if left_structured == right_structured:
                return True, "structured-equivalent"
            return False, "structured content mismatch"

        left_tokens = left_semantic.get("text", {}).get("tokens", [])
        right_tokens = right_semantic.get("text", {}).get("tokens", [])
        if isinstance(left_tokens, list) and isinstance(right_tokens, list):
            score = _jaccard_similarity(left_tokens, right_tokens)
            if score >= self.text_similarity_threshold:
                return True, f"text-equivalent score={score:.2f}"
            return False, f"text drift score={score:.2f}"
        return False, "semantic payload mismatch"

    def check_parity(self, outputs_by_host: dict[str, Any], context: dict[str, Any] | None = None) -> ParityCheckResult:
        host_results: dict[str, dict[str, Any]] = {}
        drift_details: list[str] = []

        baseline_host = ""
        baseline_output: dict[str, Any] | None = None

        for host in self.canonical_hosts:
            if host not in outputs_by_host:
                host_results[host] = {
                    "present": False,
                    "passed": False,
                    "reason": "missing host output",
                    "normalized": {},
                }
                drift_details.append(f"missing host output: {host}")
                continue

            raw_payload = outputs_by_host[host]
            payload = raw_payload if isinstance(raw_payload, dict) else {"output": raw_payload}
            normalized = self.normalize_output(host, payload, context)
            if is_synthetic(payload):
                host_results[host] = {
                    "present": True,
                    "passed": False,
                    "reason": "synthetic payload rejected",
                    "normalized": normalized,
                }
                drift_details.append(f"synthetic payload rejected: {host}")
                continue

            host_results[host] = {
                "present": True,
                "passed": True,
                "reason": "baseline",
                "normalized": normalized,
            }
            if baseline_output is None:
                baseline_host = host
                baseline_output = normalized

        if baseline_output is not None:
            for host in self.canonical_hosts:
                current = host_results.get(host, {})
                if not current.get("present"):
                    continue
                if current.get("reason") == "synthetic payload rejected":
                    continue
                normalized = current.get("normalized")
                if not isinstance(normalized, dict):
                    continue
                equivalent, reason = self._is_semantically_equivalent(baseline_output, normalized)
                current["passed"] = equivalent
                current["reason"] = reason if host != baseline_host else "baseline"
                if not equivalent:
                    drift_details.append(f"semantic drift: {host} vs {baseline_host} ({reason})")

        drift_detected = bool(drift_details)
        passed = not drift_detected and all(
            isinstance(host_results.get(host), dict)
            and bool(host_results[host].get("present"))
            and bool(host_results[host].get("passed"))
            for host in self.canonical_hosts
        )
        return ParityCheckResult(
            passed=passed,
            host_results=host_results,
            drift_detected=drift_detected,
            drift_details=drift_details,
        )


def normalize_output(host: str, raw_output: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return HostParityNormalizer().normalize_output(host, raw_output, context)


def check_parity(outputs_by_host: dict[str, Any], context: dict[str, Any] | None = None) -> ParityCheckResult:
    return HostParityNormalizer().check_parity(outputs_by_host, context)


def get_provider_parity_stubs() -> list[str]:
    return list(_PROVIDER_PARITY_STUBS)


def evaluate_provider_registry_parity() -> dict[str, Any]:
    return generate_parity_report(get_registry())


def emit_parity_report(
    run_id: str,
    results: ParityCheckResult,
    *,
    project_dir: str | None = None,
) -> str:
    base_dir = Path(project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    out_path = base_dir / ".omg" / "evidence" / f"host-parity-{run_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = HostParityReport(
        run_id=str(run_id),
        timestamp=_now_iso(),
        canonical_hosts=get_canonical_hosts(),
        parity_results=asdict(results),
        overall_status="ok" if results.passed else "drift",
    )
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(out_path)


__all__ = [
    "HostParityNormalizer",
    "ParityCheckResult",
    "HostParityReport",
    "is_synthetic",
    "normalize_output",
    "check_parity",
    "emit_parity_report",
    "get_provider_parity_stubs",
    "evaluate_provider_registry_parity",
]
