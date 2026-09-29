import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { S3PresignedUploader } from "../src/uploads.js";

// DA-2886 optics (m3/m4): the legacy-presigned warning fires ONCE PER
// PROCESS (module-level flag — documented divergence from python's
// per-call-site warnings registry). Isolated in its own file because the
// flag persists across tests within one vitest file.
describe("legacy presigned deprecation warning (DA-3314)", () => {
  let tmpDir: string;
  let filePath: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-deprecation-"));
    filePath = join(tmpDir, "out.bin");
    writeFileSync(filePath, "data");
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
    vi.restoreAllMocks();
  });

  it("warns exactly once per process for string targets", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const uploader = new S3PresignedUploader();
    // unreachable endpoints: the warning fires before the attempt
    await uploader
      .uploadFile(filePath, "http://127.0.0.1:1/put")
      .catch(() => undefined);
    await uploader
      .uploadFile(filePath, "http://127.0.0.1:2/put")
      .catch(() => undefined);

    const deprecationCalls = warn.mock.calls.filter((args) =>
      String(args[0]).includes("deprecated"),
    );
    expect(deprecationCalls).toHaveLength(1);
  });

  it("does not warn for descriptor targets (multipart is the standard path)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const uploader = new S3PresignedUploader();
    await uploader
      .uploadFile(filePath, {
        kind: "multipart-upload-session",
        session_token: "t",
        initiate_url: "http://127.0.0.1:1/init",
        complete_url: "http://127.0.0.1:1/complete",
        abort_url: "http://127.0.0.1:1/abort",
        status_url: "http://127.0.0.1:1/status",
      })
      .catch(() => undefined);

    expect(warn.mock.calls.some((args) => String(args[0]).includes("deprecated"))).toBe(
      false,
    );
  });
});
