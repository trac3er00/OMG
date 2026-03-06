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

## Notes

- `OMG-only` is the recommended adoption mode.
- Use `--mode=coexist` when you need a non-destructive landing with other plugin stacks.
- Run `/OMG:crazy <goal>` after setup.
