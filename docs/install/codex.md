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

## Notes

- OMG detects `codex` during setup and configures shared MCP state.
- Use `interop` when you want a stronger multi-host bridge.
