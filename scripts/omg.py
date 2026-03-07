#!/usr/bin/env python3
"""OMG 2.0.2 CLI entrypoint.

Implements practical command-line flows for:
- omg ship
- omg fix --issue
- omg secure
- omg maintainer
- omg trust review
- omg runtime dispatch
- omg lab train / omg lab eval
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

# --- Path resolution (never relies on CWD) ---
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = Path(SCRIPTS_DIR).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from hooks.policy_engine import evaluate_bash_command
from hooks.shadow_manager import create_evidence_pack
from hooks.trust_review import review_config_change, write_trust_manifest
from lab.pipeline import publish_artifact, run_pipeline
from runtime.dispatcher import dispatch_runtime
from runtime.compat import (
    DEFAULT_CONTRACT_SNAPSHOT_PATH,
    DEFAULT_GAP_REPORT_PATH,
    build_contract_snapshot_payload,
    build_compat_gap_report,
    dispatch_compat_skill,
    get_compat_skill_contract,
    list_compat_skill_contracts,
    list_compat_skills,
)
from runtime.adoption import CANONICAL_VERSION
from runtime.ecosystem import ecosystem_status, list_ecosystem_repos, sync_ecosystem_repos
from runtime.team_router import TeamDispatchRequest, dispatch_team, execute_ccg_mode, execute_crazy_mode


def _now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _parse_simple_idea_yaml(path: str) -> dict[str, Any]:
    """Minimal parser for `.omg/idea.yml` template shape."""
    idea: dict[str, Any] = {
        "goal": "",
        "constraints": [],
        "acceptance": [],
        "risk": {"security": [], "performance": [], "compatibility": []},
        "evidence_required": {"tests": [], "security_scans": [], "reproducibility": [], "artifacts": []},
    }
    section: str | None = None
    subsection: str | None = None

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("goal:"):
                idea["goal"] = stripped.split(":", 1)[1].strip().strip("\"'")
                section = None
                subsection = None
                continue

            if stripped in {"constraints:", "acceptance:", "risk:", "evidence_required:"}:
                section = stripped[:-1]
                subsection = None
                continue

            if section in {"risk", "evidence_required"} and stripped.endswith(":") and not stripped.startswith("- "):
                subsection = stripped[:-1]
                continue

            if stripped.startswith("- "):
                value = stripped[2:].strip().strip("\"'")
                if section in {"constraints", "acceptance"}:
                    idea[section].append(value)
                elif section in {"risk", "evidence_required"} and subsection:
                    idea[section].setdefault(subsection, []).append(value)

    return idea


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return data


def _ensure_project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def cmd_ship(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    idea_path = args.idea
    idea = _parse_simple_idea_yaml(idea_path) if idea_path.endswith((".yml", ".yaml")) else _load_json(idea_path)

    runtime = args.runtime
    dispatched = dispatch_runtime(runtime, idea)
    if dispatched.get("status") != "ok":
        print(json.dumps(dispatched, indent=2))
        return 2

    run_id = args.run_id or _now_run_id()
    verification = dispatched.get("verification", {})
    checks = verification.get("checks", []) if isinstance(verification, dict) else []
    evidence_path = create_evidence_pack(
        project_dir,
        run_id,
        tests=checks if isinstance(checks, list) else [],
        security_scans=[],
        diff_summary={"runtime": runtime, "goal": idea.get("goal", "")},
        reproducibility={"command": f"omg ship --runtime {runtime} --idea {idea_path}"},
        unresolved_risks=[],
    )

    out = {
        "status": "ok",
        "command": "ship",
        "runtime": runtime,
        "run_id": run_id,
        "goal": idea.get("goal", ""),
        "evidence_path": os.path.relpath(evidence_path, project_dir),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    goal = f"Fix issue {args.issue}"
    dispatched = dispatch_runtime(args.runtime, {"goal": goal, "acceptance": [f"issue-{args.issue}-resolved"]})
    print(json.dumps(dispatched, indent=2))
    return 0 if dispatched.get("status") == "ok" else 2


def cmd_secure(args: argparse.Namespace) -> int:
    decision = evaluate_bash_command(args.command)
    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.action != "deny" else 3


def cmd_maintainer(args: argparse.Namespace) -> int:
    project_dir = _ensure_project_dir()
    out_dir = Path(project_dir) / ".omg" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "oss-impact.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "activity": {"commits": "unverified", "reviews": "unverified", "releases": "unverified"},
        "dependents": {"direct": "unverified", "transitive": "unverified"},
        "adoption_signals": {"downloads": "unverified", "stars": "unverified"},
        "summary_500_words": "",
        "integrity": {"metric_manipulation": "forbidden"},
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(out_file)}, indent=2))
    return 0


def cmd_trust_review(args: argparse.Namespace) -> int:
    old_cfg = _load_json(args.old)
    new_cfg = _load_json(args.new)
    review = review_config_change(args.file, old_cfg, new_cfg)
    manifest = write_trust_manifest(_ensure_project_dir(), review)
    print(json.dumps({"review": review, "manifest": manifest}, indent=2))
    return 0


def cmd_runtime_dispatch(args: argparse.Namespace) -> int:
    if args.idea_json:
        idea = json.loads(args.idea_json)
    elif args.idea:
        idea = _load_json(args.idea)
    else:
        idea = {"goal": "unspecified"}
    result = dispatch_runtime(args.runtime, idea)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_lab_train(args: argparse.Namespace) -> int:
    job = json.loads(args.job_json) if args.job_json else _load_json(args.job)
    result = run_pipeline(job)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"ready", "failed_evaluation"} else 2


def cmd_lab_eval(args: argparse.Namespace) -> int:
    result = json.loads(args.result_json) if args.result_json else _load_json(args.result)
    out = publish_artifact(result)
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") == "published" else 2


def cmd_teams(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    req = TeamDispatchRequest(
        target=args.target,
        problem=args.problem,
        context=args.context,
        files=files,
        expected_outcome=args.expected_outcome,
    )
    result = dispatch_team(req).to_dict()
    print(json.dumps(result, indent=2))
    return 0


def cmd_ccg(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = execute_ccg_mode(
        problem=args.problem,
        project_dir=_ensure_project_dir(),
        context=args.context,
        files=files,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_crazy(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = execute_crazy_mode(
        problem=args.problem,
        project_dir=_ensure_project_dir(),
        context=args.context,
        files=files,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_compat_list(args: argparse.Namespace) -> int:
    skills = list_compat_skills()
    print(json.dumps({"status": "ok", "count": len(skills), "skills": skills}, indent=2))
    return 0


def cmd_compat_contract(args: argparse.Namespace) -> int:
    if args.all:
        contracts = list_compat_skill_contracts()
        print(json.dumps({"status": "ok", "count": len(contracts), "contracts": contracts}, indent=2))
        return 0
    if not args.skill:
        print(json.dumps({"status": "error", "message": "Provide --skill or --all"}, indent=2))
        return 2
    contract = get_compat_skill_contract(args.skill)
    if not contract:
        print(json.dumps({"status": "error", "message": f"Unknown skill: {args.skill}"}, indent=2))
        return 2
    print(json.dumps({"status": "ok", "contract": contract}, indent=2))
    return 0


def cmd_compat_gap_report(args: argparse.Namespace) -> int:
    report = build_compat_gap_report(_ensure_project_dir())
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(json.dumps({"status": "ok", "report": report}, indent=2))
    return 0


def cmd_compat_snapshot(args: argparse.Namespace) -> int:
    payload = build_contract_snapshot_payload(include_generated_at=True)
    out_path = args.output or DEFAULT_CONTRACT_SNAPSHOT_PATH
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps({"status": "ok", "output": out_path, "count": payload["count"]}, indent=2))
    return 0


def cmd_compat_gate(args: argparse.Namespace) -> int:
    report = build_compat_gap_report(_ensure_project_dir())
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    bridge_count = int(report.get("maturity_counts", {}).get("bridge", 0))
    if bridge_count > args.max_bridge:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"OMG compat gate failed: bridge={bridge_count} > max_bridge={args.max_bridge}",
                    "report": report,
                },
                indent=2,
            )
        )
        return 3
    print(
        json.dumps(
            {
                "status": "ok",
                "message": f"OMG compat gate passed: bridge={bridge_count} <= max_bridge={args.max_bridge}",
                "report": report,
            },
            indent=2,
        )
    )
    return 0


def cmd_compat_run(args: argparse.Namespace) -> int:
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else []
    result = dispatch_compat_skill(
        skill=args.skill,
        problem=args.problem,
        context=args.context,
        files=files,
        expected_outcome=args.expected_outcome,
        project_dir=_ensure_project_dir(),
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def cmd_ecosystem_list(args: argparse.Namespace) -> int:
    repos = list_ecosystem_repos()
    print(json.dumps({"status": "ok", "count": len(repos), "repos": repos}, indent=2))
    return 0


def cmd_ecosystem_status(args: argparse.Namespace) -> int:
    result = ecosystem_status(project_dir=_ensure_project_dir())
    print(json.dumps(result, indent=2))
    return 0


def cmd_ecosystem_sync(args: argparse.Namespace) -> int:
    names = [name.strip() for name in args.names.split(",") if name.strip()] if args.names else []
    result = sync_ecosystem_repos(
        project_dir=_ensure_project_dir(),
        names=names,
        update=bool(args.update),
        depth=int(args.depth),
    )
    print(json.dumps(result, indent=2))
    errors = [entry for entry in result.get("entries", []) if entry.get("status") == "error"]
    return 0 if not errors else 2


def _add_compat_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    compat_sub = parent.add_subparsers(dest=dest, required=True)
    compat_list = compat_sub.add_parser("list", help="List supported legacy skill names")
    compat_list.set_defaults(func=cmd_compat_list)
    compat_contract = compat_sub.add_parser("contract", help="Show skill contract schema")
    compat_contract.add_argument("--skill", default="")
    compat_contract.add_argument("--all", action="store_true")
    compat_contract.set_defaults(func=cmd_compat_contract)
    compat_gap = compat_sub.add_parser("gap-report", help="Write compatibility maturity report")
    compat_gap.add_argument("--output", default=DEFAULT_GAP_REPORT_PATH)
    compat_gap.set_defaults(func=cmd_compat_gap_report)
    compat_snapshot = compat_sub.add_parser("snapshot", help="Write current skill contracts snapshot")
    compat_snapshot.add_argument("--output", default=DEFAULT_CONTRACT_SNAPSHOT_PATH)
    compat_snapshot.set_defaults(func=cmd_compat_snapshot)
    compat_gate = compat_sub.add_parser("gate", help="Fail if bridge skill count exceeds threshold")
    compat_gate.add_argument("--max-bridge", type=int, default=0)
    compat_gate.add_argument("--output", default=DEFAULT_GAP_REPORT_PATH)
    compat_gate.set_defaults(func=cmd_compat_gate)
    compat_run = compat_sub.add_parser("run", help="Run a legacy skill through OMG router")
    compat_run.add_argument("--skill", required=True)
    compat_run.add_argument("--problem", default="")
    compat_run.add_argument("--context", default="")
    compat_run.add_argument("--files", default="")
    compat_run.add_argument("--expected-outcome", default="")
    compat_run.set_defaults(func=cmd_compat_run)


def _add_ecosystem_subcommands(parent: argparse.ArgumentParser, *, dest: str) -> None:
    ecosystem_sub = parent.add_subparsers(dest=dest, required=True)
    ecosystem_list = ecosystem_sub.add_parser("list", help="List OMG ecosystem integration targets")
    ecosystem_list.set_defaults(func=cmd_ecosystem_list)

    ecosystem_status_cmd = ecosystem_sub.add_parser("status", help="Show current ecosystem install status")
    ecosystem_status_cmd.set_defaults(func=cmd_ecosystem_status)

    ecosystem_sync = ecosystem_sub.add_parser("sync", help="Clone or refresh ecosystem repositories")
    ecosystem_sync.add_argument("--names", default="", help="Comma-separated repo names or aliases")
    ecosystem_sync.add_argument("--update", action="store_true", help="Fetch latest refs for existing clones")
    ecosystem_sync.add_argument("--depth", type=int, default=1, help="Git depth for shallow clone/fetch")
    ecosystem_sync.set_defaults(func=cmd_ecosystem_sync)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omg", description=f"OMG {CANONICAL_VERSION} CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ship = sub.add_parser("ship", help="Idea -> Evidence -> PR flow")
    ship.add_argument("--idea", default=".omg/idea.yml")
    ship.add_argument("--runtime", default="claude", choices=["claude", "gpt", "local"])
    ship.add_argument("--run-id", default="")
    ship.set_defaults(func=cmd_ship)

    fix = sub.add_parser("fix", help="Issue-driven fix flow")
    fix.add_argument("--issue", required=True)
    fix.add_argument("--runtime", default="claude", choices=["claude", "gpt", "local"])
    fix.set_defaults(func=cmd_fix)

    secure = sub.add_parser("secure", help="Evaluate command risk")
    secure.add_argument("--command", required=True)
    secure.set_defaults(func=cmd_secure)

    maintainer = sub.add_parser("maintainer", help="OSS maintainer evidence helper")
    maintainer.add_argument("--mode", default="impact", choices=["triage", "release", "review", "impact"])
    maintainer.set_defaults(func=cmd_maintainer)

    trust = sub.add_parser("trust", help="Trust review operations")
    trust_sub = trust.add_subparsers(dest="trust_command", required=True)
    trust_review = trust_sub.add_parser("review", help="Review config change")
    trust_review.add_argument("--file", default="settings.json")
    trust_review.add_argument("--old", required=True, help="Path to old config json")
    trust_review.add_argument("--new", required=True, help="Path to new config json")
    trust_review.set_defaults(func=cmd_trust_review)

    runtime = sub.add_parser("runtime", help="Runtime operations")
    runtime_sub = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_dispatch = runtime_sub.add_parser("dispatch", help="Dispatch runtime job")
    runtime_dispatch.add_argument("--runtime", required=True, choices=["claude", "gpt", "local"])
    runtime_dispatch.add_argument("--idea", default="", help="Path to idea json")
    runtime_dispatch.add_argument("--idea-json", default="", help="Inline idea json")
    runtime_dispatch.set_defaults(func=cmd_runtime_dispatch)

    lab = sub.add_parser("lab", help="Lab pipeline operations")
    lab_sub = lab.add_subparsers(dest="lab_command", required=True)
    lab_train = lab_sub.add_parser("train", help="Run lab pipeline job")
    lab_train.add_argument("--job", default="", help="Path to job json")
    lab_train.add_argument("--job-json", default="", help="Inline job json")
    lab_train.set_defaults(func=cmd_lab_train)
    lab_eval = lab_sub.add_parser("eval", help="Publish lab result when eligible")
    lab_eval.add_argument("--result", default="", help="Path to result json")
    lab_eval.add_argument("--result-json", default="", help="Inline result json")
    lab_eval.set_defaults(func=cmd_lab_eval)

    teams = sub.add_parser("teams", help="Internal OMG team routing")
    teams.add_argument("--target", default="auto", choices=["auto", "codex", "gemini", "ccg"])
    teams.add_argument("--problem", required=True)
    teams.add_argument("--context", default="")
    teams.add_argument("--files", default="")
    teams.add_argument("--expected-outcome", default="")
    teams.set_defaults(func=cmd_teams)

    ccg = sub.add_parser("ccg", help="OMG CCG (tri-track) routing")
    ccg.add_argument("--problem", required=True)
    ccg.add_argument("--context", default="")
    ccg.add_argument("--files", default="")
    ccg.add_argument("--expected-outcome", default="")
    ccg.set_defaults(func=cmd_ccg)

    crazy = sub.add_parser("crazy", help="OMG CRAZY mode - parallel multi-agent orchestration")
    crazy.add_argument("--problem", required=True, help="Task description")
    crazy.add_argument("--context", default="", help="Additional context")
    crazy.add_argument("--files", default="", help="Comma-separated focus files")
    crazy.set_defaults(func=cmd_crazy)

    compat = sub.add_parser("compat", help="OMG legacy compatibility bridge")
    _add_compat_subcommands(compat, dest="compat_command")

    omc = sub.add_parser("omc", help="Alias of `compat` for legacy scripts")
    _add_compat_subcommands(omc, dest="omc_command")

    ecosystem = sub.add_parser("ecosystem", help="Upstream ecosystem sync and status")
    _add_ecosystem_subcommands(ecosystem, dest="ecosystem_command")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
