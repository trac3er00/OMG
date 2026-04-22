export const MEMORY_CATEGORIES = [
  "user_preferences",
  "project_rules",
  "team_policies",
  "failure_patterns",
] as const;

export type MemoryCategory = (typeof MEMORY_CATEGORIES)[number];

export interface UserPreferences {
  theme?: string;
  model?: string;
  editor?: string;
  shortcuts?: string[];
}

export interface ProjectRules {
  coding_style?: string[];
  forbidden_patterns?: string[];
  naming_conventions?: string[];
}

export interface TeamPolicies {
  approval_required?: boolean;
  access_controls?: Record<string, string[]>;
  review_workflow?: string[];
}

export interface FailurePattern {
  what_failed: string;
  why: string;
  how_to_avoid: string;
  timestamp: string;
}

export interface UniversalMemorySchema {
  user_preferences: UserPreferences;
  project_rules: ProjectRules;
  team_policies: TeamPolicies;
  failure_patterns: FailurePattern[];
}

export const UNIVERSAL_MEMORY_SCHEMA_TEMPLATE: UniversalMemorySchema = {
  user_preferences: {},
  project_rules: {},
  team_policies: {},
  failure_patterns: [],
};
