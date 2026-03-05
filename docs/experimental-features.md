# Experimental Features — OMG v2.1.0-alpha

🟠 **Alpha stability** — all features documented here are experimental. APIs, behavior, and storage formats may change between releases. Do not use in production without accepting that risk.

All experimental features are disabled by default. They require no external dependencies (stdlib-only Python 3.10+).

---

## Overview

OMG v2.1.0-alpha introduces four tiers of experimental capabilities:

| Tier | Name | Feature Flag | Env Var |
|------|------|-------------|---------|
| Tier-1 | Parallel Agent Dispatch | `PARALLEL_DISPATCH` | `OMG_PARALLEL_DISPATCH_ENABLED=1` |
| Tier-1 | Ultraworker Router | `ULTRAWORKER` | `OMG_ULTRAWORKER_ENABLED=1` |
| Tier-2 | Persistent Memory | `EXPERIMENTAL_MEMORY` | `OMG_EXPERIMENTAL_MEMORY_ENABLED=1` |
| Tier-3 | Pattern Intelligence | `PATTERN_INTELLIGENCE` | `OMG_PATTERN_INTELLIGENCE_ENABLED=1` |
| Tier-4 | Advanced Integration | `ADVANCED_INTEGRATION` | `OMG_ADVANCED_INTEGRATION_ENABLED=1` |

Enable any tier via environment variable or `settings.json`:

```bash
# Environment variable (per-session)
export OMG_EXPERIMENTAL_MEMORY_ENABLED=1
```

```json
// settings.json (persistent)
{
  "_omg": {
    "features": {
      "EXPERIMENTAL_MEMORY": true
    }
  }
}
```

---

## Tier-1: Parallel Agent Dispatch 🟠

**Flag:** `PARALLEL_DISPATCH` / `OMG_PARALLEL_DISPATCH_ENABLED=1`

Real concurrent dispatch to multiple OMG agents. Supports three distribution modes and three aggregation strategies. Results are collected and merged into a single `ParallelResult`.

### `send_parallel`

```python
from claude_experimental.parallel.api import send_parallel, DistributionMode, AggregationMode

result = send_parallel(
    recipients=["explore", "oracle"],
    content="Analyze the auth module for security issues",
    distribution=DistributionMode.BROADCAST,   # or "BROADCAST"
    aggregation=AggregationMode.BEST_RESULT,   # or "BEST_RESULT"
)

print(result.aggregated)           # best response content
print(result.execution_summary)    # {"total": 2, "succeeded": 2, "failed": 0, ...}
for r in result.results:
    print(r.recipient, r.exit_code, r.duration_ms)
```

**Distribution modes:**

| Mode | Behavior |
|------|----------|
| `BROADCAST` | Same content sent to all recipients |
| `SHARD` | Content split evenly across recipients |
| `ROUTED` | Per-recipient content via `dict[str, str]` |

**Aggregation modes:**

| Mode | Behavior |
|------|----------|
| `BEST_RESULT` | Longest successful response wins |
| `ALL_RESULTS` | Returns `list[str]` of all responses |
| `FIRST_SUCCESS` | Returns first response with `exit_code == 0` |

**`SendObject` for fine-grained control:**

```python
from claude_experimental.parallel.api import SendObject, send_parallel

tasks = [
    SendObject(recipient="explore", content="Map the codebase", priority=1, timeout=120),
    SendObject(recipient="oracle", content="Identify risks", priority=0, timeout=300),
]
result = send_parallel(
    recipients=tasks,
    content="",  # ignored when passing SendObject list
    distribution="BROADCAST",
    aggregation="ALL_RESULTS",
)
```

### Tier-1: Ultraworker Router 🟠

**Flag:** `ULTRAWORKER` / `OMG_ULTRAWORKER_ENABLED=1`

High-throughput priority-queue router for batching many tasks across agents.

```python
from claude_experimental.parallel.ultraworker import UltraworkerRouter
from claude_experimental.parallel.scaling import DynamicPool

pool = DynamicPool(min_workers=2, max_workers=8)
router = UltraworkerRouter(pool=pool)

# Single task
job_id = router.submit(agent_name="explore", prompt="Analyze hooks/", priority=1)

# Batch
job_ids = router.submit_batch([
    {"agent_name": "explore", "prompt": "Analyze hooks/"},
    {"agent_name": "oracle", "prompt": "Review security"},
])

results = router.wait_for_results(job_ids, aggregation="BEST_RESULT")
stats = router.get_stats()  # {"submitted": 2, "completed": 2, "failed": 0, ...}

router.shutdown()
```

