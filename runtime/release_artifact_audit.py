"""Shared release artifact audit helpers."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import requests


def _check_status(ok: bool) -> str:
    return "ok" if ok else "fail"


def check_package_json_version(source_tree: Path, expected: str) -> dict[str, Any]:
    pkg = source_tree / "package.json"
    if not pkg.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        found = data.get("version", "<missing>")
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "found": f"<error: {exc}>", "expected": expected}
    return {"status": _check_status(found == expected), "found": found, "expected": expected}


def check_canonical_version(source_tree: Path, expected: str) -> dict[str, Any]:
    adoption = source_tree / "runtime" / "adoption.py"
    if not adoption.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    try:
        tree = ast.parse(adoption.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            found = node.value.value
                            return {
                                "status": _check_status(found == expected),
                                "found": found,
                                "expected": expected,
                            }
    except (OSError, SyntaxError) as exc:
        return {"status": "fail", "found": f"<error: {exc}>", "expected": expected}
    return {"status": "fail", "found": "<not found>", "expected": expected}


def check_cli_version(source_tree: Path, expected: str) -> dict[str, Any]:
    bin_omg = source_tree / "bin" / "omg"
    if not bin_omg.exists():
        return {"status": "skip", "found": "<bin/omg missing>", "expected": expected}
    try:
        result = subprocess.run(
            ["node", str(bin_omg), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = result.stdout.strip()
        found = output.replace("omg ", "").strip()
        return {"status": _check_status(found == expected), "found": output, "expected": expected}
    except (FileNotFoundError, subprocess.TimeoutExpired, BlockingIOError, OSError):
        return {"status": "skip", "found": "<node not available>", "expected": expected}


def check_changelog_section(source_tree: Path, expected: str) -> dict[str, Any]:
    changelog = source_tree / "CHANGELOG.md"
    if not changelog.exists():
        return {"status": "fail", "details": "CHANGELOG.md not found"}
    content = changelog.read_text(encoding="utf-8")
    header_pattern = re.compile(rf"^## \[?{re.escape(expected)}\]?", re.MULTILINE)
    has_header = bool(header_pattern.search(content))
    marker = f"OMG:GENERATED:changelog-v{expected}"
    has_marker = marker in content
    if has_header and has_marker:
        return {"status": "ok", "details": f"Found header and marker for v{expected}"}
    missing: list[str] = []
    if not has_header:
        missing.append("version header")
    if not has_marker:
        missing.append("generated marker")
    return {"status": "fail", "details": f"Missing: {', '.join(missing)}"}


def check_install_verification_index(source_tree: Path, expected: str) -> dict[str, Any]:
    verification_index = source_tree / "INSTALL-VERIFICATION-INDEX.md"
    if not verification_index.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    content = verification_index.read_text(encoding="utf-8")
    pattern = re.compile(rf"\*?\*?Version:?\*?\*?\s*OMG\s+{re.escape(expected)}")
    if pattern.search(content):
        return {"status": "ok", "found": expected, "expected": expected}
    version_match = re.search(r"\*?\*?Version:?\*?\*?\s*OMG\s+([\d.]+)", content)
    found = version_match.group(1) if version_match else "<not found>"
    return {"status": "fail", "found": found, "expected": expected}


def check_host_list_parity(source_tree: Path) -> dict[str, Any]:
    try:
        from runtime.canonical_surface import get_canonical_hosts, get_compat_hosts
    except ImportError:
        return {"status": "skip", "drift": ["cannot import canonical_surface"]}

    expected_canonical = set(get_canonical_hosts())
    expected_compat = set(get_compat_hosts())
    drift: list[str] = []

    support_matrix = source_tree / "SUPPORT-MATRIX.md"
    if support_matrix.exists():
        content = support_matrix.read_text(encoding="utf-8").lower()
        for host in expected_canonical | expected_compat:
            if host not in content:
                drift.append(f"SUPPORT-MATRIX.md missing host: {host}")

    verification_index = source_tree / "INSTALL-VERIFICATION-INDEX.md"
    if verification_index.exists():
        content = verification_index.read_text(encoding="utf-8").lower()
        for host in expected_canonical | expected_compat:
            if host not in content:
                drift.append(f"INSTALL-VERIFICATION-INDEX.md missing host: {host}")

    return {"status": _check_status(not drift), "drift": drift}


def check_install_path_hygiene(source_tree: Path) -> dict[str, Any]:
    stale: list[str] = []
    docs_to_check = [
        "README.md",
        "INSTALL-VERIFICATION-INDEX.md",
        "QUICK-REFERENCE.md",
    ]
    bare_install_sh = re.compile(r"\binstall\.sh\b")
    for doc_name in docs_to_check:
        doc = source_tree / doc_name
        if not doc.exists():
            continue
        for line_num, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
            if bare_install_sh.search(line) and "OMG-setup.sh" not in line:
                stale.append(f"{doc_name}:{line_num}: bare install.sh reference")

    return {"status": _check_status(not stale), "stale_references": stale}


def check_proof_lane_references(source_tree: Path) -> dict[str, Any]:
    targets = [
        source_tree / "README.md",
        source_tree / "docs" / "proof.md",
    ]
    missing: list[str] = []
    for path in targets:
        if not path.exists():
            missing.append(f"{path.name}:missing")
            continue
        content = path.read_text(encoding="utf-8")
        lowered = content.lower()
        if "music omr" not in lowered or "flagship" not in lowered:
            missing.append(str(path.relative_to(source_tree)))
    return {"status": _check_status(not missing), "missing": missing}


def check_python_docstring_residue(source_tree: Path, expected: str) -> dict[str, Any]:
    blockers: list[str] = []
    version_re = re.compile(r"\b(\d+\.\d+\.\d+)\b")
    for rel_dir in ("scripts", "runtime"):
        base = source_tree / rel_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            doc = ast.get_docstring(tree, clean=False)
            if not doc:
                continue
            for match in version_re.findall(doc):
                if match != expected:
                    blockers.append(f"{path.relative_to(source_tree)}:{match}")
    return {"status": _check_status(not blockers), "blockers": blockers}


def run_source_tree_audit(source_tree: Path, expected_version: str, *, npm_pack: bool = False) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "package_json_version": check_package_json_version(source_tree, expected_version),
        "canonical_version": check_canonical_version(source_tree, expected_version),
        "cli_version_output": check_cli_version(source_tree, expected_version),
        "changelog_section": check_changelog_section(source_tree, expected_version),
        "install_verification_index": check_install_verification_index(source_tree, expected_version),
        "host_list_parity": check_host_list_parity(source_tree),
        "install_path_hygiene": check_install_path_hygiene(source_tree),
        "proof_lane_references": check_proof_lane_references(source_tree),
        "python_docstring_residue": check_python_docstring_residue(source_tree, expected_version),
    }

    blockers = [
        name for name, result in checks.items()
        if result.get("status") == "fail"
    ]

    return {
        "schema": "ArtifactSelfAudit",
        "version_expected": expected_version,
        "source_tree": str(source_tree),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "overall_status": "fail" if blockers else "ok",
        "blockers": blockers,
        "npm_pack": npm_pack,
    }


def format_release_audit_text(report: dict[str, Any]) -> str:
    lines = [
        "Release Artifact Audit",
        f"Repo: {report.get('repo', '')}",
        f"Version: {report.get('version', '')}",
        f"Verdict: {report.get('verdict', report.get('overall_status', 'unknown')).upper()}",
    ]
    checks = report.get("checks", {})
    if isinstance(checks, dict) and checks:
        lines.append("")
        lines.append("CHECK | STATUS")
        for name, result in checks.items():
            status = "unknown"
            if isinstance(result, dict):
                status = str(result.get("status", "unknown"))
            elif isinstance(result, list):
                status = "ok" if not result else "fail"
            else:
                status = str(result)
            lines.append(f"{name} | {status}")

    blockers = report.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        lines.append("")
        lines.append("Actionable diff:")
        for blocker in blockers:
            lines.append(f"- {blocker}")
    return "\n".join(lines)


def run_release_artifact_audit(
    repo_root: Path,
    *,
    repo: str,
    version: str = "",
    apply: bool = False,
    confirm: str = "",
    github_token: str = "",
    session: Any | None = None,
) -> dict[str, Any]:
    expected_version = version.strip() or _detect_canonical_version(repo_root)
    if apply and confirm.strip() != expected_version:
        return {
            "status": "error",
            "error_code": "RELEASE_AUDIT_CONFIRMATION_REQUIRED",
            "message": "Apply mode requires --confirm to match the target version exactly.",
            "repo": repo,
            "version": expected_version,
            "overall_status": "fail",
            "verdict": "FAIL",
            "checks": {},
            "blockers": ["confirmation_missing_or_mismatched"],
        }
    if apply and not github_token.strip():
        return {
            "status": "error",
            "error_code": "GITHUB_TOKEN_MISSING",
            "message": "Apply mode requires a GitHub token.",
            "repo": repo,
            "version": expected_version,
            "overall_status": "fail",
            "verdict": "FAIL",
            "checks": {},
            "blockers": ["github_token_missing"],
        }

    client = session if session is not None else requests
    source_tree = run_source_tree_audit(repo_root, expected_version)
    remote = _collect_remote_release_checks(
        repo=repo,
        version=expected_version,
        github_token=github_token,
        session=client,
    )
    overall_status = "ok"
    blockers = list(source_tree.get("blockers", []))
    blockers.extend(remote.get("blockers", []))
    if str(source_tree.get("overall_status", "fail")) != "ok" or remote.get("status") != "ok":
        overall_status = "fail"
    report = {
        "status": "ok",
        "schema": "ReleaseArtifactAudit",
        "repo": repo,
        "version": expected_version,
        "apply_requested": apply,
        "overall_status": overall_status,
        "verdict": "PASS" if overall_status == "ok" else "FAIL",
        "checks": {
            **cast(dict[str, Any], source_tree.get("checks", {})),
            "github_release_surfaces": remote.get("checks", {}),
        },
        "blockers": blockers,
        "source_tree_audit": source_tree,
        "remote_release_audit": remote,
    }
    if apply and report["overall_status"] != "ok":
        release_body = _load_release_body(repo_root, expected_version)
        asset_paths = _default_release_asset_paths(repo_root, expected_version)
        report["apply"] = apply_release_artifact_remediation(
            repo=repo,
            version=expected_version,
            release_body=release_body,
            asset_paths=asset_paths,
            release=cast(dict[str, Any] | None, remote.get("release")),
            github_token=github_token,
            session=client,
            output_root=repo_root / ".omg" / "release-audit",
        )
    return report


def resolve_github_token() -> str:
    for env_name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = str(os.environ.get(env_name, "")).strip()
        if value:
            return value
    try:
        from runtime.github_integration import get_github_token
    except ImportError:
        return ""
    token_result = get_github_token(env=os.environ)
    if token_result.get("status") == "ok":
        return str(token_result.get("token", "")).strip()
    return ""


def _detect_canonical_version(repo_root: Path) -> str:
    result = check_canonical_version(repo_root, expected="")
    found = str(result.get("found", "")).strip()
    return found if found and not found.startswith("<") else ""


def apply_release_artifact_remediation(
    *,
    repo: str,
    version: str,
    release_body: str,
    asset_paths: list[Path],
    release: dict[str, Any] | None,
    github_token: str,
    session: Any | None,
    output_root: Path,
) -> dict[str, Any]:
    client = session if session is not None else requests
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tag_name = f"v{version}"
    payload = {
        "tag_name": tag_name,
        "name": tag_name,
        "body": release_body,
        "draft": False,
        "prerelease": False,
        "make_latest": "true",
    }
    if release is None:
        response = client.post(
            f"https://api.github.com/repos/{repo}/releases",
            headers=headers,
            json=payload,
            timeout=30,
        )
    else:
        response = client.patch(
            f"https://api.github.com/repos/{repo}/releases/{release['id']}",
            headers=headers,
            json=payload,
            timeout=30,
        )
    if int(getattr(response, "status_code", 0)) >= 400:
        return {
            "status": "error",
            "error_code": "GITHUB_RELEASE_MUTATION_FAILED",
            "http_status": int(getattr(response, "status_code", 0)),
            "message": str(getattr(response, "text", ""))[:300],
        }
    release_payload = response.json()
    upload_url_template = str(release_payload.get("upload_url", ""))
    release_id = int(release_payload.get("id", 0))
    uploaded_assets: list[str] = []
    upload_base = upload_url_template.split("{", 1)[0]
    asset_headers = dict(headers)
    for asset_path in asset_paths:
        if not asset_path.exists():
            continue
        upload_url = f"{upload_base}?{urlencode({'name': asset_path.name})}"
        asset_headers["Content-Type"] = "application/octet-stream"
        upload_response = client.post(
            upload_url,
            headers=asset_headers,
            data=asset_path.read_bytes(),
            timeout=30,
        )
        if int(getattr(upload_response, "status_code", 0)) < 400:
            uploaded_assets.append(asset_path.name)

    rollback_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rollback_dir.mkdir(parents=True, exist_ok=True)
    rollback_path = rollback_dir / "rollback.json"
    rollback_path.write_text(
        json.dumps(
            {
                "repo": repo,
                "version": version,
                "release_id": release_id,
                "uploaded_assets": uploaded_assets,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "status": "ok",
        "release_id": release_id,
        "uploaded_assets": uploaded_assets,
        "rollback_log": str(rollback_path),
        "html_url": str(release_payload.get("html_url", "")),
    }


def _load_release_body(repo_root: Path, version: str) -> str:
    preferred = [
        repo_root / "artifacts" / "release" / f"release-body-v{version}.md",
        repo_root / "artifacts" / "release" / f"tag-body-v{version}.md",
        repo_root / "CHANGELOG.md",
    ]
    for path in preferred:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return f"# Release v{version}\n"


def _default_release_asset_paths(repo_root: Path, version: str) -> list[Path]:
    candidates = [
        repo_root / "artifacts" / "release" / f"release-body-v{version}.md",
        repo_root / "artifacts" / "release" / f"tag-body-v{version}.md",
        repo_root / "artifacts" / "release" / f"release-notes-v{version}.md",
    ]
    return [path for path in candidates if path.exists()]


def _collect_remote_release_checks(
    *,
    repo: str,
    version: str,
    github_token: str,
    session: Any,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    blockers: list[str] = []
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token.strip():
        headers["Authorization"] = f"Bearer {github_token}"

    tag_name = f"v{version}"
    release = None

    release_response = session.get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag_name}",
        headers=headers,
        timeout=20,
    )
    checks["release_by_tag_api"] = {"status": "ok" if release_response.status_code == 200 else "fail"}
    if release_response.status_code == 200:
        release = release_response.json()
    else:
        blockers.append(f"github_release_missing:{tag_name}")

    list_response = session.get(
        f"https://api.github.com/repos/{repo}/releases",
        headers=headers,
        timeout=20,
    )
    list_payload = list_response.json() if list_response.status_code == 200 else []
    latest_tag = ""
    if isinstance(list_payload, list) and list_payload:
        first = list_payload[0]
        if isinstance(first, dict):
            latest_tag = str(first.get("tag_name", "")).strip()
    checks["releases_list_api"] = {
        "status": "ok" if latest_tag == tag_name else "fail",
        "found": latest_tag or "<missing>",
        "expected": tag_name,
    }
    if latest_tag != tag_name:
        blockers.append(f"github_releases_latest:{latest_tag or '<missing>'}:expected:{tag_name}")

    repo_page = session.get(f"https://github.com/{repo}", headers={}, timeout=20)
    repo_page_text = str(getattr(repo_page, "text", ""))
    checks["default_readme_html"] = {
        "status": "ok" if "npx omg env doctor" in repo_page_text else "fail",
    }
    if "npx omg env doctor" not in repo_page_text:
        blockers.append("github_default_readme_missing_launcher_front_door")

    releases_page = session.get(f"https://github.com/{repo}/releases", headers={}, timeout=20)
    releases_page_text = str(getattr(releases_page, "text", ""))
    checks["releases_page_html"] = {
        "status": "ok" if tag_name in releases_page_text and "Latest" in releases_page_text else "fail",
    }
    if tag_name not in releases_page_text or "Latest" not in releases_page_text:
        blockers.append(f"github_releases_page_missing_latest:{tag_name}")

    tag_page = session.get(f"https://github.com/{repo}/releases/tag/{tag_name}", headers={}, timeout=20)
    checks["tag_page_html"] = {"status": "ok" if tag_page.status_code == 200 else "fail"}
    if tag_page.status_code != 200:
        blockers.append(f"github_release_tag_page_missing:{tag_name}")

    return {
        "status": "ok" if not blockers else "fail",
        "checks": checks,
        "blockers": blockers,
        "release": release,
    }
