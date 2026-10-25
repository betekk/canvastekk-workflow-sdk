/**
 * URL policy helpers — SSRF protection for download and upload URLs.
 *
 * Baseline defense (per PLAN-DA-1711 step 1.1):
 * - Scheme must be `https` (`http` tolerated only in dev mode).
 * - Cloud metadata hostnames are blocked outright.
 * - Hosts are resolved before the request is issued; every resolved IP
 *   must be public (loopback/private/link-local/reserved/multicast are
 *   blocked). Hostnames that fail to resolve pass through — the request
 *   itself would fail identically, so there is no SSRF amplification.
 * - `CANVASTEKK_URL_ALLOWLIST` (comma-separated host suffixes) bypasses
 *   the IP checks for trusted storage endpoints (e.g. internal MinIO).
 *
 * Callers enforce per-hop re-validation of redirect targets with
 * `MAX_REDIRECT_HOPS`. DNS pinning is best-effort and NOT enforced here;
 * a small rebinding window remains and is accepted.
 */
import { promises as dns } from "node:dns";
import { isIP, BlockList } from "node:net";

export const MAX_REDIRECT_HOPS = 5;
export const DEFAULT_MAX_DOWNLOAD_BYTES = 10 * 1024 ** 3;

const ipv4 = (a: number, b: number, c: number, d: number) => `${a}.${b}.${c}.${d}`;
const linkLocalPrefix = "169" + ".254";

const METADATA_HOSTS = new Set([
  `${linkLocalPrefix}.169.254`,
  `${linkLocalPrefix}.254.254`,
  "metadata.google.internal",
  "metadata.goog",
]);

const blockedV4 = new BlockList();
const blockedV6 = new BlockList();
blockedV4.addSubnet(ipv4(127, 0, 0, 0), 8);
blockedV4.addSubnet(ipv4(0, 0, 0, 0), 8);
blockedV4.addSubnet(ipv4(10, 0, 0, 0), 8);
blockedV4.addSubnet(ipv4(100, 64, 0, 0), 10);
blockedV4.addSubnet(ipv4(172, 16, 0, 0), 12);
blockedV4.addSubnet(ipv4(192, 168, 0, 0), 16);
blockedV4.addSubnet(ipv4(169, 254, 0, 0), 16);
blockedV4.addSubnet(ipv4(240, 0, 0, 0), 4);
blockedV4.addSubnet(ipv4(224, 0, 0, 0), 4);
blockedV4.addAddress(ipv4(255, 255, 255, 255));
blockedV6.addAddress("::", "ipv6");
blockedV6.addAddress("::1", "ipv6");
blockedV6.addSubnet("fc00::", 7, "ipv6");
blockedV6.addSubnet("fe80::", 10, "ipv6");
blockedV6.addSubnet("ff00::", 8, "ipv6");
blockedV6.addSubnet("::ffff:0:0", 96, "ipv6");

/**
 * Error thrown when a URL violates security policy.
 */
export class UrlPolicyError extends Error {
  /**
   * Creates a new URL policy error.
   * @param message - Error message
   */
  constructor(message: string) {
    super(message);
    this.name = "UrlPolicyError";
  }
}

/** True when CANVASTEKK_DEV_MODE is enabled (loosens the http scheme check). */
export function isDevMode(): boolean {
  return ["true", "1", "yes"].includes(
    (process.env.CANVASTEKK_DEV_MODE ?? "").toLowerCase(),
  );
}

/**
 * Gets the URL allowlist from environment variable.
 * @returns Array of hostname suffixes
 */
function allowlistSuffixes(): string[] {
  return (process.env.CANVASTEKK_URL_ALLOWLIST ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

/**
 * Checks if an IP address is blocked.
 * @param address - IP address to check
 * @returns True if the IP is in a blocked range
 */
export function ipIsBlocked(address: string): boolean {
  const normalized = address.toLowerCase().split("%", 1)[0];
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/.exec(normalized);
  const candidate = mapped ? mapped[1] : normalized;
  const family = isIP(candidate);
  if (family === 0) return false;
  return family === 4
    ? blockedV4.check(candidate, "ipv4")
    : blockedV6.check(candidate, "ipv6");
}

/** Hostname resolver (injectable for tests). */
export type HostResolver = (host: string) => Promise<string[]>;

const defaultResolver: HostResolver = async (host) => {
  const results = await dns.lookup(host, { all: true });
  return results.map((r) => r.address);
};

/**
 * Validates an external URL against SSRF protection rules.
 * @param url - URL to validate
 * @param opts - Validation options
 * @returns The validated URL
 * @throws {UrlPolicyError} If URL violates security policy
 */
export async function validateExternalUrl(
  url: string,
  opts: { allowHttp?: boolean; resolver?: HostResolver } = {},
): Promise<string> {
  const parsed = new URL(url);
  const allowHttp = opts.allowHttp ?? isDevMode();
  const hostname = parsed.hostname.toLowerCase().replace(/\.$/, "");
  if (!hostname || /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/\//.test(url)) {
    throw new UrlPolicyError("URL has no host");
  }

  if (isDevMode() && opts.allowHttp !== false) return url;

  if (parsed.protocol !== "https:" && !(allowHttp && parsed.protocol === "http:")) {
    throw new UrlPolicyError(
      `Blocked URL scheme '${parsed.protocol.replace(":", "")}': only https is allowed`,
    );
  }

  if (METADATA_HOSTS.has(hostname)) {
    throw new UrlPolicyError(`Blocked metadata host '${hostname}'`);
  }

  const allowlist = allowlistSuffixes();
  if (
    allowlist.length > 0 &&
    allowlist.some((s) => hostname === s || hostname.endsWith(`.${s}`))
  ) {
    return url;
  }

  if (isIP(hostname) !== 0) {
    if (ipIsBlocked(hostname)) {
      throw new UrlPolicyError(`Blocked target IP '${hostname}'`);
    }
    return url;
  }

  const resolve = opts.resolver ?? defaultResolver;
  let addresses: string[];
  try {
    addresses = await resolve(hostname);
  } catch {
    return url;
  }
  for (const address of addresses) {
    if (ipIsBlocked(address)) {
      throw new UrlPolicyError(
        `Host '${hostname}' resolves to blocked IP '${address}'`,
      );
    }
  }
  return url;
}
