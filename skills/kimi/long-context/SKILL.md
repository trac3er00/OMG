---
name: kimi-long-context
description: "Use Kimi's 128K token context window for large-scale input processing and cross-file reasoning."
---

# Kimi Long Context

Leverage Kimi's 128K token context window for tasks that require ingesting and reasoning over large volumes of text in a single pass. This skill provides prompt strategies optimized for maximum context utilization with kimi-k1.

## When to Use

Activate this skill when the task matches any of these conditions:

- **Large codebase analysis**: reviewing or auditing 10+ files simultaneously, understanding cross-module dependencies, or tracing call chains across an entire project
- **Multi-file review**: code review spanning multiple PRs, comparing implementations across branches, or holistic architecture assessment
- **Long document processing**: analyzing specifications, RFCs, legal documents, or technical manuals that exceed typical context limits
- **Extended session continuity**: maintaining coherent reasoning across a long conversation with accumulated context from prior turns
- **Cross-reference tasks**: correlating information scattered across multiple sources such as logs, configs, and source files

## Trigger Conditions

```yaml
triggers:
  - input_tokens > 50000
  - file_count > 10
  - task_type: [codebase_audit, architecture_review, specification_analysis]
  - requires: cross_file_reasoning
```

## Prompt Strategies

### 1. Structured Preamble

Always front-load the most critical context. Kimi processes long inputs sequentially — place summary and objectives at the top so the model anchors on intent before digesting bulk content.

```
## Objective
[Clear, concise goal statement]

## Key Files (priority order)
1. [most critical file — full content below]
2. [second most critical]
...

## Detailed Content
[Full file contents, configs, logs]
```

### 2. Section Markers

Use explicit section delimiters when injecting multiple files. This helps the model track boundaries and attribute findings to correct sources.

```
===== FILE: src/auth/handler.ts =====
[content]
===== END FILE =====

===== FILE: src/auth/middleware.ts =====
[content]
===== END FILE =====
```

### 3. Chunked Reasoning Requests

For analysis tasks, request structured output that maps findings back to specific input sections:

```
Analyze the following codebase for security vulnerabilities.
For each finding, report:
- File and line range
- Severity (critical/high/medium/low)
- Description
- Suggested fix
```

### 4. Context Budget Allocation

Reserve 10-15% of the 128K window for the model's response. When loading content:

- Maximum input: ~108K tokens
- Response buffer: ~20K tokens
- If content exceeds budget, prioritize by relevance and truncate least-critical files

## Usage Examples

### Codebase Architecture Review

```
@kimi/long-context
Load all source files from src/ and analyze the dependency graph.
Identify circular dependencies, unused exports, and layering violations.
```

### Multi-File Security Audit

```
@kimi/long-context
Review the following 15 files for authentication and authorization issues.
Cross-reference the middleware chain with route handlers to find unprotected endpoints.
```

### Specification Compliance Check

```
@kimi/long-context
Compare this implementation (files below) against the OpenAPI spec (also below).
Report any endpoints that deviate from the specification.
```

## Limitations

- kimi-k1 context window is 128K tokens — significantly smaller than Gemini's 1M+ window
- Best suited for focused analysis rather than "dump everything" approaches
- Chinese-language inputs may tokenize more efficiently due to kimi-k1's tokenizer optimization
- Response quality can degrade if input lacks clear structure or prioritization

## OMG Integration

- Governed by OMG registry at `@kimi/long-context`
- Respects budget envelope token limits configured in `governance.yaml`
- Evidence outputs are tracked through the standard proof pipeline
