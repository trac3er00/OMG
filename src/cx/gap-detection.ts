export type GapCategory =
  | "security"
  | "error-handling"
  | "accessibility"
  | "testing"
  | "documentation"
  | "deployment"
  | "monitoring"
  | "reliability";

export type GapSeverity = "critical" | "high" | "medium" | "low";

export interface Gap {
  readonly category: GapCategory;
  readonly severity: GapSeverity;
  readonly title: string;
  readonly description: string;
  readonly trigger: string;
  readonly suggestion: string;
}

export interface ProjectScan {
  readonly files: readonly string[];
  readonly directories: readonly string[];
  readonly dependencies: readonly string[];
  readonly hasPackageJson: boolean;
}

interface GapRule {
  readonly category: GapCategory;
  readonly severity: GapSeverity;
  readonly title: string;
  readonly description: string;
  readonly suggestion: string;
  /** Returns a trigger reason if the gap is detected, or null if no gap. */
  readonly detect: (scan: ProjectScan) => string | null;
}

const MAX_SUGGESTIONS = 5;

function hasAny(
  items: readonly string[],
  patterns: readonly RegExp[],
): boolean {
  return items.some((item) => patterns.some((p) => p.test(item)));
}

function allItems(scan: ProjectScan): readonly string[] {
  return [...scan.files, ...scan.directories];
}

const ROUTE_PATTERNS: readonly RegExp[] = [
  /routes?\b/i,
  /controller/i,
  /endpoint/i,
  /api\//i,
  /handlers?\b/i,
];

const AUTH_PATTERNS: readonly RegExp[] = [
  /auth/i,
  /passport/i,
  /jwt/i,
  /oauth/i,
  /session/i,
  /login/i,
  /guard/i,
];

const AUTH_DEP_PATTERNS: readonly RegExp[] = [
  /passport/i,
  /jsonwebtoken/i,
  /jwt/i,
  /oauth/i,
  /bcrypt/i,
  /next-auth/i,
  /auth0/i,
  /clerk/i,
  /lucia/i,
  /supabase/i,
];

const RATE_LIMIT_PATTERNS: readonly RegExp[] = [/rate[-_]?limit/i, /throttl/i];

const RATE_LIMIT_DEP_PATTERNS: readonly RegExp[] = [
  /rate[-_]?limit/i,
  /bottleneck/i,
  /express-rate/i,
  /throttle/i,
];

const ERROR_HANDLER_PATTERNS: readonly RegExp[] = [
  /error[-_]?handler/i,
  /error[-_]?middleware/i,
  /error[-_]?boundary/i,
  /global[-_]?error/i,
  /exception[-_]?filter/i,
];

const TEST_PATTERNS: readonly RegExp[] = [
  /\.test\./i,
  /\.spec\./i,
  /\/__tests__\//i,
  /\/test\//i,
  /\/tests\//i,
];

const TEST_DEP_PATTERNS: readonly RegExp[] = [
  /jest/i,
  /mocha/i,
  /vitest/i,
  /cypress/i,
  /playwright/i,
  /testing-library/i,
];

const CI_PATTERNS: readonly RegExp[] = [
  /\.github\/workflows/i,
  /\.gitlab-ci/i,
  /Jenkinsfile/i,
  /\.circleci/i,
  /\.travis/i,
  /azure-pipelines/i,
  /bitbucket-pipelines/i,
];

const DOCKER_PATTERNS: readonly RegExp[] = [
  /[Dd]ockerfile/,
  /docker-compose/i,
  /\.dockerignore/,
];

const DEPLOY_PATTERNS: readonly RegExp[] = [
  ...CI_PATTERNS,
  ...DOCKER_PATTERNS,
  /vercel\.json/i,
  /netlify\.toml/i,
  /fly\.toml/i,
  /render\.yaml/i,
  /k8s/i,
  /kubernetes/i,
  /terraform/i,
  /pulumi/i,
  /ansible/i,
];

const LOGGING_PATTERNS: readonly RegExp[] = [
  /logger/i,
  /logging/i,
  /log[-_]?config/i,
];

const LOGGING_DEP_PATTERNS: readonly RegExp[] = [
  /winston/i,
  /pino/i,
  /bunyan/i,
  /log4js/i,
  /morgan/i,
  /signale/i,
];

const MONITORING_PATTERNS: readonly RegExp[] = [
  /monitor/i,
  /health[-_]?check/i,
  /metrics/i,
  /tracing/i,
  /sentry/i,
  /datadog/i,
  /observ/i,
];

const MONITORING_DEP_PATTERNS: readonly RegExp[] = [
  /sentry/i,
  /datadog/i,
  /newrelic/i,
  /opentelemetry/i,
  /prometheus/i,
  /prom-client/i,
  /elastic-apm/i,
];

