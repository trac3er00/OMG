export const DOMAIN_PACKS = [
  "saas",
  "landing",
  "ecommerce",
  "api",
  "bot",
  "admin",
  "cli",
] as const;
export type DomainPack = (typeof DOMAIN_PACKS)[number];

export interface ValidationResult {
  pack: DomainPack;
  structureValid: boolean;
  hasPackageJson: boolean;
  hasEntryPoint: boolean;
  qualityScore: number;
  issues: string[];
}

export interface PackStructureRequirements {
  requiredFiles: string[];
  requiredDirs: string[];
  minQualityScore: number;
}

export const PACK_REQUIREMENTS: Record<DomainPack, PackStructureRequirements> =
  {
    saas: {
      requiredFiles: ["package.json", "src/index.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
    landing: {
      requiredFiles: ["package.json", "index.html"],
      requiredDirs: [],
      minQualityScore: 80,
    },
    ecommerce: {
      requiredFiles: ["package.json", "src/app.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
    api: {
      requiredFiles: ["package.json", "src/server.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
    bot: {
      requiredFiles: ["package.json", "src/bot.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
    admin: {
      requiredFiles: ["package.json", "src/dashboard.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
    cli: {
      requiredFiles: ["package.json", "src/cli.ts"],
      requiredDirs: ["src"],
      minQualityScore: 80,
    },
  };

/** @param pack Domain pack name @param projectPath Generated project root @param fs File system accessor for testability */
export function validatePackStructure(
  pack: DomainPack,
  projectPath: string,
  fs: { exists: (p: string) => boolean },
): ValidationResult {
  const reqs = PACK_REQUIREMENTS[pack];
  const issues: string[] = [];

  for (const file of reqs.requiredFiles) {
    if (!fs.exists(`${projectPath}/${file}`)) {
      issues.push(`Missing required file: ${file}`);
    }
  }

  for (const dir of reqs.requiredDirs) {
    if (!fs.exists(`${projectPath}/${dir}`)) {
      issues.push(`Missing required directory: ${dir}`);
    }
  }

  const hasPackageJson = fs.exists(`${projectPath}/package.json`);
  const structureValid = issues.length === 0;
  const qualityScore = Math.max(0, 100 - issues.length * 10);

  return {
    pack,
    structureValid,
    hasPackageJson,
    hasEntryPoint: reqs.requiredFiles.some(
      (f) => f.includes("index") || f.includes("server") || f.includes("app"),
    ),
    qualityScore,
    issues,
  };
}

export function runValidationPipeline(
  projectPaths: Partial<Record<DomainPack, string>>,
  fs: { exists: (p: string) => boolean },
): ValidationResult[] {
  return DOMAIN_PACKS.filter((pack) => pack in projectPaths).map((pack) =>
    validatePackStructure(pack, projectPaths[pack]!, fs),
  );
}
