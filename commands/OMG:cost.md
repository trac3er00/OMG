---
description: "Display session cost tracking, budget status, and usage history."
allowed-tools: Read, Bash(python*:*), Grep
argument-hint: "[history|budget|reset]"
---

# /OMG:cost — Cost Tracker

Display session cost tracking, budget status, and usage history.

## Usage

```
/OMG:cost
/OMG:cost history
/OMG:cost budget
/OMG:cost reset
```

## Sub-Commands

### `/OMG:cost` (default)

Show current session cost summary: total tokens, total USD spent, and remaining budget percentage.

```python
from hooks._cost_ledger import read_cost_summary
summary = read_cost_summary(".")
print(f"Total tokens: {summary['total_tokens']}")
print(f"Total cost: ${summary['total_cost_usd']:.4f}")
print(f"Entries: {summary['entry_count']}")
```

### `/OMG:cost history`

Show cost breakdown by tool and by session. Lists top consumers and per-session aggregates.

```python
from hooks._cost_ledger import read_cost_summary
summary = read_cost_summary(".")

# By tool
for tool, stats in sorted(summary["by_tool"].items(), key=lambda x: x[1]["cost_usd"], reverse=True):
    print(f"  {tool}: {stats['count']} calls, {stats['tokens']} tokens, ${stats['cost_usd']:.4f}")

# By session
for sid, stats in summary["by_session"].items():
    print(f"  {sid}: {stats['count']} calls, ${stats['cost_usd']:.4f}")
```

### `/OMG:cost budget`

Show budget configuration and threshold status. Reads from `_omg.cost_budget` in `settings.json`.

Displays:
- Session budget limit (USD)
- Current spend vs limit
- Remaining budget percentage
- Threshold levels and which have been triggered

```python
import json
with open("settings.json") as f:
    config = json.load(f)
budget = config.get("_omg", {}).get("cost_budget", {})
print(f"Session limit: ${budget.get('session_limit_usd', 5.0):.2f}")
print(f"Thresholds: {budget.get('thresholds', [50, 80, 95])}")
print(f"Pricing: ${budget.get('pricing', {}).get('input_per_mtok', 3.0)}/Mtok in, ${budget.get('pricing', {}).get('output_per_mtok', 15.0)}/Mtok out")
```

### `/OMG:cost reset`

Clear the cost ledger and threshold state for a fresh start.

Removes:
- `.omg/state/ledger/cost-ledger.jsonl`
- `.omg/state/.cost-threshold-state.json`

## Feature Flag

- **Flag name**: `OMG_COST_TRACKING_ENABLED`
- **Default**: `False` (disabled)
- **Enable**: `export OMG_COST_TRACKING_ENABLED=1`

Or set in `settings.json`:

```json
{
  "_omg": {
    "features": {
      "COST_TRACKING": true
    }
  }
}
```

## Budget Configuration

Configure in `settings.json` under `_omg.cost_budget`:

```json
{
  "_omg": {
    "cost_budget": {
      "session_limit_usd": 5.0,
      "thresholds": [50, 80, 95],
      "pricing": {
        "input_per_mtok": 3.0,
        "output_per_mtok": 15.0
      }
    }
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `session_limit_usd` | `5.0` | Maximum spend per session in USD |
| `thresholds` | `[50, 80, 95]` | Budget percentage thresholds for alerts |
| `pricing.input_per_mtok` | `3.0` | Cost per million input tokens |
| `pricing.output_per_mtok` | `15.0` | Cost per million output tokens |

## Output Example

```
============================================================
  OMG Cost Tracker — Session Summary
============================================================

  Total tokens:     124,350
  Total cost:       $0.4821
  Budget remaining: 90.4% ($4.52 of $5.00)
  Tool calls:       47

  Top consumers:
    Bash:           23 calls, 68,200 tokens, $0.2644
    Read:           12 calls, 34,100 tokens, $0.1322
    Write:           8 calls, 15,050 tokens, $0.0583
    Edit:            4 calls,  7,000 tokens, $0.0272

============================================================
```

## Hook Integration

The `budget_governor.py` PostToolUse hook automatically tracks costs when `COST_TRACKING` is enabled. It:

1. Estimates token usage for each tool call (Tier 2 calibrated model)
2. Appends cost entries to `.omg/state/ledger/cost-ledger.jsonl`
3. Injects budget status into Claude's context via `additionalContext`
4. Fires threshold alerts at 50%, 80%, and 95% budget usage

## Safety

- **Read-only** (default): `/cost`, `/cost history`, `/cost budget` only read data
- **Feature-gated**: Hook and command require `COST_TRACKING` flag enabled
- **Advisory-only**: Budget governor never blocks tool execution
- **Crash-isolated**: All operations exit 0 on failure

## API

```python
from hooks._cost_ledger import read_cost_summary, append_cost_entry, rotate_cost_ledger

# Get aggregated cost summary
summary = read_cost_summary(".")

# Append a cost entry
append_cost_entry(".", {
    "ts": "2026-03-04T12:00:00Z",
    "tool": "Bash",
    "tokens_in": 500,
    "tokens_out": 200,
    "cost_usd": 0.0045,
    "model": "claude-opus-4-6",
    "session_id": "ses_abc123"
})

# Rotate ledger when > 5MB
rotate_cost_ledger(".")
```
