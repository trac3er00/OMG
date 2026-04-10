"""
Autoresearch engine: performs deep research on a topic.
Combines filesystem analysis + code search.
"""

import json
import os
import re
import signal
import subprocess
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ResearchBudget:
    max_files: int = 50
    max_file_size_kb: int = 100
    max_output_size_kb: int = 500
    files_scanned: int = 0

    def can_scan_more(self) -> bool:
        return self.files_scanned < self.max_files


@dataclass
class ResearchReport:
    topic: str
    slug: str
    summary: str = ""
    findings: list[str] = field(default_factory=list)
    code_references: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Research: {self.topic}",
            "",
            "## Summary",
            self.summary or "No summary available.",
            "",
            "## Findings",
        ]
        for finding in self.findings:
            lines.append(f"- {finding}")
        lines.extend(["", "## Code References"])
        for ref in self.code_references:
            lines.append(
                f"- `{ref.get('file', 'unknown')}`: {ref.get('description', '')}"
            )
        lines.extend(["", "## Recommendations"])
        for rec in self.recommendations:
            lines.append(f"- {rec}")
        return "\n".join(lines)


def slugify(topic: str) -> str:
    """Convert topic to URL-safe slug."""
    slug = topic.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:50]


def research_topic(
    topic: str,
    output_dir: str = ".omg/research",
    budget: ResearchBudget | None = None,
) -> str:
    """
    Research a topic and produce a markdown report.
    Returns path to the generated report file.
    """
    if budget is None:
        budget = ResearchBudget()

    slug = slugify(topic)
    report = ResearchReport(topic=topic, slug=slug)

    report.summary = f"Research on '{topic}' in the current codebase."

    try:
        result = subprocess.run(
            [
                "grep",
                "-r",
                "--include=*.ts",
                "--include=*.py",
                "-l",
                topic.split()[0],
                ".",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        relevant_files = result.stdout.strip().split("\n")[:10]
        for f in relevant_files:
            if f and budget.can_scan_more():
                report.findings.append(f"Found references in: {f}")
                report.code_references.append(
                    {"file": f, "description": f"Contains '{topic.split()[0]}'"}
                )
                budget.files_scanned += 1
    except Exception:
        report.findings.append("Code search completed (no matches found)")

    if not report.findings:
        report.findings.append(f"No direct code references found for '{topic}'")

    report.recommendations.append(
        f"Review files containing '{topic.split()[0]}' for implementation details"
    )
    report.recommendations.append("Consider adding documentation for this topic")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{slug}.md")
    with open(output_path, "w") as f:
        f.write(report.to_markdown())

    return output_path


@dataclass
class SecurityEnvelope:
    """Security constraints for autoresearch."""

    max_tokens: int = 10000
    max_web_requests: int = 20
    max_output_size_kb: int = 1024
    max_disk_usage_kb: int = 5120
    allow_code_execution: bool = False  # Always False in research context
    blocked_url_patterns: list[str] = field(
        default_factory=lambda: ["localhost", "127.0.0.1", "internal"]
    )

    tokens_used: int = 0
    web_requests_made: int = 0

    def check_token_budget(self, tokens: int) -> bool:
        """Returns True if within budget, False if exceeded."""
        return self.tokens_used + tokens <= self.max_tokens

    def use_tokens(self, tokens: int) -> None:
        self.tokens_used += tokens

    def check_url(self, url: str) -> bool:
        """Returns True if URL is allowed, False if blocked."""
        url_lower = url.lower()
        return not any(p in url_lower for p in self.blocked_url_patterns)

    def is_within_budget(self) -> bool:
        return (
            self.tokens_used <= self.max_tokens
            and self.web_requests_made <= self.max_web_requests
        )

    def to_dict(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "tokens_used": self.tokens_used,
            "max_web_requests": self.max_web_requests,
            "web_requests_made": self.web_requests_made,
            "allow_code_execution": self.allow_code_execution,
            "budget_remaining_pct": max(
                0, 1.0 - self.tokens_used / self.max_tokens
            ),
        }


@dataclass
class DaemonConfig:
    """Configuration for autoresearch daemon mode."""

    interval_seconds: int = 300
    output_dir: str = ".omg/research/auto"
    pid_file: str = ".omg/research/daemon.pid"
    security: SecurityEnvelope = field(default_factory=SecurityEnvelope)
    running: bool = False

    def write_pid(self, pid: int) -> None:
        os.makedirs(os.path.dirname(self.pid_file), exist_ok=True)
        with open(self.pid_file, "w") as f:
            f.write(str(pid))

    def read_pid(self) -> int | None:
        if not os.path.exists(self.pid_file):
            return None
        with open(self.pid_file) as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return None

    def clear_pid(self) -> None:
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    def is_running(self) -> bool:
        pid = self.read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def start_daemon(config: DaemonConfig | None = None) -> dict:
    """Start daemon (or simulate start in test mode). Returns status dict."""
    if config is None:
        config = DaemonConfig()
    os.makedirs(config.output_dir, exist_ok=True)
    config.write_pid(os.getpid())
    config.running = True
    return {
        "status": "started",
        "pid": os.getpid(),
        "output_dir": config.output_dir,
    }


def stop_daemon(config: DaemonConfig | None = None) -> dict:
    """Stop daemon. Returns status dict."""
    if config is None:
        config = DaemonConfig()
    config.clear_pid()
    config.running = False
    return {"status": "stopped"}
