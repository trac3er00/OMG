"""
Tests for commit_splitter.py

Tests cover:
- Feature flag behavior (enabled/disabled)
- File classification by extension and test indicators
- Hunk grouping by category
- Test files separated from source code
- Commit plan generation with conventional messages
- Preview formatting
- CLI --dry-run entry point
- Edge cases: empty hunks, single file, mixed types
- Scope derivation and description generation
"""

from unittest.mock import MagicMock, patch

import pytest

from tools.commit_splitter import (
    _classify_file,
    _derive_description,
    _derive_scope,
    analyze_changes,
    generate_commit_plan,
    main,
    preview_commit_plan,
)


# --- Helpers: build mock hunks ---

def _make_hunk(file_path: str, old_start: int = 1, lines: list = None) -> dict:
    """Build a minimal hunk dict matching git_inspector.git_hunk() output."""
    return {
        "file": file_path,
        "old_start": old_start,
        "old_count": 3,
        "new_start": old_start,
        "new_count": 4,
        "context": "",
        "lines": lines or ["+added line"],
    }


# ================================================================
# Test _classify_file
# ================================================================

class TestClassifyFile:
    """Tests for internal _classify_file() helper."""

    def test_python_extension(self):
        assert _classify_file("src/utils.py") == "python"

    def test_javascript_extension(self):
        assert _classify_file("src/app.ts") == "javascript"

    def test_config_extension(self):
        assert _classify_file("settings.json") == "config"
        assert _classify_file("config.yaml") == "config"
        assert _classify_file("pyproject.toml") == "config"

    def test_docs_extension(self):
        assert _classify_file("README.md") == "docs"
        assert _classify_file("CHANGELOG.rst") == "docs"

    def test_shell_extension(self):
        assert _classify_file("setup.sh") == "shell"

    def test_styles_extension(self):
        assert _classify_file("main.css") == "styles"
        assert _classify_file("theme.scss") == "styles"

    def test_markup_extension(self):
        assert _classify_file("index.html") == "markup"

    def test_test_file_overrides_extension(self):
        """Test files are always categorized as 'tests' regardless of extension."""
        assert _classify_file("tests/test_utils.py") == "tests"
        assert _classify_file("src/__tests__/app.test.ts") == "tests"
        assert _classify_file("spec/helper.spec.js") == "tests"
        assert _classify_file("conftest.py") == "tests"

    def test_unknown_extension(self):
        assert _classify_file("Makefile") == "other"
        assert _classify_file("Dockerfile") == "other"

    def test_none_file_path(self):
        assert _classify_file(None) == "other"


# ================================================================
# Test analyze_changes
# ================================================================

