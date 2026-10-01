import { statSync } from "node:fs";
import { open as fsOpen } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import type { UploadSessionDescriptor } from "./uploads.js";
import { NodeExecutionError, NodeIOError } from "./exceptions.js";

/**
 * Multipart upload-session client (DA-2886) — TypeScript port of the python
 * SDK's `multipart.py`. Redeems an engine-provided session descriptor:
 *
 *   1. Lazy initiate: POST `initiate_url` with the file size → the engine
 *      creates the S3 multipart upload and mints exactly
 *      `ceil(size / part_size)` presigned part URLs.
 *   2. Bounded parallel part PUTs (default 4), chunks pre-read per batch —
 *      the memory ceiling is `parallel_parts × part_size` buffered bytes,
 *      clamped to MAX_BUFFERED_BYTES (the engine bounds part_size only from
 *      below: default 100 MB, minimum 5 MB, no maximum).
 *   3. Per-part retry: 3 attempts, backoffs (1.0s, 2.0s), ANY per-attempt
 *      error retried (python `_put_one_part` parity — includes 4xx; a
 *      documented divergence from the legacy single-PUT path's
 *      transient-only rule).
 *   4. One reconcile-resume round: on a post-retry part failure, GET
 *      `status_url` (server truth of uploaded parts) and re-attempt only
 *      the unconfirmed parts.
 *   5. POST `complete_url` with all etags sorted by part number.
 *   6. Abort (best-effort) on part/resume/local-I/O failure — never on
 *      complete failure (parts are already valid in S3; complete is
 *      idempotent).
 */

const CONTROL_TIMEOUT_MS = 30_000;
const PART_PUT_TIMEOUT_MS = 600_000;
const DEFAULT_RETRY_ATTEMPTS = 3;
const DEFAULT_RETRY_BACKOFFS_MS = [1_000, 2_000] as const;
const DEFAULT_RESUME_ATTEMPTS = 1;
const DEFAULT_MAX_PARALLEL_PARTS = 4;
const MAX_BUFFERED_BYTES = 512 * 1024 * 1024;

export interface MultipartUploadOptions {
  contentType?: string;
  retryAttempts?: number;
  retryBackoffsMs?: readonly number[];
  resumeAttempts?: number;
  maxParallelParts?: number;
}

interface InitiateBundle {
  upload_id: string;
  part_size: number;
  part_urls: string[];
}

