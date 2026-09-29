import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { S3PresignedUploader } from "../src/uploads.js";

interface CapturedRequest {
  method?: string;
  url?: string;
  contentLength?: string | string[] | undefined;
  transferEncoding?: string | string[] | undefined;
  contentType?: string | string[] | undefined;
  body: Buffer;
}

// Real local HTTP server: verifies the actual wire behavior (identity
// encoding with Content-Length, no Transfer-Encoding: chunked) that S3
// requires — a fetch mock cannot assert that.
async function startServer() {
  const captured: CapturedRequest[] = [];
  let respondPair: [number, string] = [200, "OK"];
  const server: Server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c as Buffer));
    req.on("end", () => {
      captured.push({
        method: req.method,
        url: req.url,
        contentLength: req.headers["content-length"],
        transferEncoding: req.headers["transfer-encoding"],
        contentType: req.headers["content-type"],
        body: Buffer.concat(chunks),
      });
      const [status, statusText] = respondPair;
      res.writeHead(status, statusText);
      res.end(status >= 200 && status < 300 ? undefined : "error-detail");
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}/presigned-put`,
    captured,
    setResponse: (status: number, statusText: string) => {
      respondPair = [status, statusText];
    },
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

describe("S3PresignedUploader", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-uploads-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  describe("uploadFile", () => {
    it("PUTs with explicit Content-Length and identity encoding (no chunked TE)", async () => {
      const srv = await startServer();
      try {
        const payload = Buffer.from("frag-bytes-0123456789");
        const filePath = join(tmpDir, "out.frag");
        writeFileSync(filePath, payload);

        await new S3PresignedUploader().uploadFile(filePath, srv.url);

        expect(srv.captured).toHaveLength(1);
        const req = srv.captured[0];
        expect(req.method).toBe("PUT");
        expect(req.url).toBe("/presigned-put");
        expect(req.contentLength).toBe(String(payload.length));
        // S3 rejects chunked uploads with 501 — the request must be identity
        expect(req.transferEncoding).toBeUndefined();
        expect(req.contentType).toBe("application/octet-stream");
        expect(req.body.equals(payload)).toBe(true);
      } finally {
        await srv.close();
      }
    });

    it("streams large bodies without buffering (multi-chunk pipe)", async () => {
      const srv = await startServer();
      try {
        const payload = Buffer.alloc(5 * 1024 * 1024, 7); // 5 MiB
        const filePath = join(tmpDir, "big.ply");
        writeFileSync(filePath, payload);

        await new S3PresignedUploader().uploadFile(filePath, srv.url);

        const req = srv.captured[0];
        expect(req.contentLength).toBe(String(payload.length));
        expect(req.body.length).toBe(payload.length);
      } finally {
        await srv.close();
      }
    });

    it("throws on non-2xx response with status and detail", async () => {
      const srv = await startServer();
      srv.setResponse(501, "Not Implemented");
      try {
        const filePath = join(tmpDir, "out.frag");
        writeFileSync(filePath, Buffer.from("frag-bytes"));

        await expect(
          new S3PresignedUploader().uploadFile(filePath, srv.url),
        ).rejects.toThrow(/Upload failed: HTTP 501 Not Implemented.*error-detail/);
      } finally {
        await srv.close();
      }
    });
  });

  describe("uploadOutputs", () => {
    it("uploads local file outputs", async () => {
      const srv = await startServer();
      try {
        const fragPath = join(tmpDir, "converted.frag");
        writeFileSync(fragPath, Buffer.from("frag-bytes"));

        const response = {
          success: true,
          outputs: { frag_file: fragPath },
        } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

        await new S3PresignedUploader().uploadOutputs(
          response,
          { frag_file: srv.url },
          ["frag_file"],
        );

        expect(srv.captured).toHaveLength(1);
        expect(srv.captured[0].url).toBe("/presigned-put");
      } finally {
        await srv.close();
      }
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
        uploader.uploadOutputs(response, { count: "http://127.0.0.1:1/put" }, ["count"]),
      ).rejects.toThrow(/Output field 'count' value is not a string: number/);
    });

    it("throws when the value is not an existing local file", async () => {
      const uploader = new S3PresignedUploader();
      const response = {
        success: true,
        outputs: { frag_file: "/nonexistent/converted.frag" },
      } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

      const promise = uploader.uploadOutputs(
        response,
        { frag_file: "http://127.0.0.1:1/put" },
        ["frag_file"],
      );
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
        uploader.uploadOutputs(response, { frag_file: "http://127.0.0.1:1/put" }, ["frag_file"]),
      ).rejects.toThrow(/Output field 'frag_file' value is not a local file/);
    });

    it("skips fields absent from outputs (omission is legal)", async () => {
      const srv = await startServer();
      try {
        const response = {
          success: true,
          outputs: { note: "done" },
        } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

        await new S3PresignedUploader().uploadOutputs(
          response,
          { frag_file: srv.url },
          ["frag_file"],
        );

        expect(srv.captured).toHaveLength(0);
      } finally {
        await srv.close();
      }
    });

    it("uploads earlier valid fields before a bad later field throws", async () => {
      const srv = await startServer();
      try {
        const fragPath = join(tmpDir, "good.frag");
        writeFileSync(fragPath, Buffer.from("frag-bytes"));

        const response = {
          success: true,
          outputs: { good_file: fragPath, bad_file: "/nonexistent/bad.frag" },
        } as Parameters<S3PresignedUploader["uploadOutputs"]>[0];

        await expect(
          new S3PresignedUploader().uploadOutputs(
            response,
            { good_file: srv.url, bad_file: `${srv.url}/bad` },
            ["good_file", "bad_file"],
          ),
        ).rejects.toThrow(/Output field 'bad_file' value is not a local file/);

        expect(srv.captured).toHaveLength(1);
      } finally {
        await srv.close();
      }
    });
  });
});

describe("S3PresignedUploader retry (DA-1955)", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-uploads-retry-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  async function startScriptedServer(script: Array<[number, string]>) {
    let requestCount = 0;
    const server: Server = createServer((_req, res) => {
      const [status, statusText] = script[Math.min(requestCount, script.length - 1)];
      requestCount += 1;
      res.writeHead(status, statusText);
      res.end(status >= 200 && status < 300 ? undefined : "error-detail");
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    return {
      url: `http://127.0.0.1:${port}/presigned-put`,
      getRequestCount: () => requestCount,
      close: () => new Promise<void>((resolve) => server.close(() => resolve())),
    };
  }

  it("retries 5xx then succeeds on third attempt", async () => {
    const server = await startScriptedServer([
      [500, "Internal Server Error"],
      [500, "Internal Server Error"],
      [200, "OK"],
    ]);
    const filePath = join(tmpDir, "test.txt");
    writeFileSync(filePath, "test content");
    const uploader = new S3PresignedUploader();

    try {
      await uploader.uploadFile(filePath, server.url);
      expect(server.getRequestCount()).toBe(3);
    } finally {
      await server.close();
    }
  });

  it("never retries 4xx client errors", async () => {
    const server = await startScriptedServer([[403, "Forbidden"]]);
    const filePath = join(tmpDir, "test.txt");
    writeFileSync(filePath, "test content");
    const uploader = new S3PresignedUploader();

    try {
      await expect(uploader.uploadFile(filePath, server.url)).rejects.toMatchObject({
        name: "UploadHttpError",
        statusCode: 403,
      });
      expect(server.getRequestCount()).toBe(1);
    } finally {
      await server.close();
    }
  });

  it("exhausts retries on persistent 5xx and raises UploadHttpError", async () => {
    const server = await startScriptedServer([[500, "Internal Server Error"]]);
    const filePath = join(tmpDir, "test.txt");
    writeFileSync(filePath, "test content");
    const uploader = new S3PresignedUploader();

    try {
      await expect(uploader.uploadFile(filePath, server.url)).rejects.toMatchObject({
        name: "UploadHttpError",
        statusCode: 500,
      });
      expect(server.getRequestCount()).toBe(3);
    } finally {
      await server.close();
    }
  });
});

