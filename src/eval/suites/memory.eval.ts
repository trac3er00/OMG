import type { EvalSuiteDefinition } from "../runner.js";
import { MemoryStore } from "../../state/memory-store.js";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function withTempDir<T>(fn: (dir: string) => T): T {
  const dir = mkdtempSync(join(tmpdir(), "omg-eval-mem-"));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const suite: EvalSuiteDefinition = {
  module: "memory",
  description:
    "Evaluates memory operation correctness: write/read/delete, encryption, PII redaction, search",
  cases: [
    {
      name: "write-read-roundtrip",
      weight: 2,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            await store.write("test-key", {
              content: "hello world",
              tags: ["eval"],
            });
            const entry = await store.read("test-key");

            let score = 0;
            if (entry !== null) score += 25;
            if (entry?.content === "hello world") score += 25;
            if (entry?.key === "test-key") score += 25;
            if (entry?.tags.includes("eval")) score += 25;

            return {
              passed: score === 100,
              score,
              details: `roundtrip score=${score}`,
            };
          } finally {
            store.close();
          }
        }),
    },
    {
      name: "write-overwrite-consistency",
      weight: 1,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            await store.write("key-1", { content: "version-1" });
            await store.write("key-1", { content: "version-2" });
            const entry = await store.read("key-1");

            const correct = entry?.content === "version-2";
            return {
              passed: correct,
              score: correct ? 100 : 0,
              details: `overwrite=${correct}`,
            };
          } finally {
            store.close();
          }
        }),
    },
    {
      name: "delete-operation",
      weight: 1,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            await store.write("to-delete", { content: "temporary" });
            const deleted = await store.delete("to-delete");
            const afterDelete = await store.read("to-delete");
            const deleteMissing = await store.delete("never-existed");

            let score = 0;
            if (deleted) score += 34;
            if (afterDelete === null) score += 33;
            if (!deleteMissing) score += 33;

            return {
              passed: score >= 99,
              score,
              details: `delete=${deleted}, null_after=${afterDelete === null}, missing=${!deleteMissing}`,
            };
          } finally {
            store.close();
          }
        }),
    },
    {
      name: "pii-redaction-quality",
      weight: 2,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            await store.write("pii-test", {
              content:
                "Contact john@example.com or call 555-123-4567. SSN: 123-45-6789",
            });
            const entry = await store.read("pii-test");
            const content = entry?.content ?? "";

            let score = 0;
            let total = 0;

            total++;
            if (content.includes("[REDACTED:EMAIL]")) score++;
            total++;
            if (!content.includes("john@example.com")) score++;
            total++;
            if (content.includes("[REDACTED:PHONE]")) score++;
            total++;
            if (!content.includes("555-123-4567")) score++;
            total++;
            if (content.includes("[REDACTED:SSN]")) score++;
            total++;
            if (!content.includes("123-45-6789")) score++;

            const pctScore = Math.round((score / total) * 100);
            return {
              passed: pctScore >= 80,
              score: pctScore,
              details: `${score}/${total} PII patterns redacted`,
            };
          } finally {
            store.close();
          }
        }),
    },
    {
      name: "encryption-at-rest",
      weight: 2,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            const plaintext = "sensitive-data-that-should-be-encrypted";
            await store.write("enc-test", { content: plaintext });

            const db = store.getRawDb();
            const row = db.get<{ content: string }>(
              "SELECT content FROM memories WHERE key = ? AND namespace = ?",
              ["enc-test", "default"],
            );

            const rawContent = row?.content ?? "";
            const isEncrypted =
              rawContent !== plaintext && rawContent.length > 0;
            const looksLikeJson =
              rawContent.startsWith("{") || rawContent.startsWith("[");

            let score = 0;
            if (isEncrypted) score += 50;
            if (looksLikeJson) score += 25;

            const readBack = await store.read("enc-test");
            if (readBack?.content === plaintext) score += 25;

            return {
              passed: score >= 75,
              score,
              details: `encrypted=${isEncrypted}, json_format=${looksLikeJson}, decrypts_ok=${readBack?.content === plaintext}`,
            };
          } finally {
            store.close();
          }
        }),
    },
    {
      name: "namespace-isolation",
      weight: 1,
      run: () =>
        withTempDir(async (dir) => {
          const storeA = new MemoryStore({
            projectDir: dir,
            namespace: "ns-a",
          });
          const storeB = new MemoryStore({
            projectDir: dir,
            namespace: "ns-b",
          });
          try {
            await storeA.write("shared-key", { content: "from-ns-a" });
            await storeB.write("shared-key", { content: "from-ns-b" });

            const fromA = await storeA.read("shared-key");
            const fromB = await storeB.read("shared-key");

            let score = 0;
            if (fromA?.content === "from-ns-a") score += 50;
            if (fromB?.content === "from-ns-b") score += 50;

            return {
              passed: score === 100,
              score,
              details: `ns-a=${fromA?.content}, ns-b=${fromB?.content}`,
            };
          } finally {
            storeA.close();
            storeB.close();
          }
        }),
    },
    {
      name: "list-and-count",
      weight: 1,
      run: () =>
        withTempDir(async (dir) => {
          const store = new MemoryStore({ projectDir: dir });
          try {
            await store.write("item-a", { content: "a" });
            await store.write("item-b", { content: "b" });
            await store.write("other-c", { content: "c" });

            const allKeys = await store.listKeys();
            const prefixedKeys = await store.listKeys("item-");
            const count = await store.count();

            let score = 0;
            if (allKeys.length === 3) score += 34;
            if (prefixedKeys.length === 2) score += 33;
            if (count === 3) score += 33;

            return {
              passed: score >= 99,
              score,
              details: `all=${allKeys.length}, prefixed=${prefixedKeys.length}, count=${count}`,
            };
          } finally {
            store.close();
          }
        }),
    },
  ],
};

export default suite;
