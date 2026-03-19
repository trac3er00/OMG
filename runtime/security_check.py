"""Canonical OMG security check engine."""
from __future__ import annotations

import ast
from collections import Counter
from importlib import import_module
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from hooks.security_validators import ensure_path_within_dir
from plugins.dephealth.cve_scanner import scan_for_cves
from plugins.dephealth.license_checker import check_license_compatibility
from plugins.dephealth.manifest_detector import detect_manifests
from plugins.dephealth.vuln_analyzer import analyze_reachability
from runtime.adoption import CANONICAL_VERSION
from runtime.delta_classifier import classify_project_changes
from runtime.tracebank import record_trace


_SCAN_EXCLUDED_DIRS: frozenset[str] = frozenset({'.git', '.omg', '.sisyphus', 'build', 'dist', 'node_modules', 'tests'})

_SANCTIONED_CALLSITES: dict[tuple[str, str], str] = {
    ("tools/python_repl.py", "B307"): "Intentional eval() in REPL backend (contract: tools/python_repl.py, tests: tests/tools/test_python_repl.py)",
    ("tools/python_repl.py", "B102"): "Intentional exec() in REPL backend (contract: tools/python_repl.py, tests: tests/tools/test_python_repl.py)",
    ("tools/python_sandbox.py", "B307"): "Intentional eval() in sandboxed executor (contract: tools/python_sandbox.py, tests: tests/tools/test_python_sandbox.py)",
    ("tools/python_sandbox.py", "B102"): "Intentional exec() in sandboxed executor (contract: tools/python_sandbox.py, tests: tests/tools/test_python_sandbox.py)",
    ("omg_natives/shell.py", "B602"): "Intentional shell execution in native shell helper (contract: omg_natives/shell.py)",
    ("runtime/release_artifact_audit.py", "B603"): "Subprocess via _run_tool wrapper: argv list, no shell=True, timeout enforced (tests: tests/runtime/test_release_artifact_audit.py)",
}

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

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    ("SEC001", re.compile(r"AKIA[0-9A-Z]{16}"), "high", "AWS access key-like token detected."),
    ("SEC002", re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"), "critical", "Private key material detected."),
    (
        "SEC003",
        re.compile(r"(?i)(?:secret|api[_-]?key|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-\+/=]{12,}['\"]"),
        "high",
        "Hard-coded secret-like credential detected.",
    ),
)

_CONFIG_PATTERNS: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    ("CFG001", re.compile(r"0\.0\.0\.0/0"), "high", "Wildcard ingress rule detected."),
    ("CFG002", re.compile(r"(?i)verify\s*=\s*false"), "high", "TLS verification appears disabled."),
    ("CFG003", re.compile(r"(?i)(?:ssl_verify|verify_ssl)\s*[:=]\s*false"), "high", "TLS verification appears disabled."),
    ("CFG004", re.compile(r"(?i)allow_privilege_escalation\s*[:=]\s*true"), "high", "Privilege escalation enabled in runtime policy."),
    ("CFG005", re.compile(r"(?i)publicly_accessible\s*=\s*true"), "medium", "Publicly accessible infrastructure flag enabled."),
)

_CONFIG_FILE_HINTS = (
    ".tf",
    ".tfvars",
    ".yaml",
    ".yml",
    ".json",
    ".env",
    "dockerfile",
    "kustomization",
    "helm",
    "policy",
    "config",
)

_SBOM_ECOSYSTEM_PURL = {
    "npm": "npm",
    "PyPI": "pypi",
    "crates.io": "cargo",
    "Go": "golang",
    "RubyGems": "gem",
}


