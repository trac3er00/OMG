from __future__ import annotations

import importlib
from pathlib import Path
from textwrap import dedent
from typing import Callable, TypedDict, cast


class ValidationResult(TypedDict):
    valid: bool
    errors: list[str]
    warnings: list[str]
    pack_name: str


validate_pack = cast(
    Callable[..., ValidationResult],
    importlib.import_module("runtime.pack_schema_validator").validate_pack,
)


ROOT = Path(__file__).resolve().parents[2]
SAAS_PACK = ROOT / "packs" / "domains" / "saas" / "pack.yaml"
SAAS_LITE_PACK = ROOT / "packs" / "domains" / "saas-lite" / "pack.yaml"


def _write_pack(tmp_path: Path, body: str) -> Path:
    pack_path = tmp_path / "pack.yaml"
    _ = pack_path.write_text(dedent(body).strip() + "\n", encoding="utf-8")
    return pack_path


def test_saas_pack_validates_in_both_modes() -> None:
    relaxed = validate_pack(SAAS_PACK)
    strict = validate_pack(SAAS_PACK, strict=True)

    assert relaxed["valid"] is True
    assert strict["valid"] is True
    assert relaxed["pack_name"] == "saas"
    assert strict["pack_name"] == "saas"
    assert relaxed["errors"] == []
    assert strict["errors"] == []


def test_saas_lite_validates_relaxed_mode() -> None:
    result = validate_pack(SAAS_LITE_PACK)

    assert result["valid"] is True
    assert result["pack_name"] == "saas-lite"
    assert result["errors"] == []
    assert any("rules" in warning for warning in result["warnings"])


def test_saas_lite_fails_strict_mode_for_missing_recommended_fields() -> None:
    result = validate_pack(SAAS_LITE_PACK, strict=True)

    assert result["valid"] is False
    assert any("rules" in error for error in result["errors"])
    assert any("prompts" in error for error in result["errors"])
    assert any("scaffold" in error for error in result["errors"])
    assert any("evidence" in error for error in result["errors"])


def test_unknown_extension_fields_are_allowed(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path,
        body="""
        name: extension-pack
        description: Pack with optional extension fields.
        instant_mode: true
        rules:
          - rules/example.md
        prompts:
          - prompts/example.md
        scaffold:
          - scaffold/example.md
        evidence:
          required:
            - example-test
        """,
    )
    result = validate_pack(pack_path)

    assert result["valid"] is True
    assert result["errors"] == []


def test_rule_limit_blocks_new_pack_with_eight_rules_in_strict_mode(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(
        tmp_path,
        """
        name: too-many-rules
        rules:
          - rules/1.md
          - rules/2.md
          - rules/3.md
          - rules/4.md
          - rules/5.md
          - rules/6.md
          - rules/7.md
          - rules/8.md
        prompts:
          - prompts/example.md
        scaffold:
          - scaffold/example.md
        evidence:
          required:
            - example-test
        """,
    )
    result = validate_pack(pack_path, strict=True)

    assert result["valid"] is False
    assert any("rules" in error and "5" in error for error in result["errors"])


def test_missing_name_fails_even_in_relaxed_mode(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path,
        """
        description: Anonymous pack.
        instant_mode: true
        """,
    )
    result = validate_pack(pack_path)

    assert result["valid"] is False
    assert any("name" in error for error in result["errors"])