---

## Tier-2: Persistent Memory 🟠

**Flag:** `EXPERIMENTAL_MEMORY` / `OMG_EXPERIMENTAL_MEMORY_ENABLED=1`

SQLite-backed memory with three types: semantic (facts), episodic (events), and procedural (step sequences). Uses WAL mode and FTS5 full-text search. Memories persist across sessions.

**Storage paths:**
- `session` / `project` scope: `.omg/state/memory.db` (relative to `CLAUDE_PROJECT_DIR`)
- `user` scope: `~/.omg/memory.db`

### `remember`

```python
from claude_experimental.memory.api import remember

# Auto-detect type (default)
memory_id = remember(
    "The auth module uses JWT with RS256 signing",
    importance=0.8,
    memory_type="auto",   # "semantic" | "episodic" | "procedural" | "auto"
    scope="project",      # "session" | "project" | "user"
)

# Explicit procedural memory
remember(
    "1. Run tests\n2. Check coverage\n3. Commit",
    memory_type="procedural",
    scope="project",
)

# Episodic memory (event record)
remember(
    "Fixed: resolved auth token expiry bug",
    memory_type="episodic",
    importance=0.9,
    scope="project",
)
```

**Auto-detection rules:**
- `procedural` — content contains `step `, `steps:`, or a numbered list
- `episodic` — content contains `event:`, `outcome:`, `fixed`, or `resolved`
- `semantic` — everything else

### `recall`

```python
from claude_experimental.memory.api import recall

results = recall(
    "JWT authentication",
    limit=5,
    temperature=0.3,          # 0.0 = precise, 1.0 = broad
    memory_types=["semantic", "episodic"],  # None = all types
    scope_filter="project",   # None = search all scopes
    min_relevance=0.5,        # 0.0–1.0
)

for mem in results:
    print(mem.source_type, mem.relevance_score, mem.content)
    # mem.memory_id, mem.metadata also available
```

### `memory_check`

```python
from claude_experimental.memory.api import memory_check

stats = memory_check(
    scope="project",
    repair=True,    # attempt REINDEX + VACUUM if integrity check fails
    compact=False,  # run VACUUM to reclaim space
)

print(stats["healthy"])           # True/False
print(stats["total_memories"])    # int
print(stats["memories_by_type"])  # {"semantic": 42, "episodic": 7, ...}
print(stats["integrity"])         # "ok" or error string
```

---

## Tier-3: Pattern Intelligence 🟠

**Flag:** `PATTERN_INTELLIGENCE` / `OMG_PATTERN_INTELLIGENCE_ENABLED=1`

AST-based pattern mining, anti-pattern detection, and refactoring suggestions for Python codebases.

### `pattern_detect`

```python
from claude_experimental.patterns.api import pattern_detect

report = pattern_detect(
    "hooks/",
    min_support=0.05,          # minimum fraction of files that must contain pattern
    pattern_type="sequential", # "sequential" | "structural"
)

print(report.total_files)
print(report.patterns)         # list of Pattern objects
print(report.frequencies)      # {"sequential:import_a->import_b": 12, ...}
print(report.deviations)       # patterns with z-score > 2.0
print(report.baseline)         # global stats including anti-pattern counts
```

### `pattern_validate`

```python
from claude_experimental.patterns.api import pattern_validate

# Validate a string pattern name
validation = pattern_validate(
    "sequential:import_os->import_sys",
    against_path="hooks/",
    min_support=0.05,
)

print(validation.is_valid)     # True/False
print(validation.support)      # 0.0–1.0
print(validation.confidence)   # adjusted for anti-pattern violations
print(validation.violations)   # ["bare_except@42 [high]", ...]

# Validate a Pattern object
from claude_experimental.patterns.extractor import Pattern
p = Pattern(type="structural", name="class_hierarchy", frequency=3, location="", snippet="")
validation = pattern_validate(p, against_path="hooks/")
```

