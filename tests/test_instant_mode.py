"""Tests for runtime/instant_mode.py and YOLO-proof policy enforcement.

Coverage:
- Happy path project creation
- Clarification needed handling
- Empty/invalid input handling
- YOLO-proof policy enforcement (destructive ops blocked)
- Rollback manifest creation
- CLI JSON output
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.instant_mode import InstantResult, run_instant, main, _run_instant
from runtime.yolo_proof_policy import (
    DestructiveOperationError,
    YoloProofPolicy,
    get_yolo_policy,
)


class TestRunInstantHappyPath:
    """Test happy path for instant mode project creation."""

    def test_run_instant_happy_path_creates_files(self, tmp_path: Path) -> None:
        """Happy path: mock intent classifier returns saas, verify scaffold created."""
        mock_intent = {
            "type": "saas",
            "confidence": 0.95,
            "clarification_needed": False,
            "clarification_prompt": None,
        }
        mock_pack_content = {
            "name": "saas",
            "scaffold": {
                "files": [
                    "README.md",
                    "src/app.py",
                    "tests/__init__.py",
                ]
            },
        }
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_pack_loader_instance = MagicMock()
            mock_pack_loader_instance.load_pack.return_value = True
            mock_pack_loader_cls.return_value = mock_pack_loader_instance
            
            mock_proof_module = MagicMock()
            mock_proof_module.compute_score.return_value = {
                "score": 75,
                "band": "good",
                "breakdown": {
                    "completeness": 0.8,
                    "validity": 0.9,
                    "diversity": 0.6,
                    "traceability": 0.7,
                },
            }
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            with patch("runtime.instant_mode._load_pack") as mock_load_pack:
                mock_load_pack.return_value = mock_pack_content
                
                result = run_instant("saas project", str(tmp_path))
        
        assert result["success"] is True
        assert result["type"] == "saas"
        assert result["confidence"] == 0.95
        assert result.get("clarification_needed") is not True
        assert result["file_count"] == 3
        assert "rollback_manifest_path" in result

    def test_run_instant_records_progress(self, tmp_path: Path) -> None:
        """Verify on_progress callback is called during execution."""
        mock_intent = {
            "type": "landing",
            "confidence": 0.9,
            "clarification_needed": False,
            "clarification_prompt": None,
        }
        mock_pack_content = {"name": "landing", "scaffold": ["README.md"]}
        progress_log: list[dict[str, str]] = []
        
        def on_progress(event: dict[str, str]) -> None:
            progress_log.append(event)
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_pack_loader_cls.return_value.load_pack.return_value = True
            
            mock_proof_module = MagicMock()
            mock_proof_module.compute_score.return_value = {
                "score": 50,
                "band": "moderate",
                "breakdown": {"completeness": 0.5, "validity": 0.5, "diversity": 0.5, "traceability": 0.5},
            }
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            with patch("runtime.instant_mode._load_pack") as mock_load_pack:
                mock_load_pack.return_value = mock_pack_content
                
                result = run_instant("landing page", str(tmp_path), on_progress=on_progress)
        
        assert result["success"] is True
        assert len(progress_log) > 0
        phases = [e["phase"] for e in progress_log]
        assert "classify" in phases
        assert "done" in phases


class TestRunInstantClarificationNeeded:
    """Test clarification needed scenarios."""

    def test_run_instant_clarification_needed_returns_prompt(self, tmp_path: Path) -> None:
        """When intent needs clarification, return clarification prompt instead of scaffold."""
        mock_intent = {
            "type": "unknown",
            "confidence": 0.3,
            "clarification_needed": True,
            "clarification_prompt": "Could you be more specific? Are you building a SaaS, landing page, or e-commerce site?",
        }
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_proof_module = MagicMock()
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            result = run_instant("build me something", str(tmp_path))
        
        assert result["success"] is False
        assert result["clarification_needed"] is True
        assert result["clarification_prompt"] is not None
        assert "more specific" in result["clarification_prompt"]
        assert "file_count" not in result


class TestRunInstantEmptyPrompt:
    """Test error handling for empty or invalid prompts."""

    def test_run_instant_empty_prompt_triggers_clarification(self, tmp_path: Path) -> None:
        """Empty prompt should trigger clarification from classifier."""
        mock_intent = {
            "type": "unknown",
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_prompt": "Please provide a project description.",
        }
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_proof_module = MagicMock()
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            result = run_instant("", str(tmp_path))
        
        assert result["success"] is False
        assert result["clarification_needed"] is True

    def test_run_instant_whitespace_only_prompt(self, tmp_path: Path) -> None:
        """Whitespace-only prompt triggers clarification."""
        mock_intent = {
            "type": "unknown",
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_prompt": "Please provide a project description.",
        }
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_proof_module = MagicMock()
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            result = run_instant("   ", str(tmp_path))
        
        assert result["success"] is False
        assert result["clarification_needed"] is True


class TestYoloPolicyBlocksDestructive:
    """Test YOLO-proof policy blocks destructive operations."""

    def test_yolo_policy_blocks_rm_rf(self) -> None:
        """rm -rf command is blocked by YOLO policy."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("rm -rf /") is True
        assert policy.is_destructive("rm -rf .") is True
        assert policy.is_destructive("sudo rm -rf /home/user") is True
        
        with pytest.raises(DestructiveOperationError) as exc_info:
            policy.enforce("rm -rf /")
        
        assert "BLOCKED" in str(exc_info.value)
        assert "Destructive operation" in str(exc_info.value)
        assert exc_info.value.command == "rm -rf /"

    def test_yolo_policy_blocks_force_push(self) -> None:
        """git push --force is blocked by YOLO policy."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("git push --force") is True
        assert policy.is_destructive("git push -f") is True
        assert policy.is_destructive("git push origin --force") is True
        
        with pytest.raises(DestructiveOperationError):
            policy.enforce("git push --force")

    def test_yolo_policy_blocks_sql_drop(self) -> None:
        """DROP TABLE/DATABASE SQL commands are blocked."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("DROP TABLE users") is True
        assert policy.is_destructive("DROP DATABASE production") is True
        assert policy.is_destructive("TRUNCATE TABLE orders") is True
        
        with pytest.raises(DestructiveOperationError):
            policy.enforce("DROP TABLE users;")

    def test_yolo_policy_blocks_hard_reset(self) -> None:
        """git reset --hard HEAD~ is blocked."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("git reset --hard HEAD~1") is True
        assert policy.is_destructive("git reset --hard HEAD~10") is True
        
        with pytest.raises(DestructiveOperationError):
            policy.enforce("git reset --hard HEAD~3")


class TestYoloPolicyAllowsSafe:
    """Test YOLO-proof policy allows safe operations."""

    def test_yolo_policy_allows_safe_commands(self) -> None:
        """Safe commands should not be flagged as destructive."""
        policy = YoloProofPolicy()
        
        safe_commands = [
            "ls -la",
            "cat file.txt",
            "mkdir new_directory",
            "touch newfile.txt",
            "git status",
            "git add .",
            "git commit -m 'fix bug'",
            "git push",
            "npm install",
            "pip install requests",
            "python script.py",
            "rm single_file.txt",
            "echo 'hello world'",
        ]
        
        for cmd in safe_commands:
            assert policy.is_destructive(cmd) is False, f"'{cmd}' should be safe"
            policy.enforce(cmd)

    def test_yolo_policy_allows_selective_rm(self) -> None:
        """rm without -rf flags is allowed."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("rm file.txt") is False
        assert policy.is_destructive("rm -f file.txt") is False
        assert policy.is_destructive("rm -i directory/file.txt") is False
        
        policy.enforce("rm -f temp.txt")

    def test_yolo_policy_empty_command_is_safe(self) -> None:
        """Empty command is not destructive."""
        policy = YoloProofPolicy()
        
        assert policy.is_destructive("") is False
        assert policy.is_destructive("   ") is False