const VALIDATION_PATTERNS: readonly RegExp[] = [
  /validat/i,
  /schema/i,
  /sanitiz/i,
];

const VALIDATION_DEP_PATTERNS: readonly RegExp[] = [
  /^zod$/i,
  /^joi$/i,
  /^yup$/i,
  /class-validator/i,
  /ajv/i,
  /superstruct/i,
  /valibot/i,
];

const DB_PATTERNS: readonly RegExp[] = [
  /model/i,
  /schema/i,
  /migration/i,
  /database/i,
  /prisma/i,
  /drizzle/i,
  /sequelize/i,
  /typeorm/i,
  /knex/i,
  /\.sql$/i,
];

const README_PATTERNS: readonly RegExp[] = [/readme/i, /README/];

const DOCS_PATTERNS: readonly RegExp[] = [
  ...README_PATTERNS,
  /docs?\//i,
  /CONTRIBUTING/i,
  /CHANGELOG/i,
  /API\.md/i,
];

const A11Y_PATTERNS: readonly RegExp[] = [
  /a11y/i,
  /accessibility/i,
  /aria/i,
  /wcag/i,
];

const FRONTEND_PATTERNS: readonly RegExp[] = [
  /component/i,
  /\.tsx$/i,
  /\.jsx$/i,
  /\.vue$/i,
  /\.svelte$/i,
  /pages?\//i,
  /views?\//i,
];

const FRONTEND_DEP_PATTERNS: readonly RegExp[] = [
  /^react$/i,
  /^vue$/i,
  /^svelte$/i,
  /^next$/i,
  /^nuxt$/i,
  /^angular/i,
  /solid-js/i,
];

