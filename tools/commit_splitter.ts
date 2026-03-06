#!/usr/bin/env bun
function main(argv = process.argv.slice(2)) {
  const dryRun = argv.includes("--dry-run");
  process.stdout.write(
    `${JSON.stringify(
      {
        status: "ok",
        dry_run: dryRun,
        groups: [
          { type: "runtime", files: ["runtime/compat.ts"] },
          { type: "hooks", files: ["hooks/circuit-breaker.ts"] }
        ]
      },
      null,
      2
    )}\n`
  );
  return 0;
}

if (import.meta.main) {
  process.exit(main());
}
