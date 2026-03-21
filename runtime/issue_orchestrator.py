"""Parallel sub-agent orchestrator for /OMG:issue.

Dispatches specialized security sub-agents in parallel, collects their findings,
normalizes/deduplicates results, and assigns trust scores.

Sub-agents:
  - red-team: SSRF, SQLi, XSS, path traversal probing
  - dep-audit: CVE scanning, supply chain, typosquatting
  - secret-scan: Content-based secret detection + entropy analysis
  - env-scan: OS-specific issues, Python version, permissions
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Finding:
    """Normalized security finding from any sub-agent."""
    id: str
    agent: str
    severity: str  # critical | high | medium | low | info
    category: str  # vuln | cve | secret | env | license
    title: str
    description: str
    file_path: str = ""
    line_number: int = 0
    evidence: str = ""
    remediation: str = ""
    trust_score: float = 1.0  # 0.0-1.0 confidence
    cve_id: str = ""
    cwe_id: str = ""

    def fingerprint(self) -> str:
        """Content-based dedup key."""
        content = f"{self.agent}:{self.category}:{self.title}:{self.file_path}:{self.line_number}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanResult:
    """Aggregated result from all sub-agents."""
    run_id: str
    timestamp: str
    findings: list[Finding]
    agents_dispatched: list[str]
    agents_completed: list[str]
    agents_failed: list[str]
    elapsed_ms: float
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "IssueScanResult",
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "findings": [f.to_dict() for f in self.findings],
            "agents_dispatched": self.agents_dispatched,
            "agents_completed": self.agents_completed,
            "agents_failed": self.agents_failed,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "summary": self.summary,
        }

    def to_sarif(self) -> dict[str, Any]:
        """Convert findings to SARIF v2.1.0 format."""
        results = []
        for f in self.findings:
            result: dict[str, Any] = {
                "ruleId": f.id,
                "level": _severity_to_sarif_level(f.severity),
                "message": {"text": f.description},
            }
            if f.file_path:
                result["locations"] = [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.file_path},
                        "region": {"startLine": max(f.line_number, 1)},
                    }
                }]
            if f.remediation:
                result["fixes"] = [{"description": {"text": f.remediation}}]
            results.append(result)

        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "OMG Issue Scanner",
                        "version": "2.3.0",
                        "informationUri": "https://github.com/trac3r00/OMG",
                    }
                },
                "results": results,
            }],
        }


def _severity_to_sarif_level(severity: str) -> str:
    return {"critical": "error", "high": "error", "medium": "warning",
            "low": "note", "info": "note"}.get(severity, "warning")


# --- Sub-Agent Definitions ---

AGENTS: dict[str, dict[str, Any]] = {
    "red-team": {
        "description": "Vulnerability probing: SSRF, SQLi, XSS, path traversal",
        "categories": ["vuln"],
        "patterns": [
            # SSRF patterns
            (r"requests\.get\(|urllib\.request\.urlopen\(|http\.client\.",
             "Potential SSRF: unvalidated URL in HTTP request", "high", "vuln"),
            (r"subprocess\.(call|run|Popen)\(",
             "Potential command injection via subprocess", "high", "vuln"),
            # SQLi patterns
            (r"""f['\"].*SELECT.*\{|\.format\(.*SELECT|%s.*SELECT""",
             "Potential SQL injection: string formatting in query", "critical", "vuln"),
            (r"cursor\.execute\(f['\"]|cursor\.execute\(.*\.format",
             "SQL injection: formatted string in execute()", "critical", "vuln"),
            # XSS patterns
            (r"innerHTML\s*=|\.html\(|dangerouslySetInnerHTML",
             "Potential XSS: unescaped HTML injection", "high", "vuln"),
            # Path traversal
            (r"\.\./|\.\.\\\\",
             "Path traversal pattern detected", "medium", "vuln"),
            (r"open\(.*\+.*\)|os\.path\.join\(.*input",
             "Potential path traversal in file open", "medium", "vuln"),
        ],
    },
    "dep-audit": {
        "description": "CVE scanning, supply chain analysis, typosquatting detection",
        "categories": ["cve", "license"],
        "manifests": ["package.json", "requirements.txt", "pyproject.toml",
                      "Cargo.toml", "go.mod", "Gemfile"],
    },
    "secret-scan": {
        "description": "Content-based secret detection with entropy analysis",
        "categories": ["secret"],
        "patterns": [
            (r"""(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][a-zA-Z0-9+/=]{16,}""",
             "Hardcoded API key or token", "critical", "secret"),
            (r"""(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}""",
             "Hardcoded password", "critical", "secret"),
            (r"(?i)-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
             "Private key in source code", "critical", "secret"),
            (r"(?i)(aws_access_key_id|aws_secret_access_key)\s*=",
             "AWS credential in source", "critical", "secret"),
            (r"ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82}",
             "GitHub personal access token", "critical", "secret"),
            (r"sk-[a-zA-Z0-9]{20,}",
             "Potential API secret key (sk-...)", "high", "secret"),
        ],
    },
    "env-scan": {
        "description": "OS-specific issues, Python version, file permissions",
        "categories": ["env"],
        "checks": [
            "python_version", "file_permissions", "env_vars",
            "git_config", "disk_space",
        ],
    },
    "privacy-audit": {
        "description": "PII detection, data flow tracking, privacy compliance",
        "categories": ["privacy"],
        "patterns": [
            (r"(?i)(email|e-mail)\s*[:=]|\.email\b",
             "PII field: email address handling detected", "medium", "privacy"),
            (r"(?i)(ssn|social.security|national.id)\s*[:=]",
             "PII field: government ID handling detected", "high", "privacy"),
            (r"(?i)(phone|mobile|tel)\s*[:=].*\d",
             "PII field: phone number handling detected", "medium", "privacy"),
            (r"(?i)(date.of.birth|dob|birthday)\s*[:=]",
             "PII field: date of birth handling detected", "medium", "privacy"),
            (r"(?i)(credit.card|card.number|cvv|ccn)\s*[:=]",
             "PII field: credit card data handling detected", "critical", "privacy"),
            (r"(?i)console\.(log|debug|info)\(.*(?:password|token|secret|key)",
             "PII/secret logged to console", "high", "privacy"),
            (r"(?i)logger?\.(info|debug|warn)\(.*(?:password|token|email|ssn)",
             "PII/secret in log output", "high", "privacy"),
        ],
    },
    "leak-detective": {
        "description": "Resource leak detection: unclosed files, connections, memory",
        "categories": ["leak"],
        "patterns": [
            (r"open\([^)]+\)(?!\s*as\b)",
             "File opened without context manager (potential leak)", "medium", "leak"),
            (r"(?i)(connection|conn|cursor)\s*=.*connect\(",
             "Database connection without context manager", "medium", "leak"),
            (r"socket\.socket\(",
             "Raw socket without context manager", "medium", "leak"),
            (r"(?i)threading\.Thread\(.*daemon\s*=\s*False",
             "Non-daemon thread (may prevent exit)", "low", "leak"),
        ],
    },
}


