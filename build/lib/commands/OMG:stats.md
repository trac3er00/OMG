---
description: "Display session analytics, tool usage trends, file heatmaps, and failure patterns."
allowed-tools: Read, Bash(python*:*), Grep
argument-hint: "[weekly|files|failures|dashboard]"
---

# /OMG:stats — Session Analytics

Display session analytics, tool usage trends, file heatmaps, and failure patterns.

## Usage

```
/OMG:stats
/OMG:stats weekly
/OMG:stats files
/OMG:stats failures
/OMG:stats dashboard
```

## Sub-Commands

### `/OMG:stats` (default)

Show current session summary: duration, tool calls, success rate, cost, and test runs.

```python
from hooks.query import get_session_summary

summary = get_session_summary(".")
duration_m = summary["duration"] // 60
duration_s = summary["duration"] % 60
print(f"Duration:       {duration_m}m {duration_s}s")
print(f"Tool calls:     {summary['tool_calls']}")
print(f"Success rate:   {summary['success_rate']:.1%}")
print(f"Files modified: {summary['files_modified']}")
print(f"Tests run:      {summary['tests_run']}")
print(f"Tokens used:    {summary['tokens_used']:,}")
print(f"Cost:           ${summary['cost_usd']:.4f}")
```

### `/OMG:stats weekly`

Show last 7 days trend analysis by aggregating tool stats and escalation effectiveness.

```python
from hooks.query import get_tool_stats, get_escalation_effectiveness

tools = get_tool_stats(".")
escalations = get_escalation_effectiveness(".")

# Per-tool breakdown
for tool, stats in sorted(tools.items(), key=lambda x: x[1]["count"], reverse=True):
    print(f"  {tool}: {stats['count']} calls, {stats['success_rate']:.0%} success, {stats['avg_tokens']:.0f} avg tokens")

# Escalation summary
print(f"\nEscalations: {escalations['escalations']} total, {escalations['resolved']} resolved, {escalations['unresolved']} unresolved")
```

### `/OMG:stats files`

Show file-level heatmap of the most read, written, and edited files.

```python
from hooks.query import get_file_heatmap

heatmap = get_file_heatmap(".")

# Sort by total interactions (reads + writes + edits)
ranked = sorted(
    heatmap.items(),
    key=lambda x: x[1]["reads"] + x[1]["writes"] + x[1]["edits"],
    reverse=True,
)

print(f"{'File':<50} {'Reads':>6} {'Writes':>7} {'Edits':>6}")
print("-" * 73)
for path, counts in ranked[:20]:
    total = counts["reads"] + counts["writes"] + counts["edits"]
    print(f"{path:<50} {counts['reads']:>6} {counts['writes']:>7} {counts['edits']:>6}")
```

### `/OMG:stats failures`

Show top failure patterns and their resolution status.

```python
from hooks.query import get_failure_hotspots, get_escalation_effectiveness

hotspots = get_failure_hotspots(".")
escalations = get_escalation_effectiveness(".")

for pattern, details in sorted(hotspots.items(), key=lambda x: x[1]["count"], reverse=True):
    status = "ESCALATED" if details["escalated"] else "active"
    print(f"  [{status}] {pattern}: {details['count']} failures")
    for err in details["last_3_errors"]:
        print(f"    - {err[:100]}")

print(f"\nResolution: {escalations['resolved']}/{escalations['escalations']} escalations resolved")
```

### `/OMG:stats dashboard`

Generate a self-contained HTML dashboard at `.omg/state/dashboard.html`.

The dashboard includes:
- Session summary cards (duration, tool calls, cost, success rate)
- Tool usage bar chart (via CDN Chart.js)
- File heatmap table (top 20 files by interaction count)
- Failure pattern list with escalation status

```python
import json
import os
from hooks.query import (
    get_session_summary,
    get_tool_stats,
    get_file_heatmap,
    get_failure_hotspots,
)

summary = get_session_summary(".")
tools = get_tool_stats(".")
heatmap = get_file_heatmap(".")
failures = get_failure_hotspots(".")

dashboard_data = {
    "summary": summary,
    "tools": tools,
    "heatmap": dict(sorted(
        heatmap.items(),
        key=lambda x: x[1]["reads"] + x[1]["writes"] + x[1]["edits"],
        reverse=True,
    )[:20]),
    "failures": failures,
}

# Write self-contained HTML with embedded Chart.js
output_path = os.path.join(".omg", "state", "dashboard.html")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
# ... (HTML template with CDN Chart.js and embedded JSON data)
print(f"Dashboard written to {output_path}")
```

## Feature Flag

- **Flag name**: `OMG_SESSION_ANALYTICS_ENABLED`
- **Default**: `False` (disabled)
- **Enable**: `export OMG_SESSION_ANALYTICS_ENABLED=1`

Or set in `settings.json`:

```json
{
  "_omg": {
    "features": {
      "SESSION_ANALYTICS": true
    }
  }
}
```

## Output Example

```
============================================================
  OMG Session Analytics — Summary
============================================================

  Duration:       23m 47s
  Tool calls:     142
  Success rate:   94.4%
  Files modified: 18
  Tests run:      6
  Tokens used:    287,450
  Cost:           $1.1142

  Top Tools:
    Bash:           58 calls, 95% success, 1,240 avg tokens
    Read:           34 calls, 100% success, 890 avg tokens
    Edit:           22 calls, 91% success, 1,100 avg tokens
    Write:          16 calls, 100% success, 950 avg tokens
    Grep:           12 calls, 100% success, 320 avg tokens

  Failure Hotspots:
    [ESCALATED] hooks/budget_governor.py: 4 failures
    [active] tests/test_integration.py: 2 failures

  Escalations: 1 total, 0 resolved, 1 unresolved

============================================================
```

## Safety

- **Read-only**: All sub-commands only read from existing ledger/tracker files
- **Feature-gated**: Requires `SESSION_ANALYTICS` flag enabled
- **No mutations**: Never modifies ledger data, failure tracker, or working memory
- **Crash-isolated**: All query operations exit 0 on failure (via query.py internals)
- **Dashboard**: Writes only to `.omg/state/dashboard.html` (inside managed state directory)

## API

```python
from hooks.query import (
    get_session_summary,
    get_tool_stats,
    get_failure_hotspots,
    get_escalation_effectiveness,
    get_file_heatmap,
)

# Current session summary
summary = get_session_summary(".")

# Per-tool statistics
tools = get_tool_stats(".")

# Failure patterns and escalation status
failures = get_failure_hotspots(".")
escalations = get_escalation_effectiveness(".")

# File interaction heatmap
heatmap = get_file_heatmap(".")
```