### `pattern_synthesize`

```python
from claude_experimental.patterns.api import pattern_synthesize

result = pattern_synthesize(
    "hook_with_error_handling",
    constraints={"max_lines": 50, "requires_logging": True},
)

print(result.template)      # "hook_with_error_handling"
print(result.suggestions)   # ["hook_with_error_handling [max_lines=50, ...]", ...]
print(result.confidence)    # 0.9 with constraints, 0.7 without
```

---

## Tier-4: Advanced Integration 🟠

**Flag:** `ADVANCED_INTEGRATION` / `OMG_ADVANCED_INTEGRATION_ENABLED=1`

Five integration primitives: OpenAPI tool generation, SSE streaming, human-in-the-loop checkpoints, local telemetry, A/B experiments, and automatic parameter tuning.

### OpenAPI Tool Generation

Generate callable Python functions from an OpenAPI 3.x spec:

```python
from claude_experimental.integration.openapi_gen import ToolGenerator

gen = ToolGenerator()

# Returns dict[str, Callable]
tools = gen.generate("path/to/openapi.json")
result = tools["get_user"](user_id="123")

# Or generate a Python module as a string
module_src = gen.generate_module("path/to/openapi.yaml")
```

Supports JSON and YAML specs. Uses stdlib `urllib` only (no `requests` dependency). HTTP errors map to Python exceptions: `404 -> FileNotFoundError`, `400 -> ValueError`, `5xx -> RuntimeError`.

### SSE Streaming

```python
from claude_experimental.integration.streaming import SSEStream

stream = SSEStream(max_buffer=100)

# Emit events (thread-safe)
stream.emit("content", "Processing step 1...")
stream.emit("progress", "50%", event_id="evt-001")
stream.emit("complete", "Done")

# Read as SSE-formatted strings
for sse_line in stream.read():
    print(sse_line)
    # id: <uuid>
    # event: content
    # data: Processing step 1...
    #

# Resume from a specific event ID
for sse_line in stream.read(last_event_id="evt-001"):
    print(sse_line)  # only events after evt-001

stream.close()  # subsequent emit() raises RuntimeError
```

Buffer is bounded (`max_buffer=100` by default). Oldest events are dropped on overflow.

### Human-in-the-Loop Checkpoints

```python
from claude_experimental.integration.checkpoints import CheckpointManager

mgr = CheckpointManager(base_dir=".")

# Create a checkpoint (persisted to .omg/state/checkpoints/<uuid>.json)
checkpoint_id = mgr.create_checkpoint(
    checkpoint_type="DECISION",          # "VERIFICATION" | "DECISION" | "CLARIFICATION"
    description="Should we delete the legacy auth module?",
    options=["yes", "no", "defer"],
    timeout_seconds=3600,
)

# Poll for pending checkpoints
pending = mgr.list_pending()
for cp in pending:
    print(cp["checkpoint_id"], cp["description"])

# Resolve a checkpoint
mgr.resume_checkpoint(checkpoint_id, decision="yes")

# Get checkpoint state
cp = mgr.get_checkpoint(checkpoint_id)
print(cp["status"])   # "resolved"
print(cp["decision"]) # "yes"

# Clean up expired checkpoints from disk
deleted = mgr.cleanup_expired()
```

Checkpoints are written atomically (tempfile + `os.replace()`). Auto-expire after `timeout_seconds`.

### Telemetry Collection

```python
from claude_experimental.integration.telemetry import TelemetryCollector

collector = TelemetryCollector()  # stores to .omg/state/telemetry.db

# Record metrics
collector.record_counter("api.requests", tags={"endpoint": "/search"})
collector.record_gauge("memory.usage_mb", 256.5)
collector.record_histogram("response.latency_ms", 42.3)

# Query recent data
metrics = collector.query("api.requests", since_minutes=60)
for row in metrics:
    print(row["value"], row["recorded_at"])

# Aggregate by time period
agg = collector.aggregate("response.latency_ms", period="minute")
# {"2026-03-05T10:30": {"count": 5, "sum": 210.5, "min": 38.1, "max": 52.0, "avg": 42.1}, ...}

# Rotate old data
deleted = collector.rotate_old_data(days=30)
```

Privacy-first: only numeric metrics, no content capture. Local-only storage.

