import { describe, it, expect } from "vitest";
import {
  NodeExecutionError,
  NodeTimeoutError,
  NodeValidationError,
  NodeOutputValidationError,
  NodeIOError,
  NodeConfigurationError,
  WorkflowExecutionError,
  WorkflowValidationError,
  RegistrationError,
  ERROR_CODE_TO_HTTP_STATUS,
  getHttpStatusForError,
  ERROR_CATEGORIES,
  ERROR_ENVELOPE_KEYS,
  IO_SUBCODE_DOWNLOAD_FAILED,
  errorEnvelope,
} from "../src/exceptions.js";

describe("NodeExecutionError", () => {
  it("has correct defaults", () => {
    const err = new NodeExecutionError("something broke");
    expect(err.message).toBe("something broke");
    expect(err.errorCode).toBe("EXECUTION_ERROR");
    expect(err.details).toEqual({});
    expect(err.toDict()).toEqual({
      error_code: "EXECUTION_ERROR",
      category: "domain",
      message: "something broke",
      details: {},
    });
  });

  it("accepts custom errorCode and details", () => {
    const err = new NodeExecutionError("x", {
      errorCode: "CUSTOM",
      details: { foo: "bar" },
    });
    expect(err.errorCode).toBe("CUSTOM");
    expect(err.details).toEqual({ foo: "bar" });
  });
});

describe("NodeTimeoutError", () => {
  it("has correct properties", () => {
    const err = new NodeTimeoutError(30);
    expect(err.message).toBe("Node execution timed out after 30s");
    expect(err.errorCode).toBe("TIMEOUT");
    expect(err.timeoutSeconds).toBe(30);
    expect(err.details).toEqual({ timeout_seconds: 30 });
    expect(err.toDict().details).toEqual({ timeout_seconds: 30 });
  });
});

describe("NodeValidationError", () => {
  it("includes errors in toDict", () => {
    const errors = [{ path: ["inputs", "name"], message: "required" }];
    const err = new NodeValidationError("Validation failed", { errors });
    expect(err.errorCode).toBe("VALIDATION_ERROR");
    expect(err.errors).toEqual(errors);
    const dict = err.toDict();
    expect(dict.errors).toEqual(errors);
  });

  it("defaults to empty errors array", () => {
    const err = new NodeValidationError("fail");
    expect(err.errors).toEqual([]);
  });
});

describe("NodeOutputValidationError", () => {
  it("includes errors in toDict", () => {
    const errors = [{ path: ["outputs", "file"], message: "missing" }];
    const err = new NodeOutputValidationError("Output invalid", { errors });
    expect(err.errorCode).toBe("OUTPUT_VALIDATION_ERROR");
    expect(err.toDict().errors).toEqual(errors);
  });
});

describe("NodeIOError", () => {
  it("includes path in details when provided", () => {
    const err = new NodeIOError("file not found", { path: "/tmp/x.ply" });
    expect(err.errorCode).toBe("IO_ERROR");
    expect(err.path).toBe("/tmp/x.ply");
    expect(err.details.path).toBe("/tmp/x.ply");
  });

  it("path defaults to null", () => {
    const err = new NodeIOError("fail");
    expect(err.path).toBeNull();
  });
});

describe("NodeConfigurationError", () => {
  it("has correct errorCode", () => {
    const err = new NodeConfigurationError("bad config");
    expect(err.errorCode).toBe("CONFIGURATION_ERROR");
  });
});

describe("WorkflowExecutionError", () => {
  it("includes nodeId in details", () => {
    const err = new WorkflowExecutionError("workflow failed", {
      nodeId: "node-1",
    });
    expect(err.errorCode).toBe("WORKFLOW_EXECUTION_ERROR");
    expect(err.nodeId).toBe("node-1");
    expect(err.details.node_id).toBe("node-1");
  });
});

describe("WorkflowValidationError", () => {
  it("includes errors in toDict", () => {
    const err = new WorkflowValidationError("bad workflow", {
      errors: ["cycle detected"],
    });
    expect(err.errorCode).toBe("WORKFLOW_VALIDATION_ERROR");
    expect(err.errors).toEqual(["cycle detected"]);
    expect(err.toDict().errors).toEqual(["cycle detected"]);
  });
});