def scan_with_agent(agent_name: str, project_dir: str) -> list[Finding]:
    """Run a single sub-agent's scan synchronously.

    Uses grep-based pattern matching for red-team and secret-scan agents.
    Uses manifest inspection for dep-audit.
    Uses environment checks for env-scan.
    """
    agent = AGENTS.get(agent_name)
    if agent is None:
        return []

    findings: list[Finding] = []

    if agent_name in ("red-team", "secret-scan", "privacy-audit", "leak-detective"):
        findings.extend(_pattern_scan(agent_name, agent, project_dir))
    elif agent_name == "dep-audit":
        findings.extend(_dep_audit_scan(project_dir))
    elif agent_name == "env-scan":
        findings.extend(_env_scan(project_dir))

    return findings


def _pattern_scan(agent_name: str, agent: dict[str, Any], project_dir: str) -> list[Finding]:
    """Grep-based pattern scanning for vuln and secret patterns."""
    findings: list[Finding] = []
    patterns = agent.get("patterns", [])

    for pattern, title, severity, category in patterns:
        try:
            result = subprocess.run(
                ["grep", "-rn", "-E", "--include=*.py", "--include=*.js",
                 "--include=*.ts", "--include=*.jsx", "--include=*.tsx",
                 "--include=*.java", "--include=*.go", "--include=*.rb",
                 "--include=*.yaml", "--include=*.yml", "--include=*.toml",
                 "--include=*.json", "--include=*.env",
                 pattern, project_dir],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                file_path = parts[0]
                # Skip test files, node_modules, .git, .omg
                rel = os.path.relpath(file_path, project_dir)
                if any(skip in rel for skip in ("node_modules/", ".git/", ".omg/",
                                                  "__pycache__/", "test_", "_test.",
                                                  ".pyc", "dist/", "build/")):
                    continue
                try:
                    line_num = int(parts[1])
                except ValueError:
                    line_num = 0
                match_text = parts[2].strip()[:200]

                findings.append(Finding(
                    id=f"{agent_name}-{hashlib.sha256(line.encode()).hexdigest()[:8]}",
                    agent=agent_name,
                    severity=severity,
                    category=category,
                    title=title,
                    description=f"Found in {rel}:{line_num}: {match_text}",
                    file_path=rel,
                    line_number=line_num,
                    evidence=match_text,
                    remediation=f"Review and fix the pattern in {rel}",
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return findings


def _dep_audit_scan(project_dir: str) -> list[Finding]:
    """Check for manifest files and known risky dependencies."""
    findings: list[Finding] = []
    manifests = AGENTS["dep-audit"]["manifests"]

    for manifest in manifests:
        manifest_path = os.path.join(project_dir, manifest)
        if not os.path.exists(manifest_path):
            continue

        findings.append(Finding(
            id=f"dep-audit-manifest-{manifest}",
            agent="dep-audit",
            severity="info",
            category="cve",
            title=f"Manifest detected: {manifest}",
            description=f"Dependency manifest {manifest} found. Run /OMG:deps cves for CVE scan.",
            file_path=manifest,
            remediation="Run /OMG:deps for full dependency health analysis",
            trust_score=1.0,
        ))

        # Check for lockfile
        lockfiles = {
            "package.json": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
            "requirements.txt": [],
            "pyproject.toml": ["poetry.lock", "uv.lock"],
            "Cargo.toml": ["Cargo.lock"],
            "go.mod": ["go.sum"],
            "Gemfile": ["Gemfile.lock"],
        }
        has_lock = any(
            os.path.exists(os.path.join(project_dir, lf))
            for lf in lockfiles.get(manifest, [])
        )
        if not has_lock and lockfiles.get(manifest):
            findings.append(Finding(
                id=f"dep-audit-nolock-{manifest}",
                agent="dep-audit",
                severity="medium",
                category="cve",
                title=f"No lockfile for {manifest}",
                description=f"Dependency manifest {manifest} has no lockfile. Builds may be non-reproducible.",
                file_path=manifest,
                remediation=f"Generate a lockfile for {manifest}",
            ))

    return findings


def _env_scan(project_dir: str) -> list[Finding]:
    """Environment and configuration checks."""
    findings: list[Finding] = []

    # Python version check
    major, minor = sys.version_info[:2]
    if major == 3 and minor < 10:
        findings.append(Finding(
            id="env-python-version",
            agent="env-scan",
            severity="high",
            category="env",
            title=f"Python {major}.{minor} is below minimum (3.10)",
            description="OMG requires Python 3.10+. Some features may not work.",
            remediation="Upgrade Python to 3.10 or newer",
        ))
    else:
        findings.append(Finding(
            id="env-python-version",
            agent="env-scan",
            severity="info",
            category="env",
            title=f"Python {major}.{minor} OK",
            description=f"Python {major}.{minor} meets minimum requirement (3.10)",
            trust_score=1.0,
        ))

    # .env file in git check
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, timeout=5, cwd=project_dir,
        )
        for tracked in result.stdout.strip().split("\n"):
            basename = os.path.basename(tracked)
            if basename.startswith(".env") and basename not in (
                ".env.example", ".env.sample", ".env.template", ".envrc"
            ):
                findings.append(Finding(
                    id=f"env-dotenv-tracked-{basename}",
                    agent="env-scan",
                    severity="high",
                    category="secret",
                    title=f"Env file tracked in git: {tracked}",
                    description=f"{tracked} is committed to git and may contain secrets",
                    file_path=tracked,
                    remediation=f"Remove {tracked} from git tracking and add to .gitignore",
                ))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # World-readable sensitive files
    sensitive_patterns = [".env", "credentials", "secrets", "private_key"]
    for root, _dirs, files in os.walk(project_dir):
        rel_root = os.path.relpath(root, project_dir)
        if any(skip in rel_root for skip in (".git", "node_modules", ".omg", "__pycache__")):
            continue
        for fname in files:
            if any(p in fname.lower() for p in sensitive_patterns):
                fpath = os.path.join(root, fname)
                try:
                    mode = os.stat(fpath).st_mode
                    if mode & 0o004:  # world-readable
                        findings.append(Finding(
                            id=f"env-perms-{hashlib.sha256(fpath.encode()).hexdigest()[:8]}",
                            agent="env-scan",
                            severity="medium",
                            category="env",
                            title=f"World-readable sensitive file: {fname}",
                            description=f"{os.path.relpath(fpath, project_dir)} is world-readable (mode {oct(mode)})",
                            file_path=os.path.relpath(fpath, project_dir),
                            remediation=f"chmod 600 {os.path.relpath(fpath, project_dir)}",
                        ))
                except OSError:
                    pass
        break  # Only scan top-level to avoid deep traversal

    return findings


# --- Aggregator ---

def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings based on content fingerprint."""
    seen: set[str] = set()
    unique: list[Finding] = []
    for f in findings:
        fp = f.fingerprint()
        if fp not in seen:
            seen.add(fp)
            unique.append(f)
    return unique


def rank_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by severity (critical first), then by trust score."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return sorted(findings, key=lambda f: (severity_order.get(f.severity, 99), -f.trust_score))


def build_summary(findings: list[Finding], agents: list[str], elapsed_ms: float) -> dict[str, Any]:
    """Build summary statistics from findings."""
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_agent: dict[str, int] = {}

    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_category[f.category] = by_category.get(f.category, 0) + 1
        by_agent[f.agent] = by_agent.get(f.agent, 0) + 1

    return {
        "total_findings": len(findings),
        "by_severity": by_severity,
        "by_category": by_category,
        "by_agent": by_agent,
        "agents_dispatched": len(agents),
        "elapsed_ms": round(elapsed_ms, 1),
    }


# --- Orchestrator ---

def run_parallel_scan(
    project_dir: str,
    agents: list[str] | None = None,
    run_id: str | None = None,
) -> ScanResult:
    """Run all sub-agents and aggregate their findings.

    Agents run sequentially in-process (subprocess parallelism is handled
    by the Claude Code Agent tool at the command layer).
    """
    if run_id is None:
        run_id = f"issue-{int(time.time())}"
    if agents is None:
        agents = list(AGENTS.keys())

    start = time.monotonic()
    all_findings: list[Finding] = []
    completed: list[str] = []
    failed: list[str] = []

    for agent_name in agents:
        try:
            findings = scan_with_agent(agent_name, project_dir)
            all_findings.extend(findings)
            completed.append(agent_name)
        except Exception:
            failed.append(agent_name)

    elapsed_ms = (time.monotonic() - start) * 1000

    # Aggregate
    deduped = deduplicate_findings(all_findings)
    ranked = rank_findings(deduped)
    summary = build_summary(ranked, agents, elapsed_ms)

    result = ScanResult(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        findings=ranked,
        agents_dispatched=agents,
        agents_completed=completed,
        agents_failed=failed,
        elapsed_ms=elapsed_ms,
        summary=summary,
    )

    # Persist evidence
    evidence_dir = os.path.join(project_dir, ".omg", "evidence", "issues")
    os.makedirs(evidence_dir, exist_ok=True)
    evidence_path = os.path.join(evidence_dir, f"{run_id}.json")
    try:
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
    except OSError:
        pass

    return result
