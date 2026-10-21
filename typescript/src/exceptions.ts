/**
 * S.2 error taxonomy (SDK#161): every SDK exception classifies into exactly
 * one category. Engine-minted codes join the same registry — the engine's
 * D.2 synthesized envelopes carry `type` values from this tuple.
 */
export const ERROR_CATEGORIES = [
  "transport",
  "validation",
  "domain",
  "timeout",
  "lifecycle",
] as const;

export type ErrorCategory = (typeof ERROR_CATEGORIES)[number];

/**
 * S.3 error envelope (SDK#161): the one error shape the engine synthesizes on
 * failed node results (D.2), frontend ERROR rows render (CFN#2080), and node
 * repos raise against (D.4).
 */
export const ERROR_ENVELOPE_KEYS = ["type", "message", "code"] as const;

/**
 * S.6 transport sub-codes (SDK#161): machine-readable reasons carried in
 * `details["sub_code"]` by the SDK's download paths (both languages).
 */
export const IO_SUBCODE_DOWNLOAD_FAILED = "IO_DOWNLOAD_FAILED";
export const IO_SUBCODE_URL_POLICY_BLOCKED = "IO_URL_POLICY_BLOCKED";
export const IO_SUBCODE_SIZE_EXCEEDED = "IO_SIZE_EXCEEDED";

/**
 * Base error class for all node execution errors with error code and details.
 *
 * Unclassified errors (a bare `NodeExecutionError` or an uncaught exception
 * the app wraps) are `domain` — the node's own logic failed, not the
 * transport, validation, timeout, or lifecycle machinery.
 */
export class NodeExecutionError extends Error {
  readonly errorCode: string;
  readonly details: Record<string, unknown>;
  readonly category: ErrorCategory = "domain";

  /**
   * Creates a new NodeExecutionError.
   * @param message - Error message
   * @param options - Error options including error code and details
   */
  constructor(
    message: string,
    { errorCode = "EXECUTION_ERROR", details }: {
      errorCode?: string;
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message);
    this.name = "NodeExecutionError";
    this.errorCode = errorCode;
    this.details = details ?? {};
  }

  /**
   * Converts error to dictionary for serialization.
   * @returns Dictionary with error_code, category, message, and details
   */
  toDict(): Record<string, unknown> {
    return {
      error_code: this.errorCode,
      category: this.category,
      message: this.message,
      details: this.details,
    };
  }
}

/**
 * Serialize an error to the S.3 envelope shape `{type, message, code}`.
 * @param error - The exception to envelope
 * @returns Dict with the ERROR_ENVELOPE_KEYS triple
 */
export function errorEnvelope(error: NodeExecutionError): {
  type: ErrorCategory;
  message: string;
  code: string;
} {
  return { type: error.category, message: error.message, code: error.errorCode };
}

/**
 * Error thrown when node execution exceeds timeout limit.
 */
export class NodeTimeoutError extends NodeExecutionError {
  readonly category: ErrorCategory = "timeout";

  readonly timeoutSeconds: number;

  /**
   * Creates a new NodeTimeoutError.
   * @param timeoutSeconds - Timeout duration in seconds
   * @param options - Additional error details
   */
  constructor(
    timeoutSeconds: number,
    { details }: { details?: Record<string, unknown> } = {},
  ) {
    super(`Node execution timed out after ${timeoutSeconds}s`, {
      errorCode: "TIMEOUT",
      details: details ?? { timeout_seconds: timeoutSeconds },
    });
    this.name = "NodeTimeoutError";
    this.timeoutSeconds = timeoutSeconds;
  }
}

/**
 * Error thrown when node input validation fails.
 */
export class NodeValidationError extends NodeExecutionError {
  readonly category: ErrorCategory = "validation";

  readonly errors: Record<string, unknown>[];

  /**
   * Creates a new NodeValidationError.
   * @param message - Error message
   * @param options - Validation errors and additional details
   */
  constructor(
    message: string,
    { errors, details }: {
      errors?: Record<string, unknown>[];
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message, { errorCode: "VALIDATION_ERROR", details });
    this.name = "NodeValidationError";
    this.errors = errors ?? [];
  }

