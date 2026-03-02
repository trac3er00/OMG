# Runtime/Protocol Layer Review

Scope reviewed:
- `src/team/runtime.ts`
- `src/team/runtime-cli.ts`
- `src/team/tmux-session.ts`
- `skills/omc-teams/SKILL.md`

## Findings (ordered by severity)

### 1) High: Non-Claude workers skip `in_progress`, causing wrong monitor phase during active execution
- Evidence:
  - Tasks start as `pending`: `src/team/runtime.ts:133`.
  - Non-Claude startup path sends instructions but does not mark task file `in_progress`: `src/team/runtime.ts:193`, `src/team/runtime.ts:206`, `src/team/runtime.ts:213`.
  - Watchdog later writes terminal status directly: `src/team/runtime.ts:241`.
  - Phase inference marks `planning` when `inProgress=0`, `pending>0`, `completed=0`: `src/team/runtime.ts:317`.
- Impact:
  - During actual codex/gemini work, `monitorTeam()` can report `planning` instead of `executing`.
  - This skews runtime-cli logs and failure heuristics based on outstanding work.

### 2) High: `tasks[i] ?? tasks[0]` with more workers than tasks duplicates work and can produce non-existent task IDs
- Evidence:
  - Fallback duplication: `src/team/runtime.ts:187`, `src/team/runtime.ts:206`.
  - Task ID still computed as `i+1`: `src/team/runtime.ts:189`, `src/team/runtime.ts:208`.
  - Only `tasks.length` task files are created: `src/team/runtime.ts:131`.
  - Completion writes to `tasks/{event.taskId}.json`, guarded by existence: `src/team/runtime.ts:239`, `src/team/runtime.ts:241`.
- Impact:
  - Multiple workers may execute same task content.
  - Worker may emit `taskId` with no corresponding task file; result is dropped from task-state accounting.
- Note:
  - Skill doc says decomposition should produce exactly N subtasks: `skills/omc-teams/SKILL.md:64`.

### 3) High: `collectTaskResults()` can race with late watchdog completion updates
- Evidence:
  - `collectTaskResults()` runs before watchdog stop + shutdown: `src/team/runtime-cli.ts:118`, `src/team/runtime-cli.ts:122`.
  - Stopping watchdog only clears interval; in-flight tick/callback may still run: `src/team/runtime.ts:379`, `src/team/runtime.ts:381`, `src/team/runtime.ts:365`.
  - Callback can update task files after results were already collected: `src/team/runtime.ts:245`.
- Impact:
  - CLI output may contain stale `pending`/`unknown` summaries despite work finishing moments later.

### 4) Medium: Hardcoded 4000ms non-Claude startup delay is brittle
- Evidence:
  - Fixed sleep for codex/gemini: `src/team/runtime.ts:195`.
  - Claude has an explicit readiness protocol (`.ready`) with timeout: `src/team/runtime.ts:184`.
- Impact:
  - If codex/gemini startup is slower than 4s, initial instruction may land before input is accepted.
  - If faster, every worker pays avoidable latency.

### 5) Medium: `sendToWorker` 200-char truncation can break long-path inbox trigger messages
- Evidence:
  - Hard truncation at 200 chars: `src/team/tmux-session.ts:300`.
  - Non-Claude trigger message includes relative path with full `teamName`: `src/team/runtime.ts:213`.
  - Runtime CLI does not constrain `teamName` length: `src/team/runtime-cli.ts:80`.
- Impact:
  - Long `teamName` can truncate the path instruction, causing worker to read an invalid/incomplete path.

### 6) Medium: `shutdownTeam` ACK wait is mostly wasted for non-Claude workers
- Evidence:
  - Shutdown waits for all worker ACK files until deadline: `src/team/runtime.ts:437`, `src/team/runtime.ts:441`, `src/team/runtime.ts:445`.
  - Runtime CLI comment: non-Claude workers never write shutdown ACK; passes `2000ms`: `src/team/runtime-cli.ts:126`, `src/team/runtime-cli.ts:133`.
  - Poll sleep granularity: 500ms: `src/team/runtime.ts:451`.
- Effective timeout:
  - In runtime-cli path: approximately 2.0s to 2.5s before kill/cleanup.
  - In default callers: full default 30s (`src/team/runtime.ts:425`) can be wasted.

