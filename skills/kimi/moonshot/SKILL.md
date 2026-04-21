---
name: kimi-moonshot
description: "Moonshot AI native capabilities including multimodal analysis, Chinese NLP, and advanced reasoning."
---

# Kimi Moonshot

- Channel: `public`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Provider: `kimi` (Moonshot AI)
- Model: `kimi-k1` (128K context, specialties: code, chinese_language, analysis)

## Overview

This skill exposes Moonshot AI's native capabilities through the Kimi CLI interface. Moonshot AI (月之暗面) specializes in long-context understanding, Chinese natural language processing, multimodal analysis, and structured reasoning. This skill routes tasks that benefit from Moonshot's unique strengths rather than defaulting to other providers.

## Moonshot AI Capabilities

### Long-Context Understanding

Moonshot's architecture is purpose-built for 128K token windows with minimal degradation at context boundaries. Unlike models that lose coherence at high token counts, Kimi maintains consistent reasoning across the full window.

- Cross-reference analysis across documents exceeding 100K tokens
- Maintaining coherence in multi-document synthesis
- Session continuity across extended conversations

### Chinese NLP Domain

Moonshot AI was developed with first-class Chinese language support, making it the preferred provider for Chinese NLP tasks within the OMG ecosystem.

- **Text classification**: Sentiment analysis, topic categorization, and intent detection for Chinese text
- **Named entity recognition**: Chinese person names, organization names, locations, and domain-specific entities
- **Document summarization**: Abstractive and extractive summarization of Chinese documents
- **Translation quality**: Chinese-to-English and English-to-Chinese translation with domain terminology preservation
- **Bilingual code documentation**: Generating parallel Chinese/English documentation for codebases

### Multimodal Analysis Patterns

When Kimi supports multimodal input, use this skill for:

- **Image-to-text extraction**: OCR and semantic interpretation of Chinese-language images, screenshots, and documents
- **Diagram comprehension**: Interpreting flowcharts, architecture diagrams, and UML with Chinese labels
- **Screenshot analysis**: Understanding UI screenshots for test verification or design review
- **Document digitization**: Converting scanned Chinese documents into structured text

### Advanced Reasoning

Moonshot's reasoning mode provides structured chain-of-thought for complex analysis:

- **Mathematical reasoning**: Step-by-step problem solving with formal notation
- **Logical deduction**: Multi-premise reasoning chains with explicit inference steps
- **Comparative analysis**: Structured pros/cons evaluation of alternatives
- **Root cause analysis**: Systematic diagnostic reasoning from symptoms to causes

## Trigger Conditions

Use `@kimi/moonshot` when:

- Task requires native Chinese NLP (sentiment, NER, summarization, translation)
- Input contains Chinese-language images or scanned documents
- Analysis requires maintaining coherence across 100K+ token contexts
- Task benefits from Moonshot-specific reasoning patterns
- Bilingual (Chinese/English) output is required
- Cost efficiency matters and task fits within Kimi's capability profile

## Domain Specializations

### Academic and Research

- Parsing and summarizing Chinese academic papers
- Cross-referencing citations across large document collections
- Translating technical terminology with domain accuracy

### Enterprise Chinese Content

- Processing Chinese business documents (contracts, reports, specifications)
- Extracting structured data from Chinese-language forms
- Generating bilingual technical documentation

### Code with Chinese Context

- Understanding codebases with Chinese comments and variable names
- Generating code documentation in Chinese
- Translating Chinese software requirements into technical specifications

## Guidelines

### When to Use Moonshot Over Other Providers

- **Chinese-first tasks**: Moonshot is the primary choice for any task where Chinese is the dominant language
- **Cost-effective analysis**: At $0.002/1K tokens, Moonshot handles analytical tasks more economically than premium providers
- **Long-context fidelity**: When context coherence at 100K+ tokens is critical

### When NOT to Use This Skill

- **English-only tasks with no Chinese context**: Other providers may be equally or more effective
- **Security-critical operations**: Prefer Claude Opus for tasks involving sensitive data handling or security analysis
- **Tasks requiring tool use orchestration**: Claude or Codex provide richer MCP integration

## OMG Integration

- Registered in the OMG skill registry at `registry/skills.json`
- Kimi CLI must be on PATH and `~/.kimi/mcp.json` must include `omg-control`
- All Moonshot sessions are governed by OMG policy enforcement
- Evidence and proof artifacts follow standard OMG capture pipelines
- Budget envelope tracking applies to all Kimi model invocations
