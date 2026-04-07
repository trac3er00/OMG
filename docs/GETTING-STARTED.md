# Getting Started with OMG

OMG (Oh My God) is a powerful tool that extends the capabilities of existing agent hosts and adds a governance layer. Build products instantly or upgrade your existing workflow with security and verification.

## ⚡ 1-Command Quickstart

The fastest way to see OMG in action is to generate a product instantly:

```bash
# Generate a landing page
npx omg instant "make a landing page"

# Generate a SaaS boilerplate
npx omg instant "create a SaaS app with authentication"
```

### 📦 What you can build
OMG comes with 7 specialized domain packs:
- **SaaS**: Full-stack subscription apps
- **Landing**: High-conversion marketing pages
- **E-commerce**: Storefronts with cart and checkout
- **API**: Robust backend services
- **Bot**: Discord, Slack, and Telegram bots
- **Admin**: Internal dashboards and CMS
- **CLI**: Powerful command-line tools

---

## 🛠️ Installation & Setup

If you want to use OMG as a governance layer for your existing agent host (Claude Code, Codex, etc.):

### 1. Prerequisites
- **Node.js**: >= 18
- **Python**: >= 3.10
- **OS**: macOS or Linux

### 2. Initialize
Run the interactive initializer to set up your environment:

```bash
npx omg init
```

This command runs environment diagnostics (`npx omg env doctor`), previews changes, and applies configuration.

---

## First 5 Commands to Try

1. **Instant**: `npx omg instant "<prompt>"` - Build a product from a single prompt.
2. **Setup**: `npx omg env doctor` - Check if your environment is ready.
3. **Work**: `npx omg ship` - Orchestrate a release with full governance.
4. **Verify**: `npx omg proof open --html` - View the evidence dashboard.
5. **Configure**: `npx omg install --plan` - Preview configuration changes.

## Understanding Presets

OMG uses presets to determine which capabilities to enable. You can choose one during `npx omg init`:

- **minimal**: Core governance and security hooks.
- **standard**: Adds `context7` for documentation retrieval.
- **full**: Adds `websearch` and `omg-memory` for persistent state.
- **experimental**: Enables browser automation via Playwright.

## Quick Wins: What OMG Does Automatically

Once installed, OMG works behind the scenes:

- **MutationGate**: Intercepts and blocks risky file system changes.
- **Security Gates**: Screens `bash` commands for secrets and risky patterns.
- **ProofGate**: Requires machine-generated evidence before accepting a task as "done".
- **Session Health**: Monitors your session state and warns if things look unstable.

## Next Steps

- [Installation Guides](../README.md#install-guides) - Detailed steps for specific hosts.
- [Claude Code Guide](install/claude-code.md) - Specific tips for Claude users.
- [Quick Reference](../QUICK-REFERENCE.md) - A handy list of all commands and presets.

---

_OMG: Your agents, governed._
