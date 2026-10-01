/**
 * Support-horizon gate (DA-3359): warn at import, raise at node entrypoints.
 *
 * Sunset = RELEASE_DATE + SUPPORT_HORIZON_DAYS. The import path LOGS ONLY
 * (the engine lazy-imports this package — an import-time throw would silently
 * disable seeding/discovery). The throw lives at the node entrypoints
 * (createNodeApp / createMultiNodeApp / BaseNode.run).
 * CANVASTEKK_SDK_ALLOW_UNSUPPORTED=1 is the break-glass.
 */

import { RELEASE_DATE } from "./version.js";

export const SUPPORT_HORIZON_DAYS = 180;
export const WARN_WINDOW_DAYS = 30;
export const BREAK_GLASS_ENV = "CANVASTEKK_SDK_ALLOW_UNSUPPORTED";

export type HorizonOutcome = "ok" | "warn" | "expired";

function sunset(): Date {
  return new Date(new Date(`${RELEASE_DATE}T00:00:00Z`).getTime() + SUPPORT_HORIZON_DAYS * 86_400_000);
}

/** Clock seam — tests replace this for frozen-clock coverage. */
export function horizonToday(): Date {
  return new Date();
}

export function checkSupportHorizon(today: Date = horizonToday()): HorizonOutcome {
  const day = today;
  const end = sunset();
  if (day.getTime() >= end.getTime()) return "expired";
  const warnFrom = new Date(end.getTime() - WARN_WINDOW_DAYS * 86_400_000);
  if (day.getTime() >= warnFrom.getTime()) return "warn";
  return "ok";
}

/** Import-time path: LOG ONLY (never throws). */
export function warnSupportHorizon(today: Date = horizonToday()): HorizonOutcome {
  const outcome = checkSupportHorizon(today);
  if (outcome === "expired") {
    console.warn(
      `[canvastekk-workflow-sdk] support horizon expired: ${RELEASE_DATE} passed end-of-support on ${sunset().toISOString().slice(0, 10)}; node entrypoints will throw unless ${BREAK_GLASS_ENV}=1`,
    );
  } else if (outcome === "warn") {
    console.warn(
      `[canvastekk-workflow-sdk] support horizon warning: ${RELEASE_DATE} reaches end-of-support on ${sunset().toISOString().slice(0, 10)}`,
    );
  }
  return outcome;
}

export class SupportHorizonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SupportHorizonError";
  }
}

/** Entrypoint path: throws once the horizon has passed (break-glass honored). */
export function enforceSupportHorizon(today: Date = horizonToday()): void {
  if (checkSupportHorizon(today) !== "expired") return;
  if (process.env[BREAK_GLASS_ENV] === "1") {
    console.error(
      `[canvastekk-workflow-sdk] CRITICAL: support horizon expired for ${RELEASE_DATE} (sunset ${sunset().toISOString().slice(0, 10)}); continuing via ${BREAK_GLASS_ENV}=1 — upgrade the SDK`,
    );
    return;
  }
  throw new SupportHorizonError(
    `canvastekk-workflow-sdk ${RELEASE_DATE} passed its support horizon on ${sunset().toISOString().slice(0, 10)}; upgrade the SDK or set ${BREAK_GLASS_ENV}=1 to continue unsupported`,
  );
}
