#!/usr/bin/env python3
"""
Test Budget Constants — Verify budget consistency and constraints.
"""
import sys
import os

# Add hooks directory to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _budget import (
    BUDGET_SESSION_TOTAL,
    BUDGET_SESSION_IDLE,
    BUDGET_PROFILE,
    BUDGET_WORKING_MEMORY,
    BUDGET_HANDOFF,
    BUDGET_MEMORY,
    BUDGET_FAILURES,
    BUDGET_TOOLS,
    BUDGET_PLANNING,
    BUDGET_RALPH,
    BUDGET_PROMPT_TOTAL,
    BUDGET_INTENT_DISCIPLINE,
    BUDGET_KNOWLEDGE,
    BUDGET_LEARNINGS,
    BUDGET_AGENT_ROUTING,
    BUDGET_MODE,
)


def test_budget_totals_consistent():
    """
    Verify that sum of sub-budgets does not exceed total budgets.
    
    This ensures that the budget allocation is internally consistent
    and that individual components don't exceed their parent budget.
    """
    # Session-start sub-budgets
    session_sub_budgets = [
        BUDGET_SESSION_IDLE,
        BUDGET_PROFILE,
        BUDGET_WORKING_MEMORY,
        BUDGET_HANDOFF,
        BUDGET_MEMORY,
        BUDGET_FAILURES,
        BUDGET_TOOLS,
        BUDGET_PLANNING,
        BUDGET_RALPH,
    ]
    session_sum = sum(session_sub_budgets)
    
    # Verify session budgets are reasonable
    assert BUDGET_SESSION_TOTAL == 2000, f"Expected BUDGET_SESSION_TOTAL=2000, got {BUDGET_SESSION_TOTAL}"
    assert session_sum <= BUDGET_SESSION_TOTAL, (
        f"Session sub-budgets sum ({session_sum}) exceeds total ({BUDGET_SESSION_TOTAL})"
    )
    
    # Prompt-enhancer sub-budgets
    prompt_sub_budgets = [
        BUDGET_INTENT_DISCIPLINE,
        BUDGET_KNOWLEDGE,
        BUDGET_LEARNINGS,
        BUDGET_AGENT_ROUTING,
        BUDGET_MODE,
    ]
    prompt_sum = sum(prompt_sub_budgets)
    
    # Verify prompt budgets are reasonable
    assert BUDGET_PROMPT_TOTAL == 1000, f"Expected BUDGET_PROMPT_TOTAL=1000, got {BUDGET_PROMPT_TOTAL}"
    assert prompt_sum <= BUDGET_PROMPT_TOTAL, (
        f"Prompt sub-budgets sum ({prompt_sum}) exceeds total ({BUDGET_PROMPT_TOTAL})"
    )


def test_budget_values_positive():
    """Verify all budget values are positive integers."""
    all_budgets = {
        "BUDGET_SESSION_TOTAL": BUDGET_SESSION_TOTAL,
        "BUDGET_SESSION_IDLE": BUDGET_SESSION_IDLE,
        "BUDGET_PROFILE": BUDGET_PROFILE,
        "BUDGET_WORKING_MEMORY": BUDGET_WORKING_MEMORY,
        "BUDGET_HANDOFF": BUDGET_HANDOFF,
        "BUDGET_MEMORY": BUDGET_MEMORY,
        "BUDGET_FAILURES": BUDGET_FAILURES,
        "BUDGET_TOOLS": BUDGET_TOOLS,
        "BUDGET_PLANNING": BUDGET_PLANNING,
        "BUDGET_RALPH": BUDGET_RALPH,
        "BUDGET_PROMPT_TOTAL": BUDGET_PROMPT_TOTAL,
        "BUDGET_INTENT_DISCIPLINE": BUDGET_INTENT_DISCIPLINE,
        "BUDGET_KNOWLEDGE": BUDGET_KNOWLEDGE,
        "BUDGET_LEARNINGS": BUDGET_LEARNINGS,
        "BUDGET_AGENT_ROUTING": BUDGET_AGENT_ROUTING,
        "BUDGET_MODE": BUDGET_MODE,
    }
    
    for name, value in all_budgets.items():
        assert isinstance(value, int), f"{name} is not an integer: {type(value)}"
        assert value > 0, f"{name} is not positive: {value}"


def test_budget_imports():
    """Verify all budget constants can be imported."""
    # This test passes if the imports at the top of this file succeed
    assert BUDGET_SESSION_TOTAL is not None
    assert BUDGET_PROMPT_TOTAL is not None


if __name__ == "__main__":
    test_budget_totals_consistent()
    test_budget_values_positive()
    test_budget_imports()
    print("✓ All budget tests passed")
