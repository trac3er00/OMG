import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.commit_splitter import execute_commit_plan


def _init_repo() -> str:
    repo_dir = tempfile.mkdtemp(prefix="commit-executor-")
    subprocess.run(["git", "init", repo_dir], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", repo_dir, "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", repo_dir, "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
        text=True,
    )

    (Path(repo_dir) / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", repo_dir, "add", "README.md"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", repo_dir, "commit", "-m", "chore(init): bootstrap"],
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_dir


def _write_file(repo_dir: str, rel_path: str, content: str) -> None:
    path = Path(repo_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit_count(repo_dir: str) -> int:
    result = subprocess.run(
        ["git", "-C", repo_dir, "rev-list", "--count", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def _commit_subjects(repo_dir: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", repo_dir, "log", "--pretty=%s"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.strip().splitlines() if line]


def test_execute_commit_plan_success_creates_commits():
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "app.py", "print('app')\n")
        _write_file(repo_dir, "tests/test_app.py", "def test_ok():\n    assert True\n")

        plan = [
            {"files": ["app.py"], "message": "feat(app): add app entrypoint"},
            {"files": ["tests/test_app.py"], "message": "test(app): add smoke test"},
        ]

        result = execute_commit_plan(plan, repo_dir)

        assert result["succeeded"] == [
            "feat(app): add app entrypoint",
            "test(app): add smoke test",
        ]
        assert result["failed"] is None
        assert result["aborted"] == []
        assert _commit_count(repo_dir) == 3
        subjects = _commit_subjects(repo_dir)
        assert "feat(app): add app entrypoint" in subjects
        assert "test(app): add smoke test" in subjects
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_uses_per_group_add_with_listed_files():
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "src/a.py", "a = 1\n")
        _write_file(repo_dir, "src/b.py", "b = 2\n")

        plan = [
            {
                "files": ["src/a.py", "src/b.py"],
                "message": "feat(src): add paired files",
            }
        ]

        execute_commit_plan(plan, repo_dir)

        show = subprocess.run(
            ["git", "-C", repo_dir, "show", "--name-only", "--pretty=format:"],
            check=True,
            capture_output=True,
            text=True,
        )
        changed = {line for line in show.stdout.splitlines() if line}
        assert changed == {"src/a.py", "src/b.py"}
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_runs_quality_gate_before_each_commit(monkeypatch):
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "a.py", "a = 1\n")
        _write_file(repo_dir, "b.py", "b = 2\n")

        calls = []

        def fake_gate(project_dir: str):
            calls.append(project_dir)
            return {"ok": True, "results": []}

        monkeypatch.setattr("tools.commit_splitter._run_quality_gate", fake_gate)

        plan = [
            {"files": ["a.py"], "message": "feat(core): add a"},
            {"files": ["b.py"], "message": "feat(core): add b"},
        ]
        result = execute_commit_plan(plan, repo_dir)

        assert result["failed"] is None
        assert len(calls) == 2
        assert calls == [repo_dir, repo_dir]
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_aborts_on_quality_gate_failure(monkeypatch):
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "a.py", "a = 1\n")
        _write_file(repo_dir, "b.py", "b = 2\n")
        _write_file(repo_dir, "c.py", "c = 3\n")

        gate_calls = {"n": 0}

        def fake_gate(_project_dir: str):
            gate_calls["n"] += 1
            if gate_calls["n"] == 2:
                return {"ok": False, "reason": "tests failed", "step": "test"}
            return {"ok": True, "results": []}

        monkeypatch.setattr("tools.commit_splitter._run_quality_gate", fake_gate)

        plan = [
            {"files": ["a.py"], "message": "feat(core): add a"},
            {"files": ["b.py"], "message": "feat(core): add b"},
            {"files": ["c.py"], "message": "feat(core): add c"},
        ]

        result = execute_commit_plan(plan, repo_dir)

        assert result["succeeded"] == ["feat(core): add a"]
        assert result["failed"]["message"] == "feat(core): add b"
        assert result["failed"]["stage"] == "quality_gate"
        assert result["aborted"] == ["feat(core): add c"]
        assert _commit_count(repo_dir) == 2
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_aborts_when_git_commit_fails():
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "same.py", "v = 1\n")

        plan = [
            {"files": ["same.py"], "message": "feat(core): add same file"},
            {"files": ["same.py"], "message": "fix(core): retry same file"},
        ]

        result = execute_commit_plan(plan, repo_dir)

        assert result["succeeded"] == ["feat(core): add same file"]
        assert result["failed"]["message"] == "fix(core): retry same file"
        assert result["failed"]["stage"] == "git_commit"
        assert result["aborted"] == []
        assert _commit_count(repo_dir) == 2
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_dry_run_does_not_commit(capsys):
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "dry.py", "x = 1\n")
        plan = [{"files": ["dry.py"], "message": "feat(dry): no-op preview"}]

        result = execute_commit_plan(plan, repo_dir, dry_run=True)
        output = capsys.readouterr().out

        assert "[DRY-RUN]" in output
        assert "git add dry.py" in output
        assert "git commit -m feat(dry): no-op preview" in output
        assert result["succeeded"] == []
        assert result["failed"] is None
        assert result["aborted"] == []
        assert _commit_count(repo_dir) == 1
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_validates_plan_shape():
    repo_dir = _init_repo()
    try:
        with pytest.raises(ValueError):
            execute_commit_plan([{"message": "feat(core): missing files"}], repo_dir)
        with pytest.raises(ValueError):
            execute_commit_plan([{"files": ["a.py"]}], repo_dir)
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_uses_argv_only_and_timeout(monkeypatch):
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "x.py", "x = 1\n")
        plan = [{"files": ["x.py"], "message": "feat(x): add x"}]

        recorded = []
        original_run = subprocess.run

        def tracking_run(*args, **kwargs):
            if kwargs.get("cwd") == repo_dir:
                recorded.append((args, kwargs))
                assert kwargs.get("shell") is not True
                assert kwargs.get("timeout") == 60
            return original_run(*args, **kwargs)

        monkeypatch.setattr("tools.commit_splitter.subprocess.run", tracking_run)

        result = execute_commit_plan(plan, repo_dir)

        assert result["failed"] is None
        assert any(item[0][0][:3] == ["git", "-C", repo_dir] for item in recorded)
    finally:
        shutil.rmtree(repo_dir)


def test_execute_commit_plan_reads_quality_gate_config_and_runs_commands():
    repo_dir = _init_repo()
    try:
        _write_file(repo_dir, "ok.py", "x = 1\n")

        quality_dir = Path(repo_dir) / ".omg" / "state"
        quality_dir.mkdir(parents=True, exist_ok=True)
        cfg = {"test": "python3 -m pytest --version"}
        (quality_dir / "quality-gate.json").write_text(json.dumps(cfg), encoding="utf-8")

        plan = [{"files": ["ok.py"], "message": "feat(core): with quality gate"}]
        result = execute_commit_plan(plan, repo_dir)

        assert result["failed"] is None
        assert result["succeeded"] == ["feat(core): with quality gate"]
    finally:
        shutil.rmtree(repo_dir)
