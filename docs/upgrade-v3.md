# OMG v3.0.0 Upgrade Guide

This guide covers the transition from OMG v2.3.0 to v3.0.0. This major release introduces a strategic overhaul of the governance engine, security posture, and multi-agent orchestration.

## Breaking Changes

### 1. XOR Encryption Removed

The legacy XOR fallback encryption has been completely removed from `MemoryStore`. Cryptography is now a hard dependency.

- **Impact**: Any remaining XOR-encrypted data must be migrated.
- **Action**: Run the migration tool (see below) to re-encrypt data using Fernet (AES-256-GCM).

### 2. HMAC Key Persistence

The HMAC key used for audit trail signatures is now persisted to `.omg/state/audit-hmac.key`.

- **Impact**: Process restarts no longer invalidate existing signatures.
- **Action**: The first run of v3.0.0 will automatically generate and persist a key if one doesn't exist.

### 3. Security Posture Hardening

Bypass mode (`dontAsk` / `bypassPermissions`) no longer suppresses high-risk security gates.

- **Impact**: Destructive actions and sensitive file access will now trigger a hard block or require explicit approval even in bypass mode.
- **Action**: Review your `.omg/policy.yaml` if you rely on automated bypass for high-risk operations.

---

## Migration Steps

We provide an automated migration tool to handle state and configuration updates.

### Automated Migration

Run the following command to preview and apply changes:

```bash
# 1. Preview changes (Dry Run)
npx omg migrate --from=2.3.0 --to=3.0.0

# 2. Apply changes
npx omg migrate --from=2.3.0 --to=3.0.0 --apply
```

The migration tool performs:

- **Memory Migration**: Re-encrypts XOR data to Fernet.
- **Schema Updates**: Aligns on-disk JSON payloads with v3.0.0 contracts.
- **Backup**: Creates a rollback backup in `.omg/backups/migrations/` before mutating state.

---

## New Features

### 🛡️ Approval Gates & UI

A new terminal-based UI for governance gates. Destructive actions (deletions, protected-path mutations) now trigger an interactive approval prompt unless pre-approved in `.omg/state/ralph-approvals.json`.

### 🔄 Convergence Detection

The Ralph loop now detects when a task has converged (no meaningful deltas in files or tool results) and stops early to save tokens and time.

### 📜 Rollback Manifests

Every iteration now generates a rollback manifest in `.omg/state/ralph-rollbacks/`. This allows for granular, per-interaction undo of file system changes and side effects.

### 🤖 Multi-Model Routing

Complexity-aware model tiering. OMG automatically selects the optimal model (Light/Balanced/Heavy) based on task complexity and remaining budget.

### 🗺️ Governed Deep Planning

A new planning pipeline that emits structured plans with embedded governance checkpoints. Each task is evaluated against security policies before execution.

### 🤝 Governed Multi-Agent

Sub-agents now run in dedicated tool fabric lanes with per-job budget envelopes and file-ownership tracking to prevent resource conflicts.

### 📊 SIEM Export

Audit logs can now be exported in SIEM-compatible JSONL format for integration with enterprise security dashboards.

```bash
npx omg audit export --format=jsonl --output=audit-log.jsonl
```

### 🧹 Evidence Retention

Automated pruning and GZIP compression of evidence artifacts (test results, build logs) based on configurable retention policies.

---

## Feature Flags

All new v3.0.0 features are **off by default** to preserve backward compatibility. Enable them in your configuration or via environment variables:

| Feature Flag                  | Description                                           |
| :---------------------------- | :---------------------------------------------------- |
| `ralph_convergence_detection` | Enables early stop on no-delta iterations.            |
| `ralph_approval_gate`         | Enables interactive approval for destructive actions. |
| `multi_model_routing`         | Enables complexity-aware model selection.             |
| `plan_adherence_enforcement`  | Fails iterations that drift outside the active plan.  |
| `ralph_budget_tracking`       | Enables USD and token-based budget enforcement.       |

---

## Rollback Instructions

If you need to revert to v2.3.0:

1. **Restore State**: Copy the contents of the latest backup in `.omg/backups/migrations/` back to your project root.
2. **Downgrade Package**:
   ```bash
   npm install @trac3r/oh-my-god@2.3.0
   ```
3. **Clear Locks**: Remove `.omg/state/ralph-loop.lock` if it exists.
