# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportMissingTypeArgument=false, reportMissingParameterType=false, reportUnusedCallResult=false, reportDeprecated=false, reportUnusedFunction=false, reportPrivateUsage=false
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Generator, Protocol, cast
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hooks._common as _common
import hooks._cost_ledger as _cost_ledger
import hooks._token_counter as _token_counter
import hooks.branch_manager as branch_manager
import hooks.post_write as post_write
import hooks.query as query
import hooks.secret_audit as secret_audit
import plugins.dephealth.cve_scanner as cve_scanner
import plugins.dephealth.manifest_detector as manifest_detector
import plugins.viz.graph_builder as graph_builder


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload: dict = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _RequestWithData(Protocol):
    data: bytes


@pytest.fixture(autouse=True)
def _reset_feature_cache() -> Generator[None, None, None]:
    importlib.reload(_common)
    yield
    importlib.reload(_common)


def test_cost_tracking_records_git_workflow_event(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_COST_TRACKING_ENABLED", "1")
    monkeypatch.setenv("OMG_GIT_WORKFLOW_ENABLED", "1")

    def _mock_run(args, capture_output=True, text=True, timeout=5):
        del capture_output, text, timeout
        cmd = " ".join(args)
        if "--git-dir" in cmd:
            return Mock(returncode=0, stdout=".git\n")
        if "--abbrev-ref" in cmd:
            return Mock(returncode=0, stdout="main\n")
        return Mock(returncode=1, stdout="")

    with patch("hooks.branch_manager.subprocess.run", side_effect=_mock_run):
        assert _common.get_feature_flag("COST_TRACKING", default=False) is True
        assert _common.get_feature_flag("GIT_WORKFLOW", default=False) is True
        assert branch_manager._has_git(str(tmp_path)) is True
        assert branch_manager._current_branch(str(tmp_path)) == "main"

    tokens_in = _token_counter.estimate_tokens("git checkout -b feature/cross-gap")
    _cost_ledger.append_cost_entry(
        str(tmp_path),
        {
            "ts": "2026-03-04T00:00:00+00:00",
            "tool": "git-workflow",
            "tokens_in": tokens_in,
            "tokens_out": 8,
            "cost_usd": 0.0005,
            "model": "claude-3-5-haiku-20241022",
            "session_id": "s1",
        },
    )

    summary = _cost_ledger.read_cost_summary(str(tmp_path))
    assert summary["entry_count"] == 1
    assert summary["by_tool"]["git-workflow"]["count"] == 1


def test_analytics_queries_include_test_generation_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_SESSION_ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("OMG_TEST_GENERATION_ENABLED", "1")

    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    _write_jsonl(
        ledger_dir / "tool-ledger.jsonl",
        [
            {
                "ts": "2026-03-04T10:00:00+00:00",
                "tool": "Write",
                "file": "src/new_feature.py",
                "success": True,
            },
            {
                "ts": "2026-03-04T10:01:00+00:00",
                "tool": "Bash",
                "command": "pytest tests/test_new_feature.py -q",
                "exit_code": 0,
            },
        ],
    )
    _write_jsonl(
        ledger_dir / "cost-ledger.jsonl",
        [
            {"tool": "Write", "tokens_in": 25, "tokens_out": 10, "cost_usd": 0.001},
            {"tool": "Bash", "tokens_in": 30, "tokens_out": 12, "cost_usd": 0.002},
        ],
    )

    summary = query.get_session_summary(str(tmp_path))
    heatmap = query.get_file_heatmap(str(tmp_path))

    assert _common.get_feature_flag("SESSION_ANALYTICS", default=False) is True
    assert _common.get_feature_flag("TEST_GENERATION", default=False) is True
    assert summary["tests_run"] == 1
    assert summary["tool_calls"] == 2
    assert summary["tokens_used"] == 77
    assert heatmap["src/new_feature.py"]["writes"] == 1


def test_secret_audit_and_file_write_content_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_FEATURE_ENABLED", "1")
    secret_text = "api_key = 'Qx7rP1zM9kT4bN8vL2sD6fG3hJ0wY5uC1eR'\n"
    assert post_write.detect_high_entropy_strings(secret_text)

    _ = (tmp_path / ".env.production").write_text(secret_text, encoding="utf-8")
    secret_audit.log_secret_access(
        project_dir=str(tmp_path),
        tool="Write",
        file_path=".env.production",
        decision="allow",
        reason="allowlist override",
        allowlisted=True,
    )

    log_path = tmp_path / ".omg" / "state" / "ledger" / "secret-access.jsonl"
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert entries
    assert entries[-1]["allowlisted"] is True
    assert entries[-1]["file"] == "[REDACTED]"


def test_dependency_scan_detects_package_manifest_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")

    package_json = tmp_path / "package.json"
    _ = package_json.write_text(
        json.dumps({"dependencies": {"requests": "1.0.0"}}),
        encoding="utf-8",
    )
    first = manifest_detector.detect_manifests(str(tmp_path))
    first_names = {pkg.name for pkg in first.packages}
    assert "requests" in first_names

    _ = package_json.write_text(
        json.dumps({"dependencies": {"requests": "1.0.0", "urllib3": "2.0.0"}}),
        encoding="utf-8",
    )
    second = manifest_detector.detect_manifests(str(tmp_path))
    second_names = {pkg.name for pkg in second.packages}
    assert "urllib3" in second_names

    deps_for_scan = [
        {"name": pkg.name, "version": pkg.version or "", "ecosystem": "PyPI"}
        for pkg in second.packages
    ]
    with patch("plugins.dephealth.cve_scanner.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _FakeHTTPResponse({"results": [{"vulns": []}, {"vulns": []}]})
        _ = cve_scanner.scan_for_cves(deps_for_scan, project_dir=str(tmp_path))

    request_obj = cast(_RequestWithData, cast(tuple[object, ...], mock_urlopen.call_args.args)[0])
    request_data = request_obj.data
    payload = cast(dict[str, object], json.loads(request_data.decode("utf-8")))
    queries = cast(list[dict[str, object]], payload.get("queries", []))
    queried = {
        cast(dict[str, str], query_item.get("package", {})).get("name", "")
        for query_item in queries
    }
    assert {"requests", "urllib3"}.issubset(queried)


def test_graph_builder_generates_python_project_graph(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_CODEBASE_VIZ_ENABLED", "1")
    _ = (tmp_path / "app.py").write_text("import os\nfrom util import helper\n", encoding="utf-8")
    _ = (tmp_path / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    graph = graph_builder.build_project_graph(str(tmp_path))
    adjacency = cast(dict[str, list[str]], graph["graph"])
    metrics = cast(dict[str, object], graph["metrics"])

    assert "app" in adjacency
    assert "util" in adjacency
    assert cast(int, metrics["module_count"]) == 2
    assert cast(int, metrics["edge_count"]) >= 1


def test_feature_flag_isolation_keeps_other_gaps_operational(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_COST_TRACKING_ENABLED", "0")
    monkeypatch.setenv("OMG_GIT_WORKFLOW_ENABLED", "1")
    monkeypatch.setenv("OMG_CODEBASE_VIZ_ENABLED", "1")

    assert _common.get_feature_flag("COST_TRACKING", default=True) is False
    assert _common.get_feature_flag("GIT_WORKFLOW", default=False) is True

    _ = (tmp_path / "module.py").write_text("import json\n", encoding="utf-8")
    result = graph_builder.build_project_graph(str(tmp_path))
    metrics = cast(dict[str, object], result["metrics"])
    assert cast(int, metrics["module_count"]) == 1


def test_cost_ledger_persists_across_multiple_tool_calls(tmp_path: Path) -> None:
    _cost_ledger.append_cost_entry(
        str(tmp_path),
        {
            "ts": "2026-03-04T11:00:00+00:00",
            "tool": "Write",
            "tokens_in": 100,
            "tokens_out": 40,
            "cost_usd": 0.01,
            "model": "claude",
            "session_id": "s1",
        },
    )
    _cost_ledger.append_cost_entry(
        str(tmp_path),
        {
            "ts": "2026-03-04T11:01:00+00:00",
            "tool": "Bash",
            "tokens_in": 50,
            "tokens_out": 10,
            "cost_usd": 0.005,
            "model": "claude",
            "session_id": "s1",
        },
    )

    summary = _cost_ledger.read_cost_summary(str(tmp_path))
    assert summary["entry_count"] == 2
    assert summary["total_tokens"] == 200
    assert summary["by_tool"]["Write"]["count"] == 1
    assert summary["by_tool"]["Bash"]["count"] == 1


def test_multi_gap_data_flow_runs_without_conflict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMG_COST_TRACKING_ENABLED", "1")
    monkeypatch.setenv("OMG_SESSION_ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("OMG_TEST_GENERATION_ENABLED", "1")
    monkeypatch.setenv("OMG_DEP_HEALTH_ENABLED", "1")
    monkeypatch.setenv("OMG_CODEBASE_VIZ_ENABLED", "1")

    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    _write_jsonl(
        ledger_dir / "tool-ledger.jsonl",
        [{"ts": "2026-03-04T12:00:00+00:00", "tool": "Write", "file": "src/a.py", "success": True}],
    )
    _cost_ledger.append_cost_entry(
        str(tmp_path),
        {
            "ts": "2026-03-04T12:00:00+00:00",
            "tool": "Write",
            "tokens_in": 20,
            "tokens_out": 5,
            "cost_usd": 0.001,
            "model": "claude",
            "session_id": "s99",
        },
    )

    _ = (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"attrs": "23.0.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    _ = (tmp_path / "src" / "a.py").write_text("import os\n", encoding="utf-8")
    secret_audit.log_secret_access(
        project_dir=str(tmp_path),
        tool="Write",
        file_path="secrets/token.txt",
        decision="deny",
        reason="secret-like path",
        allowlisted=False,
    )

    session = query.get_session_summary(str(tmp_path))
    deps = manifest_detector.detect_manifests(str(tmp_path))
    graph = graph_builder.build_project_graph(str(tmp_path))
    metrics = cast(dict[str, object], graph["metrics"])

    assert session["tool_calls"] == 1
    assert session["tokens_used"] == 25
    assert len(deps.packages) == 1
    assert cast(int, metrics["module_count"]) >= 1
    assert (tmp_path / ".omg" / "state" / "ledger" / "secret-access.jsonl").exists()
