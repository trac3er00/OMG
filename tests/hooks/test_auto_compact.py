#!/usr/bin/env python3
"""Tests for auto-compact per-phase support in pre-compact hook."""
import json
import os
import tempfile
from datetime import datetime, timedelta
import importlib.util


def load_pre_compact_module():
    """Load pre-compact.py module dynamically."""
    spec = importlib.util.spec_from_file_location(
        "pre_compact",
        os.path.join(os.path.dirname(__file__), "..", "..", "hooks", "pre-compact.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_count_completed_phases():
    """Test _count_completed_phases helper function."""
    module = load_pre_compact_module()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write('## Phase 1\n')
        f.write('- [x] Task 1\n')
        f.write('- [ ] Task 2\n')
        f.write('- [X] Task 3\n')
        f.write('- [x] Task 4\n')
        f.write('## Phase 2\n')
        f.write('- [ ] Task 5\n')
        checklist_path = f.name

    try:
        count = module._count_completed_phases(checklist_path)
        assert count == 3, f"Expected 3 completed phases, got {count}"
    finally:
        os.unlink(checklist_path)


def test_save_and_load_auto_compact_state():
    """Test saving and loading auto-compact state."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, '.omg', 'state')
        os.makedirs(state_dir, exist_ok=True)

        # Save state
        module._save_auto_compact_state(tmpdir, 5, 100)

        # Load state
        state = module._load_auto_compact_state(tmpdir)

        assert state['last_phase_count'] == 5
        assert state['tool_count_at_compact'] == 100
        assert state['last_compact_ts'] is not None

        # Verify timestamp is recent (within last minute)
        ts = datetime.fromisoformat(state['last_compact_ts'])
        assert (datetime.now() - ts).total_seconds() < 60


def test_load_auto_compact_state_missing_file():
    """Test loading state when no state file exists."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        state = module._load_auto_compact_state(tmpdir)

        assert state['last_compact_ts'] is None
        assert state['last_phase_count'] == 0
        assert state['tool_count_at_compact'] == 0


def test_count_tool_calls_since():
    """Test counting tool calls since a timestamp."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'tool-ledger.jsonl')

        # Create ledger with timestamps
        base_time = datetime.now() - timedelta(hours=1)
        cutoff_time = base_time + timedelta(minutes=30)

        with open(ledger_path, 'w') as f:
            # 5 entries before cutoff
            for i in range(5):
                entry = {
                    'ts': (base_time + timedelta(minutes=i)).isoformat(),
                    'tool': 'Edit',
                    'file': f'old{i}.py'
                }
                f.write(json.dumps(entry) + '\n')

            # 3 entries after cutoff (starting 1 minute after to avoid edge case)
            for i in range(3):
                entry = {
                    'ts': (cutoff_time + timedelta(minutes=i+1)).isoformat(),
                    'tool': 'Edit',
                    'file': f'new{i}.py'
                }
                f.write(json.dumps(entry) + '\n')

        count = module._count_tool_calls_since(ledger_path, cutoff_time.isoformat())
        # Function uses > (not >=), so entries at exactly cutoff_time are excluded
        assert count == 3, f"Expected 3 tool calls after cutoff, got {count}"


def test_auto_compact_advisory_new_phase():
    """Test advisory triggers on new phase completion."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, '.omg', 'state')
        ledger_dir = os.path.join(state_dir, 'ledger')
        os.makedirs(ledger_dir, exist_ok=True)

        # Create checklist with 3 completed phases
        checklist_path = os.path.join(state_dir, '_checklist.md')
        with open(checklist_path, 'w') as f:
            f.write('- [x] Task 1\n')
            f.write('- [x] Task 2\n')
            f.write('- [x] Task 3\n')

        # Create empty ledger
        ledger_path = os.path.join(ledger_dir, 'tool-ledger.jsonl')
        with open(ledger_path, 'w') as f:
            pass

        # Save state with 2 phases
        module._save_auto_compact_state(tmpdir, 2, 0)

        # Check advisory (should trigger because 3 > 2)
        should_suggest, reason = module._check_auto_compact_advisory(tmpdir)

        assert should_suggest, "Should suggest compaction for new phase"
        assert "New phase completed" in reason
        assert "(3 vs 2)" in reason


def test_auto_compact_advisory_tool_threshold():
    """Test advisory triggers on tool call threshold."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, '.omg', 'state')
        ledger_dir = os.path.join(state_dir, 'ledger')
        os.makedirs(ledger_dir, exist_ok=True)

        # Create checklist
        checklist_path = os.path.join(state_dir, '_checklist.md')
        with open(checklist_path, 'w') as f:
            f.write('- [x] Task 1\n')

        # Create ledger with many recent tool calls
        ledger_path = os.path.join(ledger_dir, 'tool-ledger.jsonl')
        base_time = datetime.now() - timedelta(minutes=10)

        with open(ledger_path, 'w') as f:
            for i in range(200):  # Exceeds default threshold of 150
                entry = {
                    'ts': (base_time + timedelta(seconds=i)).isoformat(),
                    'tool': 'Edit',
                    'file': f'test{i}.py'
                }
                f.write(json.dumps(entry) + '\n')

        # Save state with current phase count and old timestamp
        module._save_auto_compact_state(tmpdir, 1, 0)

        # Manually update timestamp to be older
        state_path = os.path.join(tmpdir, '.omg', 'state', 'auto-compact-state.json')
        with open(state_path, 'r') as f:
            state = json.load(f)
        state['last_compact_ts'] = base_time.isoformat()
        with open(state_path, 'w') as f:
            json.dump(state, f)

        # Check advisory (should trigger because tool count > threshold)
        should_suggest, reason = module._check_auto_compact_advisory(tmpdir)

        assert should_suggest, "Should suggest compaction for tool threshold"
        assert "Tool threshold exceeded" in reason


def test_auto_compact_advisory_no_trigger():
    """Test advisory does not trigger when conditions not met."""
    module = load_pre_compact_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, '.omg', 'state')
        ledger_dir = os.path.join(state_dir, 'ledger')
        os.makedirs(ledger_dir, exist_ok=True)

        # Create checklist with 2 completed phases
        checklist_path = os.path.join(state_dir, '_checklist.md')
        with open(checklist_path, 'w') as f:
            f.write('- [x] Task 1\n')
            f.write('- [x] Task 2\n')

        # Create ledger with few tool calls
        ledger_path = os.path.join(ledger_dir, 'tool-ledger.jsonl')
        recent_time = datetime.now()
        with open(ledger_path, 'w') as f:
            for i in range(10):  # Well below threshold
                entry = {
                    'ts': (recent_time + timedelta(seconds=i)).isoformat(),
                    'tool': 'Edit',
                    'file': f'test{i}.py'
                }
                f.write(json.dumps(entry) + '\n')

        # Save state with same phase count
        module._save_auto_compact_state(tmpdir, 2, 0)

        # Check advisory (should NOT trigger)
        should_suggest, reason = module._check_auto_compact_advisory(tmpdir)

        assert not should_suggest, "Should not suggest compaction when conditions not met"
        assert reason == ""


if __name__ == "__main__":
    test_count_completed_phases()
    print("✓ test_count_completed_phases")

    test_save_and_load_auto_compact_state()
    print("✓ test_save_and_load_auto_compact_state")

    test_load_auto_compact_state_missing_file()
    print("✓ test_load_auto_compact_state_missing_file")

    test_count_tool_calls_since()
    print("✓ test_count_tool_calls_since")

    test_auto_compact_advisory_new_phase()
    print("✓ test_auto_compact_advisory_new_phase")

    test_auto_compact_advisory_tool_threshold()
    print("✓ test_auto_compact_advisory_tool_threshold")

    test_auto_compact_advisory_no_trigger()
    print("✓ test_auto_compact_advisory_no_trigger")

    print("\nAll auto-compact tests passed!")
