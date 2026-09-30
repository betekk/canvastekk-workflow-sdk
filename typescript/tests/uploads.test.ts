import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { S3PresignedUploader, type UploadTarget } from "../src/uploads.js";

interface SessionCall {
  method?: string;
  url?: string;
}

// Local HTTP server speaking the multipart session wire contract
// (initiate → part PUTs → complete) so the routing tests assert real
// requests, not mocks.
async function startSessionServer() {
  const calls: SessionCall[] = [];
  const server: Server = createServer((req, res) => {
    req.resume();
    req.on("end", () => {
      calls.push({ method: req.method, url: req.url });
      const url = req.url ?? "";
      if (url === "/initiate") {
        res.writeHead(200, { "Content-Type": "application/json" });
        const port = (server.address() as AddressInfo).port;
        res.end(
          JSON.stringify({
            upload_id: "up-9",
            part_size: 64,
            part_urls: [`http://127.0.0.1:${port}/part/1`],
          }),
        );
        return;
      }
      if (url.startsWith("/part/")) {
        res.writeHead(200, { ETag: '"e1"' });
        res.end();
        return;
      }
      if (url === "/complete" || url === "/abort" || url === "/status") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, uploaded_parts: [] }));
        return;
      }
      res.writeHead(404);
      res.end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    calls,
    target: {
      kind: "multipart-upload-session",
      session_token: "t",
      initiate_url: `http://127.0.0.1:${port}/initiate`,
      complete_url: `http://127.0.0.1:${port}/complete`,
      abort_url: `http://127.0.0.1:${port}/abort`,
      status_url: `http://127.0.0.1:${port}/status`,
    } satisfies UploadTarget,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

// A descriptor that must never be reached — for tests where the SDK is
// expected to fail before any upload attempt.
const untouchedTarget = {
  kind: "multipart-upload-session",
  session_token: "t",
  initiate_url: "http://127.0.0.1:1/initiate",
  complete_url: "http://127.0.0.1:1/complete",
  abort_url: "http://127.0.0.1:1/abort",
  status_url: "http://127.0.0.1:1/status",
} satisfies UploadTarget;

describe("S3PresignedUploader", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-uploads-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  describe("legacy string targets (DA-3340)", () => {
    it("uploadFile throws NodeIOError with the upgrade-the-engine message", async () => {
      const filePath = join(tmpDir, "out.bin");
      writeFileSync(filePath, "data");

      await expect(
        new S3PresignedUploader().uploadFile(filePath, "http://127.0.0.1:1/presigned" as never),
      ).rejects.toMatchObject({
        name: "NodeIOError",
        message: "engine sent deprecated presigned target — upgrade the engine",
      });
    });

    it("uploadOutputs throws before any upload for a string target", async () => {
      const filePath = join(tmpDir, "out.bin");
      writeFileSync(filePath, "data");
      const response = {
        status: "pass",
        outputs: { out: filePath },
      } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

      await expect(
        new S3PresignedUploader().uploadOutputs(
          response,
          { out: "http://127.0.0.1:1/presigned" as never },
          ["out"],
        ),
      ).rejects.toThrow(/engine sent deprecated presigned target/);
    });
  });

  describe("uploadOutputs fail-loud (DA-2337)", () => {
    it("throws when a present file-output value is not a string", async () => {
      const uploader = new S3PresignedUploader();
      const response = {
        success: true,
        outputs: { count: 123 },
      } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

      await expect(
        uploader.uploadOutputs(response, { count: untouchedTarget }, ["count"]),
      ).rejects.toThrow(/Output field 'count' value is not a string: number/);
    });

    it("throws when the value is not an existing local file", async () => {
      const uploader = new S3PresignedUploader();
      const response = {
        success: true,
        outputs: { frag_file: "/nonexistent/converted.frag" },
      } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

      const promise = uploader.uploadOutputs(response, { frag_file: untouchedTarget }, [
        "frag_file",
      ]);
      await expect(promise).rejects.toThrow(/Output field 'frag_file' value is not a local file/);
      await expect(promise).rejects.toMatchObject({
        name: "NodeIOError",
        path: "/nonexistent/converted.frag",
      });
    });

    it("throws when the value is a directory (not a regular file)", async () => {
      const uploader = new S3PresignedUploader();
      const response = {
        success: true,
        outputs: { frag_file: tmpDir },
      } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

      await expect(
        uploader.uploadOutputs(response, { frag_file: untouchedTarget }, ["frag_file"]),
      ).rejects.toThrow(/Output field 'frag_file' value is not a local file/);
    });

    it("skips fields absent from outputs (omission is legal)", async () => {
      const srv = await startSessionServer();
      try {
        const response = {
          success: true,
          outputs: { note: "done" },
        } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

        await new S3PresignedUploader().uploadOutputs(response, { frag_file: srv.target }, [
          "frag_file",
        ]);

        expect(srv.calls).toHaveLength(0);
      } finally {
        await srv.close();
      }
    });
  });

  describe("session targets (DA-2886/DA-3340)", () => {
    it("routes a descriptor target through the multipart flow via uploadOutputs", async () => {
      const srv = await startSessionServer();
      try {
        const filePath = join(tmpDir, "out.bin");
        writeFileSync(filePath, "session-bytes");

        await new S3PresignedUploader().uploadOutputs(
          { status: "pass", outputs: { out: filePath } } as never,
          { out: srv.target },
          ["out"],
        );

        expect(srv.calls.some((c) => c.url === "/initiate")).toBe(true);
        expect(srv.calls.some((c) => c.url === "/complete")).toBe(true);
      } finally {
        await srv.close();
      }
    });

    it("keeps the NodeIOError contract for descriptor targets with non-file values", async () => {
      await expect(
        new S3PresignedUploader().uploadOutputs(
          { status: "pass", outputs: { out: "/nonexistent/missing.bin" } } as never,
          { out: untouchedTarget },
          ["out"],
        ),
      ).rejects.toMatchObject({ name: "NodeIOError" });
    });

    it("uploads earlier valid fields before a bad later field throws", async () => {
      const srv = await startSessionServer();
      try {
        const goodPath = join(tmpDir, "good.frag");
        writeFileSync(goodPath, Buffer.from("frag-bytes"));

        const response = {
          success: true,
          outputs: { good_file: goodPath, bad_file: "/nonexistent/bad.frag" },
        } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

        await expect(
          new S3PresignedUploader().uploadOutputs(
            response,
            { good_file: srv.target, bad_file: untouchedTarget },
            ["good_file", "bad_file"],
          ),
        ).rejects.toThrow(/Output field 'bad_file' value is not a local file/);

        expect(srv.calls.some((c) => c.url === "/complete")).toBe(true);
      } finally {
        await srv.close();
      }
    });
  });
});
