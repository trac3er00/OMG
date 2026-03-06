"""Tests for ecosystem catalog and sync helpers."""
from __future__ import annotations

import json
from pathlib import Path

from runtime import ecosystem as eco


def test_ecosystem_catalog_contains_requested_targets():
    names = {repo["name"] for repo in eco.list_ecosystem_repos()}
    expected = {
        "omg-superpowers",
        "ralph-wiggum",
        "claude-flow",
        "claude-mem",
        "memsearch",
        "beads",
        "planning-with-files",
        "hooks-mastery",
        "compound-engineering",
    }
    assert expected.issubset(names)


def test_resolve_selection_supports_aliases_and_reports_unknown():
    selected, unknown = eco.resolve_ecosystem_selection(
        ["omg-superpowers", "ralph wiggum", "compounding-engineering", "does-not-exist"]
    )
    selected_names = {repo["name"] for repo in selected}
    assert "omg-superpowers" in selected_names
    assert "ralph-wiggum" in selected_names
    assert "compound-engineering" in selected_names
    assert unknown == ["does-not-exist"]


def test_sync_writes_lock_and_playbooks(tmp_path: Path, monkeypatch):
    def fake_clone_or_update_repo(*, repo, target, update, depth):
        target.mkdir(parents=True, exist_ok=True)
        return {
            "name": repo["name"],
            "repo": repo["repo"],
            "ref": repo.get("ref", "main"),
            "target": str(target),
            "action": "cloned",
            "commit": f"deadbeef-{repo['name']}",
            "branch": "main",
            "sparse_path": repo.get("sparse_path", ""),
        }

    monkeypatch.setattr(eco, "_clone_or_update_repo", fake_clone_or_update_repo)

    out = eco.sync_ecosystem_repos(
        project_dir=str(tmp_path),
        names=["omg-superpowers", "claude-flow", "memsearch"],
        update=False,
    )
    assert out["status"] == "ok"
    assert out["selected"] == ["omg-superpowers", "claude-flow", "memsearch"]
    assert out["unknown"] == []
    assert len(out["entries"]) == 3

    lock_path = tmp_path / eco.DEFAULT_ECOSYSTEM_LOCK_PATH
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["schema"] == eco.ECOSYSTEM_LOCK_SCHEMA
    assert payload["selected_count"] == 3
    assert payload["unknown_count"] == 0

    playbook_dir = tmp_path / eco.DEFAULT_ECOSYSTEM_PLAYBOOK_DIR
    assert (playbook_dir / "omg-superpowers.md").exists()
    assert (playbook_dir / "claude-flow.md").exists()
    assert (playbook_dir / "memsearch.md").exists()


def test_ecosystem_status_reports_installed_state(tmp_path: Path, monkeypatch):
    target = tmp_path / eco.DEFAULT_ECOSYSTEM_REPO_DIR / "omg-superpowers"
    target.mkdir(parents=True, exist_ok=True)

    def fake_run_git(args, *, cwd=None):
        joined = " ".join(args)
        if "rev-parse --abbrev-ref HEAD" in joined:
            return "main"
        if "rev-parse HEAD" in joined:
            return "abc123"
        return ""

    monkeypatch.setattr(eco, "_run_git", fake_run_git)

    status = eco.ecosystem_status(project_dir=str(tmp_path))
    assert status["status"] == "ok"
    repos = {repo["name"]: repo for repo in status["repos"]}
    assert repos["omg-superpowers"]["installed"] is True
    assert repos["omg-superpowers"]["commit"] == "abc123"
    assert repos["omg-superpowers"]["branch"] == "main"
    assert repos["claude-flow"]["installed"] is False
    assert "runtime_context" in status
    assert "host_execution_matrix" in status["runtime_context"]
    assert status["runtime_context"]["provider_host_parity"]["kimi"]["native_host"]["host_mode"] == "kimi_native"
