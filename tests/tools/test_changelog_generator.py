"""Tests for tools/changelog_generator.py"""

import os
import sys
import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_COMMITS = [
    {
        "hash": "abc1234",
        "subject": "feat(auth): add OAuth2 login",
        "author": "Alice",
        "date": "2026-03-01",
    },
    {
        "hash": "def5678",
        "subject": "fix(api): handle null response",
        "author": "Bob",
        "date": "2026-03-01",
    },
    {
        "hash": "ghi9012",
        "subject": "docs: update README",
        "author": "Carol",
        "date": "2026-03-01",
    },
    {
        "hash": "jkl3456",
        "subject": "chore: bump dependencies",
        "author": "Dave",
        "date": "2026-03-01",
    },
    {
        "hash": "mno7890",
        "subject": "refactor(core): simplify router logic",
        "author": "Eve",
        "date": "2026-03-01",
    },
    {
        "hash": "pqr1234",
        "subject": "perf(db): add index on users table",
        "author": "Frank",
        "date": "2026-03-01",
    },
    {
        "hash": "stu5678",
        "subject": "feat!: BREAKING CHANGE drop Python 3.7",
        "author": "Grace",
        "date": "2026-03-01",
    },
    {
        "hash": "vwx9012",
        "subject": "not a conventional commit",
        "author": "Hank",
        "date": "2026-03-01",
    },
]


def _make_git_log_mock(commits=None):
    """Return a mock for git_inspector.git_log that yields given commits."""
    if commits is None:
        commits = SAMPLE_COMMITS
    return MagicMock(return_value=commits)


# ---------------------------------------------------------------------------
# parse_commit_log
# ---------------------------------------------------------------------------


class TestParseCommitLog:
    """Tests for parse_commit_log()."""

    def test_returns_empty_when_flag_disabled(self):
        """Returns [] when OMG_CHANGELOG_ENABLED is False (default)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OMG_CHANGELOG_ENABLED", None)
            from tools import changelog_generator
            # Reset lazy import cache so flag is re-evaluated
            changelog_generator._get_feature_flag = None
            changelog_generator._git_inspector = None

            with patch("hooks._common.get_feature_flag", return_value=False):
                result = changelog_generator.parse_commit_log(".")
        assert result == []

    def test_returns_empty_when_git_log_empty(self):
        """Returns [] when git_log returns no commits."""
        with patch("hooks._common.get_feature_flag", return_value=True):
            from tools import changelog_generator
            changelog_generator._get_feature_flag = None
            changelog_generator._git_inspector = None

            with patch("hooks._common.get_feature_flag", return_value=True):
                changelog_generator._ensure_imports()
                with patch.object(changelog_generator._git_inspector, "git_log", return_value=[]):
                    result = changelog_generator.parse_commit_log(".")
        assert result == []

    def test_parses_feat_commit(self):
        """Parses a feat(scope): description commit correctly."""
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(
                changelog_generator._git_inspector,
                "git_log",
                return_value=[SAMPLE_COMMITS[0]],
            ):
                result = changelog_generator.parse_commit_log(".")

        assert len(result) == 1
        c = result[0]
        assert c["type"] == "feat"
        assert c["scope"] == "auth"
        assert c["description"] == "add OAuth2 login"
        assert c["hash"] == "abc1234"[:7]
        assert c["breaking"] is False

    def test_parses_fix_commit_without_scope(self):
        """Parses fix: description (no scope) correctly."""
        commit = {
            "hash": "aaa0001",
            "subject": "fix: correct off-by-one error",
            "author": "X",
            "date": "2026-03-01",
        }
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=[commit]):
                result = changelog_generator.parse_commit_log(".")

        assert len(result) == 1
        assert result[0]["scope"] == ""
        assert result[0]["type"] == "fix"

    def test_skips_non_conventional_commits(self):
        """Commits that don't match conventional format are skipped."""
        commits = [
            {"hash": "bbb0001", "subject": "WIP: something", "author": "X", "date": "2026-03-01"},
            {"hash": "bbb0002", "subject": "Merge branch main", "author": "X", "date": "2026-03-01"},
        ]
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=commits):
                result = changelog_generator.parse_commit_log(".")

        assert result == []

    def test_detects_breaking_change_in_subject(self):
        """Marks breaking=True when BREAKING CHANGE appears in subject."""
        commit = {
            "hash": "ccc0001",
            "subject": "feat: BREAKING CHANGE remove legacy API",
            "author": "X",
            "date": "2026-03-01",
        }
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=[commit]):
                result = changelog_generator.parse_commit_log(".")

        assert result[0]["breaking"] is True

    def test_detects_breaking_change_via_exclamation(self):
        """Marks breaking=True when type! prefix is used."""
        commit = {
            "hash": "ddd0001",
            "subject": "feat!: drop support for v1 API",
            "author": "X",
            "date": "2026-03-01",
        }
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=[commit]):
                result = changelog_generator.parse_commit_log(".")

        assert result[0]["breaking"] is True

    def test_all_supported_types_parsed(self):
        """All supported conventional commit types are parsed."""
        types = ["feat", "fix", "docs", "style", "refactor", "test", "chore", "perf", "ci", "build"]
        commits = [
            {"hash": f"eee000{i}", "subject": f"{t}: some change", "author": "X", "date": "2026-03-01"}
            for i, t in enumerate(types)
        ]
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=commits):
                result = changelog_generator.parse_commit_log(".")

        parsed_types = {c["type"] for c in result}
        assert parsed_types == set(types)

    def test_unknown_type_skipped(self):
        """Commit types not in CONVENTIONAL_TYPES are skipped."""
        commit = {
            "hash": "fff0001",
            "subject": "wip: half-done feature",
            "author": "X",
            "date": "2026-03-01",
        }
        from tools import changelog_generator
        changelog_generator._get_feature_flag = None
        changelog_generator._git_inspector = None

        with patch("hooks._common.get_feature_flag", return_value=True):
            changelog_generator._ensure_imports()
            with patch.object(changelog_generator._git_inspector, "git_log", return_value=[commit]):
                result = changelog_generator.parse_commit_log(".")

        assert result == []


