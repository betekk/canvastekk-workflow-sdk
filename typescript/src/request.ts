import { z } from "zod";
import { UploadSessionDescriptorSchema } from "./uploads.js";

/**
 * Slug charset for run_id/node_id — letters, digits, dot, underscore,
 * hyphen. NOTE: the charset alone still permits `..` and `.` segments;
 * the refinement rejects them (the ids flow into filesystem paths).
 */
const slugField = z
  .string()
  .regex(/^[A-Za-z0-9._-]+$/, "must contain only letters, digits, '.', '_', '-'")
  .refine((v) => !v.includes("..") && !/^\.$/.test(v) && !/^\.\.+$/.test(v), {
    message: "must not contain dot segments",
  });

export const NodeExecutionRequestSchema = z.object({
  run_id: slugField,
  node_id: slugField,
  inputs: z.record(z.unknown()).default({}),
  callback_url: z.string().nullable().optional(),
  // DA-3314 widened targets to `string | multipart-session descriptor`
  // (DA-2886) so a descriptor value must not 400 at this parse. Since
  // DA-3340 the string member exists at this parse ONLY — the upload seam
  // (uploads.ts uploadFile) throws NodeIOError for it, so a legacy engine
  // payload fails loudly instead of as an opaque 400 (python
  // request.py `dict[str, str | UploadSession]` parity).
  output_upload_url: z
    .union([z.record(z.union([z.string(), UploadSessionDescriptorSchema])), z.null()])
    .optional()
    .default(null),
});

/**
 * Node execution request payload sent by the workflow engine.
 *
 * Fields use snake_case for wire-format compatibility with the Python engine.
 *
 * @property run_id - Unique identifier for the workflow run
 * @property node_id - Unique identifier for this node within the run
 * @property inputs - Node input values (may include presigned URLs for file fields)
 * @property callback_url - Optional URL to post completion status
 * @property output_upload_url - Optional presigned URL(s) for uploading output files
 */
export type NodeExecutionRequest = z.infer<typeof NodeExecutionRequestSchema>;
