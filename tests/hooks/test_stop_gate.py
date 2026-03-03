"""Tests for stop dispatcher false-fix detection."""

def test_false_fix_non_source_patterns():
    with open("hooks/stop_dispatcher.py") as f:
        content = f.read()

    assert '".omg/"' in content, "Missing .omg/ in NON_SOURCE_PATTERNS"
    assert '".omc/"' in content, "Missing .omc/ in NON_SOURCE_PATTERNS"
    assert '"hooks/"' in content, "Missing hooks/ in NON_SOURCE_PATTERNS"
    assert '"CLAUDE.md"' in content, "Missing CLAUDE.md in NON_SOURCE_PATTERNS"
    assert '"AGENTS.md"' in content, "Missing AGENTS.md in NON_SOURCE_PATTERNS"
    assert '"readme"' in content.lower(), "Missing readme in NON_SOURCE_PATTERNS"
    assert '".github/"' in content, "Missing .github/ in NON_SOURCE_PATTERNS"

def test_false_fix_detection_message():
    with open("hooks/stop_dispatcher.py") as f:
        content = f.read()
    assert "FALSE FIX DETECTED" in content
    assert "No actual source code was changed" in content

def test_check6_write_failure_detection():
    with open("hooks/stop_dispatcher.py") as f:
        content = f.read()
    assert "WRITE/EDIT FAILURE DETECTED" in content
    assert "success" in content  # checks success field
    assert "READ the target file" in content or "Read the file" in content

def test_standalone_mode_no_coexist_toggle():
    for hook in ["stop_dispatcher.py", "stop-gate.py", "test-validator.py", "quality-runner.py"]:
        with open(f"hooks/{hook}") as f:
            content = f.read()
        assert "OMG_COEXIST_MODE" not in content, f"{hook} still references coexist mode"


def test_stop_gate_is_thin_wrapper():
    with open("hooks/stop-gate.py") as f:
        content = f.read()
    assert "from stop_dispatcher import main" in content
