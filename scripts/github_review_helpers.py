#!/usr/bin/env python3
# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runtime.github_review_bot import GitHubReviewBot


REQUIRED_PR_ARTIFACTS = (
    "omg-compat-gap.json",
    "omg-compat-contracts.json",
    "public/.omg/evidence/doctor.json",
    "public/dist/public/manifest.json",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _extract_event(event_payload: dict[str, Any]) -> dict[str, Any]:
    pull_request = event_payload.get("pull_request")
    repository = event_payload.get("repository")
    head_sha = ""
    pr_number: int | None = None
    if isinstance(pull_request, dict):
        head = pull_request.get("head")
        if isinstance(head, dict):
            head_sha = str(head.get("sha", "")).strip()
        raw_number = pull_request.get("number")
        if isinstance(raw_number, int):
            pr_number = raw_number
    repo = ""
    if isinstance(repository, dict):
        repo = str(repository.get("full_name", "")).strip()
    action = str(event_payload.get("action", "")).strip()
    return {
        "action": action,
        "repo": repo,
        "pr_number": pr_number,
        "head_sha": head_sha,
    }


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _find_parity_report(artifacts_root: Path) -> Path | None:
    candidates = sorted((artifacts_root / "public/.omg/evidence").glob("host-parity-*.json"))
    if not candidates:
        return None
    return candidates[-1]


def _check_file(artifacts_root: Path, relpath: str) -> tuple[bool, str]:
    target = artifacts_root / relpath
    return target.exists(), relpath


def build_pr_handoff(event_payload: dict[str, Any], artifacts_root: Path) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    evidence_gaps: list[str] = []
    artifacts: list[str] = []

    identity_ok = True
    for relpath in REQUIRED_PR_ARTIFACTS:
        exists, _ = _check_file(artifacts_root, relpath)
        if exists:
            artifacts.append(relpath)
        else:
            identity_ok = False
            evidence_gaps.append(f"missing artifact: {relpath}")
    checks.append({
        "name": "identity",
        "status": "ok" if identity_ok else "failed",
        "detail": "required compatibility and identity artifacts are present" if identity_ok else "required artifacts missing",
    })

    parity_path = _find_parity_report(artifacts_root)
    parity_ok = False
    parity_detail = "host parity report missing"
    if parity_path is not None:
        artifacts.append(_relative(parity_path, artifacts_root))
        try:
            parity_payload = _read_json(parity_path)
        except Exception as exc:
            parity_detail = f"host parity report invalid: {exc}"
        else:
            parity_results = parity_payload.get("parity_results")
            if isinstance(parity_results, dict) and parity_results.get("passed") is True:
                parity_ok = True
                parity_detail = "host parity report passed"
            else:
                parity_detail = "host parity report indicates drift"

    if not parity_ok:
        evidence_gaps.append(parity_detail)
    checks.append({
        "name": "parity",
        "status": "ok" if parity_ok else "failed",
        "detail": parity_detail,
    })

    verdict = "pass" if identity_ok and parity_ok else "fail"
    event = _extract_event(event_payload)
    return {
        "verdict": verdict,
        "artifacts": sorted(set(artifacts)),
        "checks": checks,
        "evidence_gaps": evidence_gaps,
        "inline_comments": [],
        "event": event,
    }


def build_release_handoff(event_payload: dict[str, Any], artifacts_root: Path) -> dict[str, Any]:
    evidence_path = artifacts_root / ".omg/evidence/release-readiness.json"
    artifacts = [".omg/evidence/release-readiness.json"]
    checks: list[dict[str, str]] = []
    evidence_gaps: list[str] = []
    verdict = "fail"

    if not evidence_path.exists():
        checks.append({
            "name": "release-readiness",
            "status": "failed",
            "detail": "release-readiness evidence missing",
        })
        evidence_gaps.append("release-readiness evidence missing")
    else:
        payload = _read_json(evidence_path)
        status = str(payload.get("status", "")).strip().lower()
        ok = status == "ok"
        checks.append({
            "name": "release-readiness",
            "status": "ok" if ok else "failed",
            "detail": f"release readiness status={status or 'unknown'}",
        })
        verdict = "pass" if ok else "fail"
        if not ok:
            evidence_gaps.append("release-readiness status is not ok")

    return {
        "verdict": verdict,
        "artifacts": artifacts,
        "checks": checks,
        "evidence_gaps": evidence_gaps,
        "inline_comments": [],
        "event": _extract_event(event_payload),
    }


def assert_pass(review_payload: dict[str, Any]) -> None:
    verdict = str(review_payload.get("verdict", review_payload.get("status", ""))).strip().lower()
    if verdict in {"ok", "pass", "passed", "success", "approved"}:
        return
    gaps = review_payload.get("evidence_gaps")
    if isinstance(gaps, list) and gaps:
        detail = "; ".join(str(item) for item in gaps)
    else:
        detail = "no evidence gap detail provided"
    raise SystemExit(f"fast blockers failed: {detail}")


def post_review(event_payload: dict[str, Any], review_payload: dict[str, Any]) -> dict[str, Any]:
    bot = GitHubReviewBot()
    return bot.process_pull_request_event(event_payload, review_payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and post GitHub PR review handoff artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_pr = subparsers.add_parser("build-pr-handoff", help="Create a PR review handoff artifact from CI artifacts.")
    build_pr.add_argument("--event-path", required=True)
    build_pr.add_argument("--artifacts-root", required=True)
    build_pr.add_argument("--output", required=True)

    build_release = subparsers.add_parser("build-release-handoff", help="Create a release-review handoff artifact.")
    build_release.add_argument("--event-path", required=True)
    build_release.add_argument("--artifacts-root", required=True)
    build_release.add_argument("--output", required=True)

    assert_cmd = subparsers.add_parser("assert-pass", help="Fail if handoff verdict is not pass.")
    assert_cmd.add_argument("--input", required=True)

    post = subparsers.add_parser("post-review", help="Use configured GitHub auth and post PR review/check run.")
    post.add_argument("--event-path", required=True)
    post.add_argument("--input", required=True)
    post.add_argument("--output", required=True)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.command == "build-pr-handoff":
        event_payload = _read_json(Path(args.event_path))
        handoff = build_pr_handoff(event_payload, Path(args.artifacts_root))
        _write_json(Path(args.output), handoff)
        return 0

    if args.command == "build-release-handoff":
        event_payload = _read_json(Path(args.event_path))
        handoff = build_release_handoff(event_payload, Path(args.artifacts_root))
        _write_json(Path(args.output), handoff)
        return 0

    if args.command == "assert-pass":
        payload = _read_json(Path(args.input))
        assert_pass(payload)
        return 0

    if args.command == "post-review":
        event_payload = _read_json(Path(args.event_path))
        payload = _read_json(Path(args.input))
        result = post_review(event_payload, payload)
        _write_json(Path(args.output), result)
        if str(result.get("status", "")).strip().lower() != "ok":
            raise SystemExit(json.dumps(result, ensure_ascii=True))
        return 0

    raise SystemExit("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
