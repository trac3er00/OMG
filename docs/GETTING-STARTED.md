# Getting Started with OMG

OMG(Oh My God)는 기존 에이전트 호스트의 기능을 확장하고 보안 및 거버넌스 계층을 추가하는 강력한 도구입니다. 이 가이드는 OMG를 빠르게 설치하고 첫 번째 작업을 시작하는 방법을 안내합니다.

Welcome to OMG! This guide helps you get up and running in minutes. OMG upgrades your agent host (Claude Code, Codex, etc.) with governance, safety gates, and evidence-backed verification.

## Prerequisites

Before you start, ensure you have:

- **Node.js**: >= 18
- **Python**: >= 3.10
- **OS**: macOS or Linux

## 1-Minute Install

The fastest way to set up OMG is using the interactive initializer:

```bash
npx omg init
```

This command runs environment diagnostics, previews the changes, and applies the configuration for your detected hosts.

## First 5 Commands to Try

Try these commands to see OMG in action:

1. **Setup**: `npx omg env doctor` - Check if your environment is ready for agent work.
2. **Work**: `npx omg ship` - Orchestrate a release with full governance and safety checks.
3. **Verify**: `npx omg proof open --html` - View the evidence dashboard for your last task.
4. **Configure**: `npx omg install --plan` - Preview configuration changes without applying them.
5. **Advanced**: `npx omg contract validate` - Validate your project's compliance with the OMG contract.

## Understanding Presets

OMG uses presets to determine which capabilities to enable. You can choose one during `npx omg init`:

- **minimal**: Core governance and security hooks. Lightweight and fast.
- **standard**: Adds `context7` for better documentation retrieval.
- **full**: Adds `websearch` and `omg-memory` for persistent state and research.
- **experimental**: Enables browser automation via Playwright.

## Quick Wins: What OMG Does Automatically

Once installed, OMG works behind the scenes to protect your project:

- **MutationGate**: Intercepts and blocks risky file system changes (like accidental deletions).
- **Security Gates**: Automatically screens `bash` commands for secrets and risky patterns.
- **ProofGate**: Requires machine-generated evidence (tests, builds) before accepting a task as "done".
- **Session Health**: Monitors your session state and warns you if things look unstable.

## Next Steps

Ready to dive deeper? Check out these guides:

- [Installation Guides](README.md#install-guides) - Detailed steps for specific hosts.
- [Claude Code Guide](docs/install/claude-code.md) - Specific tips for Claude users.
- [Quick Reference](QUICK-REFERENCE.md) - A handy list of all commands and presets.

---

_OMG: Your agents, governed._
