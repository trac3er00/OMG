export interface MemoryDeps {
  readonly readFile: (path: string) => Promise<string>;
  readonly writeFile: (path: string, content: string) => Promise<void>;
  readonly appendFile: (path: string, content: string) => Promise<void>;
  readonly exists: (path: string) => Promise<boolean>;
  readonly mkdirp: (dir: string) => Promise<void>;
  readonly listDir: (dir: string) => Promise<readonly string[]>;
  readonly remove: (path: string) => Promise<void>;
}

export interface LearningPattern {
  readonly name: string;
  readonly count: number;
}

export class MemoryHook {
  private readonly deps: MemoryDeps;
  private readonly memoryDir: string;

  constructor(projectDir: string, deps: MemoryDeps) {
    this.deps = deps;
    this.memoryDir = `${projectDir}/.omg/state/memory`;
  }

  async recordLearning(key: string, value: string): Promise<string> {
    await this.deps.mkdirp(this.memoryDir);
    const dateStr = formatDate(new Date());
    const keyShort = key.length > 8 ? key.slice(0, 8) : key;
    const filename = `${dateStr}-${keyShort}.md`;
    const filepath = `${this.memoryDir}/${filename}`;

    const content = value.slice(0, 500);
    const fileExists = await this.deps.exists(filepath);
    if (fileExists) {
      await this.deps.appendFile(filepath, "\n" + content);
    } else {
      await this.deps.writeFile(filepath, content);
    }
    return filepath;
  }

  async getLearning(key: string): Promise<string> {
    return this.searchMemories([key]);
  }

  async getRecentMemories(
    maxFiles = 5,
    maxCharsTotal = 300,
  ): Promise<string> {
    const dirExists = await this.deps.exists(this.memoryDir);
    if (!dirExists) return "";

    const allFiles = await this.deps.listDir(this.memoryDir);
    const mdFiles = allFiles
      .filter((f) => f.endsWith(".md"))
      .sort()
      .reverse()
      .slice(0, maxFiles);

    const parts: string[] = [];
    let total = 0;
    const separator = "\n---\n";

    for (const fname of mdFiles) {
      let content: string;
      try {
        content = await this.deps.readFile(`${this.memoryDir}/${fname}`);
      } catch {
        continue;
      }
      const sepLen = parts.length > 0 ? separator.length : 0;
      const remaining = maxCharsTotal - total - sepLen;
      if (remaining <= 0) break;

      if (content.length > remaining) {
        content = content.slice(0, remaining);
      }
      if (!content) break;

      if (parts.length > 0) {
        total += sepLen;
      }
      parts.push(content);
      total += content.length;
      if (total >= maxCharsTotal) break;
    }

    return parts.join(separator);
  }

  async searchMemories(
    queryKeywords: readonly string[],
    maxResults = 3,
    maxChars = 200,
  ): Promise<string> {
    const dirExists = await this.deps.exists(this.memoryDir);
    if (!dirExists) return "";

    const allFiles = await this.deps.listDir(this.memoryDir);
    const mdFiles = allFiles
      .filter((f) => f.endsWith(".md"))
      .sort()
      .reverse();

    const results: { score: number; fname: string; content: string }[] = [];
    for (const fname of mdFiles) {
      let content: string;
      try {
        content = await this.deps.readFile(`${this.memoryDir}/${fname}`);
        content = content.slice(0, 2048);
      } catch {
        continue;
      }
      const lower = content.toLowerCase();
      const score = queryKeywords.reduce(
        (sum, kw) => sum + (lower.includes(kw.toLowerCase()) ? 1 : 0),
        0,
      );
      if (score > 0) {
        results.push({ score, fname, content });
      }
    }

    results.sort((a, b) => b.score - a.score);

    const summaryParts: string[] = [];
    let charsUsed = 0;
    for (const { fname, content } of results.slice(0, maxResults)) {
      const lines = content
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#"));
      const excerpt = lines.slice(0, 3).join(" ").slice(0, 100);
      if (charsUsed + excerpt.length > maxChars) break;
      summaryParts.push(`[${fname}] ${excerpt}`);
      charsUsed += excerpt.length;
    }

    return summaryParts.join("\n");
  }

