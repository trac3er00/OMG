# OMG Governance

OMG provides a robust governance framework to ensure that AI agents operate safely and transparently.

## Enforcement Levels

Every governance gate in OMG can be configured with one of two enforcement levels:

### 1. Enforced (Block)

In this mode, any action that violates the policy is **blocked**. The agent receives an error, and the tool execution is halted. This is the default for production environments and risky operations (e.g., deleting files).

### 2. Advisory (Warn)

In this mode, the policy violation is **recorded and warned**, but the action is allowed to proceed. This is useful for experimental workflows or local development where speed is prioritized over strict safety.

## Governance Gates

### MutationGate

Intercepts file system modifications (Write, Edit, Delete). It prevents accidental destruction of project files and ensures that all changes are intended.

### ToolFabric

Governs the use of specialized tools across different "lanes" (e.g., `lsp-pack`, `terminal-lane`). It ensures that agents only use tools they are authorized for within a specific context.

### ProofGate

Ensures that all claims made by an agent are backed by verifiable evidence. It blocks "completion" of tasks if required evidence (like passing tests) is missing.

## User Control (`governance.yaml`)

Users can customize governance settings by creating a `.omg/governance.yaml` file in their project root.

### Example Configuration

```yaml
version: 1
defaultProvider: claude
gates:
  MutationGate:
    enabled: true
    enforcement: enforced
    providers:
      ollama:
        enforcement: advisory # Allow risky mutations when using local models
  ToolFabric:
    enabled: true
    enforcement: enforced
```

## Audit Trail

Every governance decision (allow, block, warn, bypass) is recorded in the project's audit trail. This ensures full transparency and accountability for all agent actions.
