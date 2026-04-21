---
name: kimi-web-search
description: "Use Kimi's built-in web search capability for real-time information retrieval and source discovery."
---

# Kimi Web Search

Leverage Kimi's native web search integration to retrieve current information, discover sources, and ground responses in live data. Unlike external search tool integrations, Kimi's web search is a first-class model capability that the model invokes and synthesizes natively.

## When to Use

Activate this skill when the task requires:

- **Current information**: facts, statistics, documentation, or news that may have changed since model training
- **External API documentation**: looking up library APIs, framework guides, or platform-specific references
- **Research assistance**: gathering background context, finding related work, or discovering prior art
- **Source verification**: confirming claims, checking version compatibility, or validating release dates
- **Trend analysis**: understanding current ecosystem state, popular approaches, or community consensus

## Trigger Conditions

```yaml
triggers:
  - requires: current_information
  - requires: external_reference
  - task_type: [research, documentation_lookup, fact_checking]
  - query_contains:
      ["latest", "current", "2024", "2025", "2026", "new version", "release"]
```

## Prompt Patterns

### 1. Explicit Search Directive

Signal that web search should be used by framing the request around external information needs:

```
Search for the latest release notes of [library] and summarize breaking changes.
```

```
Find the current best practices for [technology] authentication in 2026.
```

### 2. Search-Then-Synthesize

Structure prompts to separate the retrieval phase from the analysis phase:

```
Step 1: Search for documentation on [API/library/framework].
Step 2: Based on the search results, write an implementation that follows the documented patterns.
```

### 3. Multi-Source Corroboration

Request information from multiple angles to improve reliability:

```
Search for [topic] across official documentation, GitHub issues, and community discussions.
Synthesize findings and note any conflicting information between sources.
```

### 4. Citation-Anchored Responses

Request explicit source attribution so results can be verified:

```
Research [topic] and provide your findings with source URLs for each claim.
Format citations as: [claim] (Source: [URL])
```

## Result Citation Patterns

When Kimi returns web search results, they should be structured for traceability:

### Inline Citations

```
The library supports streaming responses as of v3.2 [1].

Sources:
[1] https://docs.example.com/changelog#v3.2
```

### Structured Reference Block

```
## Findings

| Claim | Source | Date Accessed |
|-------|--------|--------------|
| Feature X released in v2.0 | docs.example.com/releases | 2026-04-21 |
| Known issue with Y | github.com/org/repo/issues/123 | 2026-04-21 |
```

## Usage Examples

### Library Version Check

```
@kimi/web-search
What is the latest stable version of Next.js and what are its key new features?
```

### API Documentation Lookup

```
@kimi/web-search
Search for the Stripe API documentation for creating subscription schedules.
Show the required parameters and a working example.
```

### Ecosystem Research

```
@kimi/web-search
Research the current state of WebAssembly support in server-side runtimes.
Compare Deno, Node.js, and Bun's WASM capabilities with source links.
```

### Fact Verification

```
@kimi/web-search
Verify whether [library] has fixed CVE-2025-XXXXX in their latest release.
Cite the specific commit or changelog entry.
```

## Limitations

- Web search results depend on Kimi's search index — coverage may vary by language and domain
- Chinese-language queries may return higher-quality results due to kimi-k1's language optimization
- Search results reflect a point-in-time snapshot and should be validated for time-sensitive decisions
- Not a substitute for authoritative sources — always verify critical claims against official documentation
- Rate and quota limits may apply depending on the Kimi API plan

## OMG Integration

- Governed by OMG registry at `@kimi/web-search`
- Search operations are logged in the OMG session ledger for audit
- Results can feed into the evidence pipeline for proof-backed claims
- Respects data lineage tracking when search results are used in generated outputs