interface CompletedPart {
  part_number: number;
  etag: string;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestFor(url: string): typeof httpRequest | typeof httpsRequest {
  return new URL(url).protocol === "http:" ? httpRequest : httpsRequest;
}

/**
 * Normalizes an S3 ETag the way python's `_parse_etag` does: strips the
 * surrounding quotes and any `W/` weak prefix; empty results are an error.
 */
function parseEtag(raw: string | undefined | null): string {
  const cleaned = (raw ?? "").trim().replace(/^W\//i, "").replace(/^"|"$/g, "");
  if (!cleaned) {
    throw new NodeExecutionError("part PUT returned an empty ETag");
  }
  return cleaned;
}

function readBody(res: import("node:http").IncomingMessage, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const timer = setTimeout(() => {
      res.destroy();
      reject(
        Object.assign(new Error(`response timed out after ${timeoutMs} ms`), { code: "ETIMEDOUT" }),
      );
    }, timeoutMs);
    res.on("data", (c) => chunks.push(c as Buffer));
    res.on("end", () => {
      clearTimeout(timer);
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
    res.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/** Control-plane request (initiate/complete/abort/status) with a 30 s timeout. */
async function controlRequest(
  method: "POST" | "GET",
  url: string,
  body?: unknown,
): Promise<unknown> {
  const target = new URL(url);
  const payload = body === undefined ? undefined : JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = requestFor(url)(
      target,
      {
        method,
        headers: {
          ...(payload !== undefined
            ? {
                "Content-Type": "application/json",
                "Content-Length": String(Buffer.byteLength(payload)),
              }
            : {}),
        },
        timeout: CONTROL_TIMEOUT_MS,
      },
      (res) => {
        const code = res.statusCode ?? 0;
        readBody(res, CONTROL_TIMEOUT_MS)
          .then((text) => {
            if (code >= 200 && code < 300) {
              try {
                resolve(text ? JSON.parse(text) : {});
              } catch {
                reject(new NodeExecutionError(`malformed JSON from ${url}: ${text.slice(0, 200)}`));
              }
              return;
            }
            reject(
              new NodeExecutionError(
                `control-plane ${method} failed: HTTP ${code} ${text.slice(0, 200).trim()}`,
              ),
            );
          })
          .catch(reject);
      },
    );
    req.on("timeout", () => {
      req.destroy(Object.assign(new Error(`control-plane timed out after ${CONTROL_TIMEOUT_MS} ms`), { code: "ETIMEDOUT" }));
    });
    req.on("error", reject);
    if (payload !== undefined) req.write(payload);
    req.end();
  });
}

/** PUTs one buffered chunk to one presigned part URL with a 600 s timeout. */
async function putPartChunk(
  url: string,
  chunk: Buffer,
  contentType: string,
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const req = requestFor(url)(
      new URL(url),
      {
        method: "PUT",
        // No Content-MD5 (python parity, DA-3341): the engine presigns part
        // URLs with SignedHeaders=host only and the MD5 is unknowable at mint
        // time, so an unsigned Content-MD5 header makes S3 reject the PUT with
        // AccessDenied "There were headers present in the request which were
        // not signed". Integrity rides TLS in transit plus S3's MPU etag
        // consistency.
        headers: {
          "Content-Type": contentType,
          "Content-Length": String(chunk.length),
        },
        timeout: PART_PUT_TIMEOUT_MS,
      },
      (res) => {
        const code = res.statusCode ?? 0;
        readBody(res, PART_PUT_TIMEOUT_MS)
          .then((text) => {
            if (code >= 200 && code < 300) {
              resolve(parseEtag(res.headers.etag as string | undefined));
              return;
            }
            reject(
              new NodeExecutionError(
                `part PUT failed: HTTP ${code} ${text.slice(0, 200).trim()}`,
              ),
            );
          })
          .catch(reject);
      },
    );
    req.on("timeout", () => {
      req.destroy(Object.assign(new Error(`part PUT timed out after ${PART_PUT_TIMEOUT_MS} ms`), { code: "ETIMEDOUT" }));
    });
    req.on("error", reject);
    req.end(chunk);
  });
}

async function initiate(session: UploadSessionDescriptor, size: number, contentType: string): Promise<InitiateBundle> {
  const raw = await controlRequest("POST", session.initiate_url, { size, content_type: contentType });
  const bundle = raw as Partial<InitiateBundle>;
  if (
    !bundle ||
    typeof bundle.upload_id !== "string" ||
    typeof bundle.part_size !== "number" ||
    !Array.isArray(bundle.part_urls) ||
    bundle.part_urls.length === 0
  ) {
    throw new NodeExecutionError(
      `malformed initiate bundle for multipart session (missing upload_id/part_size/part_urls)`,
    );
  }
  return bundle as InitiateBundle;
}

async function abortSession(session: UploadSessionDescriptor, uploadId: string): Promise<void> {
  try {
    await controlRequest("POST", session.abort_url, { upload_id: uploadId });
  } catch (err) {
    console.warn(
      `multipart abort failed (best-effort): ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

/**
 * Runs the complete session-based multipart upload. Throws `NodeIOError` /
 * `NodeExecutionError` on failure (after the best-effort abort); complete
 * failures do NOT abort (see module docstring).
 */
export async function uploadViaSession(
  session: UploadSessionDescriptor,
  filePath: string,
  options: MultipartUploadOptions = {},
): Promise<void> {
  const contentType = options.contentType ?? "application/octet-stream";
  const retryAttempts = options.retryAttempts ?? DEFAULT_RETRY_ATTEMPTS;
  const backoffs = options.retryBackoffsMs ?? DEFAULT_RETRY_BACKOFFS_MS;
  const resumeAttempts = options.resumeAttempts ?? DEFAULT_RESUME_ATTEMPTS;

  const size = statSync(filePath).size;
  const bundle = await initiate(session, size, contentType);
  const partUrls = bundle.part_urls;
  const partSize = bundle.part_size;
  const totalParts = partUrls.length;
  console.info(
    `Starting multipart session upload file=${filePath} size=${size} parts=${totalParts} part_size=${partSize}`,
  );

  // Parallelism clamped so buffered bytes stay under MAX_BUFFERED_BYTES
  // (engine part_size is bounded below only).
  const maxParallel = Math.max(
    1,
    Math.min(
      options.maxParallelParts ?? DEFAULT_MAX_PARALLEL_PARTS,
      Math.floor(MAX_BUFFERED_BYTES / Math.max(1, partSize)),
    ),
  );

  const etags = new Map<number, string>();
  let remaining: number[] = Array.from({ length: totalParts }, (_, i) => i + 1);

  const fileHandle = await fsOpen(filePath, "r");
  try {
    for (let round = 0; round <= resumeAttempts; round++) {
      let failed = false;
      for (let start = 0; start < remaining.length; start += maxParallel) {
        const batch = remaining.slice(start, start + maxParallel);
        // Pre-read the batch's chunks sequentially (bounded memory), then
        // PUT them in parallel (DA-2882).
        const chunks: Buffer[] = [];
        for (const partNumber of batch) {
          const length = Math.min(partSize, size - (partNumber - 1) * partSize);
          const chunk = Buffer.alloc(length);
          const { bytesRead } = await fileHandle.read(chunk, 0, length, (partNumber - 1) * partSize);
          if (bytesRead !== length) {
            throw new NodeIOError(
              `short read for part ${partNumber} of ${filePath}: ${bytesRead}/${length}`,
            );
          }
          chunks.push(chunk);
        }

        const results = await Promise.allSettled(
          batch.map(async (partNumber, i) => {
            const chunk = chunks[i];
            let lastError: unknown;
            for (let attempt = 1; attempt <= retryAttempts; attempt++) {
              try {
                const etag = await putPartChunk(partUrls[partNumber - 1], chunk, contentType);
                return { part_number: partNumber, etag } satisfies CompletedPart;
              } catch (err) {
                lastError = err;
                if (attempt === retryAttempts) break;
                const backoffMs = backoffs[Math.min(attempt - 1, backoffs.length - 1)];
                console.warn(
                  `part ${partNumber} attempt ${attempt}/${retryAttempts} failed (${err instanceof Error ? err.message : String(err)}); retrying in ${backoffMs} ms`,
                );
                await sleep(backoffMs);
              }
            }
            throw lastError;
          }),
        );

        for (let i = 0; i < results.length; i++) {
          const outcome = results[i];
          if (outcome.status === "fulfilled") {
            etags.set(outcome.value.part_number, outcome.value.etag);
          } else {
            failed = true;
            console.error(
              `part ${batch[i]} failed after ${retryAttempts} attempts: ${outcome.reason instanceof Error ? outcome.reason.message : String(outcome.reason)}`,
            );
          }
        }
      }

      if (!failed) {
        remaining = [];
        break;
      }
      if (round === resumeAttempts) break;

      // DA-2881 reconcile-resume: ask the server which parts actually
      // landed (a mid-batch sibling's PUT may have completed) and re-attempt
      // only the unconfirmed ones.
      const statusRaw = await controlRequest("GET", session.status_url);
      const uploaded = new Set(
        ((statusRaw as { uploaded_parts?: Array<{ part_number?: number }> })?.uploaded_parts ?? [])
          .map((p) => p?.part_number)
          .filter((n): n is number => typeof n === "number"),
      );
      // Keep only parts with no server confirmation OR no locally-recorded
      // etag — the latter are re-PUT (idempotent overwrite of the same part).
      remaining = remaining.filter((n) => !uploaded.has(n) || !etags.has(n));
      if (remaining.length > 0) {
        console.warn(`resume round: ${remaining.length}/${totalParts} part(s) still unconfirmed`);
      }
    }

      if (remaining.length > 0 || etags.size !== totalParts) {
        await abortSession(session, bundle.upload_id);
        throw new NodeIOError(
          `multipart upload incomplete for ${filePath}: ${etags.size}/${totalParts} parts confirmed after retries + resume`,
        );
      }
    } catch (err) {
      // Local I/O / part / resume failures abort best-effort (parts are junk
      // without a complete file behind them). Re-raise the original error.
      await abortSession(session, bundle.upload_id);
      throw err;
    } finally {
      await fileHandle.close();
    }

    // DA-2886 parity: a complete failure does NOT abort — the parts are
    // already valid in S3 and complete is idempotent (python multipart.py).
    const parts: CompletedPart[] = [...etags.entries()]
      .map(([part_number, etag]) => ({ part_number, etag }))
      .sort((a, b) => a.part_number - b.part_number);
    await controlRequest("POST", session.complete_url, { upload_id: bundle.upload_id, parts });
    console.info(`Multipart session upload complete file=${filePath} parts=${totalParts}`);
}
