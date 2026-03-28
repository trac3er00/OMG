from __future__ import annotations
# pyright: reportMissingImports=false

from pathlib import Path
from typing import Any

import pytest

from hooks.security_validators import (
    ensure_path_within_dir,
    sanitize_run_id,
    toml_quote_string,
    validate_opaque_identifier,
    validate_server_name,
    validate_server_url,
)


def test_validate_opaque_identifier_accepts_trimmed_valid_value() -> None:
    assert validate_opaque_identifier("  run_1.ok-2  ", "run_id") == "run_1.ok-2"


def test_validate_opaque_identifier_rejects_non_string() -> None:
    non_string: Any = 123
    with pytest.raises(ValueError, match="must be a string"):
        validate_opaque_identifier(non_string, "run_id")


def test_validate_opaque_identifier_rejects_empty_after_trim() -> None:
    with pytest.raises(ValueError, match="value is required"):
        validate_opaque_identifier("   ", "run_id")


def test_validate_opaque_identifier_rejects_too_long_value() -> None:
    with pytest.raises(ValueError, match="exceeds 64 characters"):
        validate_opaque_identifier("a" * 65, "run_id")


def test_validate_opaque_identifier_rejects_traversal_sequence() -> None:
    with pytest.raises(ValueError, match="use only ASCII"):
        validate_opaque_identifier("good..bad", "run_id")


def test_validate_opaque_identifier_rejects_illegal_symbols() -> None:
    with pytest.raises(ValueError, match="use only ASCII"):
        validate_opaque_identifier("bad/value", "run_id")


def test_ensure_path_within_dir_returns_resolved_child_path(tmp_path: Path) -> None:
    base = tmp_path / "base"
    nested = base / "x" / ".." / "child.txt"
    base.mkdir(parents=True)
    assert ensure_path_within_dir(base, nested) == str((base / "child.txt").resolve())


def test_ensure_path_within_dir_rejects_escape_path(tmp_path: Path) -> None:
    base = tmp_path / "base"
    outside = tmp_path / "outside.txt"
    base.mkdir(parents=True)
    with pytest.raises(ValueError, match="escapes base directory"):
        ensure_path_within_dir(base, outside)


def test_validate_server_name_accepts_ascii_wording() -> None:
    assert validate_server_name("  my_server-01  ") == "my_server-01"


def test_validate_server_name_rejects_non_string() -> None:
    non_string: Any = None
    with pytest.raises(ValueError, match="must be a string"):
        validate_server_name(non_string)


def test_validate_server_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="value is required"):
        validate_server_name(" \t ")


def test_validate_server_name_rejects_disallowed_characters() -> None:
    with pytest.raises(ValueError, match="ASCII letters"):
        validate_server_name("name.with.dot")


def test_validate_server_url_accepts_http_and_https() -> None:
    assert validate_server_url("https://api.example.test/v1") == "https://api.example.test/v1"
    assert validate_server_url("http://localhost:8000") == "http://localhost:8000"


def test_validate_server_url_rejects_newline_injection() -> None:
    with pytest.raises(ValueError, match="newline"):
        validate_server_url("https://a.test\nhttps://b.test")


def test_validate_server_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        validate_server_url("ftp://example.test")


def test_sanitize_run_id_removes_traversal_and_illegal_chars() -> None:
    assert sanitize_run_id(" ../run:prod/1 ") == "-run-prod-1"


def test_sanitize_run_id_returns_unknown_for_empty() -> None:
    assert sanitize_run_id("   ") == "unknown"


def test_sanitize_run_id_applies_max_length_cap() -> None:
    assert sanitize_run_id("x" * 256, max_length=32) == "x" * 32


def test_toml_quote_string_escapes_backslash_and_quote() -> None:
    assert toml_quote_string('a\\b"c') == 'a\\\\b\\"c'
