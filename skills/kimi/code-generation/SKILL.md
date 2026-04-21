---
name: kimi-code-generation
description: "Kimi-optimized code generation with multi-language support and structured output patterns."
---

# Kimi Code Generation

- Channel: `public`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Provider: `kimi`
- Model: `kimi-k1` (128K context, specialties: code, chinese_language, analysis)

## Overview

This skill optimizes Kimi for code generation tasks by leveraging its strengths in structured code output, multi-language synthesis, and large-context code comprehension. Kimi excels at generating code that spans multiple files and languages within a single context window, particularly when the task involves Chinese-language specifications or documentation.

## Trigger Conditions

Use `@kimi/code-generation` when:

- **Complex multi-file generation**: Task requires coordinated code across 3+ files with consistent interfaces
- **Multi-language output**: Generating code in multiple languages simultaneously (e.g., TypeScript + Python + SQL)
- **Chinese-specification tasks**: Requirements, comments, or documentation are in Chinese
- **Boilerplate-heavy generation**: Large amounts of structured, repetitive code with variations
- **Algorithm implementation from specs**: Translating formal specifications or papers into working code
- **128K context utilization**: Input context (specs, examples, existing code) approaches or exceeds 100K tokens

## Prompt Patterns

### Language Specification

Always specify the target language explicitly when invoking code generation:

```
Generate [language] code that implements [specification].
Use strict typing. Follow [language] idiomatic conventions.
Include inline documentation in [documentation-language].
```

### Code Quality Directives

Append quality constraints to generation prompts:

```
Requirements:
- Type-safe: all public interfaces must have explicit types
- Error handling: wrap external calls in try/catch with typed errors
- Testable: pure functions where possible, dependency injection for side effects
- Documented: JSDoc/docstring for all exported symbols
```

### Multi-File Coordination

For cross-file generation, provide the file tree upfront:

```
Target structure:
  src/models/user.ts
  src/services/auth.ts
  src/routes/api.ts

Generate all files with consistent imports and shared type definitions.
```

## Examples

### TypeScript Service Generation

```
@kimi/code-generation
Generate a TypeScript REST service with:
- Express router with typed request/response
- Zod validation schemas
- Repository pattern for data access
- Error middleware with structured error responses
```

### Python Algorithm Implementation

```
@kimi/code-generation
Implement the following algorithm in Python 3.11+:
- Use dataclasses for structured data
- Type hints on all functions
- Include pytest test cases
- Add Chinese comments explaining the algorithm steps
```

### Complex Cross-Language Generation

```
@kimi/code-generation
Generate a full-stack feature:
- Backend: Python FastAPI endpoint with Pydantic models
- Frontend: TypeScript React component with hooks
- Database: SQL migration script
- Shared types between frontend and backend
```

## Guidelines

### When to Prefer Kimi Over Claude for Code Generation

- **Chinese-language projects**: Kimi provides superior handling of Chinese comments, documentation, and variable naming conventions
- **Cost-sensitive bulk generation**: Kimi-k1 at $0.002/1K tokens is more economical than Claude Sonnet for large generation batches
- **Specification-to-code translation**: When translating formal specs or academic papers (especially Chinese-language) into code
- **Boilerplate amplification**: Generating many similar files with systematic variations

### When NOT to Use This Skill

- **Security-critical code**: Prefer Claude Opus for code that handles authentication, encryption, or financial transactions
- **Deep architectural reasoning**: Prefer Claude for code requiring complex design pattern decisions
- **Single-file edits**: For small edits, any model suffices; skill overhead is unnecessary

## OMG Integration

- Skills are governed through the OMG registry at `registry/skills.json`
- Code generation output is subject to MutationGate file-write policies
- Generated code evidence is captured for ProofGate verification
- All generation sessions respect budget envelope token tracking
