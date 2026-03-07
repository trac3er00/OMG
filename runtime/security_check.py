"""Canonical OMG security check engine."""
from __future__ import annotations

import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from hooks.security_validators import ensure_path_within_dir
from runtime.delta_classifier import classify_project_changes
from runtime.tracebank import record_trace
from plugins.dephealth.cve_scanner import scan_for_cves
from plugins.dephealth.manifest_detector import detect_manifests
from plugins.dephealth.vuln_analyzer import analyze_reachability


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

_PYTHON_AST_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("B602", "subprocess-shell-true", "high", "Avoid shell=True in subprocess calls."),
    ("B307", "eval-use", "high", "Replace eval with explicit parsing."),
    ("B102", "exec-use", "high", "Replace exec with explicit control flow."),
    ("B301", "pickle-load", "high", "Avoid unsafe deserialization of pickle payloads."),
)


def run_security_check(
    *,
    project_dir: str,
    scope: str = ".",
    include_live_enrichment: bool = False,
    external_inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scope_path = _resolve_scope(project_dir, scope)
    findings: list[dict[str, Any]] = []
    manifests = detect_manifests(str(scope_path))

    findings.extend(_scan_python_ast(scope_path))
    findings.extend(_scan_dependency_health(scope_path, include_live_enrichment))
    findings.sort(key=lambda finding: (SEVERITY_ORDER.get(finding["severity"], 99), finding["id"]))

    severity_counts = Counter(finding["severity"] for finding in findings)
    source_counts = Counter(finding["source"] for finding in findings)
    relative_scope = _display_scope(project_dir, scope_path)
    delta = classify_project_changes(project_dir, touched_files=[relative_scope], goal="security check")
    provenance = _build_provenance(
        scope=relative_scope,
        manifests=manifests.manifests,
        findings=findings,
        include_live_enrichment=include_live_enrichment,
        external_inputs=external_inputs or [],
    )
    trust_scores = _build_trust_scores(findings)
    trace = record_trace(
        project_dir,
        trace_type="security-check",
        route="security-check",
        status="ok",
        plan={"scope": relative_scope, "delta_categories": delta["categories"]},
        verify={"finding_count": len(findings)},
        failures=[],
        rejections=[],
    )
    evidence_path = _write_evidence_record(
        project_dir,
        scope=relative_scope,
        findings=findings,
        provenance=provenance,
        trust_scores=trust_scores,
        include_live_enrichment=include_live_enrichment,
    )
    return {
        "schema": "SecurityCheckResult",
        "status": "ok",
        "scope": relative_scope,
        "findings": findings,
        "summary": {
            "finding_count": len(findings),
            "by_severity": dict(sorted(severity_counts.items())),
            "by_source": dict(sorted(source_counts.items())),
            "live_enrichment": include_live_enrichment,
            "scan_status": "completed",
            "manifest_count": len(manifests.manifests),
            "delta_categories": delta["categories"],
        },
        "provenance": provenance,
        "trust_scores": trust_scores,
        "evidence": {"path": evidence_path},
        "trace": {"trace_id": trace["trace_id"], "path": trace["path"]},
    }


def _resolve_scope(project_dir: str, scope: str) -> Path:
    if not scope:
        return Path(project_dir).resolve()
    candidate = Path(scope)
    if candidate.is_absolute():
        return candidate.resolve()
    base = Path(project_dir).resolve()
    resolved = Path(ensure_path_within_dir(base, base / candidate))
    return resolved


def _display_scope(project_dir: str, scope_path: Path) -> str:
    base = Path(project_dir).resolve()
    try:
        return scope_path.relative_to(base).as_posix() or "."
    except ValueError:
        return str(scope_path)


def _scan_python_ast(scope_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for py_file in _iter_python_files(scope_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(_scan_python_file(py_file, source))
    findings.extend(_run_bandit_if_available(scope_path))
    return findings


def _iter_python_files(scope_path: Path) -> list[Path]:
    if scope_path.is_file():
        return [scope_path] if scope_path.suffix == ".py" else []
    if not scope_path.exists():
        return []
    return sorted(path for path in scope_path.rglob("*.py") if path.is_file())


def _scan_python_file(path: Path, source: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            findings.extend(_call_findings(path, node, source))
    return findings


def _call_findings(path: Path, node: ast.Call, source: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    callee = _call_name(node.func)
    if callee in {"subprocess.run", "subprocess.Popen", "os.system"}:
        if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords):
            findings.append(
                _finding(
                    rule_id="B602",
                    source_name="bandit-lite",
                    category="python_ast",
                    severity="high",
                    path=path,
                    line=getattr(node, "lineno", 1),
                    message="subprocess call uses shell=True",
                    recommendation="Avoid shell=True in subprocess calls.",
                    snippet=_source_line(source, getattr(node, "lineno", 1)),
                )
            )
    if callee == "eval":
        findings.append(
            _finding(
                rule_id="B307",
                source_name="bandit-lite",
                category="python_ast",
                severity="high",
                path=path,
                line=getattr(node, "lineno", 1),
                message="eval() detected",
                recommendation="Replace eval with explicit parsing.",
                snippet=_source_line(source, getattr(node, "lineno", 1)),
            )
        )
    if callee == "exec":
        findings.append(
            _finding(
                rule_id="B102",
                source_name="bandit-lite",
                category="python_ast",
                severity="high",
                path=path,
                line=getattr(node, "lineno", 1),
                message="exec() detected",
                recommendation="Replace exec with explicit control flow.",
                snippet=_source_line(source, getattr(node, "lineno", 1)),
            )
        )
    if callee in {"pickle.load", "pickle.loads"}:
        findings.append(
            _finding(
                rule_id="B301",
                source_name="bandit-lite",
                category="python_ast",
                severity="high",
                path=path,
                line=getattr(node, "lineno", 1),
                message="pickle deserialization detected",
                recommendation="Avoid unsafe deserialization of pickle payloads.",
                snippet=_source_line(source, getattr(node, "lineno", 1)),
            )
        )
    return findings


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _source_line(source: str, line: int) -> str:
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def _run_bandit_if_available(scope_path: Path) -> list[dict[str, Any]]:
    if not _command_exists("bandit"):
        return []

    cmd = ["bandit", "-r", str(scope_path), "-f", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    if proc.returncode not in {0, 1}:
        return []
    try:
        import json

        payload = json.loads(proc.stdout or "{}")
    except Exception:
        return []

    findings: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        issue_severity = str(item.get("issue_severity", "LOW")).lower()
        findings.append(
            {
                "id": str(item.get("test_id", "bandit")),
                "source": "bandit",
                "category": "python_ast",
                "severity": "medium" if issue_severity == "medium" else ("critical" if issue_severity == "critical" else issue_severity),
                "exploitability": "unknown",
                "reachability": "unknown",
                "evidence": {
                    "path": str(item.get("filename", "")),
                    "line": int(item.get("line_number", 1)),
                    "snippet": str(item.get("code", "")).strip(),
                },
                "recommendation": str(item.get("more_info", "")) or "Review Bandit finding and remediate.",
                "message": str(item.get("issue_text", "Bandit finding")),
            }
        )
    return findings


def _command_exists(command: str) -> bool:
    from shutil import which

    return which(command) is not None


def _scan_dependency_health(scope_path: Path, include_live_enrichment: bool) -> list[dict[str, Any]]:
    manifests = detect_manifests(str(scope_path))
    dependencies = [
        {
            "name": package.name,
            "version": _normalize_version(package.version),
            "ecosystem": _ecosystem_from_manifest(package.source_manifest),
        }
        for package in manifests.packages
        if package.name
    ]
    if not dependencies or not include_live_enrichment:
        return []

    osv_result = scan_for_cves(dependencies, str(scope_path))
    raw_results = osv_result.get("results", {})
    findings: list[dict[str, Any]] = []
    for dependency in dependencies:
        package_name = dependency["name"]
        for vuln in raw_results.get(package_name, []):
            reachability = analyze_reachability(
                {
                    "package": package_name,
                    "id": vuln.get("id", ""),
                    "summary": vuln.get("summary", ""),
                    "fixed_version": vuln.get("fixed_version", ""),
                },
                str(scope_path),
            )
            findings.append(
                {
                    "id": str(vuln.get("id", "")),
                    "source": "osv",
                    "category": "dependency",
                    "severity": _normalize_severity(str(vuln.get("severity", "unknown"))),
                    "exploitability": "unknown",
                    "reachability": str(reachability.get("reachability", "unknown")).lower(),
                    "evidence": {
                        "package": package_name,
                        "version": dependency["version"],
                        "fixed_version": str(vuln.get("fixed_version", "")),
                        "summary": str(vuln.get("summary", "")),
                    },
                    "recommendation": reachability.get("recommendation", "Upgrade the dependency to a fixed version."),
                    "message": str(vuln.get("summary", "")) or f"Known vulnerability in {package_name}",
                }
            )
    return findings


def _normalize_version(version: str) -> str:
    normalized = (version or "").strip()
    for prefix in ("==", ">=", "<=", "~=", "^", ">"):
        if normalized.startswith(prefix):
            return normalized[len(prefix):].strip()
    return normalized


def _ecosystem_from_manifest(manifest_path: str) -> str:
    suffix = Path(manifest_path).name
    return {
        "package.json": "npm",
        "requirements.txt": "PyPI",
        "pyproject.toml": "PyPI",
        "Cargo.toml": "crates.io",
        "go.mod": "Go",
        "Gemfile": "RubyGems",
    }.get(suffix, "npm")


def _normalize_severity(raw: str) -> str:
    lowered = raw.lower()
    if "critical" in lowered:
        return "critical"
    if "high" in lowered:
        return "high"
    if "medium" in lowered or "moderate" in lowered:
        return "medium"
    if "low" in lowered:
        return "low"
    return "medium"


def _finding(
    *,
    rule_id: str,
    source_name: str,
    category: str,
    severity: str,
    path: Path,
    line: int,
    message: str,
    recommendation: str,
    snippet: str,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "source": source_name,
        "category": category,
        "severity": severity,
        "exploitability": "unknown",
        "reachability": "reachable",
        "evidence": {
            "path": str(path),
            "line": line,
            "snippet": snippet,
        },
        "recommendation": recommendation,
        "message": message,
    }


def _build_provenance(
    *,
    scope: str,
    manifests: list[Any],
    findings: list[dict[str, Any]],
    include_live_enrichment: bool,
    external_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provenance = [
        {
            "source": "bandit-lite",
            "scope": scope,
            "mode": "static",
            "finding_count": len([finding for finding in findings if finding["source"] == "bandit-lite"]),
        },
        {
            "source": "manifest-detector",
            "scope": scope,
            "manifest_count": len(manifests),
            "mode": "live" if include_live_enrichment else "offline",
        },
    ]
    if include_live_enrichment:
        provenance.append(
            {
                "source": "osv",
                "scope": scope,
                "mode": "live-enrichment",
            }
        )
    if external_inputs:
        provenance.append(
            {
                "source": "external-content",
                "scope": scope,
                "mode": "zero-trust",
                "count": len(external_inputs),
            }
        )
    return provenance


def _build_trust_scores(findings: list[dict[str, Any]]) -> dict[str, float]:
    if not findings:
        return {"overall": 1.0}
    weighted = 0.0
    for finding in findings:
        severity = finding.get("severity", "medium")
        weighted += {"critical": 0.4, "high": 0.25, "medium": 0.1, "low": 0.05}.get(str(severity), 0.1)
    overall = max(0.0, round(1.0 - min(weighted, 0.95), 3))
    return {"overall": overall}


def _write_evidence_record(
    project_dir: str,
    *,
    scope: str,
    findings: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
    trust_scores: dict[str, float],
    include_live_enrichment: bool,
) -> str:
    rel_name = f"security-check-{sha256(scope.encode('utf-8')).hexdigest()[:12]}.json"
    rel_path = Path(".omg") / "evidence" / rel_name
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "SecurityCheckEvidence",
        "scope": scope,
        "scan_status": "completed",
        "live_enrichment": include_live_enrichment,
        "findings": findings,
        "provenance": provenance,
        "trust_scores": trust_scores,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return rel_path.as_posix()
