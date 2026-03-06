# OMG Provider Routing Reference

- `codex`: backend logic, debugging, security review, algorithms
- `gemini`: UI/UX, CSS, layout, responsive behavior, accessibility
- `kimi`: runtime traces, logs, long-context synthesis, local workspace inspection
- `ccg`: dual-track `codex + gemini`

Readiness commands:

- `python3 scripts/omg.py providers status`
- `python3 scripts/omg.py providers bootstrap --provider codex`
- `python3 scripts/omg.py providers repair --provider codex`
- `python3 scripts/omg.py providers smoke --provider kimi --host-mode claude_dispatch`
