/**
 * Canonical taxonomy for OMG subscription tiers, release channels, and feature sets.
 * Mirrors runtime/canonical_taxonomy.py.
 */

export type SubscriptionTier = "community" | "standard" | "pro" | "enterprise";
export type ReleaseChannel = "stable" | "beta" | "canary" | "nightly";
export type AdoptionMode = "omg-only" | "coexist";

export interface TierCapabilities {
  readonly maxAgents: number;
  readonly maxConcurrentJobs: number;
  readonly hasForge: boolean;
  readonly hasBrowser: boolean;
  readonly hasAdvancedOrchestration: boolean;
  readonly teamDispatch: boolean;
}

export const TIER_CAPABILITIES: Record<SubscriptionTier, TierCapabilities> = {
  community: {
    maxAgents: 3,
    maxConcurrentJobs: 5,
    hasForge: false,
    hasBrowser: false,
    hasAdvancedOrchestration: false,
    teamDispatch: false,
  },
  standard: {
    maxAgents: 10,
    maxConcurrentJobs: 20,
    hasForge: false,
    hasBrowser: true,
    hasAdvancedOrchestration: false,
    teamDispatch: false,
  },
  pro: {
    maxAgents: 50,
    maxConcurrentJobs: 100,
    hasForge: true,
    hasBrowser: true,
    hasAdvancedOrchestration: true,
    teamDispatch: true,
  },
  enterprise: {
    maxAgents: 999,
    maxConcurrentJobs: 999,
    hasForge: true,
    hasBrowser: true,
    hasAdvancedOrchestration: true,
    teamDispatch: true,
  },
};

export function getTierCapabilities(tier: SubscriptionTier): TierCapabilities {
  return TIER_CAPABILITIES[tier];
}

export const CANONICAL_VERSION = "3.0.0";
export const CANONICAL_RELEASE_CHANNEL: ReleaseChannel = "stable";
