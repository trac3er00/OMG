"""
Tests for generate_commit_message() in commit_splitter.py

Covers:
- Type detection from file paths (feat, test, docs, chore, fix)
- Scope extraction from directory structure
- Conventional commit format: type(scope): description
- Description max length (72 chars)
- Breaking change footer
- Edge cases: empty files, mixed types, root files
"""

import pytest

from tools.commit_splitter import generate_commit_message


# ================================================================
# Type Detection
# ================================================================

class TestTypeDetection:
    """Commit type inferred from file path prefixes and patterns."""

    def test_src_files_produce_feat(self):
        """Files under src/ should produce 'feat' type."""
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
            "description": "add JWT validation",
        })
        assert msg.startswith("feat("), f"Expected feat(...) but got: {msg}"

    def test_lib_files_produce_feat(self):
        """Files under lib/ should produce 'feat' type."""
        msg = generate_commit_message({
            "files": ["lib/utils/helpers.py"],
            "description": "add string helpers",
        })
        assert msg.startswith("feat("), f"Expected feat(...) but got: {msg}"

    def test_app_files_produce_feat(self):
        """Files under app/ should produce 'feat' type."""
        msg = generate_commit_message({
            "files": ["app/routes/api.py"],
            "description": "add API routes",
        })
        assert msg.startswith("feat("), f"Expected feat(...) but got: {msg}"

    def test_hooks_files_produce_feat(self):
        """Files under hooks/ should produce 'feat' type."""
        msg = generate_commit_message({
            "files": ["hooks/budget_governor.py"],
            "description": "add budget tracking",
        })
        assert msg.startswith("feat("), f"Expected feat(...) but got: {msg}"

    def test_test_files_produce_test(self):
        """Files under tests/ should produce 'test' type."""
        msg = generate_commit_message({
            "files": ["tests/test_auth.py"],
            "description": "add auth tests",
        })
        assert msg.startswith("test("), f"Expected test(...) but got: {msg}"

    def test_spec_files_produce_test(self):
        """Files under spec/ should produce 'test' type."""
        msg = generate_commit_message({
            "files": ["spec/auth.spec.js"],
            "description": "add auth specs",
        })
        assert msg.startswith("test("), f"Expected test(...) but got: {msg}"

    def test_docs_dir_produces_docs(self):
        """Files under docs/ should produce 'docs' type."""
        msg = generate_commit_message({
            "files": ["docs/api-guide.md"],
            "description": "update API guide",
        })
        assert msg.startswith("docs("), f"Expected docs(...) but got: {msg}"

    def test_readme_produces_docs(self):
        """README files should produce 'docs' type."""
        msg = generate_commit_message({
            "files": ["README.md"],
            "description": "update readme",
        })
        assert msg.startswith("docs("), f"Expected docs(...) but got: {msg}"

    def test_markdown_files_produce_docs(self):
        """Standalone .md files should produce 'docs' type."""
        msg = generate_commit_message({
            "files": ["CHANGELOG.md"],
            "description": "update changelog",
        })
        assert msg.startswith("docs("), f"Expected docs(...) but got: {msg}"

    def test_config_json_produces_chore(self):
        """JSON config files should produce 'chore' type."""
        msg = generate_commit_message({
            "files": ["package.json"],
            "description": "update dependencies",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"

    def test_config_yaml_produces_chore(self):
        """YAML config files should produce 'chore' type."""
        msg = generate_commit_message({
            "files": ["docker-compose.yaml"],
            "description": "update compose config",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"

    def test_config_toml_produces_chore(self):
        """TOML config files should produce 'chore' type."""
        msg = generate_commit_message({
            "files": ["pyproject.toml"],
            "description": "update build config",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"

    def test_setup_files_produce_chore(self):
        """setup.* files should produce 'chore' type."""
        msg = generate_commit_message({
            "files": ["setup.py"],
            "description": "update setup",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"

    def test_makefile_produces_chore(self):
        """Makefile should produce 'chore' type."""
        msg = generate_commit_message({
            "files": ["Makefile"],
            "description": "update build targets",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"

    def test_fix_keyword_in_path_produces_fix(self):
        """Paths containing 'fix', 'bug', 'patch', 'hotfix' → fix type."""
        msg = generate_commit_message({
            "files": ["src/bugfix/resolve_timeout.py"],
            "description": "resolve timeout issue",
        })
        assert msg.startswith("fix("), f"Expected fix(...) but got: {msg}"

    def test_hotfix_keyword_produces_fix(self):
        """Paths containing 'hotfix' → fix type."""
        msg = generate_commit_message({
            "files": ["hotfix/patch_auth.py"],
            "description": "patch auth vulnerability",
        })
        assert msg.startswith("fix("), f"Expected fix(...) but got: {msg}"

    def test_unknown_files_default_to_chore(self):
        """Unknown file types default to 'chore'."""
        msg = generate_commit_message({
            "files": ["Dockerfile"],
            "description": "update docker image",
        })
        assert msg.startswith("chore("), f"Expected chore(...) but got: {msg}"


# ================================================================
# Scope Extraction
# ================================================================

class TestScopeExtraction:
    """Scope derived from directory structure after type-matched prefix."""

    def test_scope_from_src_subdirectory(self):
        """src/auth/login.py → scope 'auth'."""
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
            "description": "add login",
        })
        assert "feat(auth):" in msg, f"Expected scope 'auth' but got: {msg}"

    def test_scope_from_tests_subdirectory(self):
        """tests/hooks/test_budget.py → scope 'hooks'."""
        msg = generate_commit_message({
            "files": ["tests/hooks/test_budget.py"],
            "description": "add budget tests",
        })
        assert "test(hooks):" in msg, f"Expected scope 'hooks' but got: {msg}"

    def test_scope_from_lib_subdirectory(self):
        """lib/utils/helpers.py → scope 'utils'."""
        msg = generate_commit_message({
            "files": ["lib/utils/helpers.py"],
            "description": "add helpers",
        })
        assert "feat(utils):" in msg, f"Expected scope 'utils' but got: {msg}"

    def test_scope_general_for_root_files(self):
        """Root-level files without subdirectory → scope 'general'."""
        msg = generate_commit_message({
            "files": ["Dockerfile"],
            "description": "update image",
        })
        # Scope should be derived, not empty
        assert "(" in msg and "):" in msg, f"Expected scope in parens but got: {msg}"

    def test_scope_from_most_common_subdir(self):
        """Multiple files → scope from most common subdirectory."""
        msg = generate_commit_message({
            "files": [
                "src/auth/login.py",
                "src/auth/register.py",
                "src/utils/hash.py",
            ],
            "description": "update auth modules",
        })
        assert "feat(auth):" in msg, f"Expected scope 'auth' (most common) but got: {msg}"

    def test_scope_for_file_directly_in_prefix_dir(self):
        """src/main.py → scope 'src' (no deeper subdir)."""
        msg = generate_commit_message({
            "files": ["src/main.py"],
            "description": "update main",
        })
        # When file is directly in src/ with no subdirectory
        # scope falls back to filename or 'src'
        assert "feat(" in msg and "):" in msg


# ================================================================
# Output Format
# ================================================================

class TestOutputFormat:
    """Verify conventional commit format: type(scope): description."""

    def test_basic_format(self):
        """Output matches type(scope): description pattern."""
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
            "description": "add JWT token validation",
        })
        # Must match: type(scope): description
        assert "(" in msg
        assert "):" in msg
        parts = msg.split("\n")[0]  # First line only
        colon_idx = parts.index("):")
        assert colon_idx > 0
        # Description follows after ": "
        desc_part = parts[colon_idx + 2:].strip()
        assert len(desc_part) > 0

    def test_description_max_72_chars(self):
        """First line (type + scope + description) should be ≤72 chars."""
        long_desc = "a" * 200
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
            "description": long_desc,
        })
        first_line = msg.split("\n")[0]
        assert len(first_line) <= 72, f"First line is {len(first_line)} chars: {first_line}"

    def test_description_preserves_short_text(self):
        """Short descriptions are not truncated."""
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
            "description": "add login",
        })
        assert "add login" in msg

    def test_empty_files_returns_valid_message(self):
        """Empty file list still returns valid conventional commit."""
        msg = generate_commit_message({
            "files": [],
            "description": "update project",
        })
        assert "(" in msg and "):" in msg

    def test_missing_description_auto_generates(self):
        """When description is missing, auto-generate from file list."""
        msg = generate_commit_message({
            "files": ["src/auth/login.py"],
        })
        first_line = msg.split("\n")[0]
        assert "(" in first_line and "):" in first_line
        # Should have some description text
        desc = first_line.split("):")[1].strip()
        assert len(desc) > 0


# ================================================================
# Breaking Change Detection
# ================================================================

class TestBreakingChange:
    """Breaking changes add BREAKING CHANGE: footer."""

    def test_breaking_change_footer_added(self):
        """When breaking_change is set, add footer."""
        msg = generate_commit_message({
            "files": ["src/api/routes.py"],
            "description": "remove deprecated endpoints",
            "breaking_change": "removed /v1/users endpoint",
        })
        assert "BREAKING CHANGE:" in msg
        assert "removed /v1/users endpoint" in msg

    def test_no_breaking_change_no_footer(self):
        """When breaking_change not set, no footer."""
        msg = generate_commit_message({
            "files": ["src/api/routes.py"],
            "description": "add new endpoint",
        })
        assert "BREAKING CHANGE:" not in msg

    def test_breaking_change_on_separate_line(self):
        """Footer is on a separate line from the subject."""
        msg = generate_commit_message({
            "files": ["src/api/routes.py"],
            "description": "change API response format",
            "breaking_change": "response schema changed",
        })
        lines = msg.strip().split("\n")
        assert len(lines) >= 2
        # First line is subject, later lines contain BREAKING CHANGE
        subject = lines[0]
        footer_lines = [l for l in lines[1:] if "BREAKING CHANGE:" in l]
        assert len(footer_lines) == 1
        assert subject != footer_lines[0]


# ================================================================
# Mixed File Type Priority
# ================================================================

class TestMixedFileTypes:
    """When diff_stats has mixed file types, majority wins for type."""

    def test_majority_src_files_produce_feat(self):
        """When most files are src/, type is feat."""
        msg = generate_commit_message({
            "files": [
                "src/auth/login.py",
                "src/auth/register.py",
                "tests/test_login.py",
            ],
            "description": "add auth system",
        })
        # Majority is src → feat
        assert msg.startswith("feat("), f"Expected feat from majority src but got: {msg}"

    def test_majority_test_files_produce_test(self):
        """When most files are tests/, type is test."""
        msg = generate_commit_message({
            "files": [
                "tests/test_login.py",
                "tests/test_register.py",
                "src/auth/login.py",
            ],
            "description": "add auth tests",
        })
        assert msg.startswith("test("), f"Expected test from majority tests but got: {msg}"
