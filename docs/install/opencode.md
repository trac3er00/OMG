# Install OMG for OpenCode

## Fast Path

```bash
npm install -g opencode-ai
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
./OMG-setup.sh install --mode=coexist --preset=interop
```

## Notes

- `coexist` is useful when OpenCode already owns parts of your workflow.
- Re-run `/OMG:setup` after provider auth changes.
