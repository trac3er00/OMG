"""Tests for persona detection and documentation views."""

from __future__ import annotations

from pathlib import Path

from runtime.persona import detect_persona

DOCS_DIR = Path(__file__).parent.parent / "docs"


class TestDetectPersona:
    """Tests for detect_persona function."""

    def test_detect_persona_default_beginner(self) -> None:
        """Empty context should return beginner persona."""
        assert detect_persona({}) == "beginner"
        assert detect_persona(None) == "beginner"
        assert detect_persona({"flags": []}) == "beginner"

    def test_detect_persona_engineer_flags(self) -> None:
        """Context with technical flags should return engineer persona."""
        assert detect_persona({"flags": ["--verbose"]}) == "engineer"
        assert detect_persona({"flags": ["--trace"]}) == "engineer"
        assert detect_persona({"flags": ["--debug"]}) == "engineer"
        assert detect_persona({"flags": ["--diff"]}) == "engineer"
        assert detect_persona({"flags": ["--technical"]}) == "engineer"
        assert detect_persona({"flags": ["--json"]}) == "engineer"
        assert detect_persona({"flags": ["--verbose", "--trace"]}) == "engineer"

    def test_detect_persona_exec_context(self) -> None:
        """Context with exec signals should return exec persona."""
        assert detect_persona({"flags": ["--exec"]}) == "exec"
        assert detect_persona({"flags": ["--kpi"]}) == "exec"
        assert detect_persona({"flags": ["--roi"]}) == "exec"
        assert detect_persona({"flags": ["--summary"]}) == "exec"
        assert detect_persona({"flags": ["--cost"]}) == "exec"
        assert detect_persona({"flags": ["--dashboard"]}) == "exec"

    def test_detect_persona_exec_takes_priority(self) -> None:
        """Exec flags should take priority over engineer flags."""
        assert detect_persona({"flags": ["--kpi", "--verbose"]}) == "exec"

    def test_detect_persona_command_count_engineer(self) -> None:
        """High command count should return engineer persona."""
        assert detect_persona({"commandCount": 12}) == "engineer"
        assert detect_persona({"commandCount": 100}) == "engineer"

    def test_detect_persona_command_count_beginner(self) -> None:
        """Low command count should return beginner persona."""
        assert detect_persona({"commandCount": 0}) == "beginner"
        assert detect_persona({"commandCount": 2}) == "beginner"

    def test_detect_persona_beginner_flags(self) -> None:
        """Beginner flags should return beginner persona."""
        assert detect_persona({"flags": ["--help"]}) == "beginner"
        assert detect_persona({"flags": ["--simple"]}) == "beginner"
        assert detect_persona({"flags": ["--explain"]}) == "beginner"


class TestDocsExist:
    """Tests for documentation file existence."""

    def test_docs_exist(self) -> None:
        """Verify all 3 getting-started docs exist."""
        beginner_doc = DOCS_DIR / "getting-started-beginner.md"
        engineer_doc = DOCS_DIR / "getting-started-engineer.md"
        exec_doc = DOCS_DIR / "getting-started-exec.md"

        assert beginner_doc.exists(), f"Missing: {beginner_doc}"
        assert engineer_doc.exists(), f"Missing: {engineer_doc}"
        assert exec_doc.exists(), f"Missing: {exec_doc}"


class TestDocsContent:
    """Tests for documentation content validation."""

    def test_docs_have_content(self) -> None:
        """Verify docs have appropriate persona-specific content."""
        beginner_doc = DOCS_DIR / "getting-started-beginner.md"
        engineer_doc = DOCS_DIR / "getting-started-engineer.md"
        exec_doc = DOCS_DIR / "getting-started-exec.md"

        beginner_content = beginner_doc.read_text().lower()
        engineer_content = engineer_doc.read_text().lower()
        exec_content = exec_doc.read_text().lower()

        assert "simple" in beginner_content, "Beginner doc should mention 'simple'"
        assert "beginner" in beginner_content, "Beginner doc should mention 'beginner'"

        assert "engineer" in engineer_content, "Engineer doc should mention 'engineer'"
        assert "trace" in engineer_content, "Engineer doc should mention traceability"

        assert "kpi" in exec_content, "Exec doc should mention 'KPI'"
        assert "exec" in exec_content, "Exec doc should mention 'exec'"

    def test_docs_not_empty(self) -> None:
        """Verify docs have meaningful content (not just placeholders)."""
        min_content_length = 100

        for doc_name in [
            "getting-started-beginner.md",
            "getting-started-engineer.md",
            "getting-started-exec.md",
        ]:
            doc_path = DOCS_DIR / doc_name
            content = doc_path.read_text()
            assert len(content) >= min_content_length, (
                f"{doc_name} should have at least {min_content_length} characters"
            )
