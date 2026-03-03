"""
Tests for git_inspector.py

Tests cover:
- Feature flag behavior (enabled/disabled)
- git_status() parsing and branch detection
- git_log() commit parsing
- git_hunk() diff parsing with hunk headers
- CLI entry points (--overview, --hunk)
- Graceful fallback when git not available
- Subprocess timeout handling
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.git_inspector import git_hunk, git_log, git_status, main


class TestGitStatus:
    """Tests for git_status() function."""
    
    def test_feature_flag_disabled(self):
        """When feature flag is disabled, return skipped."""
        with patch("tools.git_inspector.get_feature_flag", return_value=False):
            result = git_status()
            assert result == {"skipped": True}
    
    def test_feature_flag_enabled_empty_repo(self):
        """When repo is clean, return empty lists."""
        mock_output = ""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                # Mock git status
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert result["staged"] == []
                assert result["unstaged"] == []
                assert result["untracked"] == []
                assert result["branch"] == "main"
                assert result["error"] is None
    
    def test_staged_files(self):
        """Parse staged files (M, A, D in first column)."""
        mock_output = "M  file1.py\nA  file2.py\n"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert "file1.py" in result["staged"]
                assert "file2.py" in result["staged"]
    
    def test_unstaged_files(self):
        """Parse unstaged files (M, D in second column)."""
        mock_output = " M file1.py\n M file2.py"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert len(result["unstaged"]) == 2
                assert "file1.py" in result["unstaged"]
                assert "file2.py" in result["unstaged"]
        """Parse unstaged files (M, D in second column)."""
        mock_output = " M file1.py\n M file2.py"
        """Parse unstaged files (M, D in second column)."""
        mock_output = " M file1.py\n M file2.py\n"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert len(result["unstaged"]) == 2
                assert "file1.py" in result["unstaged"]
                assert "file2.py" in result["unstaged"]
                assert "file2.py" in result["unstaged"]
    
    def test_untracked_files(self):
        """Parse untracked files (?? status)."""
        mock_output = "?? file1.py\n?? file2.py\n"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert "file1.py" in result["untracked"]
                assert "file2.py" in result["untracked"]
    
    def test_mixed_status(self):
        """Parse mixed staged/unstaged/untracked."""
        mock_output = "M  staged.py\n M unstaged.py\n?? untracked.py\n"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=mock_output),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                result = git_status()
                assert "staged.py" in result["staged"]
                assert "unstaged.py" in result["unstaged"]
                assert "untracked.py" in result["untracked"]
    
    def test_branch_detection(self):
        """Detect current branch name."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=""),
                    MagicMock(returncode=0, stdout="feature/test-branch\n")
                ]
                result = git_status()
                assert result["branch"] == "feature/test-branch"
    
    def test_git_command_failed(self):
        """Handle git command failure."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                result = git_status()
                assert result["error"] == "git command failed"
    
    def test_git_not_found(self):
        """Handle git not installed."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = git_status()
                assert result["error"] == "git not found"
    
    def test_git_timeout(self):
        """Handle git command timeout."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
                result = git_status()
                assert result["error"] == "git command timeout"
    
    def test_custom_cwd(self):
        """Accept custom working directory."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=""),
                    MagicMock(returncode=0, stdout="main\n")
                ]
                git_status(cwd="/custom/path")
                # Verify cwd was passed
                assert mock_run.call_args_list[0][1]["cwd"] == "/custom/path"