# ---------------------------------------------------------------------------
# generate_changelog_entry
# ---------------------------------------------------------------------------


class TestGenerateChangelogEntry:
    """Tests for generate_changelog_entry()."""

    def _parsed_commits(self):
        """Return a small set of pre-parsed commits for testing."""
        return [
            {"type": "feat", "scope": "auth", "description": "add login", "hash": "abc1234", "author": "A", "date": "2026-03-01", "breaking": False},
            {"type": "fix", "scope": "", "description": "fix crash", "hash": "def5678", "author": "B", "date": "2026-03-01", "breaking": False},
            {"type": "refactor", "scope": "core", "description": "simplify router", "hash": "ghi9012", "author": "C", "date": "2026-03-01", "breaking": False},
            {"type": "chore", "scope": "", "description": "bump deps", "hash": "jkl3456", "author": "D", "date": "2026-03-01", "breaking": False},
        ]

    def test_returns_empty_string_for_empty_commits(self):
        """Returns empty string when commits list is empty."""
        from tools.changelog_generator import generate_changelog_entry
        result = generate_changelog_entry([])
        assert result == ""

    def test_header_contains_version_and_date(self):
        """Entry header contains version label and today's date."""
        from tools.changelog_generator import generate_changelog_entry
        result = generate_changelog_entry(self._parsed_commits(), version="1.2.3")
        today = date.today().isoformat()
        assert f"## [1.2.3] - {today}" in result

    def test_default_version_is_unreleased(self):
        """Default version label is 'Unreleased'."""
        from tools.changelog_generator import generate_changelog_entry
        result = generate_changelog_entry(self._parsed_commits())
        assert "## [Unreleased]" in result

    def test_feat_goes_to_added_section(self):
        """feat commits appear under ### Added."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "feat", "scope": "ui", "description": "new button", "hash": "aaa", "author": "X", "date": "2026-03-01", "breaking": False}]
        result = generate_changelog_entry(commits)
        assert "### Added" in result
        assert "new button" in result

    def test_fix_goes_to_fixed_section(self):
        """fix commits appear under ### Fixed."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "fix", "scope": "", "description": "null pointer", "hash": "bbb", "author": "X", "date": "2026-03-01", "breaking": False}]
        result = generate_changelog_entry(commits)
        assert "### Fixed" in result
        assert "null pointer" in result

    def test_refactor_and_perf_go_to_changed_section(self):
        """refactor and perf commits appear under ### Changed."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [
            {"type": "refactor", "scope": "", "description": "clean up", "hash": "ccc", "author": "X", "date": "2026-03-01", "breaking": False},
            {"type": "perf", "scope": "", "description": "faster query", "hash": "ddd", "author": "X", "date": "2026-03-01", "breaking": False},
        ]
        result = generate_changelog_entry(commits)
        assert "### Changed" in result
        assert "clean up" in result
        assert "faster query" in result

    def test_breaking_change_annotated(self):
        """Breaking commits include [BREAKING] annotation."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "feat", "scope": "", "description": "drop v1", "hash": "eee", "author": "X", "date": "2026-03-01", "breaking": True}]
        result = generate_changelog_entry(commits)
        assert "[BREAKING]" in result

    def test_hash_included_in_entry(self):
        """Short hash is included in each entry."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "fix", "scope": "", "description": "fix it", "hash": "abc1234", "author": "X", "date": "2026-03-01", "breaking": False}]
        result = generate_changelog_entry(commits)
        assert "#abc1234" in result

    def test_scope_included_in_entry(self):
        """Scope is bolded and included in entry when present."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "feat", "scope": "payments", "description": "add stripe", "hash": "fff", "author": "X", "date": "2026-03-01", "breaking": False}]
        result = generate_changelog_entry(commits)
        assert "**payments**" in result

    def test_sections_only_present_when_non_empty(self):
        """Sections with no commits are omitted from output."""
        from tools.changelog_generator import generate_changelog_entry
        commits = [{"type": "feat", "scope": "", "description": "new thing", "hash": "ggg", "author": "X", "date": "2026-03-01", "breaking": False}]
        result = generate_changelog_entry(commits)
        assert "### Fixed" not in result
        assert "### Security" not in result


