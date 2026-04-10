import type { IntentAnalysis, IntentDomain } from "./index.js";

export interface Tradeoffs {
  readonly pros: readonly string[];
  readonly cons: readonly string[];
}

export interface OptionEntry {
  readonly label: string;
  readonly description: string;
  readonly tradeoffs: Tradeoffs;
  readonly recommended: boolean;
}

export interface Options131 {
  readonly problem: string;
  readonly options: readonly [OptionEntry, OptionEntry, OptionEntry];
}

interface RawOption {
  readonly label: string;
  readonly description: string;
  readonly tradeoffs: Tradeoffs;
}

interface DomainOptionConfig {
  readonly problem: string;
  readonly recommendedIndex: 0 | 1 | 2;
  readonly raw: readonly [RawOption, RawOption, RawOption];
}

const DOMAIN_CONFIGS: Readonly<Record<IntentDomain, DomainOptionConfig>> = {
  security: {
    problem:
      "Authentication implementation has multiple valid architectures — the right choice depends on scale, client types, and compliance requirements.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Session-based authentication",
        description:
          "Server-side sessions with httpOnly cookies for request authentication and CSRF protection.",
        tradeoffs: {
          pros: [
            "Simple server implementation with built-in framework support",
            "Automatic CSRF protection via same-origin cookie policy",
          ],
          cons: [
            "Requires server-side session storage that scales with active users",
            "Poor fit for mobile apps or third-party API consumers",
          ],
        },
      },
      {
        label: "JWT token-based authentication",
        description:
          "Stateless signed tokens for API-first authentication across services and clients.",
        tradeoffs: {
          pros: [
            "Stateless — no server-side session storage needed",
            "Works natively with SPAs, mobile apps, and microservices",
          ],
          cons: [
            "Token revocation requires a deny-list or short expiry with refresh tokens",
            "Larger per-request payload compared to session cookies",
          ],
        },
      },
      {
        label: "OAuth2 with external identity provider",
        description:
          "Delegate authentication to a managed provider like Auth0, Clerk, or Google Identity.",
        tradeoffs: {
          pros: [
            "Offloads credential storage and security patching to a specialist",
            "Built-in social login, MFA, and SSO support",
          ],
          cons: [
            "Vendor dependency with potential lock-in and per-MAU cost",
            "Complex redirect flows and token exchange choreography",
          ],
        },
      },
    ],
  },

  infrastructure: {
    problem:
      "Infrastructure approach has multiple valid patterns — the right choice depends on team capacity, scale requirements, and operational complexity tolerance.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Manual deployment scripts",
        description:
          "Shell scripts or Makefiles that run deployment steps sequentially on target hosts.",
        tradeoffs: {
          pros: [
            "Zero learning curve and full visibility into each step",
            "No infrastructure tooling dependencies to maintain",
          ],
          cons: [
            "Drift between environments when scripts diverge",
            "No built-in rollback or health-check orchestration",
          ],
        },
      },
      {
        label: "Container orchestration",
        description:
          "Docker images deployed via Kubernetes, ECS, or Compose with declarative manifests.",
        tradeoffs: {
          pros: [
            "Reproducible environments with image-based immutability",
            "Built-in rolling updates, health checks, and scaling",
          ],
          cons: [
            "Significant operational overhead for small teams",
            "Debugging container networking and storage adds complexity",
          ],
        },
      },
      {
        label: "Serverless platform",
        description:
          "Functions or containers deployed to a managed runtime like Lambda, Cloud Run, or Vercel.",
        tradeoffs: {
          pros: [
            "Zero server management with automatic scaling to zero",
            "Pay-per-invocation cost model for variable workloads",
          ],
          cons: [
            "Cold-start latency impacts real-time or low-latency paths",
            "Vendor-specific packaging and deployment constraints",
          ],
        },
      },
    ],
  },

  backend: {
    problem:
      "Backend implementation can follow several structural patterns — the right choice depends on coupling tolerance, scaling needs, and team conventions.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Direct handler implementation",
        description:
          "Implement logic directly in route handlers or controllers without additional abstraction layers.",
        tradeoffs: {
          pros: [
            "Fastest path to working code with minimal boilerplate",
            "Easy to understand for new contributors reading the codebase",
          ],
          cons: [
            "Business logic couples to the HTTP layer making unit testing harder",
            "Reuse across routes requires copy-paste or ad-hoc extraction",
          ],
        },
      },
      {
        label: "Service layer pattern",
        description:
          "Extract business logic into service modules that route handlers delegate to.",
        tradeoffs: {
          pros: [
            "Testable business logic independent of HTTP framework",
            "Clean separation allows swapping transport layers later",
          ],
          cons: [
            "Additional indirection increases initial file count",
            "Risk of anemic services that just proxy to the database",
          ],
        },
      },
      {
        label: "Event-driven architecture",
        description:
          "Publish domain events and let subscribers handle side effects asynchronously.",
        tradeoffs: {
          pros: [
            "Loose coupling between producers and consumers",
            "Natural fit for audit trails, notifications, and async workflows",
          ],
          cons: [
            "Eventual consistency complicates debugging and error handling",
            "Requires message broker infrastructure and dead-letter handling",
          ],
        },
      },
    ],
  },

  frontend: {
    problem:
      "Frontend approach can range from surgical to systemic — the right choice depends on consistency goals, reuse expectations, and time constraints.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Component-level patch",
        description:
          "Make targeted changes within the existing component without structural refactoring.",
        tradeoffs: {
          pros: [
            "Minimal blast radius with fast delivery",
            "No risk of breaking unrelated components",
          ],
          cons: [
            "May accumulate tech debt if the component is already complex",
            "Inconsistency with newer patterns used elsewhere in the app",
          ],
        },
      },
      {
        label: "Feature module approach",
        description:
          "Encapsulate the change in a self-contained feature module with its own state and tests.",
        tradeoffs: {
          pros: [
            "Clean boundaries make the feature independently testable",
            "Easier to remove or replace without affecting the rest of the app",
          ],
          cons: [
            "Upfront module structure adds initial development time",
            "Cross-module communication needs explicit contracts",
          ],
        },
      },
      {
        label: "Design system refactor",
        description:
          "Build or extend a shared component library and implement the feature using system primitives.",
        tradeoffs: {
          pros: [
            "Long-term consistency across all features using shared primitives",
            "Reduces future development cost for similar features",
          ],
          cons: [
            "Significant upfront investment before delivering the feature",
            "Requires buy-in from the team to adopt and maintain the system",
          ],
        },
      },
    ],
  },

  data: {
    problem:
      "Data changes carry migration risk — the right approach depends on downtime tolerance, data volume, and rollback requirements.",
    recommendedIndex: 1,
    raw: [
      {
        label: "In-place schema migration",
        description:
          "Apply ALTER statements directly to the production database during a maintenance window.",
        tradeoffs: {
          pros: [
            "Simplest implementation with a single source of truth",
            "No data synchronization or dual-read logic needed",
          ],
          cons: [
            "Requires downtime or lock contention during migration",
            "Rollback means running a reverse migration under pressure",
          ],
        },
      },
      {
        label: "Dual-write migration",
        description:
          "Write to both old and new schemas simultaneously, then cut over readers once data is consistent.",
        tradeoffs: {
          pros: [
            "Zero-downtime migration with gradual rollout",
            "Instant rollback by switching readers back to the old schema",
          ],
          cons: [
            "Dual-write logic adds application complexity and latency",
            "Data consistency verification needed before final cutover",
          ],
        },
      },
      {
        label: "Blue-green data migration",
        description:
          "Build the new schema as a parallel dataset, backfill from the old one, then swap at the routing layer.",
        tradeoffs: {
          pros: [
            "Complete isolation between old and new schemas during migration",
            "Full validation of new schema before any traffic touches it",
          ],
          cons: [
            "Doubles storage cost during the migration period",
            "Backfill pipeline must handle ongoing writes to the old schema",
          ],
        },
      },
    ],
  },

  documentation: {
    problem:
      "Documentation strategy affects long-term maintainability — the right format depends on audience, update frequency, and discoverability goals.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Inline code documentation",
        description:
          "Add JSDoc, docstrings, or inline comments directly in the source files.",
        tradeoffs: {
          pros: [
            "Documentation lives next to the code it describes and updates together",
            "IDE hover and autocomplete pick up inline docs automatically",
          ],
          cons: [
            "Clutters source files when explanations are long",
            "Not discoverable by non-developers or in external doc portals",
          ],
        },
      },
      {
        label: "Structured Markdown guide",
        description:
          "Write standalone Markdown documents with sections, examples, and cross-references.",
        tradeoffs: {
          pros: [
            "Renders natively on GitHub, GitLab, and most doc platforms",
            "Versioned alongside code with full git history",
          ],
          cons: [
            "Can drift from code when documentation updates are forgotten",
            "No interactive elements without additional tooling",
          ],
        },
      },
      {
        label: "Interactive documentation site",
        description:
          "Generate a documentation site with live examples, API playgrounds, or runnable code blocks.",
        tradeoffs: {
          pros: [
            "Best onboarding experience with try-it-now interactivity",
            "Search, navigation, and versioning built into the platform",
          ],
          cons: [
            "Requires a build pipeline and hosting for the doc site",
            "Higher maintenance burden to keep examples running on latest code",
          ],
        },
      },
    ],
  },

  other: {
    problem:
      "Multiple valid approaches exist — the right choice depends on scope boundaries, risk tolerance, and time constraints.",
    recommendedIndex: 1,
    raw: [
      {
        label: "Minimal targeted fix",
        description:
          "Address the immediate need with the smallest change that satisfies the requirement.",
        tradeoffs: {
          pros: [
            "Fastest delivery with the smallest review surface",
            "Low risk of unintended side effects in unrelated code",
          ],
          cons: [
            "May not address underlying structural issues",
            "Repeated minimal fixes can accumulate into harder-to-maintain code",
          ],
        },
      },
      {
        label: "Structured incremental approach",
        description:
          "Break the work into phased steps that each deliver value and can be independently verified.",
        tradeoffs: {
          pros: [
            "Each phase is reviewable and reversible independently",
            "Balances delivery speed with structural improvement",
          ],
          cons: [
            "Requires upfront planning to define phase boundaries",
            "Intermediate states may carry temporary duplication",
          ],
        },
      },
      {
        label: "Comprehensive redesign",
        description:
          "Redesign the affected area holistically to solve current and anticipated future needs.",
        tradeoffs: {
          pros: [
            "Addresses root causes rather than symptoms",
            "Establishes clean patterns for future development in the area",
          ],
          cons: [
            "Longest delivery timeline with highest review burden",
            "Risk of scope creep and over-engineering beyond current needs",
          ],
        },
      },
    ],
  },
};

