import os
import json
from pathlib import Path
import pytest

from runtime.playwright_pack import PlaywrightPack, IsolationError
from runtime.untrusted_content import mark_untrusted_content, clear_untrusted_content, TrustTier


def test_browser_pack_requires_isolation(tmp_path):
    """Proves unsafe execution raises IsolationError."""
    pack = PlaywrightPack(project_dir=tmp_path, isolated=False)
    
    # By default, no trust tier is active
    with pytest.raises(IsolationError, match="Browser execution requires isolated mode or active BROWSER trust tier"):
        pack.check_isolation()
        
    # Mark with RESEARCH tier (not BROWSER)
    mark_untrusted_content(
        str(tmp_path),
        source_type="web",
        content="some content",
        tier=TrustTier.RESEARCH
    )
    
    with pytest.raises(IsolationError, match="Browser execution requires BROWSER trust tier, got research"):
        pack.check_isolation()
        
    # Mark with BROWSER tier
    mark_untrusted_content(
        str(tmp_path),
        source_type="browser",
        content="some content",
        tier=TrustTier.BROWSER
    )
    
    # Should not raise
    pack.check_isolation()
    
    # Clear it
    clear_untrusted_content(str(tmp_path), reason="test")
    
    with pytest.raises(IsolationError, match="Browser execution requires isolated mode or active BROWSER trust tier"):
        pack.check_isolation()
        
    # Isolated mode bypasses the check
    isolated_pack = PlaywrightPack(project_dir=tmp_path, isolated=True)
    isolated_pack.check_isolation()


def test_browser_pack_emits_artifacts(tmp_path):
    """Proves smoke run emits trace.zip, screenshots, junit.xml."""
    fixture_path = tmp_path / "smoke_page.html"
    fixture_path.write_text("<html><body><h1>Test</h1></body></html>")
    
    pack = PlaywrightPack(project_dir=tmp_path, isolated=True)
    output_dir = tmp_path / ".omg" / "evidence" / "browser"
    
    result = pack.run_smoke(fixture_path, output_dir=output_dir)
    
    assert result["status"] == "success"
    assert result["fixture"] == str(fixture_path)
    
    artifacts = result["artifacts"]
    assert "trace" in artifacts
    assert "screenshots" in artifacts
    assert "junit" in artifacts
    
    trace_path = Path(artifacts["trace"])
    assert trace_path.exists()
    assert trace_path.name == "trace.zip"
    
    screenshot_path = Path(artifacts["screenshots"][0])
    assert screenshot_path.exists()
    assert screenshot_path.name == "smoke_test.png"
    assert screenshot_path.parent.name == "screenshots"
    
    junit_path = Path(artifacts["junit"])
    assert junit_path.exists()
    assert junit_path.name == "junit.xml"
    assert "testsuite name=\"browser_smoke\"" in junit_path.read_text()


def test_browser_pack_smoke_fixture_exists():
    """Proves local fixture is present."""
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "smoke_page.html"
    
    assert fixture_path.exists()
    content = fixture_path.read_text()
    assert "<title>OMG Browser Smoke Test</title>" in content
    assert "id=\"test-button\"" in content
