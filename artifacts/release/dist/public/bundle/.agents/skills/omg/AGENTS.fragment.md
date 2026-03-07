# OMG Codex Protection Rules

- Channel: `public`
- Protect `.omg/**, .agents/**, .codex/**, .claude/**` from unreviewed mutation.
- Require explicit invocation for production-control-plane skills.
- Rules: `protected_paths, explicit_invocation`
- Automations: `contract-compile, release-readiness`
