import { MemoryStore } from "../memory/store.js";

export type Persona = "beginner" | "engineer" | "exec";

const PERSONAS = ["beginner", "engineer", "exec"] as const;
const PERSONA_MEMORY_KEY = "persona.current";
const memoryStore = new MemoryStore();

const BEGINNER_FLAGS = [
  "--beginner",
  "--simple",
  "--explain",
  "--guide",
  "--walkthrough",
  "--help",
];

const ENGINEER_FLAGS = [
  "--engineer",
  "--diff",
  "--trace",
  "--debug",
  "--verbose",
  "--technical",
  "--json",
];

const EXEC_FLAGS = [
  "--exec",
  "--kpi",
  "--roi",
  "--summary",
  "--cost",
  "--progress",
  "--dashboard",
];

function isPersona(value: unknown): value is Persona {
  return typeof value === "string" && PERSONAS.includes(value as Persona);
}

function normalizeFlags(flags: readonly string[] | undefined): string[] {
  return (flags ?? []).map((flag) => flag.trim().toLowerCase()).filter(Boolean);
}

function includesAny(
  flags: readonly string[],
  markers: readonly string[],
): boolean {
  return flags.some((flag) => markers.some((marker) => flag.includes(marker)));
}

export function setPersona(persona: Persona): void {
  memoryStore.set(PERSONA_MEMORY_KEY, persona);
}

export function getPersona(): Persona {
  const stored = memoryStore.get(PERSONA_MEMORY_KEY);
  return isPersona(stored) ? stored : "beginner";
}

export function detectPersona(context: {
  commandCount?: number;
  flags?: string[];
}): Persona {
  const flags = normalizeFlags(context.flags);

  if (includesAny(flags, EXEC_FLAGS)) {
    return "exec";
  }

  if (includesAny(flags, ENGINEER_FLAGS)) {
    return "engineer";
  }

  if (includesAny(flags, BEGINNER_FLAGS)) {
    return "beginner";
  }

  const commandCount = context.commandCount ?? 0;
  if (commandCount >= 12) {
    return "engineer";
  }

  if (commandCount <= 2) {
    return "beginner";
  }

  return getPersona();
}
