import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { uploadViaSession } from "../src/multipart.js";
import type { UploadSessionDescriptor } from "../src/uploads.js";

interface CapturedCall {
  method: string;
  url: string;
  body: Buffer;
  contentType?: string | string[];
  contentMd5?: string | string[];
  contentLength?: string | string[] | undefined;
}

/**
 * One local HTTP server standing in for the engine control plane
 * (initiate/complete/abort/status) AND S3 part PUTs (/part/N), with
 * scriptable part-PUT failures — real wire behavior, no fetch mocks
 * (parity with uploads.test.ts).
 */
async function startServer(opts: {
  /** part number → number of INITIAL attempts that must fail (then succeed). */
  failPartsFirst?: Record<number, number>;
  failComplete?: boolean;
  uploadedParts?: number[];
  initiatePartUrls?: number;
  initiatePartSize?: number;
} = {}) {
  const calls: CapturedCall[] = [];
  const partAttemptCounts = new Map<number, number>();
  const failPartsFirst = opts.failPartsFirst ?? {};
  let port = 0;

  const server: Server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c as Buffer));
    req.on("end", () => {
      const url = req.url ?? "";
      const path = new URL(url, "http://127.0.0.1").pathname;
      calls.push({
        method: req.method ?? "",
        url,
        body: Buffer.concat(chunks),
        contentType: req.headers["content-type"],
        contentMd5: req.headers["content-md5"],
        contentLength: req.headers["content-length"],
      });

      const json = (code: number, obj: unknown) => {
        res.writeHead(code, { "Content-Type": "application/json" });
        res.end(JSON.stringify(obj));
      };

      if (path === "/initiate") {
        const n = opts.initiatePartUrls ?? 3;
        json(200, {
          upload_id: "up-123",
          part_size: opts.initiatePartSize ?? 4,
          part_urls: Array.from(
            { length: n },
            (_, i) => `http://127.0.0.1:${port}/part/${i + 1}`,
          ),
        });
        return;
      }
      if (url.startsWith("/part/")) {
        const partNumber = Number(url.split("/part/")[1]);
        const count = (partAttemptCounts.get(partNumber) ?? 0) + 1;
        partAttemptCounts.set(partNumber, count);
        if (count <= (failPartsFirst[partNumber] ?? 0)) {
          res.writeHead(500);
          res.end("part-error");
          return;
        }
        res.writeHead(200, { ETag: `"etag-${partNumber}"` });
        res.end();
        return;
      }
      if (path === "/complete") {
        if (opts.failComplete) {
          res.writeHead(500);
          res.end("complete-error");
          return;
        }
        json(200, { ok: true });
        return;
      }
      if (path === "/abort") {
        json(200, { ok: true });
        return;
      }
      if (path === "/status") {
        json(200, { upload_id: "up-123", uploaded_parts: opts.uploadedParts ?? [] });
        return;
      }
      res.writeHead(404);
      res.end();
    });
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  port = (server.address() as AddressInfo).port;

  return {
    calls,
    descriptor: (
      kind: UploadSessionDescriptor["kind"] = "multipart-upload-session",
    ): UploadSessionDescriptor => ({
      kind,
      session_token: "tok",
      initiate_url: `http://127.0.0.1:${port}/initiate`,
      complete_url: `http://127.0.0.1:${port}/complete`,
      abort_url: `http://127.0.0.1:${port}/abort`,
      status_url: `http://127.0.0.1:${port}/status`,
    }),
    partAttempt: (n: number) => partAttemptCounts.get(n) ?? 0,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

describe("uploadViaSession (DA-2886)", () => {
  let filePath: string;
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-multipart-run-"));
    filePath = join(tmpDir, "out.bin");
    writeFileSync(filePath, "AAAABBBBCCCC");
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("happy path: initiate → parallel part PUTs without unsigned headers → complete sorted, no abort", async () => {
    const srv = await startServer();
    try {
      await uploadViaSession(srv.descriptor(), filePath, { retryBackoffsMs: [1, 1] });

      const initiate = srv.calls.find((c) => c.url === "/initiate");
      expect(initiate).toBeDefined();
      expect(JSON.parse(String(initiate!.body))).toEqual({
        size: 12,
        content_type: "application/octet-stream",
      });

      const parts = srv.calls.filter((c) => c.url.startsWith("/part/"));
      expect(parts).toHaveLength(3);
      expect(parts.map((p) => p.url.split("/part/")[1])).toEqual(["1", "2", "3"]);
      for (const p of parts) {
        expect(p.contentMd5).toBeUndefined();
        expect(p.contentLength).toBeDefined();
      }

      const complete = srv.calls.find((c) => c.url === "/complete");
      expect(complete).toBeDefined();
      const body = JSON.parse(String(complete!.body));
      expect(body.upload_id).toBe("up-123");
      expect(body.parts).toEqual([
        { part_number: 1, etag: "etag-1" },
        { part_number: 2, etag: "etag-2" },
        { part_number: 3, etag: "etag-3" },
      ]);

      expect(srv.calls.some((c) => c.url === "/abort")).toBe(false);
    } finally {
      await srv.close();
    }
  });

  it("retries a part failure then succeeds (fail-first-N scripting)", async () => {
    const srv = await startServer({ failPartsFirst: { 2: 1 } });
    try {
      await uploadViaSession(srv.descriptor(), filePath, { retryBackoffsMs: [1, 1] });
      expect(srv.partAttempt(2)).toBe(2);
      expect(srv.calls.some((c) => c.url === "/complete")).toBe(true);
      expect(srv.calls.some((c) => c.url === "/abort")).toBe(false);
    } finally {
      await srv.close();
    }
  });

  it("resume: always-failing part exhausts retries → status reconcile → abort + rethrow", async () => {
    const srv = await startServer({ failPartsFirst: { 1: 999 } });
    try {
      await expect(
        uploadViaSession(srv.descriptor(), filePath, {
          retryBackoffsMs: [1, 1],
          resumeAttempts: 1,
        }),
      ).rejects.toThrow(/incomplete/);

      expect(srv.partAttempt(1)).toBe(6);
      expect(srv.calls.some((c) => c.url === "/status")).toBe(true);
      expect(srv.calls.some((c) => c.url === "/abort")).toBe(true);
      expect(srv.calls.some((c) => c.url === "/complete")).toBe(false);
    } finally {
      await srv.close();
    }
  });

  it("complete failure does NOT abort (parts stay valid; complete is idempotent)", async () => {
    const srv = await startServer({ failComplete: true });
    try {
      await expect(
        uploadViaSession(srv.descriptor(), filePath, { retryBackoffsMs: [1, 1] }),
      ).rejects.toThrow(/control-plane POST failed/);
      expect(srv.calls.some((c) => c.url === "/abort")).toBe(false);
    } finally {
      await srv.close();
    }
  });

  it("0 part URLs → malformed-initiate error, no abort (python parity: pre-try raise)", async () => {
    const srv = await startServer({ initiatePartUrls: 0 });
    try {
      await expect(
        uploadViaSession(srv.descriptor(), filePath, { retryBackoffsMs: [1, 1] }),
      ).rejects.toThrow(/malformed initiate bundle/);
      expect(srv.calls.some((c) => new URL(c.url, "http://127.0.0.1").pathname === "/abort")).toBe(false);
    } finally {
      await srv.close();
    }
  });

  it("capability single-file replay completes again with no element and no legacy 409", async () => {
    const srv = await startServer({ failPartsFirst: { 1: 1 } });
    try {
      const descriptor = srv.descriptor("multipart-upload-capability");
      const options = { retryBackoffsMs: [1, 1] };
      await uploadViaSession(descriptor, filePath, options);
      await uploadViaSession(descriptor, filePath, options);

      const initiates = srv.calls.filter((c) => new URL(c.url, "http://127.0.0.1").pathname === "/initiate");
      expect(initiates).toHaveLength(2);
      const completes = srv.calls.filter((c) => new URL(c.url, "http://127.0.0.1").pathname === "/complete");
      expect(completes).toHaveLength(2);
      for (const complete of completes) {
        expect(JSON.parse(String(complete.body))).not.toHaveProperty("element");
      }
    } finally {
      await srv.close();
    }
  });

  it("capability single-file status carries upload_id and abort stays element-free", async () => {
    const srv = await startServer({ failPartsFirst: { 1: 999 }, uploadedParts: [] });
    try {
      await expect(
        uploadViaSession(srv.descriptor("multipart-upload-capability"), filePath, {
          retryBackoffsMs: [1, 1],
          resumeAttempts: 1,
        }),
      ).rejects.toThrow(/incomplete/);

      const status = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/status");
      expect(status).toBeDefined();
      const query = new URL(status!.url, "http://127.0.0.1").searchParams;
      expect(query.get("upload_id")).toBe("up-123");
      expect(query.get("index")).toBeNull();
      const abort = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/abort");
      expect(JSON.parse(String(abort!.body))).toEqual({ upload_id: "up-123" });
    } finally {
      await srv.close();
    }
  });

  it.each(["multipart-upload-session", "multipart-upload-capability"])(
    "array complete adds element only for capabilities (%s)",
    async (kind) => {
      const srv = await startServer();
      try {
        const element = { index: 3, suffix: ".frag" };
        await uploadViaSession(srv.descriptor(kind), filePath, {
          retryBackoffsMs: [1, 1],
          element,
        });

        const initiate = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/initiate");
        expect(JSON.parse(String(initiate!.body))).toEqual({
          size: 12,
          content_type: "application/octet-stream",
          element,
        });

        const complete = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/complete");
        const body = JSON.parse(String(complete!.body));
        expect(body.upload_id).toBe("up-123");
        expect(body.parts).toEqual([
          { part_number: 1, etag: "etag-1" },
          { part_number: 2, etag: "etag-2" },
          { part_number: 3, etag: "etag-3" },
        ]);
        if (kind === "multipart-upload-capability") {
          expect(body.element).toEqual(element);
        } else {
          expect(body).not.toHaveProperty("element");
        }
      } finally {
        await srv.close();
      }
    },
  );

  it.each(["multipart-upload-session", "multipart-upload-capability"])(
    "array status/abort contract differs by descriptor kind (%s)",
    async (kind) => {
      const srv = await startServer({ failPartsFirst: { 1: 999 }, uploadedParts: [] });
      try {
        const element = { index: 3, suffix: ".frag" };
        await expect(
          uploadViaSession(srv.descriptor(kind), filePath, {
            retryBackoffsMs: [1, 1],
            resumeAttempts: 1,
            element,
          }),
        ).rejects.toThrow(/incomplete/);

        const status = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/status");
        expect(status).toBeDefined();
        const query = new URL(status!.url, "http://127.0.0.1").searchParams;
        const abort = srv.calls.find((c) => new URL(c.url, "http://127.0.0.1").pathname === "/abort");
        const abortBody = JSON.parse(String(abort!.body));

        if (kind === "multipart-upload-capability") {
          expect(query.get("upload_id")).toBe("up-123");
          expect(query.get("index")).toBe("3");
          expect(query.get("suffix")).toBe(".frag");
          expect(abortBody).toEqual({ upload_id: "up-123", element });
        } else {
          expect(query.get("upload_id")).toBeNull();
          expect(query.get("index")).toBeNull();
          expect(query.get("suffix")).toBeNull();
          expect(abortBody).toEqual({ upload_id: "up-123" });
        }
      } finally {
        await srv.close();
      }
    },
  );
});
