from __future__ import annotations

import pytest

from runtime.language_pipeline import (
    SUPPORTED_LANGUAGES,
    detect_language,
    should_use_pipeline,
    wrap_for_internal_processing,
)


def test_detect_english_text():
    result = detect_language("Create a login page with authentication")
    assert result.language == "english"
    assert result.confidence > 0.5


def test_detect_korean_text():
    result = detect_language("로그인 페이지를 만들어줘")
    assert result.language == "korean"
    assert result.confidence > 0.3


def test_detect_japanese_text():
    result = detect_language("ログインページを作成してください")
    assert result.language == "japanese"


def test_code_identifiers_preserved():
    result = detect_language("handleSubmit 함수를 수정해줘")
    assert result.has_code is True
    assert any("handleSubmit" in term for term in result.preserved_terms)


def test_pipeline_active_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OMG_LANGUAGE_PIPELINE", raising=False)
    assert should_use_pipeline() is True


def test_pipeline_disabled_by_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMG_LANGUAGE_PIPELINE", "0")
    assert should_use_pipeline() is False


def test_wrap_korean_adds_context():
    result = wrap_for_internal_processing("로그인 페이지를 만들어줘")
    assert result["pipeline_active"] is True
    assert result["source_language"] == "korean"
    assert "English" in result["internal_text"] or "korean" in result[
        "internal_text"
    ].lower()


def test_wrap_english_no_change():
    result = wrap_for_internal_processing("Create a login page")
    assert result["source_language"] == "english"
    assert isinstance(result["internal_text"], str)


def test_language_result_fields():
    result = detect_language("test")
    assert result.language in SUPPORTED_LANGUAGES
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.has_code, bool)
    assert isinstance(result.preserved_terms, list)


def test_empty_text_defaults_to_english():
    result = detect_language("")
    assert result.language == "english"
