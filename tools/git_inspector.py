#!/usr/bin/env python3
"""
Git Inspection Tools for OAL

Read-only git inspection: status, log, and hunk-level diffs.
Feature flag: OAL_GIT_TOOLS_ENABLED (default: False)
"""

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

# Import feature flag helper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hooks._common import get_feature_flag


def git_status(cwd: str = ".") -> Dict[str, Any]:
    """
    Get git status: staged, unstaged, untracked files and current branch.
    
    Args:
        cwd: Working directory (default: current directory)
    
    Returns:
        {
            "skipped": True  # if feature flag disabled
        }
        or
        {
            "staged": ["file1.py", "file2.py"],
            "unstaged": ["file3.py"],
            "untracked": ["file4.py"],
            "branch": "main",
            "error": None
        }
        or
        {
            "error": "git not found"
        }
    """
    # Check feature flag
    if not get_feature_flag("git_tools", default=False):
        return {"skipped": True}
    
    try:
        # Get status with porcelain format
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {"error": "git command failed"}
        
        staged = []
        unstaged = []
        untracked = []
        
        for line in result.stdout.split("\n"):
            if not line:
                continue
            
            status_code = line[:2]
            file_path = line[3:]
            
            # First char: index (staged)
            # Second char: working tree (unstaged)
            if status_code[0] != " ":
                staged.append(file_path)
            if status_code[1] != " ":
                unstaged.append(file_path)
            if status_code == "??":
                untracked.append(file_path)
        
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        
        return {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "branch": branch,
            "error": None
        }
    
    except FileNotFoundError:
        return {"error": "git not found"}
    except subprocess.TimeoutExpired:
        return {"error": "git command timeout"}
    except Exception as e:
        return {"error": str(e)}


def git_log(cwd: str = ".", n: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent N commits with hash, subject, author, and date.
    
    Args:
        cwd: Working directory (default: current directory)
        n: Number of commits to retrieve (default: 10)
    
    Returns:
        List of {hash, subject, author, date} dicts
        Empty list if git not available or feature flag disabled
    """
    # Check feature flag
    if not get_feature_flag("git_tools", default=False):
        return []
    
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-n", str(n), 
             "--format=%H|%s|%an|%ai"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3]
                })
        
        return commits
    
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []


def git_hunk(cwd: str = ".", file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get hunk-level diff for a file or all files.
    
    Args:
        cwd: Working directory (default: current directory)
        file_path: Specific file to diff (None for all files)
    
    Returns:
        List of {file, old_start, old_count, new_start, new_count, context, lines} dicts
        Empty list if no diff or git not available or feature flag disabled
    """
    # Check feature flag
    if not get_feature_flag("git_tools", default=False):
        return []
    
    try:
        cmd = ["git", "diff", "--unified=3"]
        if file_path:
            cmd.append(file_path)
        
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        hunks = []
        current_file = None
        current_hunk = None
        hunk_lines = []
        
        # Regex to match hunk header: @@ -a,b +c,d @@ context
        hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\s*(.*)")
        
        for line in result.stdout.split("\n"):
            # File header
            if line.startswith("diff --git"):
                # Save previous hunk if exists
                if current_hunk and hunk_lines:
                    current_hunk["lines"] = hunk_lines
                    hunks.append(current_hunk)
                    hunk_lines = []
                    current_hunk = None
                
                # Extract filename from "diff --git a/file b/file"
                parts = line.split()
                if len(parts) >= 4:
                    current_file = parts[3][2:]  # Remove "b/" prefix
            
            # Hunk header
            elif line.startswith("@@"):
                # Save previous hunk if exists
                if current_hunk and hunk_lines:
                    current_hunk["lines"] = hunk_lines
                    hunks.append(current_hunk)
                    hunk_lines = []
                
                match = hunk_header_re.match(line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1
                    context = match.group(5).strip()
                    
                    current_hunk = {
                        "file": current_file,
                        "old_start": old_start,
                        "old_count": old_count,
                        "new_start": new_start,
                        "new_count": new_count,
                        "context": context,
                        "lines": []
                    }
            
            # Hunk content
            elif current_hunk is not None:
                if line.startswith("+") or line.startswith("-") or line.startswith(" "):
                    hunk_lines.append(line)
        
        # Save last hunk
        if current_hunk and hunk_lines:
            current_hunk["lines"] = hunk_lines
            hunks.append(current_hunk)
        
        return hunks
    
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  python3 git_inspector.py --overview", file=sys.stderr)
        print("  python3 git_inspector.py --hunk [--file <path>]", file=sys.stderr)
        sys.exit(1)
    
    cwd = os.getcwd()
    
    if sys.argv[1] == "--overview":
        # Return status + log
        status = git_status(cwd)
        log = git_log(cwd)
        result = {
            "status": status,
            "log": log
        }
        print(json.dumps(result, indent=2))
    
    elif sys.argv[1] == "--hunk":
        # Return hunk diff
        file_path = None
        if len(sys.argv) >= 4 and sys.argv[2] == "--file":
            file_path = sys.argv[3]
        
        hunks = git_hunk(cwd, file_path)
        result = {"hunks": hunks}
        print(json.dumps(result, indent=2))
    
    else:
        print(f"Unknown command: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
