/**
 * Skill Active State Management
 *
 * Tracks when a skill is actively executing so the persistent-mode Stop hook
 * can prevent premature session termination.
 *
 * Skills like code-review, plan, tdd, analyze, build-fix, security-review,
 * external-context, deepinit etc. don't write mode state files (ralph-state.json,
 * etc.), so the Stop hook previously had no way to know they were running.
 *
 * This module provides:
 * 1. A protection level registry for all skills (none/light/medium/heavy)
 * 2. Read/write/clear functions for skill-active-state.json
 * 3. A check function for the Stop hook to determine if blocking is needed
 *
 * Fix for: https://github.com/Yeachan-Heo/oh-my-claudecode/issues/1033
 */
export type SkillProtectionLevel = 'none' | 'light' | 'medium' | 'heavy';
export interface SkillStateConfig {
    /** Max stop-hook reinforcements before allowing stop */
    maxReinforcements: number;
    /** Time-to-live in ms before state is considered stale */
    staleTtlMs: number;
}
export interface SkillActiveState {
    active: boolean;
    skill_name: string;
    session_id?: string;
    started_at: string;
    last_checked_at: string;
    reinforcement_count: number;
    max_reinforcements: number;
    stale_ttl_ms: number;
}
/**
 * Get the protection level for a skill.
 * Unknown skills default to 'light' for safety.
 */
export declare function getSkillProtection(skillName: string): SkillProtectionLevel;
/**
 * Get the protection config for a skill.
 */
export declare function getSkillConfig(skillName: string): SkillStateConfig;
/**
 * Resolve the path to skill-active-state.json.
 * Uses session-scoped path when sessionId is provided.
 */
export declare function getSkillStatePath(directory: string, sessionId?: string): string;
/**
 * Read the current skill active state.
 * Returns null if no state exists or state is invalid.
 */
export declare function readSkillActiveState(directory: string, sessionId?: string): SkillActiveState | null;
/**
 * Write skill active state.
 * Called when a skill is invoked via the Skill tool.
 */
export declare function writeSkillActiveState(directory: string, skillName: string, sessionId?: string): SkillActiveState | null;
/**
 * Clear skill active state.
 * Called when a skill completes or is cancelled.
 */
export declare function clearSkillActiveState(directory: string, sessionId?: string): boolean;
/**
 * Check if the skill state is stale (exceeded its TTL).
 */
export declare function isSkillStateStale(state: SkillActiveState): boolean;
/**
 * Check skill active state for the Stop hook.
 * Returns blocking decision with continuation message.
 *
 * Called by checkPersistentModes() in the persistent-mode hook.
 */
export declare function checkSkillActiveState(directory: string, sessionId?: string): {
    shouldBlock: boolean;
    message: string;
    skillName?: string;
};
//# sourceMappingURL=index.d.ts.map