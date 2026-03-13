from __future__ import annotations

import json
from pathlib import Path

from runtime import equalizer
from runtime.contract_compiler import _check_host_semantic_parity
from runtime.host_parity import check_parity, emit_parity_report, normalize_output


def test_canonical_hosts_produce_equivalent_normalized_outcomes() -> None:
    outputs = {
        "claude": {
            "model": "claude",
            "output": '{"status":"ok","summary":"flow complete","skills":["control-plane","mcp-fabric"]}',
            "exit_code": 0,
        },
        "codex": {
            "model": "codex-cli",
            "output": '{"skills":["mcp-fabric","control-plane"],"summary":"flow complete","status":"ok"}',
            "exit_code": 0,
        },
        "gemini": {
            "model": "gemini-cli",
            "output": "status: ok\nsummary: flow complete\nskills: control-plane, mcp-fabric",
            "exit_code": 0,
        },
        "kimi": {
            "model": "kimi-cli",
            "output": '{"status":"ok","summary":"flow complete","skills":["control-plane","mcp-fabric"]}',
            "exit_code": 0,
        },
    }

    result = check_parity(outputs, context={"surface": "skills"})

    assert result.passed is True
    assert result.drift_detected is False
    assert result.drift_details == []


def test_regression_is_reported_as_drift() -> None:
    outputs = {
        "claude": {"output": '{"status":"ok","result":"pass"}', "exit_code": 0},
        "codex": {"output": '{"status":"ok","result":"pass"}', "exit_code": 0},
        "gemini": {"output": "status: ok\nresult: pass", "exit_code": 0},
        "kimi": {"output": '{"status":"error","result":"fail"}', "exit_code": 1},
    }

    result = check_parity(outputs, context={"surface": "automations"})

    assert result.passed is False
    assert result.drift_detected is True
    assert any("kimi" in detail for detail in result.drift_details)


def test_semantic_parity_report_is_required_for_canonical_hosts(tmp_path: Path) -> None:
    result = _check_host_semantic_parity(tmp_path, {"claude", "codex", "gemini", "kimi"})

    assert result["status"] == "error"
    assert result["blockers"] == ["host_semantic_parity: missing host parity report"]


def test_semantic_parity_blocks_cross_run_report(tmp_path: Path) -> None:
    evidence_root = tmp_path / ".omg" / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "host-parity-run-old.json").write_text(
        json.dumps(
            {
                "schema": "HostParityReport",
                "run_id": "run-old",
                "canonical_hosts": ["claude", "codex", "gemini", "kimi"],
                "overall_status": "ok",
                "parity_results": {"passed": True},
            }
        ),
        encoding="utf-8",
    )

    result = _check_host_semantic_parity(
        tmp_path,
        {"claude", "codex", "gemini", "kimi"},
        release_run_id="run-new",
    )

    assert result["status"] == "error"
    assert "host_parity_report:cross_run" in result["blockers"]


def test_gemini_text_output_normalizes_to_structured_form() -> None:
    normalized = normalize_output(
        "gemini",
        {
            "model": "gemini-cli",
            "output": "status: ok\nsummary: route complete\ncommands: OMG:browser, OMG:validate",
            "exit_code": 0,
        },
        context={"surface": "commands"},
    )

    assert normalized["status"] == "ok"
    structured = normalized["semantic"]["structured"]
    assert structured["status"] == "ok"
    assert structured["summary"] == "route complete"
    assert structured["commands"] == ["OMG:browser", "OMG:validate"]


def test_claude_is_not_hardcoded_as_always_available(monkeypatch) -> None:
    monkeypatch.delenv("OMG_CLAUDE_WORKER_CMD", raising=False)
    monkeypatch.delenv("OMG_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(equalizer.shutil, "which", lambda _name: None)

    available, auth_ok, reason = equalizer._probe_provider("claude")

    assert available is False
    assert auth_ok is False
    assert reason == "provider CLI unavailable"


def test_emit_parity_report_writes_expected_evidence_shape(tmp_path) -> None:
    result = check_parity(
        {
            "claude": {"output": '{"status":"ok"}', "exit_code": 0},
            "codex": {"output": '{"status":"ok"}', "exit_code": 0},
            "gemini": {"output": "status: ok", "exit_code": 0},
            "kimi": {"output": '{"status":"ok"}', "exit_code": 0},
        }
    )

    report_path = emit_parity_report("run-test", result, project_dir=str(tmp_path))
    payload = json.loads((tmp_path / ".omg" / "evidence" / "host-parity-run-test.json").read_text(encoding="utf-8"))

    assert report_path.endswith(".omg/evidence/host-parity-run-test.json")
    assert payload["run_id"] == "run-test"
    assert payload["overall_status"] == "ok"
    assert payload["parity_results"]["passed"] is True
