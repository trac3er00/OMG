#!/usr/bin/env bun
function main() {
  process.stdout.write(
    `${JSON.stringify(
      {
        status: "ok",
        hunks: []
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