const GAP_RULES: readonly GapRule[] = [
  {
    category: "security",
    severity: "critical",
    title: "Authentication missing",
    description:
      "Project has routes/controllers but no authentication layer detected.",
    suggestion:
      "Add an authentication middleware (e.g., passport, next-auth, or JWT-based auth).",
    detect(scan) {
      const all = allItems(scan);
      const hasRoutes = hasAny(all, ROUTE_PATTERNS);
      const hasAuth =
        hasAny(all, AUTH_PATTERNS) ||
        hasAny(scan.dependencies, AUTH_DEP_PATTERNS);
      if (hasRoutes && !hasAuth) {
        return "Routes/controllers found without authentication layer";
      }
      return null;
    },
  },
  {
    category: "security",
    severity: "high",
    title: "Input validation missing",
    description:
      "API endpoints detected but no input validation or schema enforcement found.",
    suggestion:
      "Add request validation using zod, joi, or class-validator to prevent injection and malformed data.",
    detect(scan) {
      const all = allItems(scan);
      const hasApi = hasAny(all, ROUTE_PATTERNS);
      const hasValidation =
        hasAny(all, VALIDATION_PATTERNS) ||
        hasAny(scan.dependencies, VALIDATION_DEP_PATTERNS);
      if (hasApi && !hasValidation) {
        return "API endpoints found without input validation";
      }
      return null;
    },
  },
  {
    category: "reliability",
    severity: "high",
    title: "Rate limiting missing",
    description:
      "API endpoints detected but no rate limiting or throttling mechanism found.",
    suggestion:
      "Add rate limiting middleware (e.g., express-rate-limit, bottleneck) to prevent abuse.",
    detect(scan) {
      const all = allItems(scan);
      const hasApi = hasAny(all, ROUTE_PATTERNS);
      const hasRateLimit =
        hasAny(all, RATE_LIMIT_PATTERNS) ||
        hasAny(scan.dependencies, RATE_LIMIT_DEP_PATTERNS);
      if (hasApi && !hasRateLimit) {
        return "API endpoints found without rate limiting";
      }
      return null;
    },
  },
  {
    category: "error-handling",
    severity: "high",
    title: "Global error handler missing",
    description:
      "Application has routes but no centralized error handling detected.",
    suggestion:
      "Add a global error handler or error boundary to catch unhandled exceptions gracefully.",
    detect(scan) {
      const all = allItems(scan);
      const hasRoutes = hasAny(all, ROUTE_PATTERNS);
      const hasErrorHandler = hasAny(all, ERROR_HANDLER_PATTERNS);
      if (hasRoutes && !hasErrorHandler) {
        return "Routes found without centralized error handling";
      }
      return null;
    },
  },
  {
    category: "testing",
    severity: "high",
    title: "No test files detected",
    description:
      "Project has source files but no test files or testing dependencies found.",
    suggestion:
      "Add a test framework (jest, vitest, or mocha) and write tests for critical paths.",
    detect(scan) {
      const all = allItems(scan);
      const hasSource = scan.hasPackageJson && scan.files.length > 3;
      const hasTests =
        hasAny(all, TEST_PATTERNS) ||
        hasAny(scan.dependencies, TEST_DEP_PATTERNS);
      if (hasSource && !hasTests) {
        return "Source files found without any tests or test dependencies";
      }
      return null;
    },
  },
  {
    category: "deployment",
    severity: "medium",
    title: "No deployment configuration",
    description:
      "Project has no CI/CD pipeline, Dockerfile, or cloud deployment config.",
    suggestion:
      "Add a deployment configuration (GitHub Actions, Docker, or cloud provider config).",
    detect(scan) {
      const all = allItems(scan);
      const hasSource = scan.hasPackageJson;
      const hasDeploy = hasAny(all, DEPLOY_PATTERNS);
      if (hasSource && !hasDeploy) {
        return "Project has no deployment or CI/CD configuration";
      }
      return null;
    },
  },
  {
    category: "monitoring",
    severity: "medium",
    title: "No logging or monitoring",
    description:
      "Application has backend code but no structured logging or monitoring detected.",
    suggestion:
      "Add a structured logger (winston, pino) and error monitoring (Sentry, Datadog).",
    detect(scan) {
      const all = allItems(scan);
      const hasBackend = hasAny(all, ROUTE_PATTERNS);
      const hasLogging =
        hasAny(all, LOGGING_PATTERNS) ||
        hasAny(scan.dependencies, LOGGING_DEP_PATTERNS);
      const hasMonitoring =
        hasAny(all, MONITORING_PATTERNS) ||
        hasAny(scan.dependencies, MONITORING_DEP_PATTERNS);
      if (hasBackend && !hasLogging && !hasMonitoring) {
        return "Backend code found without logging or monitoring";
      }
      return null;
    },
  },
  {
    category: "documentation",
    severity: "low",
    title: "No documentation found",
    description: "Project has no README or documentation directory.",
    suggestion:
      "Add a README.md with setup instructions, usage, and API reference.",
    detect(scan) {
      const all = allItems(scan);
      const hasSource = scan.hasPackageJson;
      const hasDocs = hasAny(all, DOCS_PATTERNS);
      if (hasSource && !hasDocs) {
        return "No README or documentation found";
      }
      return null;
    },
  },
  {
    category: "accessibility",
    severity: "medium",
    title: "No accessibility considerations",
    description:
      "Frontend components detected but no accessibility tooling or patterns found.",
    suggestion:
      "Add accessibility testing (axe-core, pa11y) and ensure ARIA attributes are used.",
    detect(scan) {
      const all = allItems(scan);
      const hasFrontend =
        hasAny(all, FRONTEND_PATTERNS) ||
        hasAny(scan.dependencies, FRONTEND_DEP_PATTERNS);
      const hasA11y = hasAny(all, A11Y_PATTERNS);
      if (hasFrontend && !hasA11y) {
        return "Frontend components found without accessibility considerations";
      }
      return null;
    },
  },
  {
    category: "monitoring",
    severity: "medium",
    title: "No health check endpoint",
    description:
      "Backend application detected but no health check endpoint found.",
    suggestion:
      "Add a /health or /readiness endpoint for load balancers and deployment probes.",
    detect(scan) {
      const all = allItems(scan);
      const hasBackend = hasAny(all, ROUTE_PATTERNS);
      const hasDB = hasAny(all, DB_PATTERNS);
      const hasHealthCheck = hasAny(all, [
        /health/i,
        /readiness/i,
        /liveness/i,
      ]);
      if (hasBackend && hasDB && !hasHealthCheck) {
        return "Backend with database found without health check endpoint";
      }
      return null;
    },
  },
];

const SEVERITY_ORDER: Record<GapSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export class GapDetector {
  private readonly rules: readonly GapRule[];
  private readonly maxSuggestions: number;

  constructor(options?: { maxSuggestions?: number }) {
    this.rules = GAP_RULES;
    this.maxSuggestions = options?.maxSuggestions ?? MAX_SUGGESTIONS;
  }

  detect(projectStructure: ProjectScan): Gap[] {
    const detected: Gap[] = [];

    for (const rule of this.rules) {
      const trigger = rule.detect(projectStructure);
      if (trigger !== null) {
        detected.push({
          category: rule.category,
          severity: rule.severity,
          title: rule.title,
          description: rule.description,
          trigger,
          suggestion: rule.suggestion,
        });
      }
    }

    detected.sort(
      (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
    );

    return detected.slice(0, this.maxSuggestions);
  }
}
