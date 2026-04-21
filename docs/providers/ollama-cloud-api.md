# Ollama Cloud API Investigation

_Last verified: 2026-04-21_

## API Status

**Decision: Ollama Cloud has a public REST API available at `https://ollama.com/api`.**

This is not a separate `api.ollama.ai` or `cloud.ollama.com` host in current public docs/observations. The official cloud docs explicitly describe direct cloud access through `ollama.com` acting as a remote Ollama host.

### Evidence summary

- `https://ollama.com/api/tags` returns `200` with a JSON model list.
- `https://ollama.com/api/chat` without auth returns `401 unauthorized` (expected for protected inference).
- `https://api.ollama.ai` and `https://cloud.ollama.com` do not resolve in DNS from this environment.
- Official docs (`docs.ollama.com/cloud`, `docs.ollama.com/api/authentication`) state cloud API base URL is `https://ollama.com/api`.
- Upstream repo (`ollama/ollama`) includes cloud docs (`docs/cloud.mdx`) and cloud-proxy related release/commit activity, indicating active cloud support.

## Base URL

- **Cloud REST base URL:** `https://ollama.com/api`
- **Local Ollama base URL (for comparison):** `http://localhost:11434/api`

The path shape matches local Ollama APIs (`/api/tags`, `/api/chat`), which aligns with existing local provider behavior in `src/providers/ollama.ts`.

## Authentication

- **Method:** Bearer token via `Authorization` header
- **Key source:** API key generated from `https://ollama.com/settings/keys`
- **Env var convention:** `OLLAMA_API_KEY`
- **Header format:** `Authorization: Bearer $OLLAMA_API_KEY`

Notes:
- Local `localhost:11434` API does not require auth by default.
- Direct cloud calls to `ollama.com/api` require API-key auth for protected inference endpoints.

## Endpoints

### Model list API

- **Endpoint:** `GET https://ollama.com/api/tags`
- **Observed result:** `200 OK`, JSON payload with `models[]` metadata
- **Purpose:** discover available cloud models and metadata before routing

### Chat API

- **Endpoint:** `POST https://ollama.com/api/chat`
- **Observed unauthenticated result:** `401 unauthorized`
- **Expected authenticated usage:** same request body structure as local Ollama chat API (`model`, `messages`, `stream`, etc.)

### Streaming support

- Official API docs describe Ollama chat/generate as streaming by default.
- `stream: false` disables streaming; `stream: true` (or omitted) returns streamed chunks.
- The cloud docs show `client.chat(..., stream=True)` examples against `host="https://ollama.com"`.

## Release/GitHub Check

`https://github.com/ollama/ollama/releases` and API output show ongoing release activity. Recent release notes are mostly model/runtime/integration focused, with cloud details often documented in docs and code changes rather than a dedicated “Cloud API launch” release note. This supports treating cloud API as an existing/active surface rather than a newly announced endpoint family.

## Fallback Strategy

**Clear decision:**

1. **Primary:** use direct Ollama Cloud REST (`https://ollama.com/api`) with API-key auth.
2. **Fallback A (compat):** if direct cloud API is unavailable/blocked, route through existing local Ollama daemon (`http://localhost:11434/api`) and rely on `ollama signin`-backed cloud passthrough behavior.
3. **Fallback B (provider abstraction):** maintain a separate `ollama-cloud` provider that can degrade to an OpenAI-compatible wrapper layer when deployment environments require a standardized `v1`-style client surface.

Rationale:
- Keeps `ollama` (local) and `ollama-cloud` (hosted) as separate provider identities.
- Preserves reliability under DNS/network/policy failures.
- Minimizes implementation risk by reusing existing local request schema and transport semantics.
