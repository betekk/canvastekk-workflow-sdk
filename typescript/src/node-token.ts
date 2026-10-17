/**
 * Run-scoped node tokens — node-side helpers for the engine→node
 * credential contract (#3825).
 *
 * Shape checking only, no cryptography: nodes never hold the signing
 * key. Verification is delegated to the engine's verify endpoint via
 * `NodeAuth.central()`. The normative implementation is the SDK Python
 * module `node_token.py`; see `docs/NODE-TOKEN-CONTRACT.md`.
 */

/** Scheme prefix shared by every node token (version-tagged for upgrades). */
export const NODE_TOKEN_PREFIX = "cwnt_v1.";

/** Verified claims as reported by the engine verify endpoint. */
export interface NodeTokenClaims {
  runId: string;
  nodeId: string;
  exp: number;
}

/**
 * Shape-checks a presented credential without cryptography.
 *
 * @param value - The presented `X-API-Key` value.
 * @returns True when the value has the node-token shape (prefix plus two
 * non-empty segments); proves nothing about validity.
 */
export function isNodeToken(value: string): boolean {
  if (typeof value !== "string" || !value.startsWith(NODE_TOKEN_PREFIX)) return false;
  const remainder = value.slice(NODE_TOKEN_PREFIX.length);
  const dotCount = remainder.split(".").length - 1;
  if (dotCount !== 1) return false;
  const [payload, signature] = remainder.split(".");
  return payload.length > 0 && signature.length > 0;
}
