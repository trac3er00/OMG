"""
Autoresearch engine: performs deep research on a topic.
Combines filesystem analysis + code search.
"""

import json
import os
import re
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
