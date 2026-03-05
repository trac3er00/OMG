#!/usr/bin/env python3
"""Tests for tools/pr_generator.py — PR description generator."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from pr_generator import generate_pr_description, write_pr_description


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_commits():
    """Standard set of commits for testing."""
    return [
        {"message": "feat(auth): add JWT validation", "hash": "abc1234"},
        {"message": "fix(auth): handle expired tokens", "hash": "def5678"},
        {"message": "test(auth): add JWT unit tests", "hash": "aaa1111"},
        {"message": "docs(auth): update API docs", "hash": "bbb2222"},
    ]


@pytest.fixture
def sample_diff_stats():
    """Standard diff stats for testing."""
    return {"files_changed": 5, "insertions": 120, "deletions": 10}


@pytest.fixture
def feature_branch():
    return "feature/add-jwt-auth"


# ---------------------------------------------------------------------------
# Test: All sections present
# ---------------------------------------------------------------------------

class TestAllSections:
    """Verify generated PR description contains all required sections."""

    def test_summary_section_present(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert "## Summary" in result

    def test_changes_section_present(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert "## Changes" in result

    def test_testing_section_present(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert "## Testing" in result

    def test_checklist_section_present(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert "## Checklist" in result

    def test_section_order(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        summary_pos = result.index("## Summary")
        changes_pos = result.index("## Changes")
        testing_pos = result.index("## Testing")
        checklist_pos = result.index("## Checklist")
        assert summary_pos < changes_pos < testing_pos < checklist_pos


# ---------------------------------------------------------------------------
# Test: Empty / edge-case inputs
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Handle empty and degenerate inputs gracefully."""

    def test_empty_commits_no_crash(self):
        result = generate_pr_description("feature/empty", [], {})
        assert isinstance(result, str)
        assert "## Summary" in result

    def test_empty_diff_stats(self, feature_branch, sample_commits):
        result = generate_pr_description(feature_branch, sample_commits, {})
        assert "## Summary" in result

    def test_commits_without_hash(self, feature_branch, sample_diff_stats):
        commits = [{"message": "feat: add login"}]
        result = generate_pr_description(feature_branch, commits, sample_diff_stats)
        assert "## Summary" in result

    def test_single_commit(self, sample_diff_stats):
        commits = [{"message": "fix: resolve null pointer", "hash": "abc1234"}]
        result = generate_pr_description("fix/null-pointer", commits, sample_diff_stats)
        assert "## Summary" in result
        assert "## Changes" in result


# ---------------------------------------------------------------------------
# Test: Summary section content
# ---------------------------------------------------------------------------

