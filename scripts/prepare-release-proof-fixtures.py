#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prepare_release_proof_fixtures(output_root: Path) -> None:
    trace_id = "trace-1"
    eval_id = "eval-1"

    junit_path = output_root / ".omg" / "evidence" / "junit.xml"
    coverage_path = output_root / ".omg" / "evidence" / "coverage.xml"
    sarif_path = output_root / ".omg" / "evidence" / "results.sarif"
    browser_trace_path = output_root / ".omg" / "evidence" / "browser_trace.json"
    lineage_path = output_root / ".omg" / "lineage" / "lineage-1.json"
    eval_path = output_root / ".omg" / "evals" / "latest.json"
    security_path = output_root / ".omg" / "evidence" / "security-check.json"
    evidence_path = output_root / ".omg" / "evidence" / "run-1.json"
    tracebank_path = output_root / ".omg" / "tracebank" / "events.jsonl"

    _write_text(
        junit_path,
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="release-proof" tests="1" failures="0" errors="0">
    <testcase classname="release" name="standalone_ready" time="0.01" />
  </testsuite>
</testsuites>
""",
    )
    _write_text(
        coverage_path,
        """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1.0" branch-rate="1.0" version="1.0" />
""",
    )
    _write_json(
        sarif_path,
        {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "release-proof"}}, "results": []}],
        },
    )
    _write_json(
        browser_trace_path,
        {
            "trace": {"name": "browser-smoke"},
            "events": [{"type": "navigation", "url": "https://example.test"}],
        },
    )
    _write_json(
        lineage_path,
        {
            "schema": "LineageRecord",
            "trace_id": trace_id,
            "path": ".omg/lineage/lineage-1.json",
        },
    )
    _write_json(
        eval_path,
        {
            "schema": "EvalGateResult",
            "eval_id": eval_id,
            "trace_id": trace_id,
            "lineage": {"trace_id": trace_id, "path": ".omg/lineage/lineage-1.json"},
            "timestamp": "2026-03-07T00:00:00Z",
            "executor": {"user": "release-bot", "pid": 1},
            "environment": {"hostname": "localhost", "platform": "linux"},
            "status": "ok",
            "summary": {"regressed": False},
        },
    )
    _write_json(
        security_path,
        {
            "schema": "SecurityCheckResult",
            "status": "ok",
            "evidence": {"sarif_path": ".omg/evidence/results.sarif"},
        },
    )
    _write_json(
        evidence_path,
        {
            "schema": "EvidencePack",
            "run_id": "run-1",
            "timestamp": "2026-03-07T00:00:00Z",
            "executor": {"user": "release-bot", "pid": 1},
            "environment": {"hostname": "localhost", "platform": "linux"},
            "tests": [{"name": "release_readiness", "passed": True}],
            "security_scans": [{"tool": "security-check", "path": ".omg/evidence/security-check.json"}],
            "diff_summary": {"files": 1},
            "reproducibility": {"cmd": "python3 scripts/omg.py release readiness --channel dual"},
            "unresolved_risks": [],
            "provenance": [{"source": "release-proof"}],
            "trust_scores": {"overall": 1.0},
            "claims": [
                {
                    "claim_type": "release_ready",
                    "artifacts": [
                        "junit.xml",
                        "coverage.xml",
                        "results.sarif",
                        "browser_trace.json",
                    ],
                    "trace_ids": [trace_id],
                }
            ],
            "trace_ids": [trace_id],
            "lineage": {"trace_id": trace_id, "path": ".omg/lineage/lineage-1.json"},
            "test_delta": {"override": {"approved_by": "release-bot"}},
        },
    )
    tracebank_path.parent.mkdir(parents=True, exist_ok=True)
    tracebank_path.write_text(
        json.dumps(
            {
                "schema": "TracebankRecord",
                "trace_id": trace_id,
                "timestamp": "2026-03-07T00:00:00Z",
                "executor": {"user": "release-bot", "pid": 1},
                "environment": {"hostname": "localhost", "platform": "linux"},
                "path": ".omg/tracebank/events.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Write deterministic proof fixtures for release readiness.")
    parser.add_argument("--output-root", default=".", help="Root directory that should receive the .omg fixture tree.")
    args = parser.parse_args()
    prepare_release_proof_fixtures(Path(args.output_root).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