# ---------------------------------------------------------------------------
# update_changelog
# ---------------------------------------------------------------------------


class TestUpdateChangelog:
    """Tests for update_changelog()."""

    def _mock_parse(self, commits):
        """Patch parse_commit_log to return given commits."""
        from tools import changelog_generator
        return patch.object(changelog_generator, "parse_commit_log", return_value=commits)

    def test_returns_false_when_no_commits(self):
        """Returns False when parse_commit_log returns empty list."""
        from tools import changelog_generator
        with self._mock_parse([]):
            result = changelog_generator.update_changelog(".")
        assert result is False

    def test_creates_changelog_if_missing(self):
        """Creates CHANGELOG.md if it does not exist."""
        commits = [{"type": "feat", "scope": "", "description": "init", "hash": "aaa", "author": "X", "date": "2026-03-01", "breaking": False}]
        from tools import changelog_generator
        with tempfile.TemporaryDirectory() as tmpdir:
            with self._mock_parse(commits):
                result = changelog_generator.update_changelog(tmpdir)
            assert result is True
            assert os.path.exists(os.path.join(tmpdir, "CHANGELOG.md"))

    def test_prepends_entry_after_header(self):
        """New entry is inserted after the # Changelog header."""
        commits = [{"type": "fix", "scope": "", "description": "bug fix", "hash": "bbb", "author": "X", "date": "2026-03-01", "breaking": False}]
        from tools import changelog_generator
        with tempfile.TemporaryDirectory() as tmpdir:
            changelog_path = os.path.join(tmpdir, "CHANGELOG.md")
            with open(changelog_path, "w") as f:
                f.write("# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Fixed\n- old fix\n")
            with self._mock_parse(commits):
                result = changelog_generator.update_changelog(tmpdir)
            assert result is True
            with open(changelog_path) as f:
                content = f.read()
            # New entry should appear before old entry
            new_pos = content.find("bug fix")
            old_pos = content.find("old fix")
            assert new_pos < old_pos

    def test_does_not_overwrite_existing_sections(self):
        """Existing changelog content is preserved after update."""
        commits = [{"type": "feat", "scope": "", "description": "new feature", "hash": "ccc", "author": "X", "date": "2026-03-01", "breaking": False}]
        from tools import changelog_generator
        with tempfile.TemporaryDirectory() as tmpdir:
            changelog_path = os.path.join(tmpdir, "CHANGELOG.md")
            original_content = "# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Fixed\n- existing fix\n"
            with open(changelog_path, "w") as f:
                f.write(original_content)
            with self._mock_parse(commits):
                changelog_generator.update_changelog(tmpdir)
            with open(changelog_path) as f:
                content = f.read()
            assert "existing fix" in content

    def test_returns_true_on_success(self):
        """Returns True when changelog is successfully updated."""
        commits = [{"type": "feat", "scope": "", "description": "something", "hash": "ddd", "author": "X", "date": "2026-03-01", "breaking": False}]
        from tools import changelog_generator
        with tempfile.TemporaryDirectory() as tmpdir:
            with self._mock_parse(commits):
                result = changelog_generator.update_changelog(tmpdir)
        assert result is True

    def test_version_label_used_in_entry(self):
        """Specified version label appears in the written entry."""
        commits = [{"type": "feat", "scope": "", "description": "release", "hash": "eee", "author": "X", "date": "2026-03-01", "breaking": False}]
        from tools import changelog_generator
        with tempfile.TemporaryDirectory() as tmpdir:
            with self._mock_parse(commits):
                changelog_generator.update_changelog(tmpdir, version="2.0.0")
            with open(os.path.join(tmpdir, "CHANGELOG.md")) as f:
                content = f.read()
        assert "[2.0.0]" in content
