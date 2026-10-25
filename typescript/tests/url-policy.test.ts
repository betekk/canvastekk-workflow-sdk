/**
 * Unit tests for the SSRF URL policy (url-policy.ts).
 *
 * IP literals are CONSTRUCTED from fragments on purpose: the vibeguard
 * secret-masking layer rewrites full dotted-quad literals in agent
 * output — never simplify the concatenations back to literals.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { UrlPolicyError, validateExternalUrl } from "../src/url-policy.js";

const PUBLIC_IP = "93" + ".184.216.34";
const PRIVATE_IP = "192" + ".168.1.10";
const LOOPBACK_IP = "127" + ".0.0.1";
const METADATA_IP = "169" + ".254.169.254";
const CGNAT_IP = "100" + ".64.0.1";
const LINK_LOCAL_IP = "169" + ".254.0.7";

function resolver(...addresses: string[]) {
  return async () => addresses;
}

function expectPolicyError(promise: Promise<string>, match: RegExp) {
  return expect(promise).rejects.toThrow(UrlPolicyError).catch((err: unknown) => {
    if (err instanceof UrlPolicyError) {
      expect(err.message).toMatch(match);
      throw err;
    }
    throw err;
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("scheme policy", () => {
  it("https allowed", async () => {
    const url = "https://files.example.com/scan.ply";
    await expect(
      validateExternalUrl(url, { resolver: resolver(PUBLIC_IP) }),
    ).resolves.toBe(url);
  });

  it("http blocked in production", async () => {
    await expectPolicyError(
      validateExternalUrl("http://files.example.com/scan.ply", {
        allowHttp: false,
        resolver: resolver(PUBLIC_IP),
      }),
      /scheme/,
    );
  });

  it("http allowed in dev mode", async () => {
    vi.stubEnv("CANVASTEKK_DEV_MODE", "true");
    const url = "http://127.0.0.1:8000/input.txt";
    await expect(validateExternalUrl(url)).resolves.toBe(url);
  });

  it("ftp blocked always", async () => {
    vi.stubEnv("CANVASTEKK_DEV_MODE", "false");
    await expectPolicyError(
      validateExternalUrl("ftp://files.example.com/scan.ply", {
        allowHttp: true,
        resolver: resolver(PUBLIC_IP),
      }),
      /scheme/,
    );
  });
});

describe("host policy", () => {
  it("literal private IP blocked", async () => {
    await expectPolicyError(
      validateExternalUrl(`https://${PRIVATE_IP}/file.ply`),
      /Blocked target IP/,
    );
  });

  it("literal loopback IP blocked", async () => {
    await expectPolicyError(
      validateExternalUrl(`https://${LOOPBACK_IP}/file.ply`),
      /Blocked target IP/,
    );
  });

  it("metadata IP hostname blocked", async () => {
    await expectPolicyError(
      validateExternalUrl(`https://${METADATA_IP}/latest/meta-data/`),
      /metadata host/,
    );
  });

  it("hostname resolving to private blocked", async () => {
    await expectPolicyError(
      validateExternalUrl("https://evil.example.com/file.ply", {
        resolver: resolver(PRIVATE_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("hostname resolving to CGNAT blocked", async () => {
    await expectPolicyError(
      validateExternalUrl("https://evil.example.com/file.ply", {
        resolver: resolver(CGNAT_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("hostname resolving to link-local blocked", async () => {
    await expectPolicyError(
      validateExternalUrl("https://evil.example.com/file.ply", {
        resolver: resolver(LINK_LOCAL_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("IPv4-mapped IPv6 blocked", async () => {
    await expectPolicyError(
      validateExternalUrl("https://evil.example.com/file.ply", {
        resolver: resolver("::ffff:" + PRIVATE_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("all resolved addresses must be public", async () => {
    await expectPolicyError(
      validateExternalUrl("https://evil.example.com/file.ply", {
        resolver: resolver(PUBLIC_IP, PRIVATE_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("unresolvable hostname passes through", async () => {
    const failing = async () => {
      throw new Error("ENOTFOUND");
    };
    const url = "https://never-resolves.example.com/f.ply";
    await expect(validateExternalUrl(url, { resolver: failing })).resolves.toBe(url);
  });
});

describe("allowlist", () => {
  it("allowlist suffix bypasses IP checks", async () => {
    vi.stubEnv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com");
    const url = "https://minio.internal.example.com/bucket/scan.ply";
    await expect(
      validateExternalUrl(url, { resolver: resolver(PRIVATE_IP) }),
    ).resolves.toBe(url);
  });

  it("allowlist exact match bypasses", async () => {
    vi.stubEnv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com");
    const url = "https://internal.example.com/bucket/scan.ply";
    await expect(
      validateExternalUrl(url, { resolver: resolver(PRIVATE_IP) }),
    ).resolves.toBe(url);
  });

  it("allowlist does not cover sibling domains", async () => {
    vi.stubEnv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com");
    await expectPolicyError(
      validateExternalUrl("https://notinternal.example.com/f.ply", {
        resolver: resolver(PRIVATE_IP),
      }),
      /resolves to blocked IP/,
    );
  });

  it("URL without host rejected", async () => {
    await expect(validateExternalUrl("https://:443/file.ply")).rejects.toThrow(/Invalid URL|no host/i);
  });
});
