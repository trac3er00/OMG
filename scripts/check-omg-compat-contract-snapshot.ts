#!/usr/bin/env bun
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR } from "../runtime/common.ts";
import { buildContractSnapshotPayload } from "../runtime/compat.ts";

function main() {
  const snapshotPath = join(ROOT_DIR, "runtime", "omg_compat_contract_snapshot.json");
  const actual = JSON.parse(readFileSync(snapshotPath, "utf8"));
  const expected = buildContractSnapshotPayload();
  if (JSON.stringify(actual.contracts) !== JSON.stringify(expected.contracts)) {
    process.stderr.write("compat contract snapshot drift detected\n");
    return 1;
  }
  return 0;
}

if (import.meta.main) {
  process.exit(main());
}
