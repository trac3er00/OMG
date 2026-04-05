import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { PluginLoader, create } from "./loader.js";

const PLUGINS_ROOT = join(import.meta.dir, "../../plugins");
const CORE_PLUGIN_DIR = join(PLUGINS_ROOT, "core");
const ADVANCED_PLUGIN_DIR = join(PLUGINS_ROOT, "advanced");

describe("PluginLoader", () => {
  test("create returns a PluginLoader instance", () => {
    const loader = PluginLoader.create();
    expect(loader).toBeInstanceOf(PluginLoader);
  });

  test("loads core plugin manifest", () => {
    const loader = create();
    const manifest = loader.loadPlugin(CORE_PLUGIN_DIR);
    expect(manifest.name).toBe("omg-core");
    expect(manifest.type).toBe("omg-plugin");
  });

  test("core plugin registers >= 20 commands", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    const commands = loader.getCommandsByPlugin("omg-core");
    expect(commands.length).toBeGreaterThanOrEqual(20);
  });

  test("loads advanced plugin manifest", () => {
    const loader = create();
    const manifest = loader.loadPlugin(ADVANCED_PLUGIN_DIR);
    expect(manifest.name).toBe("omg-advanced");
  });

  test("advanced plugin registers 9 commands", () => {
    const loader = create();
    loader.loadPlugin(ADVANCED_PLUGIN_DIR);
    const commands = loader.getCommandsByPlugin("omg-advanced");
    expect(commands.length).toBe(9);
  });

  test("loads both plugins and lists all commands", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    loader.loadPlugin(ADVANCED_PLUGIN_DIR);
    const all = loader.getCommands();
    expect(all.length).toBeGreaterThanOrEqual(29);
  });

  test("getCommandsByCategory returns matching commands", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    const setupCmds = loader.getCommandsByCategory("setup");
    expect(setupCmds.length).toBeGreaterThanOrEqual(2);
    for (const cmd of setupCmds) {
      expect(cmd.category).toBe("setup");
    }
  });

  test("getManifest returns loaded manifest", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    const manifest = loader.getManifest("omg-core");
    expect(manifest).toBeDefined();
    expect(manifest?.version).toBeDefined();
  });

  test("getManifest returns undefined for unknown plugin", () => {
    const loader = create();
    expect(loader.getManifest("nonexistent")).toBeUndefined();
  });

  test("getPluginNames lists loaded plugins", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    loader.loadPlugin(ADVANCED_PLUGIN_DIR);
    const names = loader.getPluginNames();
    expect(names).toContain("omg-core");
    expect(names).toContain("omg-advanced");
  });

  test("throws on missing plugin directory", () => {
    const loader = create();
    expect(() => loader.loadPlugin("/nonexistent/path")).toThrow("Plugin manifest not found");
  });

  test("deprecated commands are flagged", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    const commands = loader.getCommandsByPlugin("omg-core");
    const deprecated = commands.filter((c) => c.deprecated);
    expect(deprecated.length).toBeGreaterThanOrEqual(1);
  });

  test("getCommandCount returns total", () => {
    const loader = create();
    loader.loadPlugin(CORE_PLUGIN_DIR);
    expect(loader.getCommandCount()).toBeGreaterThanOrEqual(20);
  });
});
