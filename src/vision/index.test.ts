import { beforeEach, describe, expect, mock, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_MAX_VISION_ASSET_BYTES,
  type VisionAsset,
  VisionAssetTooLargeError,
  VisionNotSupportedError,
  analyzeImage,
  compareImages,
  configureVision,
  describeDiagram,
  extractText,
  resetVisionConfiguration,
} from "./index.js";

const fixturePath = fileURLToPath(
  new URL("../../tests/fixtures/vision/test-image.txt", import.meta.url),
);

describe("vision module", () => {
  beforeEach(() => {
    resetVisionConfiguration();
  });

  test("analyzeImage returns a structured provider-backed description", async () => {
    const analyzeImageMock = mock(async (_asset: VisionAsset) => ({
      description: "mock provider description",
    }));

    configureVision({
      provider: "claude",
      adapters: {
        claude: {
          supportsVision: true,
          analyzeImage: analyzeImageMock,
        },
      },
    });

    await expect(analyzeImage(fixturePath)).resolves.toEqual({
      description: "mock provider description",
      provider: "claude",
      sourcePath: fixturePath,
    });

    expect(analyzeImageMock).toHaveBeenCalledTimes(1);
    const [asset] = analyzeImageMock.mock.calls[0] ?? [];
    expect(asset?.path).toBe(fixturePath);
    expect(asset?.mimeType).toBe("text/plain");
    expect(typeof asset?.contentBase64).toBe("string");
    expect(asset?.contentBase64.length).toBeGreaterThan(0);
  });

  test("extractText returns OCR text from the configured provider adapter", async () => {
    const extractTextMock = mock(async () => "HELLO FROM MOCK OCR");

    configureVision({
      provider: "claude",
      adapters: {
        claude: {
          supportsVision: true,
          extractText: extractTextMock,
        },
      },
    });

    await expect(extractText(fixturePath)).resolves.toBe("HELLO FROM MOCK OCR");
    expect(extractTextMock).toHaveBeenCalledTimes(1);
  });

  test("compareImages and describeDiagram delegate through the provider adapter", async () => {
    const compareImagesMock = mock(async () => ({
      summary: "images are visually identical",
      similarityScore: 1,
    }));
    const describeDiagramMock = mock(
      async () => "diagram contains one box connected to another box",
    );

    configureVision({
      provider: "claude",
      adapters: {
        claude: {
          supportsVision: true,
          compareImages: compareImagesMock,
          describeDiagram: describeDiagramMock,
        },
      },
    });

    await expect(compareImages(fixturePath, fixturePath)).resolves.toEqual({
      summary: "images are visually identical",
      provider: "claude",
      leftPath: fixturePath,
      rightPath: fixturePath,
      similarityScore: 1,
    });
    await expect(describeDiagram(fixturePath)).resolves.toBe(
      "diagram contains one box connected to another box",
    );

    expect(compareImagesMock).toHaveBeenCalledTimes(1);
    expect(describeDiagramMock).toHaveBeenCalledTimes(1);
  });

  test("providers without a vision API fail with a clear error", async () => {
    configureVision({ provider: "gemini" });

    await expect(extractText(fixturePath)).rejects.toThrow(
      VisionNotSupportedError,
    );
    await expect(extractText(fixturePath)).rejects.toThrow(
      'Provider "gemini" does not expose a vision API for extractText.',
    );
  });

  test("oversized asset is rejected before base64 load or adapter call", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "omg-vision-"));
    const oversizedPath = join(tempDir, "oversized.txt");
    const extractTextMock = mock(async () => "unreachable");

    try {
      await writeFile(
        oversizedPath,
        Buffer.alloc(DEFAULT_MAX_VISION_ASSET_BYTES + 1, 0x61),
      );

      configureVision({
        provider: "claude",
        adapters: {
          claude: {
            supportsVision: true,
            extractText: extractTextMock,
          },
        },
      });

      await expect(extractText(oversizedPath)).rejects.toThrow(
        VisionAssetTooLargeError,
      );
      expect(extractTextMock).not.toHaveBeenCalled();
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });

  test("configureVision snapshots adapter objects to avoid external mutation bleed", async () => {
    const stableExtractTextMock = mock(async () => "stable");
    const mutatedExtractTextMock = mock(async () => "mutated");

    const adapters = {
      claude: {
        supportsVision: true,
        extractText: stableExtractTextMock,
      },
    };

    configureVision({ provider: "claude", adapters });

    adapters.claude = {
      supportsVision: true,
      extractText: mutatedExtractTextMock,
    };

    await expect(extractText(fixturePath)).resolves.toBe("stable");
    expect(stableExtractTextMock).toHaveBeenCalledTimes(1);
    expect(mutatedExtractTextMock).not.toHaveBeenCalled();
  });
});
