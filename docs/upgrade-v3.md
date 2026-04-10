# OMG v3.0.0 Upgrade Guide

This guide covers the transition from OMG v2.3.0 to v3.0.0. This major release introduces a strategic overhaul of the governance engine, security posture, and multi-agent orchestration.

## TL;DR

| Item                    | Detail                                                                               |
| :---------------------- | :----------------------------------------------------------------------------------- |
| **Version**             | 2.3.0 → 3.0.0                                                                        |
| **Breaking changes**    | 3 (soft-block default, CMMS tier routing required, min runtime bump)                 |
| **Migration command**   | `npx omg migrate --from=2.3.0 --to=3.0.0`                                            |
| **New feature phases**  | 4 (Context & Memory, Planning & Thought, Governance & Security, Multi-Agent & Scale) |
| **Feature flags added** | 10 (all default `off`)                                                               |
| **Performance**         | Token usage −14.7%, startup +8.2% (within threshold)                                 |
| **Rollback**            | Backup in `.omg/backups/migrations/`, downgrade to `@trac3r/oh-my-god@2.3.0`         |

## Breaking Changes

### 1. Enforcement Mode Change (Soft-Block)

In v3.0.0, the default enforcement mode for security violations has shifted from advisory (warnings) to a "soft-block". High-risk actions will now pause execution and require explicit confirmation unless pre-authorized.

- **Impact**: Automation scripts that were not previously encountering blocks may now pause.
- **Action**: Use `--apply` or update `.omg/policy.yaml` to authorize specific recurring high-risk operations.

### 2. Version Bump Requirements

Minimum dependency versions have been raised. Node.js >=18 and Python >=3.10 are now strictly required and enforced during `env doctor`.

- **Impact**: Installation or updates will fail on older environments.
- **Action**: Upgrade your runtime environment before running `npx omg install`.

### 3. CMMS Tier Routing Required

State persistence now mandates a tier selection. Un-tiered memory routing is deprecated and will default to the `Micro` tier, which may cause context truncation for large tasks.

- **Impact**: Complex tasks may lose context if not explicitly routed to the `Ship` tier.
- **Action**: Update your task definitions to include a `tier` parameter or enable `cmms_memory_tiers` auto-routing.

---

## Migration Steps

Run the following command to migrate your existing installation to v3.0.0:

```bash
npx omg migrate --from=2.3.0 --to=3.0.0
```

---

## New Features Overview

### Phase 1: Context & Memory

- **CMMS Memory Tiers**: Auto/Micro/Ship tier-aware memory routing.
- **Context Durability**: Freshness scoring and adaptive reconstruction.
- **Session Checkpoints**: `/pause` and `/continue` flows.

### Phase 2: Planning & Thought

- **Governed Deep Planning**: Structured planning with embedded security checkpoints.
- **Society of Thought**: Complexity-gated debate planning.

### Phase 3: Governance & Security

- **Approval UI**: Interactive terminal interface for governance gates.
- **MutationGate**: Hard block on unauthorized file mutations.
- **Audit SIEM Export**: JSONL export for enterprise security monitoring.

### Phase 4: Multi-Agent & Scale

- **Governed Multi-Agent**: Lane-based tool fabric for sub-agents.
- **Multi-Model Routing**: Complexity-aware model selection.
- **Convergence Detection**: Early stop on no-delta iterations.

---

## Feature Flags

| Flag                          | Default | Description                                           |
| :---------------------------- | :-----: | :---------------------------------------------------- |
| `cmms_memory_tiers`           |   off   | Enables tier-aware memory routing.                    |
| `pause_continue`              |   off   | Enables session checkpoint persistence.               |
| `context_durability`          |   off   | Enables adaptive workspace reconstruction.            |
| `society_of_thought`          |   off   | Enables complexity-gated debate planning.             |
| `ralph_convergence_detection` |   off   | Enables early stop on no-delta iterations.            |
| `ralph_approval_gate`         |   off   | Enables interactive approval for destructive actions. |
| `multi_model_routing`         |   off   | Enables complexity-aware model selection.             |
| `plan_adherence_enforcement`  |   off   | Fails iterations that drift from the plan.            |
| `governed_tool_fabric`        |   off   | Lane-based tool governance with signed approval.      |
| `audit_siem_export`           |   off   | JSONL export for enterprise security monitoring.      |

---

## Performance Benchmark (v2.3.0 → v3.0.0-rc)

| Metric                       | v2.3.0 | v3.0.0-rc |  Delta |       Status        |
| :--------------------------- | -----: | --------: | -----: | :-----------------: |
| Startup (ms)                 |    850 |       920 |  +8.2% | ✅ Within threshold |
| Token usage / session        | 15,000 |    12,800 | −14.7% |     ✅ Improved     |
| Wall clock, simple task (ms) |  3,200 |     3,100 |  −3.1% |     ✅ Improved     |
| Memory (MB)                  |    128 |       145 | +13.3% | ✅ Within threshold |

All regressions are within the 20% tolerance. Token savings come from CMMS tier routing and context durability reducing redundant reconstruction. Full data: `.omg/evidence/benchmark.json`.

---

## Rollback Instructions

If you need to revert to v2.3.0:

1. **Restore State**: Copy the contents of the latest backup in `.omg/backups/migrations/` back to your project root.
2. **Downgrade Package**:
   ```bash
   npm install @trac3r/oh-my-god@2.3.0
   ```
3. **Clear Locks**: Remove `.omg/state/ralph-loop.lock` if it exists.