class TestYoloPolicyPreMutation:
    """Test YOLO policy pre_mutation creates rollback points."""

    def test_pre_mutation_creates_rollback_manifest(self, tmp_path: Path) -> None:
        """pre_mutation should create a rollback manifest."""
        policy = YoloProofPolicy()
        
        target_file = tmp_path / "target.txt"
        target_file.write_text("original content", encoding="utf-8")
        
        result = policy.pre_mutation(
            target_path=str(target_file),
            project_dir=str(tmp_path),
        )
        
        assert "rollback_id" in result
        assert "rollback_path" in result
        assert result["rollback_enabled"] is True
        assert Path(result["rollback_path"]).exists()

    def test_pre_mutation_with_intent_creates_lock(self, tmp_path: Path) -> None:
        """pre_mutation with intent should create test intent lock."""
        policy = YoloProofPolicy()
        
        target_file = tmp_path / "target.txt"
        
        result = policy.pre_mutation(
            target_path=str(target_file),
            project_dir=str(tmp_path),
            intent={"tests": ["test_example"], "expected_pass": True},
        )
        
        assert "rollback_id" in result


class TestYoloPolicyPostCompletion:
    """Test YOLO policy post_completion collects evidence."""

    def test_post_completion_collects_evidence(self, tmp_path: Path) -> None:
        """post_completion should collect evidence."""
        policy = YoloProofPolicy()
        
        mock_result = {"success": True, "files_written": ["file1.py"]}
        
        result = policy.post_completion(
            result=mock_result,
            project_dir=str(tmp_path),
        )
        
        assert result["evidence_collected"] is True
        assert "evidence_timestamp" in result
        assert "completion_validity" in result


