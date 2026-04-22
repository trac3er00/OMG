# Getting Started for Engineers

OMG is tuned for operators who want explicit previews, traceability, and verifiable delivery.

## Fast path

```bash
npx omg env doctor
npx omg install --plan
npx omg install --apply
```

## What engineers usually care about

- Safe mutation flow with preview-before-apply
- Evidence-backed verification instead of trust-me completions
- Trace-friendly artifacts across proof, hooks, and release surfaces

## Commands worth memorizing

- `npx omg ship` — governed release workflow
- `npx omg proof open --html` — inspect generated evidence
- `npx omg blocked --last` — inspect the latest blocked action
- `npx omg contract validate` — verify contract integrity

## Debug posture

- Run doctor first when environment behavior looks wrong.
- Check proof artifacts before assuming a task really passed.
- Keep setup explicit: preview, inspect, then apply.

## Next step

Continue with [docs/command-surface.md](command-surface.md) and [docs/proof.md](proof.md) for deeper operational detail.