  /**
   * Converts error to dictionary for serialization.
   * @returns Dictionary with validation errors
   */
  toDict(): Record<string, unknown> {
    return { ...super.toDict(), errors: this.errors };
  }
}

/**
 * Error thrown when node output validation fails.
 */
export class NodeOutputValidationError extends NodeExecutionError {
  readonly category: ErrorCategory = "validation";

  readonly errors: Record<string, unknown>[];

  /**
   * Creates a new NodeOutputValidationError.
   * @param message - Error message
   * @param options - Validation errors and additional details
   */
  constructor(
    message: string,
    { errors, details }: {
      errors?: Record<string, unknown>[];
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message, { errorCode: "OUTPUT_VALIDATION_ERROR", details });
    this.name = "NodeOutputValidationError";
    this.errors = errors ?? [];
  }

  /**
   * Converts error to dictionary for serialization.
   * @returns Dictionary with validation errors
   */
  toDict(): Record<string, unknown> {
    return { ...super.toDict(), errors: this.errors };
  }
}

/**
 * Error thrown when file I/O operations fail.
 */
export class NodeIOError extends NodeExecutionError {
  readonly category: ErrorCategory = "transport";

  readonly path: string | null;

  /**
   * Creates a new NodeIOError.
   * @param message - Error message
   * @param options - File path and additional details
   */
  constructor(
    message: string,
    { path, details }: {
      path?: string | null;
      details?: Record<string, unknown>;
    } = {},
  ) {
    const mergedDetails: Record<string, unknown> = { ...details };
    if (path) mergedDetails.path = path;
    super(message, { errorCode: "IO_ERROR", details: mergedDetails });
    this.name = "NodeIOError";
    this.path = path ?? null;
  }
}

/**
 * Error thrown when node configuration is invalid.
 */
export class NodeConfigurationError extends NodeExecutionError {
  readonly category: ErrorCategory = "lifecycle";

  /**
   * Creates a new NodeConfigurationError.
   * @param message - Error message
   * @param options - Additional error details
   */
  constructor(
    message: string,
    {
      errorCode = "CONFIGURATION_ERROR",
      details,
    }: {
      errorCode?: string;
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message, { errorCode, details });
    this.name = "NodeConfigurationError";
  }
}

/**
 * Error thrown when workflow execution fails.
 */
export class WorkflowExecutionError extends NodeExecutionError {
  readonly nodeId: string | null;

  /**
   * Creates a new WorkflowExecutionError.
   * @param message - Error message
   * @param options - Node ID and additional details
   */
  constructor(
    message: string,
    { nodeId, details }: {
      nodeId?: string | null;
      details?: Record<string, unknown>;
    } = {},
  ) {
    const mergedDetails: Record<string, unknown> = { ...details };
    if (nodeId) mergedDetails.node_id = nodeId;
    super(message, { errorCode: "WORKFLOW_EXECUTION_ERROR", details: mergedDetails });
    this.name = "WorkflowExecutionError";
    this.nodeId = nodeId ?? null;
  }
}

/**
 * Error thrown when workflow validation fails.
 */
export class WorkflowValidationError extends NodeExecutionError {
  readonly category: ErrorCategory = "validation";

  readonly errors: string[];

  /**
   * Creates a new WorkflowValidationError.
   * @param message - Error message
   * @param options - Validation errors and additional details
   */
  constructor(
    message: string,
    { errors, details }: {
      errors?: string[];
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message, { errorCode: "WORKFLOW_VALIDATION_ERROR", details });
    this.name = "WorkflowValidationError";
    this.errors = errors ?? [];
  }

  /**
   * Converts error to dictionary for serialization.
   * @returns Dictionary with validation errors
   */
  toDict(): Record<string, unknown> {
    return { ...super.toDict(), errors: this.errors };
  }
}

/**
 * Error thrown when node registration fails.
 */
export class RegistrationError extends Error {
  readonly statusCode: number;
  readonly body: Record<string, unknown>;
  /** Engine error code from the envelope, or null when unmapped. */
  readonly code: string | null;
  /** Actionable fix suggestion derived from the envelope, or null. */
  readonly guidance: string | null;