class TestGitLog:
    """Tests for git_log() function."""
    
    def test_feature_flag_disabled(self):
        """When feature flag is disabled, return empty list."""
        with patch("tools.git_inspector.get_feature_flag", return_value=False):
            result = git_log()
            assert result == []
    
    def test_single_commit(self):
        """Parse single commit."""
        mock_output = "abc123|Initial commit|Alice|2025-03-01T10:00:00+00:00\n"
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_log()
                assert len(result) == 1
                assert result[0]["hash"] == "abc123"
                assert result[0]["subject"] == "Initial commit"
                assert result[0]["author"] == "Alice"
                assert result[0]["date"] == "2025-03-01T10:00:00+00:00"
    
    def test_multiple_commits(self):
        """Parse multiple commits."""
        mock_output = (
            "abc123|Initial commit|Alice|2025-03-01T10:00:00+00:00\n"
            "def456|Add feature|Bob|2025-03-02T11:00:00+00:00\n"
            "ghi789|Fix bug|Charlie|2025-03-03T12:00:00+00:00\n"
        )
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_log()
                assert len(result) == 3
                assert result[0]["hash"] == "abc123"
                assert result[1]["hash"] == "def456"
                assert result[2]["hash"] == "ghi789"
    
    def test_custom_n_parameter(self):
        """Accept custom number of commits."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                git_log(n=20)
                # Verify -n 20 was passed
                call_args = mock_run.call_args[0][0]
                assert "-n" in call_args
                assert "20" in call_args
    
    def test_git_command_failed(self):
        """Handle git command failure."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                result = git_log()
                assert result == []
    
    def test_git_not_found(self):
        """Handle git not installed."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = git_log()
                assert result == []
    
    def test_git_timeout(self):
        """Handle git command timeout."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
                result = git_log()
                assert result == []
    
    def test_empty_repo(self):
        """Handle empty repository."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = git_log()
                assert result == []


class TestGitHunk:
    """Tests for git_hunk() function."""
    
    def test_feature_flag_disabled(self):
        """When feature flag is disabled, return empty list."""
        with patch("tools.git_inspector.get_feature_flag", return_value=False):
            result = git_hunk()
            assert result == []
    
    def test_single_hunk(self):
        """Parse single hunk."""
        mock_output = (
            "diff --git a/file.py b/file.py\n"
            "@@ -1,3 +1,4 @@ def foo():\n"
            " line1\n"
            " line2\n"
            "+line3\n"
            " line4\n"
        )
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_hunk()
                assert len(result) == 1
                assert result[0]["file"] == "file.py"
                assert result[0]["old_start"] == 1
                assert result[0]["old_count"] == 3
                assert result[0]["new_start"] == 1
                assert result[0]["new_count"] == 4
                assert result[0]["context"] == "def foo():"
    
    def test_multiple_hunks_same_file(self):
        """Parse multiple hunks in same file."""
        mock_output = (
            "diff --git a/file.py b/file.py\n"
            "@@ -1,3 +1,4 @@ def foo():\n"
            " line1\n"
            "+line2\n"
            " line3\n"
            "@@ -10,3 +11,4 @@ def bar():\n"
            " line10\n"
            "+line11\n"
            " line12\n"
        )
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_hunk()
                assert len(result) == 2
                assert result[0]["old_start"] == 1
                assert result[1]["old_start"] == 10
    
    def test_multiple_files(self):
        """Parse hunks from multiple files."""
        mock_output = (
            "diff --git a/file1.py b/file1.py\n"
            "@@ -1,3 +1,4 @@\n"
            "+line\n"
            "diff --git a/file2.py b/file2.py\n"
            "@@ -5,2 +5,3 @@\n"
            "+line\n"
        )
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_hunk()
                assert len(result) == 2
                assert result[0]["file"] == "file1.py"
                assert result[1]["file"] == "file2.py"
    
    def test_hunk_lines_captured(self):
        """Capture hunk content lines."""
        mock_output = (
            "diff --git a/file.py b/file.py\n"
            "@@ -1,3 +1,4 @@\n"
            " context\n"
            "-removed\n"
            "+added\n"
            " context\n"
        )
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
                result = git_hunk()
                assert len(result[0]["lines"]) == 4
                assert " context" in result[0]["lines"]
                assert "-removed" in result[0]["lines"]
                assert "+added" in result[0]["lines"]
    
    def test_file_path_parameter(self):
        """Accept specific file path."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                git_hunk(file_path="specific.py")
                # Verify file path was passed
                call_args = mock_run.call_args[0][0]
                assert "specific.py" in call_args
    
    def test_git_command_failed(self):
        """Handle git command failure."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                result = git_hunk()
                assert result == []
    
    def test_git_not_found(self):
        """Handle git not installed."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = git_hunk()
                assert result == []
    
    def test_git_timeout(self):
        """Handle git command timeout."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
                result = git_hunk()
                assert result == []
    
    def test_no_diff(self):
        """Handle no diff output."""
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                result = git_hunk()
                assert result == []


class TestCLI:
    """Tests for CLI entry points."""
    
    def test_overview_command(self, capsys):
        """Test --overview command."""
        with patch("tools.git_inspector.git_status") as mock_status:
            with patch("tools.git_inspector.git_log") as mock_log:
                mock_status.return_value = {"branch": "main", "staged": []}
                mock_log.return_value = [{"hash": "abc123", "subject": "test"}]
                
                with patch("sys.argv", ["git_inspector.py", "--overview"]):
                    main()
                
                captured = capsys.readouterr()
                output = json.loads(captured.out)
                assert "status" in output
                assert "log" in output
    
    def test_hunk_command(self, capsys):
        """Test --hunk command."""
        with patch("tools.git_inspector.git_hunk") as mock_hunk:
            mock_hunk.return_value = [{"file": "test.py", "old_start": 1}]
            
            with patch("sys.argv", ["git_inspector.py", "--hunk"]):
                main()
            
            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert "hunks" in output
    
    def test_hunk_with_file(self, capsys):
        """Test --hunk --file command."""
        with patch("tools.git_inspector.git_hunk") as mock_hunk:
            mock_hunk.return_value = []
            
            with patch("sys.argv", ["git_inspector.py", "--hunk", "--file", "test.py"]):
                main()
            
            # Verify file_path was passed
            mock_hunk.assert_called_once()
            call_args = mock_hunk.call_args
            399#JS|            # Check positional or keyword args
            if len(call_args[0]) > 1:
                assert call_args[0][1] == "test.py"
            else:
                assert call_args[1].get("file_path") == "test.py"
    
    def test_no_arguments(self, capsys):
        """Test with no arguments."""
        with patch("sys.argv", ["git_inspector.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
    
    def test_unknown_command(self, capsys):
        """Test with unknown command."""
        with patch("sys.argv", ["git_inspector.py", "--unknown"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestIntegration:
    """Integration tests with real git operations (if available)."""
    
    @pytest.mark.skipif(
        not __import__("shutil").which("git"),
        reason="git not available"
    )
    def test_real_git_status(self, tmp_path):
        """Test with real git repository."""
        import subprocess
        
        # Initialize repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True
        )
        
        # Create and stage a file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        
        with patch("tools.git_inspector.get_feature_flag", return_value=True):
            result = git_status(cwd=str(tmp_path))
            assert "test.py" in result["staged"]
