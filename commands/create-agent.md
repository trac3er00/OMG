---
description: "Wizard command for creating new custom agents in ~/.oal/agents/ or .oal/agents/."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "[agent-name]"
---

# /OAL:create-agent — Custom Agent Creation Wizard

Create a custom agent for your project or user-level configuration.

## Prerequisites

Enable the custom agents feature:

```bash
export OAL_CUSTOM_AGENTS_ENABLED=1
```

Or add to your project's `settings.json`:

```json
{
  "_oal": {
    "features": {
      "CUSTOM_AGENTS": true
    }
  }
}
```

## Agent Locations

- **User-level**: `~/.oal/agents/<name>.md` — available in all projects
- **Project-level**: `.oal/agents/<name>.md` — available in this project only

Project-level agents override user-level agents with the same name.

## Quick Start

1. Create the agents directory:

```bash
# For project-level agents:
mkdir -p .oal/agents

# For user-level agents:
mkdir -p ~/.oal/agents
```

2. Create your agent file (e.g., `.oal/agents/my-agent.md`):

```markdown
---
name: my-agent
description: Brief description of what this agent does
model: claude-sonnet-4-5
tools: Read, Grep, Glob, Edit, Write
bundled: false
---

# Agent: My Agent

## Role

Describe the agent's primary role and responsibilities here.
This should be a clear, concise statement of what the agent does.

## Model

`default` (claude-sonnet-4-5) — general-purpose model for this agent.

Available roles: `smol` (haiku, fast), `default` (sonnet), `slow` (opus, deep reasoning).

## Capabilities

- List specific capabilities here
- What tools does this agent use?
- What domains does it specialize in?

## Instructions

Detailed behavioral instructions for the agent.

**Core rules:**
- Rule 1
- Rule 2
- Rule 3

**Strategy:**
1. Step 1
2. Step 2
3. Step 3

## Example Prompts

- "Example prompt 1"
- "Example prompt 2"
- "Example prompt 3"
```

## Required Sections

Your agent **must** include these sections to pass validation:

| Section | Required | Description |
|---------|----------|-------------|
| `# Agent: <name>` | ✅ Yes | Agent header with name |
| `## Role` | ✅ Yes | Primary role description |
| `## Model` | Optional | Model preference (smol/default/slow) |
| `## Capabilities` | Optional | List of capabilities |
| `## Instructions` | Optional | Behavioral instructions |

## Validation

Custom agents are validated on load. Invalid agents (missing required sections) are skipped with warnings.

To verify your agent is valid:

```bash
export OAL_CUSTOM_AGENTS_ENABLED=1
python3 -c "
from runtime.custom_agent_loader import load_custom_agents
agents = load_custom_agents('.')
for a in agents:
    status = '✅' if a['validated'] else '❌'
    print(f\"{status} {a['name']} ({a['level']}) — {a['description'][:60]}\")
    if a.get('issues'):
        for issue in a['issues']:
            print(f\"   ⚠️  {issue}\")
"
```

## Examples

### Minimal Valid Agent

```markdown
# Agent: Greeter

## Role

Simple greeting agent that welcomes users.
```

### Full Agent with All Sections

See the template in Quick Start above.

### Specialized Domain Agent

```markdown
# Agent: Data Pipeline

## Role

ETL pipeline specialist. Designs and optimizes data transformation workflows.

## Model

`slow` (claude-opus-4-5) — deep reasoning for complex pipeline design.

## Capabilities

- Design ETL pipelines with error handling and retry logic
- Optimize SQL queries for large datasets
- Schema migration planning
- Data quality validation rules

## Instructions

You are a data engineering specialist.

**Core rules:**
- Always consider idempotency in pipeline design
- Prefer incremental processing over full reloads
- Include monitoring and alerting in every pipeline

**Strategy:**
1. Understand the data sources and sinks
2. Design the transformation logic
3. Add error handling and retry mechanisms
4. Plan for monitoring and observability
```