const HIGH_DECISION_DOMAINS: readonly IntentDomain[] = [
  "security",
  "infrastructure",
];

function isDecisionWorthy(analysis: IntentAnalysis): boolean {
  if (analysis.intent === "trivial") {
    return false;
  }

  if (
    analysis.complexity.effort === "low" &&
    analysis.complexity.riskLevel === "low"
  ) {
    return false;
  }

  if (analysis.ambiguities.length > 0) {
    return true;
  }

  if (HIGH_DECISION_DOMAINS.includes(analysis.domain)) {
    return true;
  }

  if (
    analysis.intent === "complex" ||
    analysis.intent === "architectural" ||
    analysis.intent === "research"
  ) {
    return true;
  }

  return false;
}

export function generate131Options(
  ambiguity: string,
  context: IntentAnalysis,
): Options131 {
  const config = DOMAIN_CONFIGS[context.domain];
  const problem = ambiguity || config.problem;

  const options = config.raw.map((raw, index) => ({
    label: raw.label,
    description: raw.description,
    tradeoffs: raw.tradeoffs,
    recommended: index === config.recommendedIndex,
  })) as [OptionEntry, OptionEntry, OptionEntry];

  return { problem, options };
}

export function resolveDecisionPoint(
  analysis: IntentAnalysis,
): Options131 | null {
  if (!isDecisionWorthy(analysis)) {
    return null;
  }

  const ambiguity =
    analysis.ambiguities[0] ?? DOMAIN_CONFIGS[analysis.domain].problem;

  return generate131Options(ambiguity, analysis);
}
