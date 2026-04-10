export { OmgDatabase } from "./database.js";
export type { DatabaseConfig, FtsSearchResult, Migration } from "./database.js";

export {
  atomicWrite,
  atomicWriteJson,
  readJsonFile,
  readJsonLines,
  appendJsonLine,
} from "./atomic-io.js";

export { StateResolver } from "./state-resolver.js";
export type { StateLayout } from "./state-resolver.js";

export { DSS, MemoryStoreFullError } from "./dss.js";
export type {
  DssConfig,
  DssEntry,
  DssImportResult,
  DssSetOptions,
} from "./dss.js";

export { acquireLock, withLock } from "./file-lock.js";
export type { LockOptions, ReleaseFn } from "./file-lock.js";

export { SessionCache, computeHash } from "./cache.js";
export type { SessionCacheConfig, CacheWriteResult } from "./cache.js";
