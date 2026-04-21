import { readFile, stat } from "node:fs/promises";
import { extname } from "node:path";
import { HostTypeSchema, type HostType } from "../types/config.js";

const DEFAULT_PROVIDER: HostType = "claude";
export const DEFAULT_MAX_VISION_ASSET_BYTES = 10 * 1024 * 1024;

type VisionOperation =
  | "analyzeImage"
  | "extractText"
  | "compareImages"
  | "describeDiagram";

type VisionAdapterMap = Partial<Record<HostType, VisionProviderAdapter>>;

type VisionResultLike = {
  readonly description: string;
  readonly provider?: HostType;
  readonly sourcePath?: string;
  readonly metadata?: Record<string, unknown>;
};

type ComparisonResultLike = {
  readonly summary: string;
  readonly provider?: HostType;
  readonly leftPath?: string;
  readonly rightPath?: string;
  readonly similarityScore?: number;
  readonly differences?: readonly string[];
};

export interface VisionAsset {
  readonly path: string;
  readonly mimeType: string;
  readonly contentBase64: string;
}

export interface VisionResult {
  readonly description: string;
  readonly provider: HostType;
  readonly sourcePath: string;
  readonly metadata?: Record<string, unknown>;
}

export interface ComparisonResult {
  readonly summary: string;
  readonly provider: HostType;
  readonly leftPath: string;
  readonly rightPath: string;
  readonly similarityScore?: number;
  readonly differences?: readonly string[];
}

export interface VisionProviderAdapter {
  readonly supportsVision: boolean;
  analyzeImage?(image: VisionAsset): Promise<VisionResultLike>;
  extractText?(image: VisionAsset): Promise<string>;
  compareImages?(
    leftImage: VisionAsset,
    rightImage: VisionAsset,
  ): Promise<ComparisonResultLike>;
  describeDiagram?(image: VisionAsset): Promise<string>;
}

export interface VisionConfiguration {
  readonly provider?: HostType;
  readonly adapters?: VisionAdapterMap;
}

export class VisionNotSupportedError extends Error {
  readonly provider: HostType;
  readonly operation: VisionOperation;

  constructor(provider: HostType, operation: VisionOperation) {
    super(
      `Provider \"${provider}\" does not expose a vision API for ${operation}. Configure a provider adapter with vision support to enable this feature.`,
    );
    this.name = "VisionNotSupportedError";
    this.provider = provider;
    this.operation = operation;
  }
}

export class VisionAssetTooLargeError extends Error {
  readonly path: string;
  readonly sizeBytes: number;
  readonly maxBytes: number;

  constructor(path: string, sizeBytes: number, maxBytes: number) {
    super(
      `Vision asset at "${path}" is too large (${sizeBytes} bytes). Maximum allowed size is ${maxBytes} bytes.`,
    );
    this.name = "VisionAssetTooLargeError";
    this.path = path;
    this.sizeBytes = sizeBytes;
    this.maxBytes = maxBytes;
  }
}

const DEFAULT_ADAPTERS: Readonly<Record<HostType, VisionProviderAdapter>> = {
  claude: { supportsVision: false },
  codex: { supportsVision: false },
  gemini: { supportsVision: false },
  kimi: { supportsVision: false },
  ollama: { supportsVision: false },
  opencode: { supportsVision: false },
};

let configuredProvider: HostType | undefined;
let configuredAdapters: VisionAdapterMap = {};

export function configureVision(config: VisionConfiguration): void {
  if (config.provider) {
    configuredProvider = config.provider;
  }

  if (config.adapters) {
    configuredAdapters = cloneAdapterMap({
      ...configuredAdapters,
      ...config.adapters,
    });
  }
}

export function resetVisionConfiguration(): void {
  configuredProvider = undefined;
  configuredAdapters = {};
}

export async function analyzeImage(path: string): Promise<VisionResult> {
  const config = getCurrentConfiguration();
  const provider = resolveProvider(config.provider);
  const adapter = getSupportedAdapter(
    provider,
    "analyzeImage",
    config.adapters,
  );
  const image = await loadVisionAsset(path);
  const result = await adapter.analyzeImage(image);
  return normalizeVisionResult(result, provider, path);
}

export async function extractText(path: string): Promise<string> {
  const config = getCurrentConfiguration();
  const provider = resolveProvider(config.provider);
  const adapter = getSupportedAdapter(provider, "extractText", config.adapters);
  const image = await loadVisionAsset(path);
  return adapter.extractText(image);
}

export async function compareImages(
  path1: string,
  path2: string,
): Promise<ComparisonResult> {
  const config = getCurrentConfiguration();
  const provider = resolveProvider(config.provider);
  const adapter = getSupportedAdapter(
    provider,
    "compareImages",
    config.adapters,
  );
  const [leftImage, rightImage] = await Promise.all([
    loadVisionAsset(path1),
    loadVisionAsset(path2),
  ]);
  const result = await adapter.compareImages(leftImage, rightImage);
  return normalizeComparisonResult(result, provider, path1, path2);
}