describe("retry classification (DA-1955 review fix)", () => {
  it("missing local file fails fast without retries (ENOENT is not transient)", async () => {
    const uploader = new S3PresignedUploader();
    await expect(
      uploader.uploadFile("/nonexistent/sdk-test-file.bin", "http://127.0.0.1:1/presigned"),
    ).rejects.toThrow(/ENOENT/);
  });
});

describe("S3PresignedUploader — widened targets (DA-3314)", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "sdk-uploads-wide-"));
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("routes a descriptor target through the multipart flow via uploadOutputs", async () => {
    const calls: { method?: string; url?: string; body: Buffer }[] = [];
    const server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (c) => chunks.push(c as Buffer));
      req.on("end", () => {
        calls.push({ method: req.method, url: req.url, body: Buffer.concat(chunks) });
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
    try {
      const payload = "session-bytes";
      const filePath = join(tmpDir, "out.bin");
      writeFileSync(filePath, payload);

      await new S3PresignedUploader().uploadOutputs(
        { status: "pass", outputs: { out: filePath } } as never,
        {
          out: {
            kind: "multipart-upload-session",
            session_token: "t",
            initiate_url: `http://127.0.0.1:${port}/initiate`,
            complete_url: `http://127.0.0.1:${port}/complete`,
            abort_url: `http://127.0.0.1:${port}/abort`,
            status_url: `http://127.0.0.1:${port}/status`,
          },
        },
        ["out"],
      );

      expect(calls.some((c) => c.url === "/initiate")).toBe(true);
      expect(calls.some((c) => c.url === "/complete")).toBe(true);
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });

  it("keeps the NodeIOError contract for descriptor targets with non-file values", async () => {
    await expect(
      new S3PresignedUploader().uploadOutputs(
        { status: "pass", outputs: { out: "/nonexistent/missing.bin" } } as never,
        {
          out: {
            kind: "multipart-upload-session",
            session_token: "t",
            initiate_url: "http://127.0.0.1:1/initiate",
            complete_url: "http://127.0.0.1:1/complete",
            abort_url: "http://127.0.0.1:1/abort",
            status_url: "http://127.0.0.1:1/status",
          },
        },
        ["out"],
      ),
    ).rejects.toMatchObject({ name: "NodeIOError" });
  });
});
