import { describe, expect, test } from "bun:test";
import {
  getFirewallConfigForTrust,
  scoreDomain,
  scoreSource,
  TRUST_SCORES,
  TrustTier,
} from "./trust-scoring.js";

describe("trust-scoring", () => {
  test("assigns VERIFIED tier to official docs domains", () => {
    const github = scoreDomain("https://github.com/repo/file");
    expect(github.tier).toBe(TrustTier.VERIFIED);
    expect(github.domain).toBe("github.com");

    const mdn = scoreDomain("https://developer.mozilla.org/en-US/docs/Web");
    expect(mdn.tier).toBe(TrustTier.VERIFIED);
    expect(mdn.domain).toBe("developer.mozilla.org");

    const docs = scoreDomain("https://docs.python.org/3/library/");
    expect(docs.tier).toBe(TrustTier.VERIFIED);
    expect(docs.domain).toBe("docs.python.org");
  });

  test("assigns RESEARCH tier to unknown http domains", () => {
    const unknown = scoreDomain("https://random-blog.example.com/article");
    expect(unknown.tier).toBe(TrustTier.RESEARCH);
    expect(unknown.reason).toBe("General web URL");
  });

  test("assigns LOCAL tier to file:// URLs", () => {
    const fileUrl = scoreDomain("file:///home/user/code/file.ts");
    expect(fileUrl.tier).toBe(TrustTier.LOCAL);
    expect(fileUrl.score).toBe(1.0);

    const absolutePath = scoreDomain("/home/user/code/file.ts");
    expect(absolutePath.tier).toBe(TrustTier.LOCAL);

    const windowsPath = scoreDomain("C:\\Users\\dev\\file.ts");
    expect(windowsPath.tier).toBe(TrustTier.LOCAL);
  });

  test("lower trust triggers stricter sanitization", () => {
    const untrusted = scoreDomain("https://malicious.example.com");
    const verified = scoreDomain("https://github.com/repo");

    const untrustedConfig = getFirewallConfigForTrust(untrusted);
    const verifiedConfig = getFirewallConfigForTrust(verified);

    expect(untrustedConfig.maxContentBytes).toBeLessThan(
      verifiedConfig.maxContentBytes!,
    );
    expect(untrustedConfig.allowExternalRaw).toBe(false);
    expect(verifiedConfig.allowExternalRaw).toBe(false);
  });

  test("getFirewallConfigForTrust returns correct config per tier", () => {
    const local = scoreDomain("file:///path/to/file.ts");
    const verified = scoreDomain("https://npmjs.com/package/foo");
    const research = scoreDomain("https://some-blog.com/article");
    const untrusted = scoreDomain("data:text/html,<script>alert(1)</script>");

    const localConfig = getFirewallConfigForTrust(local);
    expect(localConfig.allowExternalRaw).toBe(true);
    expect(localConfig.maxContentBytes).toBeUndefined();

    const verifiedConfig = getFirewallConfigForTrust(verified);
    expect(verifiedConfig.allowExternalRaw).toBe(false);
    expect(verifiedConfig.maxContentBytes).toBe(102_400);

    const researchConfig = getFirewallConfigForTrust(research);
    expect(researchConfig.allowExternalRaw).toBe(false);
    expect(researchConfig.maxContentBytes).toBe(51_200);

    const untrustedConfig = getFirewallConfigForTrust(untrusted);
    expect(untrustedConfig.allowExternalRaw).toBe(false);
    expect(untrustedConfig.maxContentBytes).toBe(10_240);
  });

  test("RESEARCH tier for generic http URL", () => {
    const http = scoreDomain("http://example.com/page");
    expect(http.tier).toBe(TrustTier.RESEARCH);
    expect(http.score).toBe(0.3);

    const https = scoreDomain("https://some-site.org/content");
    expect(https.tier).toBe(TrustTier.RESEARCH);
  });

  test("additionalVerifiedDomains extends VERIFIED list", () => {
    const customDomain = "internal.corp.example.com";
    const url = `https://${customDomain}/docs`;

    const withoutConfig = scoreDomain(url);
    expect(withoutConfig.tier).toBe(TrustTier.RESEARCH);

    const withConfig = scoreDomain(url, {
      additionalVerifiedDomains: [customDomain],
    });
    expect(withConfig.tier).toBe(TrustTier.VERIFIED);
    expect(withConfig.score).toBe(0.8);
  });

  test("trust score values are correct", () => {
    expect(TRUST_SCORES[TrustTier.LOCAL]).toBe(1.0);
    expect(TRUST_SCORES[TrustTier.VERIFIED]).toBe(0.8);
    expect(TRUST_SCORES[TrustTier.RESEARCH]).toBe(0.3);
    expect(TRUST_SCORES[TrustTier.UNTRUSTED]).toBe(0.0);
  });

  test("scoreSource treats plain text as UNTRUSTED", () => {
    const plainText = scoreSource("some user input");
    expect(plainText.tier).toBe(TrustTier.UNTRUSTED);
    expect(plainText.reason).toContain("User-provided");

    const withUrl = scoreSource("https://github.com/repo");
    expect(withUrl.tier).toBe(TrustTier.VERIFIED);
  });

  test("untrusted schemes (data:, javascript:, blob:) are UNTRUSTED", () => {
    const dataUrl = scoreDomain("data:text/html,<h1>test</h1>");
    expect(dataUrl.tier).toBe(TrustTier.UNTRUSTED);

    const jsUrl = scoreDomain("javascript:alert(1)");
    expect(jsUrl.tier).toBe(TrustTier.UNTRUSTED);

    const blobUrl = scoreDomain("blob:https://example.com/uuid");
    expect(blobUrl.tier).toBe(TrustTier.UNTRUSTED);
  });

  test("empty URLs are UNTRUSTED", () => {
    const empty = scoreDomain("");
    expect(empty.tier).toBe(TrustTier.UNTRUSTED);
    expect(empty.reason).toBe("Empty URL");

    const whitespace = scoreDomain("   ");
    expect(whitespace.tier).toBe(TrustTier.UNTRUSTED);
  });
});