def run_security_check(
    *,
    project_dir: str,
    scope: str = ".",
    include_live_enrichment: bool = False,
    external_inputs: list[dict[str, Any]] | None = None,
    waivers: list[dict[str, Any] | str] | None = None,
) -> dict[str, Any]:
    scope_path = _resolve_scope(project_dir, scope)
    findings: list[dict[str, Any]] = []
    manifests = detect_manifests(str(scope_path))
    waiver_map = _normalize_waivers(waivers or [])

    findings.extend(_scan_python_ast(scope_path))
    findings.extend(_scan_secret_patterns(scope_path))
    findings.extend(_scan_config_and_iac(scope_path))
    findings.extend(_scan_dependency_health(scope_path, include_live_enrichment))
    findings = _finalize_findings(findings, waiver_map, project_dir=project_dir)
    findings.sort(key=lambda finding: (SEVERITY_ORDER.get(finding["severity"], 99), finding["id"]))

    severity_counts = Counter(finding["severity"] for finding in findings)
    source_counts = Counter(finding["source"] for finding in findings)
    relative_scope = _display_scope(project_dir, scope_path)
    delta = classify_project_changes(project_dir, touched_files=_delta_touched_files(project_dir, scope_path), goal="security check")
    evidence_requirements = _requirements_for_profile(delta.get("evidence_profile"))
    unresolved_high_risk = [
        finding
        for finding in findings
        if finding.get("severity") in {"critical", "high"} and not finding.get("waived", False)
    ]
    provenance = _build_provenance(
        scope=relative_scope,
        manifests=manifests.manifests,
        findings=findings,
        include_live_enrichment=include_live_enrichment,
        external_inputs=external_inputs or [],
    )
    trust_scores = _build_trust_scores(findings)
    generated_at = datetime.now(timezone.utc).isoformat()
    license_artifact = _build_license_artifact(
        project_dir=project_dir,
        scope_path=scope_path,
        manifests=manifests,
        generated_at=generated_at,
    )
    unresolved_risks = [
        {
            "finding_id": finding.get("finding_id"),
            "id": finding.get("id"),
            "severity": finding.get("severity"),
            "exploitability": finding.get("exploitability", "unknown"),
            "reachability": finding.get("reachability", "unknown"),
            "kev_listed": finding.get("kev_listed", False),
            "epss_score": finding.get("epss_score"),
            "waived": bool(finding.get("waived")),
            "waiver_justification": finding.get("waiver_justification", ""),
            "message": finding.get("message", ""),
        }
        for finding in findings
        if finding.get("severity") in {"critical", "high"}
    ]
    trace = record_trace(
        project_dir,
        trace_type="security-check",
        route="security-check",
        status="error" if unresolved_high_risk else "ok",
        plan={"scope": relative_scope, "delta_categories": delta["categories"]},
        verify={"finding_count": len(findings), "unresolved_high_risk_count": len(unresolved_high_risk)},
        failures=[finding["finding_id"] for finding in unresolved_high_risk],
        rejections=[],
    )
    artifacts = _write_evidence_artifacts(
        project_dir,
        scope=relative_scope,
        generated_at=generated_at,
        findings=findings,
        provenance=provenance,
        trust_scores=trust_scores,
        include_live_enrichment=include_live_enrichment,
        waivers=waivers or [],
        license_artifact=license_artifact,
        manifests=manifests,
        unresolved_risks=unresolved_risks,
    )
    return {
        "schema": "SecurityCheckResult",
        "status": "error" if unresolved_high_risk else "ok",
        "scope": relative_scope,
        "findings": findings,
        "waivers": {
            "requested": len(waivers or []),
            "applied": len([finding for finding in findings if finding.get("waived")]),
        },
        "release_blocked": bool(unresolved_high_risk),
        "unresolved_risks": unresolved_risks,
        "security_scans": [
            {
                "tool": "security-check",
                "path": artifacts["json_path"],
                "sarif_path": artifacts["sarif_path"],
                "sbom_path": artifacts["sbom_path"],
                "license_path": artifacts["license_path"],
                "findings": findings,
            }
        ],
        "summary": {
            "finding_count": len(findings),
            "unresolved_high_risk_count": len(unresolved_high_risk),
            "by_severity": dict(sorted(severity_counts.items())),
            "by_source": dict(sorted(source_counts.items())),
            "live_enrichment": include_live_enrichment,
            "scan_status": "completed",
            "manifest_count": len(manifests.manifests),
            "delta_categories": delta["categories"],
            "delta_evidence_profile": delta.get("evidence_profile"),
            "evidence_requirements": evidence_requirements,
        },
        "evidence_requirements": evidence_requirements,
        "provenance": provenance,
        "trust_scores": trust_scores,
        "license": license_artifact,
        "sbom": _build_sbom_payload(generated_at=generated_at, manifests=manifests),
        "evidence": {
            "path": artifacts["json_path"],
            "json_path": artifacts["json_path"],
            "sarif_path": artifacts["sarif_path"],
            "sbom_path": artifacts["sbom_path"],
            "license_path": artifacts["license_path"],
        },
        "trace": {"trace_id": trace["trace_id"], "path": trace["path"]},
}