export async function describeDiagram(path: string): Promise<string> {
  const config = getCurrentConfiguration();
  const provider = resolveProvider(config.provider);
  const adapter = getSupportedAdapter(
    provider,
    "describeDiagram",
    config.adapters,
  );
  const image = await loadVisionAsset(path);
  return adapter.describeDiagram(image);
}

function getCurrentConfiguration(): {
  readonly provider: HostType | undefined;
  readonly adapters: VisionAdapterMap;
} {
  return {
    provider: configuredProvider,
    adapters: configuredAdapters,
  };
}

function resolveProvider(providerFromConfig: HostType | undefined): HostType {
  if (providerFromConfig) {
    return providerFromConfig;
  }

  const candidate = process.env.OMG_PROVIDER;
  const parsed = HostTypeSchema.safeParse(candidate);
  return parsed.success ? parsed.data : DEFAULT_PROVIDER;
}

function getSupportedAdapter(
  provider: HostType,
  operation: "analyzeImage",
  adapters: VisionAdapterMap,
): Required<Pick<VisionProviderAdapter, "analyzeImage">>;
function getSupportedAdapter(
  provider: HostType,
  operation: "extractText",
  adapters: VisionAdapterMap,
): Required<Pick<VisionProviderAdapter, "extractText">>;
function getSupportedAdapter(
  provider: HostType,
  operation: "compareImages",
  adapters: VisionAdapterMap,
): Required<Pick<VisionProviderAdapter, "compareImages">>;
function getSupportedAdapter(
  provider: HostType,
  operation: "describeDiagram",
  adapters: VisionAdapterMap,
): Required<Pick<VisionProviderAdapter, "describeDiagram">>;
function getSupportedAdapter(
  provider: HostType,
  operation: VisionOperation,
  adapters: VisionAdapterMap,
):
  | Required<Pick<VisionProviderAdapter, "analyzeImage">>
  | Required<Pick<VisionProviderAdapter, "extractText">>
  | Required<Pick<VisionProviderAdapter, "compareImages">>
  | Required<Pick<VisionProviderAdapter, "describeDiagram">> {
  const adapter = adapters[provider] ?? DEFAULT_ADAPTERS[provider];
  const operationHandler = adapter[operation];

  if (!adapter.supportsVision || typeof operationHandler !== "function") {
    throw new VisionNotSupportedError(provider, operation);
  }

  return { [operation]: operationHandler } as
    | Required<Pick<VisionProviderAdapter, "analyzeImage">>
    | Required<Pick<VisionProviderAdapter, "extractText">>
    | Required<Pick<VisionProviderAdapter, "compareImages">>
    | Required<Pick<VisionProviderAdapter, "describeDiagram">>;
}

async function loadVisionAsset(path: string): Promise<VisionAsset> {
  const fileStats = await stat(path);
  if (fileStats.size > DEFAULT_MAX_VISION_ASSET_BYTES) {
    throw new VisionAssetTooLargeError(
      path,
      fileStats.size,
      DEFAULT_MAX_VISION_ASSET_BYTES,
    );
  }

  const contents = await readFile(path);
  return {
    path,
    mimeType: inferMimeType(path),
    contentBase64: contents.toString("base64"),
  };
}

function cloneAdapterMap(adapters: VisionAdapterMap): VisionAdapterMap {
  const cloned: VisionAdapterMap = {};
  for (const provider of Object.keys(adapters) as HostType[]) {
    const adapter = adapters[provider];
    if (adapter) {
      cloned[provider] = { ...adapter };
    }
  }
  return cloned;
}

function inferMimeType(path: string): string {
  switch (extname(path).toLowerCase()) {
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".gif":
      return "image/gif";
    case ".webp":
      return "image/webp";
    case ".bmp":
      return "image/bmp";
    case ".svg":
      return "image/svg+xml";
    case ".txt":
      return "text/plain";
    default:
      return "application/octet-stream";
  }
}

function normalizeVisionResult(
  result: VisionResultLike,
  provider: HostType,
  sourcePath: string,
): VisionResult {
  const normalized: VisionResult = {
    description: result.description,
    provider: result.provider ?? provider,
    sourcePath: result.sourcePath ?? sourcePath,
  };

  if (result.metadata) {
    return { ...normalized, metadata: result.metadata };
  }

  return normalized;
}

function normalizeComparisonResult(
  result: ComparisonResultLike,
  provider: HostType,
  leftPath: string,
  rightPath: string,
): ComparisonResult {
  const normalized: ComparisonResult = {
    summary: result.summary,
    provider: result.provider ?? provider,
    leftPath: result.leftPath ?? leftPath,
    rightPath: result.rightPath ?? rightPath,
  };

  if (result.similarityScore !== undefined) {
    return {
      ...normalized,
      similarityScore: result.similarityScore,
      ...(result.differences ? { differences: result.differences } : {}),
    };
  }

  if (result.differences) {
    return { ...normalized, differences: result.differences };
  }

  return normalized;
}
