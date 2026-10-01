import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BREAK_GLASS_ENV,
  SUPPORT_HORIZON_DAYS,
  SupportHorizonError,
  checkSupportHorizon,
  enforceSupportHorizon,
  warnSupportHorizon,
} from "../src/support-horizon.js";
import { RELEASE_DATE } from "../src/version.js";

describe("support horizon (DA-3359)", () => {
  const release = new Date(`${RELEASE_DATE}T00:00:00Z`);

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("normal window is ok and never raises", () => {
    vi.setSystemTime(new Date(release.getTime() + 30 * 86_400_000));
    expect(checkSupportHorizon()).toBe("ok");
    expect(() => warnSupportHorizon()).not.toThrow();
    expect(() => enforceSupportHorizon()).not.toThrow();
  });

  it("warn window warns but does not raise", () => {
    vi.setSystemTime(
      new Date(release.getTime() + (SUPPORT_HORIZON_DAYS - 5) * 86_400_000),
    );
    expect(checkSupportHorizon()).toBe("warn");
    expect(() => enforceSupportHorizon()).not.toThrow();
  });

  it("expired raises at the entrypoint, not at import", () => {
    vi.setSystemTime(
      new Date(release.getTime() + (SUPPORT_HORIZON_DAYS + 1) * 86_400_000),
    );
    expect(checkSupportHorizon()).toBe("expired");
    expect(() => warnSupportHorizon()).not.toThrow(); // import path: log only
    expect(() => enforceSupportHorizon()).toThrow(SupportHorizonError);
  });

  it("break-glass env downgrades the raise", () => {
    vi.setSystemTime(
      new Date(release.getTime() + (SUPPORT_HORIZON_DAYS + 1) * 86_400_000),
    );
    process.env[BREAK_GLASS_ENV] = "1";
    try {
      expect(() => enforceSupportHorizon()).not.toThrow();
    } finally {
      delete process.env[BREAK_GLASS_ENV];
    }
  });

  it("clock seam is honored", () => {
    const patched = new Date(release.getTime() + (SUPPORT_HORIZON_DAYS + 5) * 86_400_000);
    expect(checkSupportHorizon(patched)).toBe("expired");
    expect(checkSupportHorizon(new Date(release))).toBe("ok");
  });
});
