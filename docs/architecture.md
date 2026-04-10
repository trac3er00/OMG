# OMG Architecture

OMG (Oh My God) is a governance and orchestration layer designed to bring safety, verifiability, and multi-model capability to AI agent hosts like Claude Code and Codex.

## Core Design Principles

1.  **Governance-First**: Every tool call is intercepted and evaluated against security policies.
2.  **Evidence-Backed**: Claims must be supported by machine-generated proof (test results, build logs).
3.  **Tiered Memory**: State is managed across different lifespans (session, project, user).
4.  **Host Parity**: Consistent behavior across different AI providers.

## System Components

### 1. Control Plane

The central nervous system of OMG. It manages the session state, coordinates between providers, and enforces policies. It exposes a stdio-first MCP interface (`omg-control`) for seamless host integration.

### 2. CMMS (Tiered Memory)

State is managed across three primary tiers:

- **IMSS (Instant Mode Session State)**: Volatile, in-memory state for the current interaction.
- **DSS (Deep Session State)**: Project-specific persistence, surviving session restarts.
- **USS (User-wide Shared State)**: Global state shared across all projects for a specific user.

### 3. Hooks System

A middleware layer that wraps tool execution:

- **Pre-tool Hooks**: Security screening (Firewall, SecretGuard), budget checks.
- **Post-tool Hooks**: Evidence capture, state synchronization, convergence detection.

### 4. Forge

A modular orchestration engine for complex, multi-step tasks. It uses domain packs to provide specialized capabilities (e.g., SaaS, API, Bot).

### 5. Gates & Judges

- **MutationGate**: Protects the filesystem from unauthorized or risky changes.
- **ProofGate**: Collects and validates evidence.
- **ClaimJudge**: Evaluates agent claims against the collected evidence.

## Module Structure

- `src/providers/`: Adapter layer for different AI backends.
- `src/state/`: Implementation of IMSS, DSS, USS, and Cache.
- `src/governance/`: Policy enforcement and user control logic.
- `src/cx/`: Context Experience modules (Proactive, GapDetection, etc.).
- `src/vision/`: Vision and OCR capabilities.
- `src/skills/`: Domain-specific skill validation and execution.
- `runtime/`: Python-based helpers for security and specialized tasks.
