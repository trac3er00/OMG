---
description: Kimi-specific skills available when using OMG with Kimi CLI
disable-model-invocation: false
---

# Kimi CLI Skills

Skills optimized for Kimi CLI with provider-specific capabilities and OMG governance.

## Available Skills

### @kimi/long-context

Use Kimi's 128K token context window for large inputs.

- Long-document analysis
- Cross-file reasoning
- Extended session continuity

### @kimi/web-search

Use Kimi's built-in web search capability.

- Fresh information retrieval
- Source discovery
- Research assistance

### @kimi/code-generation

Optimize Kimi for code generation tasks.

- Implementation drafting
- Refactor assistance
- Boilerplate generation

### @kimi/moonshot

Access Moonshot AI capabilities through Kimi.

- Model-native assistance
- Advanced completions
- Hosted provider features

## Usage

```bash
# Install Kimi-specific skill
omg skills install @kimi/long-context

# Use in conversation
@kimi/web-search find references for this API
```

## OMG Integration

OMG governs Kimi through MCP registration and policy enforcement.

- Skills are exposed through the OMG registry
- MCP handles tool access and host integration
- Policy, proof, and memory remain centralized in OMG
- Kimi-specific skills follow the same governed install flow as other providers
