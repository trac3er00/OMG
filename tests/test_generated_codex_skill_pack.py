from __future__ import annotations

import json
from pathlib import Path

from runtime.contract_compiler import (
    REQUIRED_CODEX_AGENTS_SECTIONS,
    REQUIRED_CODEX_OUTPUTS,
    compile_contract_outputs,
)


ROOT = Path(__file__).resolve().parents[1]


def test_codex_skill_pack_exists_for_production_contract() -> None:
    skill_dir = ROOT / ".agents" / "skills" / "omg" / "control-plane"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "openai.yaml").exists()


def test_codex_skill_pack_declares_explicit_invocation_policy() -> None:
    openai_yaml = (ROOT / ".agents" / "skills" / "omg" / "control-plane" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in openai_yaml
    assert "omg-control" in openai_yaml


def test_compiled_codex_agents_fragment_has_required_sections(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    agents_path = tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md"
    content = agents_path.read_text(encoding="utf-8")

    for section in REQUIRED_CODEX_AGENTS_SECTIONS:
        assert section in content, f"Compiled AGENTS.fragment.md missing: {section}"


def test_compiled_codex_surfaces_encode_safe_defaults(tmp_path: Path) -> None:
    result = compile_contract_outputs(
        root_dir=ROOT,
        output_root=tmp_path,
        hosts=["codex"],
        channel="enterprise",
    )
    assert result["status"] == "ok"

    agents_content = (tmp_path / ".agents" / "skills" / "omg" / "AGENTS.fragment.md").read_text(encoding="utf-8")
    rules_content = (tmp_path / ".agents" / "skills" / "omg" / "codex-rules.md").read_text(encoding="utf-8")

    assert "prefer_cached" in rules_content or "prefer_cached" in agents_content
    assert "deny_by_default" in rules_content
    assert "destructive_approval: required" in rules_content

    for path_pattern in (".omg/**", ".agents/**", ".codex/**", ".claude/**"):
        assert path_pattern in agents_content or path_pattern in rules_content


def test_absent_required_codex_output_causes_validation_failure(tmp_path: Path) -> None:
    from runtime.contract_compiler import _validate_compiled_codex_output

    shared_dir = tmp_path / ".agents" / "skills" / "omg"
    shared_dir.mkdir(parents=True, exist_ok=True)

    errors = _validate_compiled_codex_output(tmp_path)
    assert len(errors) >= len(REQUIRED_CODEX_OUTPUTS)
    for output_name in REQUIRED_CODEX_OUTPUTS:
        assert any(output_name in err for err in errors), f"Expected failure for missing {output_name}"