def _requirements_for_profile(evidence_profile: str | None) -> list[str]:
    module = import_module("runtime.evidence_requirements")
    resolver = getattr(module, "requirements_for_profile", None)
    if callable(resolver):
        resolved = resolver(evidence_profile)
        if isinstance(resolved, (list, tuple, set)):
            return [str(item) for item in resolved]
    full = getattr(module, "FULL_REQUIREMENTS", [])
    return [str(item) for item in full]


def security_check(
    *,
    project_dir: str,
    scope: str = ".",
    include_live_enrichment: bool = False,
    external_inputs: list[dict[str, Any]] | None = None,
    waivers: list[dict[str, Any] | str] | None = None,
) -> dict[str, Any]:
    return run_security_check(
        project_dir=project_dir,
        scope=scope,
        include_live_enrichment=include_live_enrichment,
        external_inputs=external_inputs,
        waivers=waivers,
    )


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


def _delta_touched_files(project_dir: str, scope_path: Path) -> list[str]:
    base = Path(project_dir).resolve()
    if scope_path.is_file():
        return [_display_scope(project_dir, scope_path)]
    touched: list[str] = []
    for path in sorted(scope_path.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.resolve().relative_to(base).as_posix()
        except ValueError:
            rel = str(path.resolve())
        touched.append(rel)
        if len(touched) >= 64:
            break
    return touched or [_display_scope(project_dir, scope_path)]


def _scan_python_ast(scope_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for py_file in _iter_python_files(scope_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(_scan_python_file(py_file, source))
    findings.extend(_run_bandit_if_available(scope_path))
    findings.extend(_scan_semgrep(scope_path))
    return findings


def run_semgrep_scan(project_dir: str, rules: str = "auto") -> dict[str, Any]:
    unavailable = {"status": "unavailable", "findings": [], "error": "semgrep not found"}
    if shutil.which("semgrep") is None:
        return unavailable

    cmd = ["semgrep", "--json", "--config", rules, project_dir]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    except Exception:
        return unavailable

    if proc.returncode not in {0, 1}:
        return unavailable

    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        return unavailable

    findings: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        start = item.get("start") if isinstance(item.get("start"), dict) else {}
        findings.append(
            {
                "severity": _normalize_semgrep_severity(str(extra.get("severity", "WARNING"))),
                "rule": str(item.get("check_id", "semgrep")),
                "path": str(item.get("path", "")),
                "line": _safe_int(start.get("line", 1), default=1),
                "message": str(extra.get("message", "Semgrep finding")),
            }
        )
    return {"status": "ok", "findings": findings, "error": ""}


def _normalize_semgrep_severity(raw: str) -> str:
    lowered = raw.lower()
    if lowered in {"error", "critical"}:
        return "high"
    if lowered in {"warning", "warn"}:
        return "medium"
    if lowered in {"info", "note", "low"}:
        return "low"
    return _normalize_severity(lowered)


def _scan_semgrep(scope_path: Path) -> list[dict[str, Any]]:
    result = run_semgrep_scan(str(scope_path))
    if result.get("status") != "ok":
        return []

    findings: list[dict[str, Any]] = []
    for item in result.get("findings", []):
        if not isinstance(item, dict):
            continue
        file_path = Path(str(item.get("path", "")))
        findings.append(
            _finding(
                rule_id=str(item.get("rule", "semgrep")),
                source_name="semgrep-ce",
                category="python_ast",
                severity=_normalize_severity(str(item.get("severity", "medium"))),
                path=file_path,
                line=_safe_int(item.get("line", 1), default=1),
                message=str(item.get("message", "Semgrep finding")),
                recommendation="Review Semgrep finding and apply the suggested remediation.",
                snippet="",
            )
        )
    return findings


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scan_secret_patterns(scope_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for candidate in _iter_text_candidates(scope_path):
        try:
            source = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(source.splitlines(), start=1):
            for rule_id, pattern, severity, message in _SECRET_PATTERNS:
                if not pattern.search(line):
                    continue
                findings.append(
                    _finding(
                        rule_id=rule_id,
                        source_name="secret-scan",
                        category="secret",
                        severity=severity,
                        path=candidate,
                        line=line_no,
                        message=message,
                        recommendation="Move secrets to an approved secret manager or environment injection.",
                        snippet=line.strip(),
                    )
                )
    return findings


def _scan_config_and_iac(scope_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for candidate in _iter_text_candidates(scope_path):
        lowered = candidate.name.lower()
        rel_lower = candidate.as_posix().lower()
        if not any(hint in lowered or hint in rel_lower for hint in _CONFIG_FILE_HINTS):
            continue
        try:
            source = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(source.splitlines(), start=1):
            for rule_id, pattern, severity, message in _CONFIG_PATTERNS:
                if not pattern.search(line):
                    continue
                findings.append(
                    _finding(
                        rule_id=rule_id,
                        source_name="config-scan",
                        category="config",
                        severity=severity,
                        path=candidate,
                        line=line_no,
                        message=message,
                        recommendation="Apply least-privilege defaults and tighten network/transport policy.",
                        snippet=line.strip(),
                    )
                )
    return findings


def _iter_text_candidates(scope_path: Path) -> list[Path]:
    if scope_path.is_file():
        return [scope_path]
    if not scope_path.exists():
        return []
    candidates: list[Path] = []
    for path in sorted(scope_path.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 1_000_000:
            continue
        if any(part in _SCAN_EXCLUDED_DIRS for part in path.parts):
            continue
        candidates.append(path)
    return candidates


def _iter_python_files(scope_path: Path) -> list[Path]:
    if scope_path.is_file():
        return [scope_path] if scope_path.suffix == ".py" else []
    if not scope_path.exists():
        return []
    result = []
    for path in sorted(scope_path.rglob("*.py")):
        if not path.is_file():
            continue
        if any(part in _SCAN_EXCLUDED_DIRS for part in path.parts):
            continue
        result.append(path)
    return result


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
    return shutil.which(command) is not None


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
                    "exploitability": _risk_to_exploitability(str(reachability.get("risk_level", ""))),
                    "reachability": _normalize_reachability(str(reachability.get("reachability", "unknown"))),
                    "kev_listed": reachability.get("kev_listed", False),
                    "epss_score": reachability.get("epss_score"),
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


def _risk_to_exploitability(risk_level: str) -> str:
    lowered = risk_level.lower()
    if lowered in {"critical", "high"}:
        return "high"
    if lowered == "medium":
        return "medium"
    if lowered == "low":
        return "low"
    return "unknown"


def _normalize_reachability(raw: str) -> str:
    lowered = raw.lower()
    if lowered in {"reachable", "potentially_reachable", "potentially-reachable"}:
        return "reachable"
    if lowered == "unreachable":
        return "unreachable"
    return "unknown"


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
    exploitability = "high" if severity in {"critical", "high"} else ("medium" if severity == "medium" else "low")
    return {
        "id": rule_id,
        "source": source_name,
        "category": category,
        "severity": severity,
        "exploitability": exploitability,
        "reachability": "reachable",
        "evidence": {
            "path": str(path),
            "line": line,
            "snippet": snippet,
        },
        "recommendation": recommendation,
        "message": message,
    }


def _normalize_waivers(waivers: list[dict[str, Any] | str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for waiver in waivers:
        if isinstance(waiver, str):
            key = waiver.strip()
            if key:
                normalized[key] = "waived"
            continue
        if not isinstance(waiver, dict):
            continue
        target = str(waiver.get("finding_id") or waiver.get("id") or "").strip()
        if not target:
            continue
        justification = str(waiver.get("justification") or waiver.get("reason") or "waived").strip()
        normalized[target] = justification
    return normalized


def _finding_instance_id(finding: dict[str, Any]) -> str:
    evidence = finding.get("evidence", {})
    base = "|".join(
        [
            str(finding.get("id", "")),
            str(evidence.get("path", "")),
            str(evidence.get("line", "")),
            str(finding.get("message", "")),
        ]
    )
    digest = sha256(base.encode("utf-8")).hexdigest()
    return f"{finding.get('id', 'SEC')}-{digest[:12]}"


def _finalize_findings(findings: list[dict[str, Any]], waiver_map: dict[str, str], *, project_dir: str = "") -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    project_root = Path(project_dir).resolve() if project_dir else None
    for finding in findings:
        item = dict(finding)
        item["severity"] = _normalize_severity(str(item.get("severity", "medium")))
        item.setdefault("exploitability", "unknown")
        item.setdefault("reachability", "unknown")
        item["exploitability"] = _normalize_exploitability(str(item.get("exploitability", "unknown")), item)
        item["reachability"] = _normalize_reachability(str(item.get("reachability", "unknown")))
        item["finding_id"] = _finding_instance_id(item)
        sanctioned_justification: str | None = None
        evidence_path = str(item.get("evidence", {}).get("path", ""))
        rule_id = str(item.get("id", ""))
        if evidence_path and rule_id:
            rel_path = evidence_path.replace("\\", "/")
            if project_root is not None:
                try:
                    rel_path = str(Path(evidence_path).resolve().relative_to(project_root))
                except ValueError:
                    pass
            rel_path = rel_path.replace("\\", "/")
            sanctioned_justification = _SANCTIONED_CALLSITES.get((rel_path, rule_id))
        justification = sanctioned_justification or waiver_map.get(item["finding_id"]) or waiver_map.get(str(item.get("id", "")))
        if justification:
            item["waived"] = True
            item["waiver_justification"] = justification
        else:
            item["waived"] = False
        finalized.append(item)
    return finalized


def _normalize_exploitability(raw: str, finding: dict[str, Any]) -> str:
    lowered = raw.lower()
    if lowered in {"high", "medium", "low"}:
        return lowered
    category = str(finding.get("category", "")).lower()
    severity = str(finding.get("severity", "medium")).lower()
    if category in {"secret", "python_ast"}:
        return "high"
    if severity in {"critical", "high"}:
        return "high"
    if severity == "medium":
        return "medium"
    if severity == "low":
        return "low"
    return "unknown"


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


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_sarif_payload(findings: list[dict[str, Any]]) -> dict[str, Any]:
    rules_by_id: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for finding in findings:
        rule_id = str(finding.get("id", "OMG000"))
        if rule_id not in rules_by_id:
            rules_by_id[rule_id] = {
                "id": rule_id,
                "name": str(finding.get("category", "security")),
                "shortDescription": {"text": str(finding.get("message", "Security finding"))},
                "help": {"text": str(finding.get("recommendation", "Review finding and remediate."))},
            }
        evidence = finding.get("evidence", {})
        level = "warning"
        if finding.get("severity") in {"critical", "high"}:
            level = "error"
        elif finding.get("severity") == "low":
            level = "note"
        location = {
            "physicalLocation": {
                "artifactLocation": {"uri": str(evidence.get("path", ""))},
                "region": {"startLine": int(evidence.get("line", 1) or 1)},
            }
        }
        result_payload: dict[str, Any] = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": str(finding.get("message", "Security finding"))},
            "partialFingerprints": {
                "findingId": str(finding.get("finding_id", "")),
            },
            "properties": {
                "severity": str(finding.get("severity", "medium")),
                "exploitability": str(finding.get("exploitability", "unknown")),
                "reachability": str(finding.get("reachability", "unknown")),
                "waived": bool(finding.get("waived", False)),
            },
            "locations": [location],
        }
        if finding.get("waived"):
            result_payload["suppressions"] = [
                {
                    "kind": "inSource",
                    "justification": str(finding.get("waiver_justification", "waived")),
                }
            ]
        results.append(result_payload)

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "omg-security-check",
                        "version": CANONICAL_VERSION,
                        "rules": [rules_by_id[key] for key in sorted(rules_by_id.keys())],
                    }
                },
                "results": results,
            }
        ],
    }


def _build_sbom_payload(*, generated_at: str, manifests: Any) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    for package in manifests.packages:
        version = _normalize_version(package.version)
        ecosystem = _ecosystem_from_manifest(package.source_manifest)
        purl_type = _SBOM_ECOSYSTEM_PURL.get(ecosystem, "generic")
        purl = f"pkg:{purl_type}/{package.name}"
        if version:
            purl = f"{purl}@{version}"
        component = {
            "type": "library",
            "name": package.name,
            "version": version,
            "purl": purl,
        }
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "timestamp": generated_at,
            "tools": [{"vendor": "OMG", "name": "omg-security-check", "version": CANONICAL_VERSION}],
        },
        "components": components,
    }


