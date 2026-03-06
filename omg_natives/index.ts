import { existsSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

export const OMG_RUST_ENABLED = /^(1|true|yes)$/i.test(process.env.OMG_RUST_ENGINE_ENABLED || "");
export const RUST_AVAILABLE = false;

export function grep(pattern: string, path: string): string[] {
  try {
    const matcher = new RegExp(pattern);
    return readFileSync(path, "utf8")
      .split(/\r?\n/)
      .filter((line) => matcher.test(line));
  } catch {
    return [];
  }
}

export function globMatch(pattern: string, base = "."): string[] {
  try {
    const glob = new Bun.Glob(pattern);
    return [...glob.scanSync({ cwd: base, absolute: false })].sort();
  } catch {
    return [];
  }
}

export function normalize(text: string): string {
  return text.replace(/\r\n/g, "\n").trim();
}

export function highlightSyntax(code: string, language = ""): string {
  void language;
  return code;
}

export function stripTags(markup: string): string {
  return markup.replace(/<[^>]+>/g, "");
}

export function glob(pattern: string, base = "."): string[] {
  return globMatch(pattern, base);
}

export function shell(command: string, cwd = process.cwd()) {
  const proc = Bun.spawnSync({
    cmd: ["bash", "-lc", command],
    cwd,
    stdout: "pipe",
    stderr: "pipe"
  });
  return {
    exitCode: proc.exitCode,
    stdout: proc.stdout.toString(),
    stderr: proc.stderr.toString()
  };
}

export function text(value: string): string {
  return normalize(value);
}

export function keys(value: Record<string, unknown>): string[] {
  return Object.keys(value || {}).sort();
}

export function highlight(code: string, language = ""): string {
  return highlightSyntax(code, language);
}

export function taskRun(command: string, cwd = process.cwd()) {
  return shell(command, cwd);
}

export function ps() {
  return {
    pid: process.pid,
    ppid: process.ppid,
    argv: [...process.argv]
  };
}

export function prof() {
  return {
    uptime_s: process.uptime(),
    memory: process.memoryUsage()
  };
}

export function image(path: string) {
  const resolved = resolve(path);
  if (!existsSync(resolved)) {
    return { exists: false, path: resolved };
  }
  const stats = statSync(resolved);
  return { exists: true, path: resolved, size: stats.size };
}

export function clipboard() {
  return {
    status: "unsupported",
    reason: "clipboard integration is not bundled in the Bun runtime"
  };
}

export function html(markup: string) {
  return {
    text: stripTags(markup),
    length: markup.length
  };
}

export default {
  OMG_RUST_ENABLED,
  RUST_AVAILABLE,
  grep,
  globMatch,
  normalize,
  highlightSyntax,
  stripTags,
  glob,
  shell,
  text,
  keys,
  highlight,
  taskRun,
  ps,
  prof,
  image,
  clipboard,
  html
};
