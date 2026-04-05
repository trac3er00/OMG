import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const CommandSchema = z.object({
  path: z.string(),
  description: z.string(),
  category: z.string(),
  deprecated: z.boolean().optional(),
  feature_flag: z.string().optional(),
});

const CategorySchema = z.object({
  description: z.string(),
  commands: z.array(z.string()),
});

const RoleSchema = z.object({
  description: z.string(),
  bundle: z.string(),
});

const PluginManifestSchema = z.object({
  name: z.string(),
  version: z.string(),
  description: z.string(),
  type: z.literal("omg-plugin"),
  commands: z.record(z.string(), CommandSchema),
  categories: z.record(z.string(), CategorySchema).optional(),
  roles: z.record(z.string(), RoleSchema).optional(),
});

export type PluginManifest = z.infer<typeof PluginManifestSchema>;

// ---------------------------------------------------------------------------
// Command registration
// ---------------------------------------------------------------------------

export interface RegisteredCommand {
  readonly name: string;
  readonly pluginName: string;
  readonly path: string;
  readonly description: string;
  readonly category: string;
  readonly deprecated: boolean;
  readonly featureFlag: string | undefined;
}

// ---------------------------------------------------------------------------
// PluginLoader
// ---------------------------------------------------------------------------

export class PluginLoader {
  private readonly commands: Map<string, RegisteredCommand> = new Map();
  private readonly manifests: Map<string, PluginManifest> = new Map();

  private constructor() {}

  static create(): PluginLoader {
    return new PluginLoader();
  }

  loadPlugin(pluginDir: string): PluginManifest {
    const manifestPath = join(resolve(pluginDir), "plugin.json");
    if (!existsSync(manifestPath)) {
      throw new Error(`Plugin manifest not found: ${manifestPath}`);
    }

    const raw = readFileSync(manifestPath, "utf8");
    const parsed: unknown = JSON.parse(raw);
    const manifest = PluginManifestSchema.parse(parsed);

    this.manifests.set(manifest.name, manifest);

    for (const [cmdName, cmdDef] of Object.entries(manifest.commands)) {
      const registered: RegisteredCommand = {
        name: cmdName,
        pluginName: manifest.name,
        path: join(resolve(pluginDir), cmdDef.path),
        description: cmdDef.description,
        category: cmdDef.category,
        deprecated: cmdDef.deprecated ?? false,
        featureFlag: cmdDef.feature_flag,
      };
      this.commands.set(`${manifest.name}:${cmdName}`, registered);
    }

    return manifest;
  }

  getCommands(): readonly RegisteredCommand[] {
    return Array.from(this.commands.values());
  }

  getCommandsByPlugin(pluginName: string): readonly RegisteredCommand[] {
    return Array.from(this.commands.values()).filter((c) => c.pluginName === pluginName);
  }

  getCommandsByCategory(category: string): readonly RegisteredCommand[] {
    return Array.from(this.commands.values()).filter((c) => c.category === category);
  }

  getManifest(pluginName: string): PluginManifest | undefined {
    return this.manifests.get(pluginName);
  }

  getPluginNames(): readonly string[] {
    return Array.from(this.manifests.keys());
  }

  getCommandCount(): number {
    return this.commands.size;
  }
}

export function create(): PluginLoader {
  return PluginLoader.create();
}
