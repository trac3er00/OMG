import json
from pathlib import Path

import pytest

from runtime.playwright_pack import PlaywrightPack, IsolationError
from runtime.untrusted_content import (
    TrustTier,
    clear_untrusted_content,
    mark_untrusted_content,
)


def test_browser_pack_requires_isolation(tmp_path):
    pack = PlaywrightPack(project_dir=tmp_path, isolated=False)

    with pytest.raises(IsolationError, match="Browser execution requires isolated mode or active BROWSER trust tier"):
        pack.check_isolation()

    mark_untrusted_content(
        str(tmp_path),
        source_type="web",
        content="some content",
        tier=TrustTier.RESEARCH,
    )

    with pytest.raises(IsolationError, match="Browser execution requires BROWSER trust tier, got research"):
        pack.check_isolation()

    mark_untrusted_content(
        str(tmp_path),
        source_type="browser",
        content="some content",
        tier=TrustTier.BROWSER,
    )

    pack.check_isolation()

    clear_untrusted_content(str(tmp_path), reason="test")

    with pytest.raises(IsolationError, match="Browser execution requires isolated mode or active BROWSER trust tier"):
        pack.check_isolation()

    isolated_pack = PlaywrightPack(project_dir=tmp_path, isolated=True)
    isolated_pack.check_isolation()


def test_browser_pack_emits_proof_ready_artifacts(tmp_path):
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

    assert "metadata" in result
    assert result["metadata"]["isolated"] is True

    evidence_path = output_dir / "browser-evidence.json"
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text())
    assert evidence["schema"] == "BrowserEvidence"
    assert evidence["fixture_hash"]
    assert evidence["artifacts"]["trace"] == artifacts["trace"]


def test_browser_pack_metadata_includes_trust_tier(tmp_path):
    fixture_path = tmp_path / "smoke_page.html"
    fixture_path.write_text("<html><body>OK</body></html>")

    pack = PlaywrightPack(project_dir=tmp_path, isolated=True)
    result = pack.run_smoke(fixture_path, output_dir=tmp_path / "out")

    metadata = result["metadata"]
    assert metadata["trust_tier"] == "browser"
    assert metadata["trust_label"] == "UNTRUSTED_EXTERNAL_CONTENT"
    assert metadata["trust_score"] == 0.0
    assert metadata["isolated"] is True
    assert metadata["timestamp"]
    assert metadata["project_dir"] == str(tmp_path.resolve())


def test_browser_pack_non_isolated_with_browser_tier_includes_metadata(tmp_path):
    fixture_path = tmp_path / "smoke_page.html"
    fixture_path.write_text("<html><body>OK</body></html>")

    mark_untrusted_content(
        str(tmp_path),
        source_type="browser",
        content="dom content",
        tier=TrustTier.BROWSER,
    )

    pack = PlaywrightPack(project_dir=tmp_path, isolated=False)
    result = pack.run_smoke(fixture_path, output_dir=tmp_path / "out")

    assert result["metadata"]["trust_tier"] == "browser"
    assert result["metadata"]["isolated"] is False
    assert result["metadata"]["trust_score"] == 0.0


def test_browser_pack_smoke_fixture_exists():
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = repo_root / "tests" / "fixtures" / "smoke_page.html"

    assert fixture_path.exists()
    content = fixture_path.read_text()
    assert "<title>OMG Browser Smoke Test</title>" in content
    assert "id=\"test-button\"" in content


def test_browser_pack_run_smoke_rejects_missing_fixture(tmp_path):
    pack = PlaywrightPack(project_dir=tmp_path, isolated=True)
    with pytest.raises(FileNotFoundError, match="Smoke fixture not found"):
        pack.run_smoke(tmp_path / "nonexistent.html")