### A/B Experiment Tagging

```python
from claude_experimental.integration.experiments import ExperimentTracker

tracker = ExperimentTracker()

# Define an experiment
exp_id = tracker.define_experiment(
    name="prompt_style",
    variants=["concise", "verbose", "structured"],
)

# Assign a variant (hash-based = deterministic per subject)
variant = tracker.assign_variant(exp_id, subject_id="user_123", use_hash=True)

# Record a metric for this variant
tracker.tag_metric(exp_id, variant=variant, metric_name="task_success", value=1.0)

# Compare variants
comparison = tracker.compare(exp_id, metric_name="task_success")
# {"concise": {"count": 10, "mean": 0.8, "min": 0.0, "max": 1.0}, ...}
```

### Automatic Parameter Tuning

```python
from claude_experimental.integration.autotuner import AutoTuner
from claude_experimental.parallel.scaling import DynamicPool
from claude_experimental.integration.telemetry import TelemetryCollector

pool = DynamicPool(min_workers=1, max_workers=8)
telemetry = TelemetryCollector(db_path="/tmp/telemetry.db")

tuner = AutoTuner(
    pool=pool,
    telemetry=telemetry,
    min_workers=1,
    max_workers=8,
    target_p99_ms=5000,
)

# Run one tuning cycle (call periodically)
tuner.tune_cycle()

# Inspect current parameters
params = tuner.get_current_params()
print(params["pool_size"], params["target_p99_ms"])
```

Tuning rules: scale up when P99 latency exceeds 2x target; scale down when utilization stays below 30% for 30+ seconds.

---

## Migration Guide: Markdown Memories to SQLite

If you have existing memories in `.omg/state/memory/*.md` (created by earlier OMG versions), migrate them to the new SQLite store:

```python
from claude_experimental.memory.migrate import migrate_markdown_memories

# Migrate from project directory
result = migrate_markdown_memories(
    project_dir=".",           # directory containing .omg/state/memory/
    target_store=None,         # None = use default project-scoped store
)

print(result["files_found"])         # number of .md files discovered
print(result["memories_migrated"])   # number successfully imported
print(result["skipped_duplicates"])  # already-imported files (idempotent)
print(result["errors"])              # files that failed to import
```

**What the migration does:**
- Reads all `.md` files from `.omg/state/memory/`
- Stores each as a `semantic` memory with `scope="project"`
- Extracts the date from filenames in `YYYY-MM-DD` format as `created_at`
- Computes a SHA-256 content hash for deduplication
- Preserves original markdown files (safe to re-run)

**Running twice is safe** — duplicate content is detected via content hash and skipped.

---

## Troubleshooting

### Feature flag not taking effect

Check that the env var is set in the same shell session that launches Claude Code:

```bash
export OMG_EXPERIMENTAL_MEMORY_ENABLED=1
claude  # start Claude Code after setting the var
```

Or add it to `settings.json` for persistent activation.

### `RuntimeError: feature flag disabled`

All experimental APIs raise `RuntimeError` when called without the corresponding flag enabled. Enable the flag for the tier you're using (see the table at the top of this document).

### SQLite database locked

The memory and telemetry stores use WAL mode with a 5-second busy timeout. If you see `database is locked` errors, another process may be holding a write lock. WAL mode allows concurrent reads, so this is rare. If it persists, check for zombie processes holding the DB file open.

### Memory recall returns no results

- Check that `min_relevance` isn't too high (default `0.5`). Try `min_relevance=0.0` to see all stored memories.
- FTS5 does not stem words. "container" won't match "containers". Use exact tokens that appear in stored content.
- Verify the correct `scope_filter` — memories stored with `scope="project"` won't appear when searching `scope="user"`.

### Pattern detection finds nothing

- Ensure the path contains `.py` files. Non-Python files use regex fallback with limited pattern coverage.
- Lower `min_support` (e.g., `0.01`) if your codebase is small.
- `pattern_type="structural"` requires class inheritance patterns. Use `"sequential"` for import chain analysis.

### Checkpoint files not appearing

Checkpoints are written to `.omg/state/checkpoints/` relative to the `base_dir` passed to `CheckpointManager`. Default is `"."` (current working directory). Verify the path exists and is writable.
