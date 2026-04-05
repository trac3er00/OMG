"""OMG hooks subsystem entrypoint.

The hooks package hosts pre-execution and post-execution governance gates that
sit between the agent host and runtime tools. Hooks are used to enforce
security, policy, and orchestration invariants before work executes and to
capture verification/ledger outcomes after work completes.

Hook lifecycle phases:
    - pre-tool: Validate and gate an incoming tool request.
    - post-tool: Inspect tool results and attach governance evidence.
    - stop: Handle termination/stop events and persist shutdown state.
    - session-start: Initialize session-scoped state and guardrails.
    - session-end: Finalize artifacts, summaries, and teardown handling.

Hook communication model:
    Hooks read JSON payloads from stdin and emit JSON responses on stdout.
    This keeps hook execution deterministic and host-agnostic across supported
    OMG runtimes.

Key hooks in this subsystem include:
    - firewall: Screens risky or disallowed tool/command patterns.
    - policy_engine: Applies governance and policy decisions to tool requests.
    - stop_dispatcher: Routes and coordinates stop-related lifecycle events.
"""
