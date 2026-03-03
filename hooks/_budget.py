#!/usr/bin/env python3
"""
Budget Constants — OMG Context & Prompt Budgets

Named constants for token/character budgets across OMG hooks.
Replaces magic numbers with semantic names for maintainability.
"""

# ═══════════════════════════════════════════════════════════
# Session-start budgets (chars)
# ═══════════════════════════════════════════════════════════
BUDGET_SESSION_TOTAL = 2000          # Total context injection budget
BUDGET_SESSION_IDLE = 200            # When no features active
BUDGET_PROFILE = 200                 # Project profile section
BUDGET_WORKING_MEMORY = 400          # Working memory section
BUDGET_HANDOFF = 300                 # Handoff section
BUDGET_MEMORY = 300                  # Memory/state section
BUDGET_FAILURES = 200                # Active failures section
BUDGET_TOOLS = 100                   # Tools inventory section
BUDGET_PLANNING = 100                # Planning/checklist section
BUDGET_RALPH = 100                   # Ralph/persistent mode section

# ═══════════════════════════════════════════════════════════
# Prompt-enhancer budgets (chars)
# ═══════════════════════════════════════════════════════════
BUDGET_PROMPT_TOTAL = 1000           # Total prompt enhancement budget
BUDGET_INTENT_DISCIPLINE = 200       # Intent classification + discipline
BUDGET_KNOWLEDGE = 300               # Knowledge retrieval section
BUDGET_LEARNINGS = 200               # Learnings/patterns section
BUDGET_AGENT_ROUTING = 200           # Agent routing directives
BUDGET_MODE = 100                    # Mode detection (ulw/crazy/etc)
