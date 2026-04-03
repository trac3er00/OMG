---
description: Gemini-specific skills for long context and multimodal
disable-model-invocation: false
---

# Gemini-Specific Skills

Skills optimized for Gemini CLI with long context and multimodal.

## Available Skills

### @gemini/long-context

Leverage Gemini's large context window.

- Document analysis
- Codebase-wide reasoning
- Extended memory

### @gemini/multimodal

Process images, audio, and video alongside text.

- Image understanding
- Video analysis
- Cross-modal reasoning

### @gemini/reasoning

Use Gemini's advanced reasoning capabilities.

- Complex problem solving
- Mathematical reasoning
- Logical deduction

## Gemini Skill Bundle Distribution

Gemini uses an MCP-only approach for OMG integration.

- No local AGENTS.md/SKILL.md bundle is loaded for Gemini
- Gemini capabilities are distributed through registry-backed MCP surfaces
- Provider skills are enabled via OMG-managed registration, not file bundle loading

## Usage

```bash
# Install Gemini-specific skill
omg skills install @gemini/long-context

# Use in conversation
@gemini/multimodal analyze this architecture diagram
```
