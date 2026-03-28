---
description: Universal skill system for all agent providers (Claude Code, Codex, OpenCode, Gemini)
disable-model-invocation: false
---

# Universal Skills

Provider-agnostic skills that work across all supported agent hosts.

## Available Skills

### @governance
Enforce security and governance policies on all tool operations.

- Pre-tool validation
- Post-tool audit logging
- Mutation gate for risky operations

### @orchestrate
Multi-agent orchestration and coordination.

- Task decomposition
- Agent delegation
- Result aggregation

### @memory
Secure, namespaced, encrypted state management.

- Session state persistence
- Cross-session memory
- Secure credential storage

### @proof
Evidence-backed verification for all claims.

- Test result validation
- Build log verification
- Claim adjudication

### @forge
Modular orchestration engine for complex tasks.

- Step-based execution
- Circuit breaker
- Retry policies

## Usage

```bash
# List available universal skills
omg skills list --universal

# Install a universal skill
omg skills install @governance

# Show skill details
omg skills show @orchestrate
```
