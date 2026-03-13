---
description: "Contract replay and fixture-based API simulation with fidelity tracking and live verification requirements."
allowed-tools: Read, Write, Edit, MultiEdit, Grep, Glob, Bash(python3:*), Bash(rg:*)
argument-hint: "[ingest|record|serve|verify]"
---

# /OMG:api-twin — Contract Replay

Build a local API twin from contracts and recorded fixtures without treating simulation as final proof.

## Verbs

- `ingest`: load OpenAPI, Swagger, Postman, or example JSON into OMG state
- `record`: store approved request/response fixtures and tag fidelity
- `serve`: replay a fixture locally with optional latency, failure, or schema drift
- `verify`: compare a twin fixture against a live response before release proof

## Rules

- every fixture carries a fidelity tag such as `schema-only`, `recorded`, `recorded-validated`, or `stale`
- simulated endpoints are useful for development, not release signoff
- release proof still requires a final live verification pass
