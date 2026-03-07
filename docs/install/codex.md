# Install OMG for Codex

## Fast Path

```bash
npm install -g @openai/codex
npm install @trac3er/oh-my-god
```

Then run:

```text
/OMG:setup
```

## Manual Path

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
chmod +x OMG-setup.sh
./OMG-setup.sh install --mode=omg-only --preset=interop
```

## Verify

- OMG detects `codex` during setup and configures shared MCP state.
- `interop` is the recommended preset when Codex is part of a multi-host workflow.
- Run `/OMG:crazy <goal>` once setup confirms host detection and MCP wiring.