describe("RegistrationError", () => {
  it("extracts message from body", () => {
    const err = new RegistrationError(400, { detail: "Already exists" });
    expect(err.statusCode).toBe(400);
    expect(err.message).toBe("Already exists");
    expect(err.body).toEqual({ detail: "Already exists" });
  });

  it("falls back to generic message", () => {
    const err = new RegistrationError(500, {});
    expect(err.message).toBe("Registration failed with status 500");
  });
});

describe("ERROR_CODE_TO_HTTP_STATUS", () => {
  it("maps all error codes correctly", () => {
    expect(ERROR_CODE_TO_HTTP_STATUS).toEqual({
      EXECUTION_ERROR: 500,
      TIMEOUT: 408,
      VALIDATION_ERROR: 422,
      OUTPUT_VALIDATION_ERROR: 422,
      IO_ERROR: 500,
      CONFIGURATION_ERROR: 500,
      WORKFLOW_EXECUTION_ERROR: 500,
      WORKFLOW_VALIDATION_ERROR: 422,
    });
  });
});

describe("getHttpStatusForError", () => {
  it("maps known error codes", () => {
    expect(getHttpStatusForError(new NodeTimeoutError(30))).toBe(408);
    expect(getHttpStatusForError(new NodeValidationError("x"))).toBe(422);
    expect(getHttpStatusForError(new NodeIOError("x"))).toBe(500);
    expect(getHttpStatusForError(new NodeConfigurationError("x"))).toBe(500);
    expect(getHttpStatusForError(new WorkflowValidationError("x"))).toBe(422);
    expect(getHttpStatusForError(new NodeOutputValidationError("x"))).toBe(422);
    expect(getHttpStatusForError(new WorkflowExecutionError("x"))).toBe(500);
    expect(getHttpStatusForError(new NodeExecutionError("x"))).toBe(500);
  });

  it("returns 500 for unknown error code", () => {
    const err = new NodeExecutionError("x", { errorCode: "UNKNOWN" });
    expect(getHttpStatusForError(err)).toBe(500);
  });
});

describe("error taxonomy (S.2, SDK#161)", () => {
  it("ERROR_CATEGORIES is the five axes", () => {
    expect(ERROR_CATEGORIES).toEqual([
      "transport",
      "validation",
      "domain",
      "timeout",
      "lifecycle",
    ]);
  });

  it("subclass category mapping", () => {
    expect(new NodeTimeoutError(10).category).toBe("timeout");
    expect(new NodeValidationError("x").category).toBe("validation");
    expect(new NodeIOError("x").category).toBe("transport");
    expect(new NodeConfigurationError("x").category).toBe("lifecycle");
    expect(new NodeOutputValidationError("x").category).toBe("validation");
    expect(new WorkflowValidationError(["bad"]).category).toBe("validation");
  });

  it("base defaults to domain", () => {
    expect(new NodeExecutionError("boom").category).toBe("domain");
  });

  it("toDict carries category", () => {
    const payload = new NodeIOError("download failed").toDict();
    expect(payload.category).toBe("transport");
    expect(payload.error_code).toBe("IO_ERROR");
  });
});

describe("error envelope (S.3, SDK#161)", () => {
  it("ERROR_ENVELOPE_KEYS constant", () => {
    expect(ERROR_ENVELOPE_KEYS).toEqual(["type", "message", "code"]);
  });

  it("envelope triple", () => {
    expect(errorEnvelope(new NodeIOError("download failed"))).toEqual({
      type: "transport",
      message: "download failed",
      code: "IO_ERROR",
    });
  });

  it("envelope on subcoded error", () => {
    const err = new NodeIOError("download failed", {
      details: { sub_code: IO_SUBCODE_DOWNLOAD_FAILED },
    });
    expect(errorEnvelope(err).code).toBe("IO_ERROR");
    expect(err.details.sub_code).toBe("IO_DOWNLOAD_FAILED");
  });
});

describe("structured sunset (S.2, SDK#161)", () => {
  it("sunset refusal carries NODE_SUNSET + details", () => {
    const err = new NodeConfigurationError("was sunset", {
      errorCode: "NODE_SUNSET",
      details: { sunset_date: "2026-01-01", replacement_slug: "next" },
    });
    expect(err.errorCode).toBe("NODE_SUNSET");
    expect(err.category).toBe("lifecycle");
    expect(err.details.replacement_slug).toBe("next");
  });
});