def _build_license_artifact(*, project_dir: str, scope_path: Path, manifests: Any, generated_at: str) -> dict[str, Any]:
    project_license = _detect_project_license(project_dir=project_dir, scope_path=scope_path)
    dependencies = [{"name": package.name, "license": "UNKNOWN"} for package in manifests.packages]
    compatibility = check_license_compatibility(project_license, dependencies)
    packages_by_license: dict[str, list[str]] = {}
    for dependency in dependencies:
        package_name = str(dependency.get("name", "")).strip()
        if not package_name:
            continue
        spdx_id = str(dependency.get("license", "UNKNOWN") or "UNKNOWN").strip() or "UNKNOWN"
        packages_by_license.setdefault(spdx_id, []).append(package_name)

    licenses = [
        {
            "name": spdx_id,
            "spdx_id": spdx_id,
            "packages": sorted(packages),
        }
        for spdx_id, packages in sorted(packages_by_license.items())
    ]

    if not licenses:
        licenses = [{"name": project_license, "spdx_id": project_license, "packages": []}]

    return {
        "timestamp": generated_at,
        "licenses": licenses,
        "project_license": project_license,
        "compatibility": compatibility,
    }


def _detect_project_license(*, project_dir: str, scope_path: Path) -> str:
    candidates = [scope_path / "package.json", Path(project_dir).resolve() / "package.json"]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("license"), str) and payload["license"].strip():
            return str(payload["license"]).strip()
    if (Path(project_dir).resolve() / "LICENSE").exists() or (Path(project_dir).resolve() / "LICENSE.md").exists():
        return "MIT"
    return "UNKNOWN"


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_evidence_artifacts(
    project_dir: str,
    *,
    scope: str,
    generated_at: str,
    findings: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
    trust_scores: dict[str, float],
    include_live_enrichment: bool,
    waivers: list[dict[str, Any] | str],
    license_artifact: dict[str, Any],
    manifests: Any,
    unresolved_risks: list[dict[str, Any]],
) -> dict[str, str]:
    stamp = _timestamp_slug()
    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    json_rel = Path(".omg") / "evidence" / f"security-{stamp}.json"
    sarif_rel = Path(".omg") / "evidence" / f"security-{stamp}.sarif"
    sbom_rel = Path(".omg") / "evidence" / f"sbom-{stamp}.cdx.json"
    license_rel = Path(".omg") / "evidence" / f"license-{stamp}.json"

    unresolved_high_risk = [
        finding
        for finding in findings
        if finding.get("severity") in {"critical", "high"} and not finding.get("waived", False)
    ]

    payload = {
        "schema": "SecurityCheckEvidence",
        "generated_at": generated_at,
        "scope": scope,
        "scan_status": "completed",
        "live_enrichment": include_live_enrichment,
        "findings": findings,
        "waivers": waivers,
        "unresolved_high_risk": [finding.get("finding_id") for finding in unresolved_high_risk],
        "unresolved_risks": unresolved_risks,
        "security_scans": [
            {
                "tool": "security-check",
                "path": json_rel.as_posix(),
                "findings": findings,
            }
        ],
        "provenance": provenance,
        "trust_scores": trust_scores,
        "artifacts": {
            "sarif_path": sarif_rel.as_posix(),
            "sbom_path": sbom_rel.as_posix(),
            "license_path": license_rel.as_posix(),
        },
    }
    _write_json_file(Path(project_dir) / json_rel, payload)
    _write_json_file(Path(project_dir) / sarif_rel, _build_sarif_payload(findings))
    _write_json_file(Path(project_dir) / sbom_rel, _build_sbom_payload(generated_at=generated_at, manifests=manifests))
    _write_json_file(Path(project_dir) / license_rel, license_artifact)
    return {
        "json_path": json_rel.as_posix(),
        "sarif_path": sarif_rel.as_posix(),
        "sbom_path": sbom_rel.as_posix(),
        "license_path": license_rel.as_posix(),
    }