  /**
   * Creates a new RegistrationError.
   * @param statusCode - HTTP status code
   * @param body - Response body with error details
   */
  constructor(statusCode: number, body: Record<string, unknown>) {
    const message = body.detail?.toString() ?? body.message?.toString() ?? `Registration failed with status ${statusCode}`;
    super(message);
    this.name = "RegistrationError";
    this.statusCode = statusCode;
    this.body = body;
    const derived = deriveCodeAndGuidance(body, statusCode);
    this.code = derived.code;
    this.guidance = derived.guidance;
  }
}

/**
 * Unwraps a JSON-encoded detail string (engine canonical errors).
 * Non-string or unparsable values pass through unchanged.
 */
function parseDetail(detail: unknown): unknown {
  if (typeof detail === "string") {
    try {
      return JSON.parse(detail);
    } catch {
      return detail;
    }
  }
  return detail;
}

function collectFieldMessages(body: Record<string, unknown>, statusCode: number): string[] {
  const messages: string[] = [];
  const errors = body["errors"];
  if (Array.isArray(errors)) {
    for (const item of errors) {
      if (typeof item === "object" && item !== null && item["message"]) {
        messages.push(String(item["message"]));
      } else if (typeof item === "string") {
        messages.push(item);
      }
    }
  }
  if (messages.length === 0 && statusCode === 422) {
    const detail = parseDetail(body["detail"]);
    if (Array.isArray(detail)) {
      for (const item of detail) {
        if (typeof item === "object" && item !== null) {
          const loc = Array.isArray(item["loc"])
            ? (item["loc"] as unknown[]).filter((p) => p !== "body").join(".")
            : "";
          const msg = String(item["msg"] ?? "invalid value");
          messages.push(loc ? `${loc}: ${msg}` : msg);
        } else if (typeof item === "string") {
          messages.push(item);
        }
      }
    }
  }
  return messages;
}

function deriveCodeAndGuidance(
  body: Record<string, unknown>,
  statusCode: number,
): { code: string | null; guidance: string | null } {
  const rawCode = body["error"];
  const code = typeof rawCode === "string" && rawCode.length > 0 ? rawCode : null;

  if (code === "node_version_immutable") {
    const detail = parseDetail(body["detail"]);
    const changed: string[] = [];
    if (typeof detail === "object" && detail !== null && Array.isArray((detail as Record<string, unknown>)["changed_fields"])) {
      for (const item of (detail as Record<string, unknown>)["changed_fields"] as unknown[]) {
        if (typeof item === "object" && item !== null && (item as Record<string, unknown>)["field"]) {
          changed.push(String((item as Record<string, unknown>)["field"]));
        }
      }
    }
    const fields = changed.length > 0 ? changed.join(", ") : "unknown fields";
    return {
      code,
      guidance: `This version is already published and immutable (changed: ${fields}). Bump 'version' to a higher semver and re-register.`,
    };
  }
  if (statusCode === 409) {
    return {
      code,
      guidance: "The registry rejected this version conflict. Publish a version higher than the current latest.",
    };
  }
  if (statusCode === 400 || statusCode === 422) {
    const messages = collectFieldMessages(body, statusCode);
    if (messages.length > 0) {
      return { code, guidance: `Fix the validation errors and retry: ${messages.join("; ")}` };
    }
  }
  return { code, guidance: null };
}

/**
 * Mapping of error codes to HTTP status codes.
 */
export const ERROR_CODE_TO_HTTP_STATUS: Record<string, number> = {
  EXECUTION_ERROR: 500,
  TIMEOUT: 408,
  VALIDATION_ERROR: 422,
  OUTPUT_VALIDATION_ERROR: 422,
  IO_ERROR: 500,
  CONFIGURATION_ERROR: 500,
  WORKFLOW_EXECUTION_ERROR: 500,
  WORKFLOW_VALIDATION_ERROR: 422,
};

/**
 * Converts a NodeExecutionError to its HTTP status code.
 * @param exc - Node execution error
 * @returns HTTP status code (500 default)
 */
export function getHttpStatusForError(exc: NodeExecutionError): number {
  return ERROR_CODE_TO_HTTP_STATUS[exc.errorCode] ?? 500;
}
