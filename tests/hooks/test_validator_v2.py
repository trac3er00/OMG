"""Tests for test-validator.py v2 enhancements (T32).

New anti-pattern detections:
  1. Skip/ignore tests
  2. Mock-heavy tests (ratio-based)
  3. Parameterized test gaps
  4. Assertion-free tests (Python-style)
  5. Empty test bodies
Plus: coverage metrics persistence to .omg/state/test-metrics.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# Import test-validator.py via importlib (hyphenated filename)
_HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

_spec = importlib.util.spec_from_file_location(
    "test_validator", str(_HOOKS_DIR / "test-validator.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

analyze_test_content = _mod.analyze_test_content
persist_metrics = _mod.persist_metrics


# --- 1. Skip/Ignore Detection ---

def test_skip_decorator_detected():
    """@pytest.mark.skip flagged."""
    content = """\
import pytest

@pytest.mark.skip(reason="not ready")
def test_something():
    assert 1 == 1
"""
    issues = analyze_test_content(content, "test_example.py")
    assert any("SKIP" in i for i in issues), f"Should detect @pytest.mark.skip, got: {issues}"


def test_xit_detected():
    """xit( flagged."""
    content = """\
xit('should do something', function() {
    expect(true).toBe(true);
});

xdescribe('disabled suite', function() {
    it('works', function() { expect(1).toBe(1); });
});
"""
    issues = analyze_test_content(content, "example.test.js")
    assert any("SKIP" in i for i in issues), f"Should detect xit(, got: {issues}"


# --- 2. Assertion-Free Tests ---

def test_assertion_free_test_detected():
    """Test with no assertions flagged."""
    content = """\
def test_does_nothing():
    x = 1 + 2
    print(x)
    result = calculate(x)

def test_also_nothing():
    data = fetch_data()
    process(data)
"""
    issues = analyze_test_content(content, "test_example.py")
    assert any("ASSERTION" in i.upper() for i in issues), \
        f"Should detect assertion-free test, got: {issues}"


# --- 3. Empty Test Bodies ---

def test_empty_test_body_detected():
    """pass only body flagged."""
    content = """\
def test_placeholder():
    pass

def test_ellipsis():
    ...

def test_just_comment():
    # TODO: implement this test
"""
    issues = analyze_test_content(content, "test_example.py")
    assert any("EMPTY" in i for i in issues), \
        f"Should detect empty test body, got: {issues}"


# --- 4. Mock-Heavy Tests ---

def test_mock_heavy_test_detected():
    """4 mocks, 1 assertion flagged."""
    content = """\
from unittest.mock import patch, MagicMock

@patch('module.service_a')
@patch('module.service_b')
@patch('module.service_c')
@patch('module.service_d')
def test_everything_mocked(mock_d, mock_c, mock_b, mock_a):
    result = do_something()
    assert result is not None
"""
    issues = analyze_test_content(content, "test_example.py")
    assert any("MOCK" in i.upper() for i in issues), \
        f"Should detect mock-heavy test (4 mocks, 1 assert), got: {issues}"


# --- 5. Parameterized Gap ---

def test_parameterized_gap_detected():
    """Same function tested 3x with literals flagged."""
    content = """\
def test_calculate_one():
    assert calculate(1) == 1

def test_calculate_two():
    assert calculate(2) == 4

def test_calculate_three():
    assert calculate(3) == 9

def test_calculate_four():
    assert calculate(4) == 16
"""
    issues = analyze_test_content(content, "test_example.py")
    assert any("PARAM" in i.upper() for i in issues), \
        f"Should detect parameterized gap, got: {issues}"


# --- 6. Metrics Persistence ---

def test_metrics_json_written():
    """Metrics file created with correct schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = {
            "total_tests": 10,
            "fake_count": 2,
            "boilerplate_count": 1,
            "edge_case_count": 0,
            "skip_count": 3,
            "assertion_free_count": 1,
        }
        persist_metrics(tmpdir, analysis)

        metrics_path = os.path.join(tmpdir, ".omg", "state", "test-metrics.json")
        assert os.path.exists(metrics_path), "Metrics file should be created"

        with open(metrics_path) as f:
            metrics = json.load(f)

        assert "ts" in metrics, "Must have timestamp"
        assert "quality_score" in metrics, "Must have quality_score"
        assert 0.0 <= metrics["quality_score"] <= 1.0, "Quality score must be 0-1"
        assert metrics["total_tests"] == 10
        assert metrics["fake_count"] == 2
        assert metrics["skip_count"] == 3


# --- 7. Existing Patterns Regression ---

def test_existing_patterns_unchanged():
    """Original 5 patterns still work."""
    # Pattern 1: FAKE (assert True)
    fake_content = """\
def test_trivial():
    assert True
"""
    issues = analyze_test_content(fake_content, "test_fake.py")
    assert any("FAKE" in i for i in issues), f"Should still detect assert True, got: {issues}"

    # Pattern 2: BOILERPLATE (type checks only)
    boilerplate_content = """\
test('is defined', () => {
    expect(typeof myFunc).toBeDefined();
    expect(typeof myClass).toBeDefined();
    expect(myObj instanceof Object).toBeDefined();
    expect(typeof helper).toBeDefined();
});
"""
    issues2 = analyze_test_content(boilerplate_content, "test_boiler.test.js")
    assert any("BOILERPLATE" in i for i in issues2), \
        f"Should still detect boilerplate, got: {issues2}"

    # Pattern 3: HAPPY PATH ONLY (no error tests, 3+ tests)
    happy_content = """\
test('adds numbers', () => { expect(add(1,2)).toBe(3); });
test('multiplies numbers', () => { expect(mul(2,3)).toBe(6); });
test('divides numbers', () => { expect(div(6,2)).toBe(3); });
"""
    issues3 = analyze_test_content(happy_content, "test_happy.test.js")
    assert any("HAPPY" in i.upper() for i in issues3), \
        f"Should still detect happy-path-only, got: {issues3}"

    # Pattern 4: OVER-MOCKED (6+ mocks, <=1 behavior check)
    overmock_content = """\
jest.mock('a');
jest.mock('b');
jest.mock('c');
jest.mock('d');
jest.mock('e');
jest.mock('f');
test('does stuff', () => { doStuff(); });
"""
    issues4 = analyze_test_content(overmock_content, "test_mock.test.js")
    assert any("MOCK" in i.upper() for i in issues4), \
        f"Should still detect over-mocked, got: {issues4}"


# --- 8. Quality Score Computation ---

def test_quality_score_decreases_with_issues():
    """Quality score should be lower when more issues are found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Clean analysis
        clean = {
            "total_tests": 10,
            "fake_count": 0,
            "boilerplate_count": 0,
            "edge_case_count": 0,
            "skip_count": 0,
            "assertion_free_count": 0,
        }
        persist_metrics(tmpdir, clean)
        with open(os.path.join(tmpdir, ".omg", "state", "test-metrics.json")) as f:
            clean_metrics = json.load(f)

    with tempfile.TemporaryDirectory() as tmpdir2:
        # Dirty analysis
        dirty = {
            "total_tests": 10,
            "fake_count": 5,
            "boilerplate_count": 3,
            "edge_case_count": 0,
            "skip_count": 2,
            "assertion_free_count": 4,
        }
        persist_metrics(tmpdir2, dirty)
        with open(os.path.join(tmpdir2, ".omg", "state", "test-metrics.json")) as f:
            dirty_metrics = json.load(f)

    assert clean_metrics["quality_score"] > dirty_metrics["quality_score"], \
        f"Clean ({clean_metrics['quality_score']}) should score higher than dirty ({dirty_metrics['quality_score']})"
