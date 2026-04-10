# OMG Providers

OMG supports multiple AI providers, ensuring that you can use the best model for your task while maintaining consistent governance and orchestration.

## Supported Providers

There are currently 6 providers implemented in OMG:

### 1. Claude

- **Type**: Canonical Behavior-Parity Host
- **Target CLI**: Claude Code (`claude`)
- **Capabilities**: Full support for hooks, HUD, and MCP.
- **MCP Integration**: `omg-control` is registered via `.claude-plugin/mcp.json`.

### 2. Codex

- **Type**: Canonical Behavior-Parity Host
- **Target CLI**: Codex (`codex`)
- **Capabilities**: Full behavior parity with Claude.
- **Config Path**: `~/.codex/config.toml`

### 3. Gemini

- **Type**: Canonical Behavior-Parity Host
- **Target CLI**: Gemini CLI (`gemini`)
- **Capabilities**: Native integration with Google's Gemini models.
- **Config Path**: `~/.gemini/settings.json`

### 4. Kimi

- **Type**: Canonical Behavior-Parity Host
- **Target CLI**: Kimi CLI (`kimi`)
- **Capabilities**: Full support for Kimi's specific tool formats.
- **Config Path**: `~/.kimi/mcp.json`

### 5. Ollama (Local)

- **Type**: Local-First Provider
- **Target**: Local Ollama instance
- **Capabilities**: Allows for private execution of models. Useful for sensitive tasks.
- **Enforcement**: Default enforcement is often set to `advisory` to avoid blocking local experimental flows.

### 6. OpenCode (Compatibility)

- **Type**: Legacy Compatibility Host
- **Target**: OpenCode environments
- **Capabilities**: Maintains support for teams using legacy OpenCode stacks.

## Provider Parity

OMG uses a unified `ICliProvider` interface to ensure that governance gates and orchestration logic work identically regardless of the underlying model.

- **Hook Injection**: Standardized across all providers.
- **Evidence Collection**: Normalized test results and build logs.
- **State Management**: CMMS tiers (IMSS/DSS/USS) are provider-agnostic.

## Configuration

Providers can be selected and configured via `governance.yaml`. You can set the `defaultProvider` and define specific gate enforcement levels per provider.
