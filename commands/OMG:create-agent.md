---
description: "Create a new OMG markdown agent definition that matches the Bun runtime conventions."
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: "<agent-name>"
---

# /OMG:create-agent

Create a new markdown agent under `agents/` with:

- a clear role
- scope boundaries
- inputs and outputs
- success criteria
- any required `.omg/` artifacts

## Template

```md
# <agent-name>

## Role
- One sentence describing what the agent owns.

## Inputs
- Required files, context, or commands.

## Outputs
- Expected edits, reports, or evidence artifacts.

## Guardrails
- Things the agent must not change or assume.
```