class TestAnalyzeChanges:
    """Tests for analyze_changes() function."""

    def test_feature_flag_disabled_returns_empty(self):
        """When OMG_AI_COMMIT_ENABLED is False, return empty list."""
        with patch("tools.commit_splitter._is_enabled", return_value=False):
            result = analyze_changes()
            assert result == []

    def test_no_hunks_returns_empty(self):
        """When git_hunk returns nothing, return empty list."""
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = []
                    result = analyze_changes()
                    assert result == []

    def test_single_python_file(self):
        """Single python file grouped correctly."""
        hunks = [_make_hunk("tools/helper.py")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    result = analyze_changes()
                    assert len(result) == 1
                    assert result[0]["group_name"] == "python"
                    assert result[0]["suggested_type"] == "feat"
                    assert "tools/helper.py" in result[0]["files"]

    def test_test_files_separated(self):
        """Test files get their own group, separate from source."""
        hunks = [
            _make_hunk("tools/helper.py"),
            _make_hunk("tests/tools/test_helper.py"),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    result = analyze_changes()
                    group_names = [g["group_name"] for g in result]
                    assert "python" in group_names
                    assert "tests" in group_names

    def test_multiple_categories(self):
        """Mixed file types create separate groups."""
        hunks = [
            _make_hunk("tools/splitter.py"),
            _make_hunk("README.md"),
            _make_hunk("settings.json"),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    result = analyze_changes()
                    group_names = sorted([g["group_name"] for g in result])
                    assert group_names == ["config", "docs", "python"]

    def test_multiple_hunks_same_file(self):
        """Multiple hunks in one file still produce a single group entry."""
        hunks = [
            _make_hunk("tools/helper.py", old_start=1),
            _make_hunk("tools/helper.py", old_start=50),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    result = analyze_changes()
                    assert len(result) == 1
                    assert len(result[0]["files"]) == 1
                    assert len(result[0]["hunks"]) == 2

    def test_hunks_preserved_per_group(self):
        """Each group carries its raw hunks."""
        hunks = [
            _make_hunk("src/app.ts"),
            _make_hunk("tests/app.test.ts"),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    result = analyze_changes()
                    for group in result:
                        assert len(group["hunks"]) >= 1


# ================================================================
# Test generate_commit_plan
# ================================================================

class TestGenerateCommitPlan:
    """Tests for generate_commit_plan() function."""

    def test_feature_flag_disabled_empty_plan(self):
        """When disabled, return empty plan structure."""
        with patch("tools.commit_splitter._is_enabled", return_value=False):
            plan = generate_commit_plan()
            assert plan["groups"] == []
            assert plan["proposed_commits"] == []
            assert plan["total_commits"] == 0

    def test_conventional_commit_format(self):
        """Messages follow type(scope): description format."""
        hunks = [_make_hunk("tools/helper.py")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    plan = generate_commit_plan()
                    msg = plan["proposed_commits"][0]["message"]
                    # Must contain type(scope): description
                    assert "(" in msg
                    assert "):" in msg
                    assert msg.startswith("feat(")

    def test_total_commits_matches_groups(self):
        """total_commits matches number of proposed commits."""
        hunks = [
            _make_hunk("tools/splitter.py"),
            _make_hunk("README.md"),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    plan = generate_commit_plan()
                    assert plan["total_commits"] == len(plan["proposed_commits"])
                    assert plan["total_commits"] == 2

    def test_test_group_uses_test_type(self):
        """Test file groups get 'test' commit type."""
        hunks = [_make_hunk("tests/test_foo.py")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    plan = generate_commit_plan()
                    msg = plan["proposed_commits"][0]["message"]
                    assert msg.startswith("test(")

    def test_docs_group_uses_docs_type(self):
        """Docs file groups get 'docs' commit type."""
        hunks = [_make_hunk("docs/guide.md")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    plan = generate_commit_plan()
                    msg = plan["proposed_commits"][0]["message"]
                    assert msg.startswith("docs(")

    def test_each_commit_has_files_and_hunks(self):
        """Each proposed commit carries files and hunks."""
        hunks = [_make_hunk("tools/helper.py")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    plan = generate_commit_plan()
                    commit = plan["proposed_commits"][0]
                    assert "files" in commit
                    assert "hunks" in commit
                    assert "message" in commit
                    assert len(commit["files"]) > 0


# ================================================================
# Test preview_commit_plan
# ================================================================

class TestPreviewCommitPlan:
    """Tests for preview_commit_plan() function."""

    def test_disabled_shows_notice(self):
        """When disabled, show descriptive notice."""
        with patch("tools.commit_splitter._is_enabled", return_value=False):
            output = preview_commit_plan()
            assert "disabled" in output.lower() or "OMG_AI_COMMIT_ENABLED" in output

    def test_no_changes_shows_notice(self):
        """When no changes found, show appropriate message."""
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = []
                    output = preview_commit_plan()
                    assert "No uncommitted changes" in output

    def test_preview_contains_commit_messages(self):
        """Preview output includes commit messages and file list."""
        hunks = [
            _make_hunk("tools/helper.py"),
            _make_hunk("tests/test_helper.py"),
        ]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    output = preview_commit_plan()
                    assert "Proposed Commit Plan" in output
                    assert "tools/helper.py" in output
                    assert "tests/test_helper.py" in output
                    assert "preview only" in output.lower()

    def test_preview_shows_total_count(self):
        """Preview includes total number of proposed commits."""
        hunks = [_make_hunk("src/app.py")]
        with patch("tools.commit_splitter._is_enabled", return_value=True):
            with patch("tools.commit_splitter._ensure_imports"):
                with patch("tools.commit_splitter._git_inspector") as mock_gi:
                    mock_gi.git_hunk.return_value = hunks
                    output = preview_commit_plan()
                    assert "Total proposed commits: 1" in output


# ================================================================
# Test _derive_scope and _derive_description helpers
# ================================================================

class TestHelpers:
    """Tests for internal helper functions."""

    def test_derive_scope_single_dir(self):
        assert _derive_scope(["tools/helper.py"]) == "tools"

    def test_derive_scope_root_file(self):
        assert _derive_scope(["setup.py"]) == "setup"

    def test_derive_scope_empty(self):
        assert _derive_scope([]) == "general"

    def test_derive_scope_most_common_dir(self):
        files = ["tools/a.py", "tools/b.py", "hooks/c.py"]
        assert _derive_scope(files) == "tools"

    def test_derive_description_single_test(self):
        desc = _derive_description("tests", ["tests/test_foo.py"])
        assert "test_foo.py" in desc

    def test_derive_description_multiple_docs(self):
        desc = _derive_description("docs", ["a.md", "b.md"])
        assert "2" in desc
        assert "documentation" in desc


# ================================================================
# Test CLI
# ================================================================

class TestCLI:
    """Tests for CLI entry point."""

    def test_dry_run_prints_preview(self, capsys):
        """--dry-run prints preview output."""
        with patch("tools.commit_splitter.preview_commit_plan") as mock_preview:
            mock_preview.return_value = "mock preview output"
            with patch("sys.argv", ["commit_splitter.py", "--dry-run"]):
                main()
            captured = capsys.readouterr()
            assert "mock preview output" in captured.out

    def test_no_args_exits_with_error(self):
        """No arguments exits with code 1."""
        with patch("sys.argv", ["commit_splitter.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_unknown_arg_exits_with_error(self):
        """Unknown argument exits with code 1."""
        with patch("sys.argv", ["commit_splitter.py", "--unknown"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