  async rotateMemories(maxFiles = 50): Promise<number> {
    const dirExists = await this.deps.exists(this.memoryDir);
    if (!dirExists) return 0;

    const allFiles = await this.deps.listDir(this.memoryDir);
    const mdFiles = allFiles.filter((f) => f.endsWith(".md")).sort();
    const excess = mdFiles.length - maxFiles;
    if (excess <= 0) return 0;

    for (const fname of mdFiles.slice(0, excess)) {
      try {
        await this.deps.remove(`${this.memoryDir}/${fname}`);
      } catch {
        continue;
      }
    }
    return excess;
  }
}

export class LearningsAggregator {
  private readonly projectDir: string;
  private readonly deps: MemoryDeps;
  private readonly learningsDir: string;

  constructor(projectDir: string, deps: MemoryDeps) {
    this.projectDir = projectDir;
    this.deps = deps;
    this.learningsDir = `${projectDir}/.omg/state/learnings`;
  }

  async aggregateLearnings(maxPatterns = 10): Promise<string> {
    const dirExists = await this.deps.exists(this.learningsDir);
    if (!dirExists) return "";

    const allTools = new Map<string, number>();
    const allFiles = new Map<string, number>();

    const dirFiles = await this.deps.listDir(this.learningsDir);
    for (const fname of dirFiles) {
      if (!fname.endsWith(".md")) continue;
      let content: string;
      try {
        content = await this.deps.readFile(`${this.learningsDir}/${fname}`);
      } catch {
        continue;
      }

      let inTools = false;
      let inFiles = false;
      for (const line of content.split("\n")) {
        if (line.startsWith("## Most Used Tools")) {
          inTools = true;
          inFiles = false;
          continue;
        }
        if (line.startsWith("## Most Modified Files")) {
          inTools = false;
          inFiles = true;
          continue;
        }
        if (line.startsWith("##")) {
          inTools = false;
          inFiles = false;
          continue;
        }

        const match = /^-\s+(.+?):\s+(\d+)x\s*$/.exec(line.trim());
        if (match !== null) {
          const name = match[1].trim();
          const count = parseInt(match[2], 10);
          if (inTools) {
            allTools.set(name, (allTools.get(name) ?? 0) + count);
          } else if (inFiles) {
            allFiles.set(name, (allFiles.get(name) ?? 0) + count);
          }
        }
      }
    }

    return formatCriticalPatterns(allTools, allFiles, maxPatterns);
  }

  async rotateLearnings(maxFiles = 30): Promise<number> {
    const dirExists = await this.deps.exists(this.learningsDir);
    if (!dirExists) return 0;

    const dirFiles = await this.deps.listDir(this.learningsDir);
    const mdFiles = dirFiles.filter((f) => f.endsWith(".md")).sort();
    const excess = mdFiles.length - maxFiles;
    if (excess <= 0) return 0;

    for (const fname of mdFiles.slice(0, excess)) {
      try {
        await this.deps.remove(`${this.learningsDir}/${fname}`);
      } catch {
        continue;
      }
    }
    return excess;
  }

  async saveCriticalPatterns(): Promise<string> {
    const content = await this.aggregateLearnings();
    if (!content) return "";

    const knowledgeDir = `${this.projectDir}/.omg/knowledge`;
    await this.deps.mkdirp(knowledgeDir);
    const path = `${knowledgeDir}/critical-patterns.md`;
    await this.deps.writeFile(path, content);
    return path;
  }
}

function formatCriticalPatterns(
  tools: Map<string, number>,
  files: Map<string, number>,
  maxPatterns: number,
): string {
  if (tools.size === 0 && files.size === 0) return "";

  const lines = ["# Critical Patterns"];

  if (tools.size > 0) {
    lines.push("## Top Tools");
    const sorted = Array.from(tools.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, maxPatterns);
    for (const [tool, count] of sorted) {
      lines.push(`- ${tool}: ${count}x total`);
    }
  }

  if (files.size > 0) {
    lines.push("## Top Files");
    const sorted = Array.from(files.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, maxPatterns);
    for (const [filepath, count] of sorted) {
      const basename = filepath.split("/").pop() ?? filepath;
      lines.push(`- ${basename}: ${count}x total`);
    }
  }

  return lines.join("\n").slice(0, 500);
}

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
