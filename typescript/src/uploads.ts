import { statSync } from "node:fs";
import { z } from "zod";
import type { NodeExecutionResponse } from "./response.js";
import { uploadViaSession } from "./multipart.js";
import { NodeIOError } from "./exceptions.js";

/**
 * Engine-provided multipart upload-session descriptor (DA-2886).
 *
 * Wire contract (snake_case, matching the execute-request wire):
 * - `initiate`  POST `{"size", "content_type"}` → `{"upload_id", "part_size", "part_urls": [...]}`
 * - `complete`  POST `{"upload_id", "parts": [{"part_number", "etag"}]}`
 * - `abort`     POST `{"upload_id"}` (best-effort)
 * - `status`    GET → `{"upload_id", "uploaded_parts": [...]}`
 *
 * Mirrors the python SDK's `UploadSession` model (uploads.py).
 */
export const UploadSessionDescriptorSchema = z.object({
  kind: z.literal("multipart-upload-session").default("multipart-upload-session"),
  session_token: z.string(),
  initiate_url: z.string().url(),
  complete_url: z.string().url(),
  abort_url: z.string().url(),
  status_url: z.string().url(),
  expires_at: z.string().optional(),
});

export type UploadSessionDescriptor = z.infer<typeof UploadSessionDescriptorSchema>;

/**
 * An upload target. Session-only since SDK 0.36.0 (DA-3340): the legacy
 * presigned-PUT `string` member was removed; a string target reaching the
 * upload seam throws {@link NodeIOError}.
 */
export type UploadTarget = UploadSessionDescriptor;

/**
 * Interface for uploading node output files.
 */
export interface OutputUploader {
  /**
   * Uploads one file to one target. Since SDK 0.36.0 (DA-3340) the target
   * is a session descriptor only; a legacy presigned-PUT string fails
   * loudly with {@link NodeIOError} — the engine must be upgraded.
   */
  uploadFile(filePath: string, target: UploadTarget): Promise<void>;
  /**
   * Implementations MUST throw (not skip) when a file-output field that is
   * present in `response.outputs` and has an upload target holds a value
   * that is not an existing local file — silently skipping would report
   * success while the engine stamps a storage URI for the missing object,
   * corrupting downstream consumers (DA-2337).
   */
  uploadOutputs(
    response: NodeExecutionResponse,
    uploadUrls: Record<string, UploadTarget>,
    fileOutputFields: string[],
  ): Promise<void>;
}

/** Exact fail-loud message for a legacy presigned-PUT string target (DA-3340). */
const LEGACY_TARGET_MESSAGE = "engine sent deprecated presigned target — upgrade the engine";

/**
 * Uploads output files via engine-provided upload sessions.
 */
export class S3PresignedUploader implements OutputUploader {
  /**
   * Uploads a single file via an upload target.
   *
   * Session-only since SDK 0.36.0 (DA-3340): a session descriptor takes
   * the multipart client (`uploadViaSession` — lazy initiate → bounded
   * parallel part PUTs → complete; per-part retry; status reconcile;
   * abort on failure). A legacy presigned-PUT string throws
   * {@link NodeIOError} — fail-loud compliance, never a silent fallback;
   * the engine must be upgraded (DA-3338), not the node.
   *
   * @param filePath - Local file path
   * @param target - Multipart upload-session descriptor
   * @throws NodeIOError when a legacy string target is received, or on a
   * part-PUT/local I/O failure after retries/resume/abort
   * @throws NodeExecutionError on control-plane failure
   */
  async uploadFile(filePath: string, target: UploadTarget): Promise<void> {
    if (typeof target === "string") {
      throw new NodeIOError(LEGACY_TARGET_MESSAGE);
    }
    await uploadViaSession(target, filePath);
  }

  /**
   * Uploads all file outputs from a node response.
   *
   * Upload failures PROPAGATE so the caller can fail the execution —
   * silently reporting success with local-only paths would strand
   * downstream consumers (DA-1711 4.1).
   *
   * A declared file-output field that HAS an upload target but whose value
   * is not a string referencing an existing regular file THROWS — the
   * engine stamps an `s3://` URI for every present output field on pass,
   * so skipping the upload would report success while corrupting every
   * downstream consumer (DA-2337). Fields ABSENT from the response are
   * skipped (omission is legal — the engine never stamps them).
   *
   * @param response - Node execution response
   * @param uploadUrls - Mapping of field names to upload targets
   * @param fileOutputFields - Names of file output fields
   * @throws NodeIOError when a present file-output field is not a string,
   * not an existing local file, or its target is a legacy presigned-PUT
   * string (DA-3340)
   */
  async uploadOutputs(
    response: NodeExecutionResponse,
    uploadUrls: Record<string, UploadTarget>,
    fileOutputFields: string[],
  ): Promise<void> {
    if (!response.outputs) return;

    for (const fieldName of fileOutputFields) {
      if (!(fieldName in uploadUrls)) continue;

      if (!Object.hasOwn(response.outputs, fieldName)) {
        // Omitted output: the engine stamps s3:// URIs only for fields
        // present in the response, so omission is legal.
        continue;
      }

      const value = response.outputs[fieldName];
      if (typeof value !== "string") {
        throw new NodeIOError(
          `Output field '${fieldName}' value is not a string: ${typeof value}`,
        );
      }

      let isRegularFile = false;
      try {
        isRegularFile = statSync(value).isFile();
      } catch {
        isRegularFile = false;
      }

      if (!isRegularFile) {
        throw new NodeIOError(
          `Output field '${fieldName}' value is not a local file: ${value}`,
          { path: value },
        );
      }

      await this.uploadFile(value, uploadUrls[fieldName]);
      const size = statSync(value).size;
      console.info(`Uploaded output '${fieldName}' to S3 (${size} bytes)`);
    }
  }
}

let _defaultUploader: S3PresignedUploader | null = null;

/**
 * Gets the default S3 uploader instance (singleton).
 * @returns Default S3 presigned uploader
 */
export function getDefaultUploader(): S3PresignedUploader {
  if (!_defaultUploader) {
    _defaultUploader = new S3PresignedUploader();
  }
  return _defaultUploader;
}
