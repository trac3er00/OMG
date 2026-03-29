export { OmgDatabase } from "./database.js";
export type { DatabaseConfig, FtsSearchResult, Migration } from "./database.js";

export { atomicWrite, atomicWriteJson, readJsonFile, readJsonLines, appendJsonLine } from "./atomic-io.js";

export { StateResolver } from "./state-resolver.js";
export type { StateLayout } from "./state-resolver.js";

export { acquireLock, withLock } from "./file-lock.js";
export type { LockOptions, ReleaseFn } from "./file-lock.js";
