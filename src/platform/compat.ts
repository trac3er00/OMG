export type Platform = "linux" | "darwin" | "win32" | "unknown";

export function detectPlatform(): Platform {
  const platform = process.platform;
  if (platform === "linux") return "linux";
  if (platform === "darwin") return "darwin";
  if (platform === "win32") return "win32";
  return "unknown";
}

export interface PlatformCompatResult {
  platform: Platform;
  nodeVersion: string;
  pathSeparator: "/" | "\\";
  homeDir: string;
  supported: boolean;
}

export function checkPlatformCompat(): PlatformCompatResult {
  const platform = detectPlatform();
  return {
    platform,
    nodeVersion: process.version,
    pathSeparator: platform === "win32" ? "\\" : "/",
    homeDir: process.env.HOME ?? process.env.USERPROFILE ?? "/home",
    supported: platform !== "unknown",
  };
}