class TestInstantModeCliJsonOutput:
    """Test instant mode CLI with --json output."""

    def test_instant_mode_cli_json_output(self, tmp_path: Path) -> None:
        """Test CLI with --json flag returns valid JSON."""
        mock_intent = {
            "type": "saas",
            "confidence": 0.95,
            "clarification_needed": False,
            "clarification_prompt": None,
        }
        mock_pack_content = {"name": "saas", "scaffold": ["README.md"]}
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_pack_loader_cls.return_value.load_pack.return_value = True
            
            mock_proof_module = MagicMock()
            mock_proof_module.compute_score.return_value = {
                "score": 75,
                "band": "good",
                "breakdown": {"completeness": 0.8, "validity": 0.9, "diversity": 0.6, "traceability": 0.7},
            }
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            with patch("runtime.instant_mode._load_pack") as mock_load_pack:
                mock_load_pack.return_value = mock_pack_content
                
                import io
                captured = io.StringIO()
                old_stdout = sys.stdout
                sys.stdout = captured
                
                try:
                    exit_code = main([
                        "--prompt", "saas project",
                        "--target-dir", str(tmp_path),
                        "--json",
                    ])
                finally:
                    sys.stdout = old_stdout
                
                output = captured.getvalue()
        
        assert exit_code == 0
        result = json.loads(output)
        assert result["success"] is True
        assert result["type"] == "saas"

    def test_instant_mode_cli_dry_run(self, tmp_path: Path) -> None:
        """Test CLI with --dry-run flag doesn't write files."""
        mock_intent = {
            "type": "api",
            "confidence": 0.9,
            "clarification_needed": False,
            "clarification_prompt": None,
        }
        mock_pack_content = {"name": "api", "scaffold": ["README.md", "api/__init__.py"]}
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_pack_loader_cls.return_value.load_pack.return_value = True
            
            mock_proof_module = MagicMock()
            mock_proof_module.compute_score.return_value = {
                "score": 60,
                "band": "moderate",
                "breakdown": {"completeness": 0.6, "validity": 0.6, "diversity": 0.6, "traceability": 0.6},
            }
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            with patch("runtime.instant_mode._load_pack") as mock_load_pack:
                mock_load_pack.return_value = mock_pack_content
                
                import io
                captured = io.StringIO()
                old_stdout = sys.stdout
                sys.stdout = captured
                
                try:
                    exit_code = main([
                        "--prompt", "api service",
                        "--target-dir", str(tmp_path),
                        "--json",
                        "--dry-run",
                    ])
                finally:
                    sys.stdout = old_stdout
                
                output = captured.getvalue()
        
        assert exit_code == 0
        result = json.loads(output)
        assert result["dry_run"] is True
        assert not (tmp_path / "README.md").exists()
        assert not (tmp_path / "api" / "__init__.py").exists()


