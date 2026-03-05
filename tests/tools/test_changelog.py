"""Tests for synthesize_changelog() and write_changelog() in tools/changelog_generator.py"""

import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.changelog_generator import synthesize_changelog, write_changelog


# ---------------------------------------------------------------------------
# synthesize_changelog
# ---------------------------------------------------------------------------


class TestSynthesizeChangelog:
    """Tests for synthesize_changelog()."""

    def test_groups_commits_by_type(self):
        """Commits are grouped into Features, Bug Fixes, and Other sections."""
        commits = [
            {"message": "feat(auth): add JWT validation"},
            {"message": "fix(api): handle null response"},
            {"message": "chore: update deps"},
        ]
        result = synthesize_changelog(commits)
        assert "### Features" in result
        assert "### Bug Fixes" in result
        assert "### Other" in result
        assert "JWT validation" in result
        assert "handle null response" in result
        assert "update deps" in result

    def test_empty_groups_omitted(self):
        """Sections with no commits are not present in output."""
        commits = [{"message": "feat(auth): add login"}]
        result = synthesize_changelog(commits)
        assert "### Features" in result
        assert "### Bug Fixes" not in result
        assert "### Breaking Changes" not in result
        assert "### Other" not in result

    def test_empty_commits_returns_empty(self):
        """Empty commits list returns empty string."""
        result = synthesize_changelog([])
        assert result == ""

    def test_breaking_change_detected_from_message(self):
        """BREAKING CHANGE in message body groups under Breaking Changes."""
        commits = [
            {"message": "BREAKING CHANGE: removed deprecated endpoint"},
        ]
        result = synthesize_changelog(commits)
        assert "### Breaking Changes" in result
        assert "removed deprecated endpoint" in result

    def test_breaking_change_via_exclamation(self):
        """feat!: syntax groups under Breaking Changes."""
        commits = [
            {"message": "feat!: drop Python 3.7 support"},
        ]
        result = synthesize_changelog(commits)
        assert "### Breaking Changes" in result
        assert "drop Python 3.7 support" in result

    def test_output_starts_with_changes_header(self):
        """Output starts with ## Changes header."""
        commits = [{"message": "feat: new feature"}]
        result = synthesize_changelog(commits)
        assert result.startswith("## Changes")

    def test_bullet_list_format(self):
        """Each commit is rendered as a markdown bullet."""
        commits = [{"message": "feat(auth): add JWT validation"}]
        result = synthesize_changelog(commits)
        assert "- feat(auth): add JWT validation" in result

    def test_multiple_types_grouped_correctly(self):
        """docs, test, refactor, chore all go to Other."""
        commits = [
            {"message": "docs: update README"},
            {"message": "test: add unit tests"},
            {"message": "refactor(core): simplify logic"},
            {"message": "chore: lint"},
        ]
        result = synthesize_changelog(commits)
        assert "### Other" in result
        assert "### Features" not in result
        assert "### Bug Fixes" not in result
        # All four should be in the Other section
        assert "update README" in result
        assert "add unit tests" in result
        assert "simplify logic" in result
        assert "lint" in result

    def test_preserves_original_message_in_bullet(self):
        """The full original commit message is used in the bullet."""
        commits = [{"message": "fix(db): correct migration order"}]
        result = synthesize_changelog(commits)
        assert "- fix(db): correct migration order" in result

    def test_non_conventional_commit_goes_to_other(self):
        """Messages that don't match conventional format go to Other."""
        commits = [{"message": "random commit message without type"}]
        result = synthesize_changelog(commits)
        assert "### Other" in result
        assert "random commit message without type" in result


# ---------------------------------------------------------------------------
# write_changelog
# ---------------------------------------------------------------------------


class TestWriteChangelog:
    """Tests for write_changelog()."""

    def test_returns_string_when_no_output_path(self):
        """Returns markdown string when output_path is None."""
        commits = [{"message": "feat: something new"}]
        result = write_changelog(commits)
        assert isinstance(result, str)
        assert "### Features" in result

    def test_writes_to_file_when_path_given(self):
        """Writes changelog to file and returns the content."""
        commits = [
            {"message": "feat(ui): add dark mode"},
            {"message": "fix: typo in docs"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "changelog.md")
            result = write_changelog(commits, output_path=outpath)
            assert os.path.exists(outpath)
            with open(outpath, "r") as f:
                content = f.read()
            assert content == result
            assert "### Features" in content
            assert "### Bug Fixes" in content

    def test_creates_parent_directories(self):
        """Creates parent directories if they don't exist."""
        commits = [{"message": "feat: init"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "nested", "dir", "changelog.md")
            result = write_changelog(commits, output_path=outpath)
            assert os.path.exists(outpath)

    def test_empty_commits_returns_empty_string(self):
        """Empty commits with no output_path returns empty string."""
        result = write_changelog([])
        assert result == ""

    def test_empty_commits_does_not_write_file(self):
        """Empty commits with output_path does not create file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "changelog.md")
            result = write_changelog([], output_path=outpath)
            assert result == ""
            assert not os.path.exists(outpath)
