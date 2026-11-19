/**
 * Node protocol version negotiation (N1, betekk/canvastekk-workflow-engine#1300).
 *
 * Protocol 2 renames the node call outcomes: `pass` -> `SUCCEEDED`,
 * `fail` -> `FAILED`, `pending` -> `ACCEPTED`. The engine advertises the
 * protocol it reads with the `X-Node-Protocol` request header; a node answers
 * in the new words only when that header says 2 or more, so a node on this
 * SDK keeps answering `pass` / `fail` to an engine that has not moved yet.
 *
 * Node code never sees the new words: it keeps building `pass` / `fail`
 * responses and `/execute` translates on the way out.
 */

/** Request header carrying the engine's node protocol version (lower-case, as Node exposes it). */
export const NODE_CALL_PROTOCOL_HEADER = "x-node-protocol";

/** Highest node protocol this SDK speaks. */
export const NODE_CALL_PROTOCOL_VERSION = 2;

const TO_PROTOCOL_2: Record<string, string> = { pass: "SUCCEEDED", fail: "FAILED", pending: "ACCEPTED" };

/** Exact protocol-2 words mapped to their protocol-1 equivalents (strict readers). */
export const NODE_CALL_PROTOCOL_2_OUTCOMES: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(Object.entries(TO_PROTOCOL_2).map(([oldWord, newWord]) => [newWord, oldWord])),
);

/**
 * The protocol a request asks for; 1 when the header is absent or malformed.
 *
 * @param headerValue - Raw `X-Node-Protocol` header value
 * @returns The requested version, capped at {@link NODE_CALL_PROTOCOL_VERSION}
 */
export function requestedNodeCallProtocol(headerValue: string | string[] | undefined): number {
  const raw = Array.isArray(headerValue) ? headerValue[0] : headerValue;
  if (raw === undefined || !/^\s*-?\d+\s*$/.test(raw)) return 1;
  const version = Number.parseInt(raw.trim(), 10);
  return Math.max(1, Math.min(version, NODE_CALL_PROTOCOL_VERSION));
}

/**
 * Wire outcome for `status` under `protocol`.
 *
 * @param status - The outcome node code produced (`pass` / `fail` / `pending`)
 * @param protocol - The negotiated protocol version
 * @returns The protocol-2 word when `protocol >= 2`, else `status` unchanged
 */
export function nodeCallOutcomeForProtocol(status: string, protocol: number): string {
  if (protocol >= 2) return TO_PROTOCOL_2[status] ?? status;
  return status;
}

/**
 * Read an outcome in either protocol as `pass` / `fail` / `pending`.
 *
 * @param value - Wire outcome from a node response or callback
 * @returns The protocol-1 word, or `null` when absent or unknown
 */
export function readNodeCallOutcome(value: unknown): string | null {
  if (typeof value !== "string" || value === "") return null;
  const folded = value.trim().toLowerCase();
  if (folded in TO_PROTOCOL_2) return folded;
  const match = Object.entries(TO_PROTOCOL_2).find(([, newWord]) => newWord.toLowerCase() === folded);
  return match ? match[0] : null;
}