class TestInstantModeRollbackCreation:
    """Test rollback manifest is created correctly."""

    def test_instant_mode_creates_rollback_manifest(self, tmp_path: Path) -> None:
        """Instant mode should create a rollback manifest for the operation."""
        mock_intent = {
            "type": "landing",
            "confidence": 0.9,
            "clarification_needed": False,
            "clarification_prompt": None,
        }
        mock_pack_content = {"name": "landing", "scaffold": ["index.html"]}
        
        with patch("runtime.instant_mode.import_module") as mock_import:
            mock_intent_module = MagicMock()
            mock_intent_module.classify_intent.return_value = mock_intent
            
            mock_pack_loader_cls = MagicMock()
            mock_pack_loader_cls.return_value.load_pack.return_value = True
            
            mock_proof_module = MagicMock()
            mock_proof_module.compute_score.return_value = {
                "score": 70,
                "band": "good",
                "breakdown": {"completeness": 0.7, "validity": 0.8, "diversity": 0.6, "traceability": 0.7},
            }
            
            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "runtime.intent_classifier":
                    return mock_intent_module
                elif module_name == "runtime.pack_loader":
                    m = MagicMock()
                    m.PackLoader = mock_pack_loader_cls
                    return m
                elif module_name == "runtime.proof_score":
                    return mock_proof_module
                raise ImportError(f"Unknown module: {module_name}")
            
            mock_import.side_effect = import_side_effect
            
            with patch("runtime.instant_mode._load_pack") as mock_load_pack:
                mock_load_pack.return_value = mock_pack_content
                
                result = run_instant("landing page", str(tmp_path))
        
        assert result["success"] is True
        assert "rollback_manifest_path" in result
        
        rollback_path = Path(result["rollback_manifest_path"])
        assert rollback_path.exists()
        
        with open(rollback_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        assert "run_id" in manifest
        assert "step_id" in manifest
        assert manifest["run_id"].startswith("instant-landing")


class TestGetYoloPolicy:
    """Test get_yolo_policy singleton."""

    def test_get_yolo_policy_returns_singleton(self) -> None:
        """get_yolo_policy should return the same instance."""
        policy1 = get_yolo_policy()
        policy2 = get_yolo_policy()
        
        assert policy1 is policy2
        assert isinstance(policy1, YoloProofPolicy)


class TestCheckAndPrepare:
    """Test combined check_and_prepare method."""

    def test_check_and_prepare_blocks_destructive(self, tmp_path: Path) -> None:
        """check_and_prepare should block destructive commands."""
        policy = YoloProofPolicy()
        
        with pytest.raises(DestructiveOperationError):
            policy.check_and_prepare(
                command="rm -rf /",
                target_path=str(tmp_path / "file.txt"),
                project_dir=str(tmp_path),
            )

    def test_check_and_prepare_creates_rollback_for_safe(self, tmp_path: Path) -> None:
        """check_and_prepare should create rollback for safe commands."""
        policy = YoloProofPolicy()
        
        result = policy.check_and_prepare(
            command="echo 'hello'",
            target_path=str(tmp_path / "file.txt"),
            project_dir=str(tmp_path),
        )
        
        assert "rollback_id" in result
        assert "rollback_path" in result
        assert result["rollback_enabled"] is True