class TestSummaryContent:
    """Summary should contain bullet points derived from commits."""

    def test_summary_has_bullet_points(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        # Extract summary section
        lines = result.split("\n")
        in_summary = False
        bullets = []
        for line in lines:
            if line.startswith("## Summary"):
                in_summary = True
                continue
            if in_summary and line.startswith("## "):
                break
            if in_summary and line.startswith("- "):
                bullets.append(line)
        assert len(bullets) >= 1, "Summary should have at least 1 bullet point"
        assert len(bullets) <= 5, "Summary should have at most 5 bullet points"


# ---------------------------------------------------------------------------
# Test: Changes section content
# ---------------------------------------------------------------------------

class TestChangesContent:
    """Changes section should categorize commits."""

    def test_changes_has_entries(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        lines = result.split("\n")
        in_changes = False
        entries = []
        for line in lines:
            if line.startswith("## Changes"):
                in_changes = True
                continue
            if in_changes and line.startswith("## "):
                break
            if in_changes and line.startswith("- "):
                entries.append(line)
        assert len(entries) >= 1, "Changes should have at least 1 entry"


# ---------------------------------------------------------------------------
# Test: Testing section content
# ---------------------------------------------------------------------------

class TestTestingContent:
    """Testing section reflects test-related commits."""

    def test_testing_section_reflects_test_commits(self, feature_branch, sample_diff_stats):
        commits = [
            {"message": "feat(api): add endpoint", "hash": "aaa"},
            {"message": "test(api): add endpoint tests", "hash": "bbb"},
        ]
        result = generate_pr_description(feature_branch, commits, sample_diff_stats)
        lines = result.split("\n")
        in_testing = False
        testing_lines = []
        for line in lines:
            if line.startswith("## Testing"):
                in_testing = True
                continue
            if in_testing and line.startswith("## "):
                break
            if in_testing and line.strip():
                testing_lines.append(line)
        assert len(testing_lines) >= 1, "Testing section should have content"

    def test_no_test_commits_still_has_section(self, feature_branch, sample_diff_stats):
        commits = [{"message": "feat: add login", "hash": "aaa"}]
        result = generate_pr_description(feature_branch, commits, sample_diff_stats)
        assert "## Testing" in result


# ---------------------------------------------------------------------------
# Test: Checklist section content
# ---------------------------------------------------------------------------

class TestChecklistContent:
    """Checklist section has standard PR review items."""

    def test_checklist_has_test_item(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert "- [ ] Tests pass" in result or "- [ ] tests pass" in result.lower()

    def test_checklist_has_breaking_changes_item(self, feature_branch, sample_commits, sample_diff_stats):
        result = generate_pr_description(feature_branch, sample_commits, sample_diff_stats)
        lower = result.lower()
        assert "breaking change" in lower or "no breaking" in lower


# ---------------------------------------------------------------------------
# Test: write_pr_description
# ---------------------------------------------------------------------------

class TestWritePrDescription:
    """write_pr_description writes to file or returns string."""

    def test_returns_string_when_no_path(self, feature_branch, sample_commits, sample_diff_stats):
        result = write_pr_description(feature_branch, sample_commits, sample_diff_stats)
        assert isinstance(result, str)
        assert "## Summary" in result

    def test_writes_to_file(self, feature_branch, sample_commits, sample_diff_stats):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "pr_description.md")
            result = write_pr_description(
                feature_branch, sample_commits, sample_diff_stats,
                output_path=output_path,
            )
            assert os.path.exists(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "## Summary" in content
            assert result == content

    def test_creates_parent_dirs(self, feature_branch, sample_commits, sample_diff_stats):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "nested", "dir", "pr.md")
            write_pr_description(
                feature_branch, sample_commits, sample_diff_stats,
                output_path=output_path,
            )
            assert os.path.exists(output_path)

    def test_empty_commits_returns_empty_string(self):
        result = write_pr_description("feature/empty", [], {})
        assert isinstance(result, str)
        # Should still return content (even for empty commits)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Test: Diff stats reflected
# ---------------------------------------------------------------------------

class TestDiffStatsReflected:
    """Diff stats should appear somewhere in the output."""

    def test_files_changed_mentioned(self, feature_branch, sample_commits):
        diff_stats = {"files_changed": 12, "insertions": 300, "deletions": 50}
        result = generate_pr_description(feature_branch, sample_commits, diff_stats)
        # Stats should be reflected (e.g., in summary or changes section)
        assert "12" in result or "file" in result.lower()


# ---------------------------------------------------------------------------
# Test: Branch name parsing
# ---------------------------------------------------------------------------

class TestBranchNameParsing:
    """Branch name should influence the PR description."""

    def test_feature_branch_prefix(self, sample_commits, sample_diff_stats):
        result = generate_pr_description("feature/add-jwt-auth", sample_commits, sample_diff_stats)
        assert isinstance(result, str)
        assert len(result) > 50  # Non-trivial content

    def test_fix_branch_prefix(self, sample_commits, sample_diff_stats):
        result = generate_pr_description("fix/null-pointer-exception", sample_commits, sample_diff_stats)
        assert isinstance(result, str)
        assert len(result) > 50
