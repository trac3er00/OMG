"""YOLO-Proof Policy Enforcement for OMG.

This module defines YOLO mode governance policy. YOLO mode is speed-optimized
but NOT safety-compromised. It enforces:
- Rollback always enabled (automatic rollback point creation)
- Evidence auto-collected (no user prompts)
- Only block destructive operations (rm -rf, force push, etc.)
- Test-intent auto-lock before mutation and auto-verify after

Use this module when you want fast iteration with proof-backed safety.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from runtime.rollback_manifest import (
    create_rollback_manifest,
    record_side_effect,
    write_rollback_manifest,
)
from runtime.evidence_narrator import check_completion_claim_validity
from runtime.test_intent_lock import lock_intent, verify_intent


class DestructiveOperationError(Exception):
    """Raised when a destructive operation is attempted in YOLO mode."""

    def __init__(self, command: str, pattern: str) -> None:
        self.command = command
        self.pattern = pattern
        super().__init__(
            f"BLOCKED: Destructive operation detected.\n"
            f"Command: {command}\n"
            f"Pattern matched: {pattern}\n"
            f"YOLO mode blocks destructive operations. Use explicit approval if intended."
        )


class YoloProofPolicy:
    """YOLO-proof policy enforcement for fast but safe execution.
    
    YOLO mode principles:
    1. Rollback ALWAYS enabled - every mutation gets a rollback point
    2. Evidence auto-collected - no user prompts, silent collection
    3. Only block destructive ops - speed for safe ops, hard stop for dangerous ones
    4. Test-intent auto-lock - mutations are bracketed by test intent verification
    
    Attributes:
        DESTRUCTIVE_PATTERNS: Regex patterns for destructive operations.
        DESTRUCTIVE_COMMANDS: Literal command substrings to block.
    """
    
    DESTRUCTIVE_COMMANDS: list[str] = [
        "rm -rf",
        "rm -r /",
        "rmdir /s /q",
        "DROP TABLE",
        "DROP DATABASE",
        "TRUNCATE TABLE",
        "git push --force",
        "git push -f",
        "git push origin --force",
        "git push origin -f",
        "dd if=",
        "mkfs",
        "shred ",
        "wipe ",
        "format c:",
        "wipefs",
        "> /dev/sda",
        "fdisk",
    ]
    
    DESTRUCTIVE_PATTERNS: list[str] = [
        r"\brm\s+-[^\s]*r[^\s]*f",  # rm with -rf flags in any order
        r"\bgit\s+push\s+[^\s]*--force",  # git push with --force anywhere
        r"\bgit\s+push\s+[^\s]*-f\b",  # git push with -f
        r"\bgit\s+reset\s+--hard\s+HEAD~",  # hard reset with history rewrite
        r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",  # SQL DROP statements
        r"\bTRUNCATE\s+TABLE\b",  # SQL TRUNCATE
        r"\bDELETE\s+FROM\s+\w+\s*;?\s*$",  # DELETE without WHERE clause
        r"\bchmod\s+777\s+/",  # chmod 777 on root paths
        r"\bchown\s+-R\s+\w+:\w+\s+/[^/]",  # recursive chown on system dirs
    ]
    
    def __init__(self) -> None:
        """Initialize YOLO-proof policy."""
        self._compiled_patterns: list[re.Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.DESTRUCTIVE_PATTERNS
        ]
        self._active_locks: dict[str, dict[str, Any]] = {}
    
    def is_destructive(self, command: str) -> bool:
        """Check if a command is destructive.
        
        Args:
            command: The command string to check.
            
        Returns:
            True if the command matches any destructive pattern.
        """
        if not command:
            return False
            
        normalized = command.strip().lower()
        
        for destructive_cmd in self.DESTRUCTIVE_COMMANDS:
            if destructive_cmd.lower() in normalized:
                return True
        
        for pattern in self._compiled_patterns:
            if pattern.search(command):
                return True
        
        return False
    
    def _get_matching_pattern(self, command: str) -> str | None:
        """Get the pattern that matches a destructive command.
        
        Args:
            command: The command string to check.
            
        Returns:
            The matching pattern string, or None if no match.
        """
        if not command:
            return None
            
        normalized = command.strip().lower()
        
        for destructive_cmd in self.DESTRUCTIVE_COMMANDS:
            if destructive_cmd.lower() in normalized:
                return destructive_cmd
        
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(command):
                return self.DESTRUCTIVE_PATTERNS[i]
        
        return None
    
    def enforce(self, command: str) -> None:
        """Enforce policy by raising if command is destructive.
        
        Args:
            command: The command string to check.
            
        Raises:
            DestructiveOperationError: If the command is destructive.
        """
        matching_pattern = self._get_matching_pattern(command)
        if matching_pattern:
            raise DestructiveOperationError(command, matching_pattern)
    
    def pre_mutation(
        self,
        target_path: str,
        project_dir: str,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        intent: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare for mutation: create rollback point and lock test intent.
        
        This method should be called BEFORE any mutation operation.
        
        Args:
            target_path: Path to the file/directory being mutated.
            project_dir: Project root directory.
            run_id: Optional run identifier (auto-generated if not provided).
            step_id: Optional step identifier (auto-generated if not provided).
            intent: Optional test intent specification for locking.
            
        Returns:
            Dict containing:
            - rollback_id: ID of the created rollback point
            - rollback_path: Path to the rollback manifest file
            - lock_id: ID of the test intent lock (if intent provided)
            - lock_status: Status of the test intent lock
        """
        effective_run_id = run_id or f"yolo-{uuid4().hex[:8]}"
        effective_step_id = step_id or f"step-{uuid4().hex[:8]}"
        
        manifest = create_rollback_manifest(effective_run_id, effective_step_id)
        
        record_side_effect(manifest, {
            "category": "local_file",
            "decision": "pre_mutation_snapshot",
            "reversible": True,
            "reason": "yolo_proof_policy_pre_mutation",
            "target_path": target_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        rollback_path = write_rollback_manifest(project_dir, manifest)
        rollback_id = f"{effective_run_id}-{effective_step_id}"
        
        result: dict[str, Any] = {
            "rollback_id": rollback_id,
            "rollback_path": rollback_path,
            "run_id": effective_run_id,
            "step_id": effective_step_id,
            "rollback_enabled": True,
        }
        
        if intent:
            lock_result = lock_intent(project_dir, {
                "run_id": effective_run_id,
                "touched_paths": [target_path],
                **intent,
            })
            result["lock_id"] = lock_result.get("lock_id")
            result["lock_status"] = lock_result.get("status")
            
            lock_id = lock_result.get("lock_id")
            if lock_id:
                self._active_locks[rollback_id] = {
                    "lock_id": lock_id,
                    "intent": intent,
                    "project_dir": project_dir,
                }
        
        return result
    
    def post_completion(
        self,
        result: dict[str, Any],
        project_dir: str,
        *,
        rollback_id: str | None = None,
        test_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Post-completion: collect evidence and verify test intent.
        
        This method should be called AFTER a mutation operation completes.
        
        Args:
            result: The result from the mutation operation.
            project_dir: Project root directory.
            rollback_id: The rollback ID from pre_mutation (for lock verification).
            test_results: Optional test results for intent verification.
            
        Returns:
            Dict containing:
            - evidence_collected: True if evidence was collected
            - completion_validity: Result of completion claim validity check
            - intent_verification: Result of test intent verification (if applicable)
        """
        completion_validity = check_completion_claim_validity(project_dir)
        
        evidence_result: dict[str, Any] = {
            "evidence_collected": True,
            "evidence_timestamp": datetime.now(timezone.utc).isoformat(),
            "completion_validity": completion_validity,
            "operation_result": result,
        }
        
        if rollback_id and rollback_id in self._active_locks:
            lock_info = self._active_locks.pop(rollback_id)
            lock_id = lock_info.get("lock_id")
            stored_project_dir = lock_info.get("project_dir", project_dir)
            
            if lock_id:
                verification_results = test_results or {
                    "tests": lock_info.get("intent", {}).get("tests", []),
                }
                intent_verification = verify_intent(
                    stored_project_dir,
                    lock_id,
                    verification_results,
                )
                evidence_result["intent_verification"] = intent_verification
                evidence_result["lock_id"] = lock_id
        
        return evidence_result
    
    def check_and_prepare(
        self,
        command: str,
        target_path: str,
        project_dir: str,
        *,
        run_id: str | None = None,
        intent: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Combined check and preparation for YOLO mode execution.
        
        This is a convenience method that:
        1. Checks if the command is destructive (raises if so)
        2. Creates a rollback point
        3. Locks test intent (if provided)
        
        Args:
            command: The command to execute.
            target_path: Path to the file/directory being affected.
            project_dir: Project root directory.
            run_id: Optional run identifier.
            intent: Optional test intent specification.
            
        Returns:
            Pre-mutation result dict (same as pre_mutation).
            
        Raises:
            DestructiveOperationError: If the command is destructive.
        """
        self.enforce(command)
        
        return self.pre_mutation(
            target_path,
            project_dir,
            run_id=run_id,
            intent=intent,
        )


_default_policy: YoloProofPolicy | None = None


def get_yolo_policy() -> YoloProofPolicy:
    """Get the default YOLO-proof policy instance.
    
    Returns:
        The singleton YoloProofPolicy instance.
    """
    global _default_policy
    if _default_policy is None:
        _default_policy = YoloProofPolicy()
    return _default_policy
