const DOMAIN_AGENT_MAP = {
  algorithms: "forge-algorithms",
  code: "forge-code",
  cybersecurity: "forge-cybersecurity",
  health: "forge-health",
  robotics: "forge-robotics",
  vision: "forge-vision",
  "vision-agent": "forge-vision",
} as const;

export type ForgeJobStatus = "pending" | "queued" | "running" | "completed" | "failed";

export interface ForgeJob {
  readonly id: string;
  readonly domain: string;
  readonly task: string;
  readonly agent?: string;
  readonly status: ForgeJobStatus;
}

export class ForgeSystem {
  static create(): ForgeSystem {
    return new ForgeSystem();
  }

  submit(job: ForgeJob): ForgeJob {
    const normalizedDomain = normalizeDomain(job.domain);
    const specialist = DOMAIN_AGENT_MAP[normalizedDomain as keyof typeof DOMAIN_AGENT_MAP];
    if (specialist === undefined) {
      const validDomains = this.validDomains();
      throw new Error(`Unknown domain: ${job.domain}. Valid domains: ${validDomains.join(", ")}`);
    }

    return {
      ...job,
      domain: normalizedDomain,
      agent: specialist,
      status: "queued",
    };
  }

  validDomains(): string[] {
    return Object.keys(DOMAIN_AGENT_MAP).sort();
  }
}

function normalizeDomain(domain: string): string {
  return domain.trim().toLowerCase();
}
