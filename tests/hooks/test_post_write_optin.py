"""Tests for post-write auto-format opt-in (§4.4)."""

def test_format_requires_quality_gate():
    """§4.4: Auto-format should only run if quality-gate.json has format."""
    with open("hooks/post-write.py") as f:
        content = f.read()
    assert "quality-gate.json" in content
    assert "format_enabled" in content
    # Must check for opt-in, not auto-run
    assert "if format_enabled and ext" in content
