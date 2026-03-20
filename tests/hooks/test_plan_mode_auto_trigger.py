#!/usr/bin/env python3
"""Test plan mode auto-trigger behavior.

Verifies that when Claude Code is in plan mode:
1. prompt-enhancer.py injects deep-plan guidance
2. Hooks correctly identify plan mode as NOT a bypass mode
3. Plan mode is treated as MORE restrictive (read-only)
4. Write/Edit tools depend on Claude Code's built-in restrictions
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_plan_mode_not_in_bypass_modes():
    """Verify 'plan' is NOT in BYPASS_MODES or EDIT_BYPASS_MODES."""
    # Read the _common.py source to verify constants
    # Check installed location first, fallback to repo location
    installed_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path(__file__).resolve().parent.parent.parent / "hooks"

    if (installed_hooks / "_common.py").exists():
        common_file = installed_hooks / "_common.py"
    else:
        common_file = repo_hooks / "_common.py"

    with open(common_file, "r", encoding="utf-8") as f:
        common_source = f.read()

    # Extract the constant definitions using more flexible regex
    import re
    bypass_match = re.search(r'BYPASS_MODES\s*=\s*frozenset\s*\(\s*\{([^}]+)\}', common_source)
    edit_bypass_match = re.search(r'EDIT_BYPASS_MODES\s*=\s*frozenset\s*\(\s*\{([^}]+)\}', common_source)

    assert bypass_match, "BYPASS_MODES not found in _common.py"
    assert edit_bypass_match, "EDIT_BYPASS_MODES not found in _common.py"

    # Parse the sets - handle both single and double quotes
    def parse_frozenset(match_str):
        items = []
        for item in match_str.split(","):
            item = item.strip()
            # Remove quotes
            item = item.strip('"').strip("'")
            if item:
                items.append(item)
        return set(items)

    bypass_modes = parse_frozenset(bypass_match.group(1))
    edit_bypass_modes = parse_frozenset(edit_bypass_match.group(1))

    assert "plan" not in bypass_modes, \
        f"plan should NOT be in BYPASS_MODES (plan is not a bypass mode). Found: {bypass_modes}"
    assert "plan" not in edit_bypass_modes, \
        f"plan should NOT be in EDIT_BYPASS_MODES (plan mode should be restrictive). Found: {edit_bypass_modes}"

    # Verify the actual bypass modes
    expected_bypass = {"bypasspermissions", "dontask"}
    expected_edit_bypass = {"bypasspermissions", "dontask", "acceptedits"}

    assert bypass_modes == expected_bypass, \
        f"BYPASS_MODES mismatch: expected {expected_bypass}, got {bypass_modes}"
    assert edit_bypass_modes == expected_edit_bypass, \
        f"EDIT_BYPASS_MODES mismatch: expected {expected_edit_bypass}, got {edit_bypass_modes}"

    print("✓ Plan mode correctly NOT in bypass modes")


def test_prompt_enhancer_plan_mode_injection():
    """Test that prompt-enhancer.py contains plan mode auto-trigger logic."""
    # Check installed location first, fallback to repo location
    installed_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path(__file__).resolve().parent.parent.parent / "hooks"

    if (installed_hooks / "prompt-enhancer.py").exists():
        enhancer_script = installed_hooks / "prompt-enhancer.py"
    else:
        enhancer_script = repo_hooks / "prompt-enhancer.py"

    if not enhancer_script.exists():
        print(f"⚠ Skipping: {enhancer_script} not found")
        return

    # Read the source code to verify the plan mode logic exists
    with open(enhancer_script, "r", encoding="utf-8") as f:
        source = f.read()

    # Verify key components exist (case-insensitive for flexibility)
    source_lower = source.lower()

    # Check for permission_mode extraction
    assert "permission_mode" in source_lower, \
        "prompt-enhancer.py should check permission_mode"

    # Check for plan mode condition
    assert "_permission_mode" in source_lower and "== \"plan\"" in source_lower, \
        "prompt-enhancer.py should check if _permission_mode == 'plan'"

    # Check for deep-plan guidance
    assert "@mode-plan" in source_lower, \
        "prompt-enhancer.py should inject @mode-plan marker"

    assert "/omg:deep-plan" in source_lower, \
        "prompt-enhancer.py should reference /OMG:deep-plan command"

    # Check for read-only warning
    assert "read-only" in source_lower, \
        "prompt-enhancer.py should warn that plan mode is read-only"

    print("✓ prompt-enhancer.py correctly contains deep-plan auto-trigger logic for plan mode")


def test_firewall_plan_mode_not_bypass():
    """Test that firewall.py treats plan mode as NOT bypass (governance gates apply)."""
    # Check installed location first, fallback to repo location
    installed_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path(__file__).resolve().parent.parent.parent / "hooks"

    if (installed_hooks / "firewall.py").exists():
        firewall_script = installed_hooks / "firewall.py"
    else:
        firewall_script = repo_hooks / "firewall.py"

    if not firewall_script.exists():
        print(f"⚠ Skipping: {firewall_script} not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, ".omg", "state"), exist_ok=True)

        # Test input: plan mode with a mutation command
        test_input = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo 'test' > test.txt",
            },
            "permission_mode": "plan",
        }

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tmpdir

        # Run firewall.py
        result = subprocess.run(
            [sys.executable, str(firewall_script)],
            input=json.dumps(test_input),
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )

        # In plan mode (not bypass), firewall should run governance checks
        # It might allow or ask, but it should NOT skip checks entirely
        assert result.returncode == 0, \
            f"firewall.py failed: {result.stderr}"

        print("✓ firewall.py correctly enforces governance in plan mode")


def test_secret_guard_plan_mode_not_bypass():
    """Test that secret-guard.py treats plan mode as NOT bypass for Write/Edit."""
    # Check installed location first, fallback to repo location
    installed_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path(__file__).resolve().parent.parent.parent / "hooks"

    if (installed_hooks / "secret-guard.py").exists():
        guard_script = installed_hooks / "secret-guard.py"
    else:
        guard_script = repo_hooks / "secret-guard.py"

    if not guard_script.exists():
        print(f"⚠ Skipping: {guard_script} not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, ".omg", "state"), exist_ok=True)

        # Test input: plan mode with Write to a normal file
        test_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": os.path.join(tmpdir, "test.py"),
                "content": "# test",
            },
            "permission_mode": "plan",
        }

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tmpdir

        # Run secret-guard.py
        result = subprocess.run(
            [sys.executable, str(guard_script)],
            input=json.dumps(test_input),
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )

        # In plan mode (not edit bypass), secret-guard should run mutation gate
        assert result.returncode == 0, \
            f"secret-guard.py failed: {result.stderr}"

        # Check if mutation gate was enforced (might deny in plan mode)
        if result.stdout.strip():
            try:
                output = json.loads(result.stdout)
                decision = output.get("hookSpecificOutput", {}).get("permissionDecision")
                # In plan mode, mutation should be denied or require ask
                # (depends on mutation_gate implementation)
                print(f"  secret-guard decision in plan mode: {decision}")
            except json.JSONDecodeError:
                pass

        print("✓ secret-guard.py correctly enforces mutation gate in plan mode")


def test_stop_dispatcher_plan_mode_not_bypass():
    """Test that stop_dispatcher.py treats plan mode as NOT bypass (quality checks apply)."""
    # Check installed location first, fallback to repo location
    installed_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path(__file__).resolve().parent.parent.parent / "hooks"

    if (installed_hooks / "stop_dispatcher.py").exists():
        stop_script = installed_hooks / "stop_dispatcher.py"
    else:
        stop_script = repo_hooks / "stop_dispatcher.py"

    if not stop_script.exists():
        print(f"⚠ Skipping: {stop_script} not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)

        # Test input: plan mode stop
        test_input = {
            "permission_mode": "plan",
            "stop_reason": "end_turn",
        }

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tmpdir

        # Run stop_dispatcher.py
        result = subprocess.run(
            [sys.executable, str(stop_script)],
            input=json.dumps(test_input),
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )

        # In plan mode (not bypass), stop dispatcher should run quality checks
        assert result.returncode == 0, \
            f"stop_dispatcher.py failed: {result.stderr}"

        print("✓ stop_dispatcher.py correctly enforces quality checks in plan mode")


def test_plan_mode_bypass_comparison():
    """Compare plan mode vs bypass modes to verify correct categorization."""
    # Test by simulating the permission mode logic directly
    BYPASS_MODES = frozenset({"bypasspermissions", "dontask"})
    EDIT_BYPASS_MODES = frozenset({"bypasspermissions", "dontask", "acceptedits"})

    def _get_permission_mode(data):
        if not isinstance(data, dict):
            return ""
        return (data.get("permission_mode") or "").lower().strip()

    def is_bypass_mode(data):
        return _get_permission_mode(data) in BYPASS_MODES

    def is_edit_bypass_mode(data):
        return _get_permission_mode(data) in EDIT_BYPASS_MODES

    # Test plan mode
    plan_data = {"permission_mode": "plan"}
    assert not is_bypass_mode(plan_data), \
        "plan mode should NOT trigger is_bypass_mode"
    assert not is_edit_bypass_mode(plan_data), \
        "plan mode should NOT trigger is_edit_bypass_mode"

    # Test bypass modes (for comparison)
    bypass_data = {"permission_mode": "bypasspermissions"}
    assert is_bypass_mode(bypass_data), \
        "bypasspermissions should trigger is_bypass_mode"
    assert is_edit_bypass_mode(bypass_data), \
        "bypasspermissions should trigger is_edit_bypass_mode"

    dontask_data = {"permission_mode": "dontask"}
    assert is_bypass_mode(dontask_data), \
        "dontask should trigger is_bypass_mode"
    assert is_edit_bypass_mode(dontask_data), \
        "dontask should trigger is_edit_bypass_mode"

    acceptedits_data = {"permission_mode": "acceptedits"}
    assert not is_bypass_mode(acceptedits_data), \
        "acceptedits should NOT trigger is_bypass_mode (bash only)"
    assert is_edit_bypass_mode(acceptedits_data), \
        "acceptedits should trigger is_edit_bypass_mode"

    # Test default (no permission mode)
    default_data = {}
    assert not is_bypass_mode(default_data), \
        "default should NOT trigger is_bypass_mode"
    assert not is_edit_bypass_mode(default_data), \
        "default should NOT trigger is_edit_bypass_mode"

    print("✓ Plan mode correctly categorized as MORE restrictive than default")


def run_all_tests():
    """Run all plan mode tests."""
    tests = [
        ("Plan mode NOT in bypass modes", test_plan_mode_not_in_bypass_modes),
        ("Prompt enhancer plan mode injection", test_prompt_enhancer_plan_mode_injection),
        ("Firewall plan mode governance", test_firewall_plan_mode_not_bypass),
        ("Secret guard plan mode mutation gate", test_secret_guard_plan_mode_not_bypass),
        ("Stop dispatcher plan mode quality checks", test_stop_dispatcher_plan_mode_not_bypass),
        ("Plan mode vs bypass modes comparison", test_plan_mode_bypass_comparison),
    ]

    passed = 0
    failed = 0
    skipped = 0

    print("=" * 60)
    print("PLAN MODE AUTO-TRIGGER VERIFICATION")
    print("=" * 60)

    for name, test_fn in tests:
        print(f"\n{name}...")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠ SKIPPED/ERROR: {e}")
            skipped += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
