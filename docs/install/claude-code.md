# Install OMG for Claude Code

## Fast Path

```bash
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
./OMG-setup.sh install --mode=omg-only --preset=balanced
```

## Verify

- `OMG-only` is the recommended adoption mode.
- You should see `.mcp.json` plus `.omg/state/cli-config.yaml`.
- If Claude Code already has overlapping plugins, OMG will emit `.omg/state/adoption-report.json`.
- Run `/OMG:crazy <goal>` after setup.