### 7) Medium: Watchdog partial `done.json` writes are tolerated, but there is no explicit atomic-write contract
- Evidence:
  - Watchdog polls every 3000ms: `src/team/runtime.ts:229`, `src/team/runtime.ts:379`.
  - Read/parse failures return `null` and are ignored: `src/team/runtime.ts:79`, `src/team/runtime.ts:351`.
- Impact:
  - Partial/incomplete JSON during write is not fatal; watchdog retries next tick.
  - Main downside is completion latency and dependency on eventual valid rewrite.

### 8) Low: `isWorkerAlive` via `#{pane_dead}` correctly detects exited codex process, but not hangs
- Evidence:
  - Liveness check: `src/team/tmux-session.ts:417`, `src/team/tmux-session.ts:420`.
  - Worker launch uses `exec` so shell is replaced by CLI process: `src/team/tmux-session.ts:246`.
- Conclusion:
  - For actual process exit, this check is appropriate.
  - It cannot detect "alive but unresponsive" states without heartbeat/IO heuristics.

### 9) Medium: Watchdog processes at most one completion per worker across entire runtime
- Evidence:
  - `processed` set is keyed by worker name and never cleared: `src/team/runtime.ts:341`, `src/team/runtime.ts:348`, `src/team/runtime.ts:355`.
  - `assignTask()` exists for additional assignments: `src/team/runtime.ts:387`.
- Impact:
  - If a worker is assigned multiple tasks sequentially, only first `done.json` is consumed.
  - Subsequent completions from the same worker are ignored.

### 10) Medium: Initial assignment message tells worker to "claim tasks", but runtime pre-assigns task IDs inconsistently
- Evidence:
  - Initial inbox prompt says "claim tasks" from task dir: `src/team/runtime.ts:157`.
  - Runtime also pushes an explicit "Initial Task Assignment" with fixed `Task ID`: `src/team/runtime.ts:190`, `src/team/runtime.ts:209`.
- Impact:
  - Worker behavior may diverge (self-claim vs. follow fixed ID), increasing protocol ambiguity and state drift.

### 11) Low: `sendToWorker` `sessionName` parameter is unused in implementation
- Evidence:
  - Function signature includes `sessionName`: `src/team/tmux-session.ts:296`.
  - Body only targets pane ID; session name is ignored.
- Impact:
  - Not a functional bug, but indicates API drift and potential confusion for callers.

### 12) Low: Team name/path handling is unsanitized in state paths
- Evidence:
  - State path uses `teamName` directly: `src/team/runtime.ts:71`.
  - `tmux` names are sanitized separately in `tmux-session.ts`, but file paths are not.
- Impact:
  - Path characters from `teamName` can make instructions/path lengths fragile; path traversal risk depends on upstream validation (not visible in reviewed scope).

## Direct answers to requested checks

1. Non-Claude workers skipping `in_progress` does cause `monitorTeam` phase misreporting (`planning` while executing).
2. Hardcoded 4000ms can be too short (lost/garbled first instruction) or too long (wasted latency).
3. `tasks[i] ?? tasks[0]` is likely unintended for production; it can duplicate work and emit non-existent task IDs.
4. Partial `done.json` is retried safely (parse failure -> ignore), but completion may be delayed.
5. 200-char limit is not always safe for long `teamName` paths.
6. Runtime-cli effectively waits ~2-2.5s; default shutdown path can still waste up to 30s.
7. There is a real race around result collection vs in-flight watchdog completion updates.
8. `pane_dead` correctly indicates exited codex worker process, but cannot detect hangs.
9. Additional fragility exists (one-completion-per-worker watchdog design, protocol ambiguity, API drift).

## Suggested remediation order

1. Mark non-Claude initial tasks `in_progress` before notifying workers.
2. Enforce `workerCount <= tasks.length` (or generate concrete extra tasks) and remove `tasks[i] ?? tasks[0]` fallback.
3. Replace fixed 4000ms with readiness probe per CLI type.
4. Make done-signal writes atomic by contract (`tmp + rename`) and validate required fields.
5. Remove 200-char truncation risk by using short trigger tokens + file-backed payload.
6. In shutdown path, skip ACK waiting for non-Claude workers or use agent-type-aware expected ACK set.
7. Serialize shutdown with watchdog completion drain before collecting task results.
8. Redesign watchdog processed key to include task ID (or sequence), not only worker name.
