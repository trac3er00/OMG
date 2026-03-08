import zipfile
from pathlib import Path

from runtime.playwright_adapter import summarize_playwright_artifacts


def test_summarize_playwright_artifacts_happy_path(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.zip"
    with zipfile.ZipFile(trace_path, "w") as z:
        z.writestr("trace.trace", "{}")

    junit_path = tmp_path / "junit.xml"
    junit_path.write_text("<testsuites></testsuites>")

    screenshot_path = tmp_path / "screenshot.png"
    screenshot_path.write_bytes(b"")

    metadata = {"isolated": True, "trust_tier": "browser"}

    result = summarize_playwright_artifacts(
        trace_path=str(trace_path),
        junit_path=str(junit_path),
        screenshots=[str(screenshot_path)],
        metadata=metadata,
    )

    assert result["status"] == "ok"
    assert result["artifacts"]["trace"] == str(trace_path)
    assert result["artifacts"]["junit"] == str(junit_path)
    assert result["artifacts"]["screenshots"] == [str(screenshot_path)]
    assert result["metadata"] == metadata


def test_summarize_playwright_artifacts_no_artifacts() -> None:
    result = summarize_playwright_artifacts()
    assert result["status"] == "error"
    assert result["reason"] == "no_artifacts_provided"


def test_summarize_playwright_artifacts_partial_artifacts(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.zip"
    with zipfile.ZipFile(trace_path, "w") as z:
        z.writestr("trace.trace", "{}")

    result = summarize_playwright_artifacts(trace_path=str(trace_path))

    assert result["status"] == "ok"
    assert result["artifacts"]["trace"] == str(trace_path)
    assert "junit" not in result["artifacts"]
    assert "screenshots" not in result["artifacts"]
    assert result["metadata"] == {}
