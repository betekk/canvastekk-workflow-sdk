import { describe, it, expect } from "vitest";
import {
  NodeExecutionRequestSchema,
} from "../src/request.js";

describe("NodeExecutionRequestSchema", () => {
  it("parses a full request", () => {
    const req = NodeExecutionRequestSchema.parse({
      run_id: "run-abc",
      node_id: "echo-1",
      inputs: { message: "hi" },
      callback_url: "https://example.com/callback",
      output_upload_url: { file: "https://s3.example.com/presigned" },
    });
    expect(req.run_id).toBe("run-abc");
    expect(req.node_id).toBe("echo-1");
    expect(req.inputs).toEqual({ message: "hi" });
    expect(req.callback_url).toBe("https://example.com/callback");
    expect(req.output_upload_url).toEqual({ file: "https://s3.example.com/presigned" });
  });

  it("defaults inputs to empty object", () => {
    const req = NodeExecutionRequestSchema.parse({
      run_id: "run-1",
      node_id: "node-1",
    });
    expect(req.inputs).toEqual({});
  });

  it("defaults callback_url and output_upload_url", () => {
    const req = NodeExecutionRequestSchema.parse({
      run_id: "run-1",
      node_id: "node-1",
    });
    expect(req.callback_url).toBeUndefined();
    expect(req.output_upload_url).toBeNull();
  });

  it("accepts null output_upload_url", () => {
    const req = NodeExecutionRequestSchema.parse({
      run_id: "run-1",
      node_id: "node-1",
      output_upload_url: null,
    });
    expect(req.output_upload_url).toBeNull();
  });
});

describe("NodeExecutionRequest slug validation (DA-1711)", () => {
  it("rejects run_id with dot segments", () => {
    const parsed = NodeExecutionRequestSchema.safeParse({
      run_id: "../../etc",
      node_id: "n1",
      inputs: {},
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects dot-only node_id", () => {
    const parsed = NodeExecutionRequestSchema.safeParse({
      run_id: "r1",
      node_id: "..",
      inputs: {},
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects absolute-ish ids", () => {
    const parsed = NodeExecutionRequestSchema.safeParse({
      run_id: "/abs/path",
      node_id: "n1",
      inputs: {},
    });
    expect(parsed.success).toBe(false);
  });

  it("accepts valid slugs", () => {
    const parsed = NodeExecutionRequestSchema.safeParse({
      run_id: "run-abc.123_x",
      node_id: "node.1-y",
      inputs: {},
    });
    expect(parsed.success).toBe(true);
  });
});

describe("NodeExecutionRequest output_upload_url targets (DA-3314)", () => {
  it("parses a full execute request with a multipart-session descriptor", () => {
    const parsed = NodeExecutionRequestSchema.safeParse({
      run_id: "run-1",
      node_id: "n1",
      inputs: {},
      output_upload_url: {
        frag_file: {
          kind: "multipart-upload-session",
          session_token: "tok",
          initiate_url: "https://engine/initiate",
          complete_url: "https://engine/complete",
          abort_url: "https://engine/abort",
          status_url: "https://engine/status",
        },
      },
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      const target = parsed.data.output_upload_url?.["frag_file"];
      expect(typeof target).toBe("object");
    }
  });

  it("still parses legacy string targets and null", () => {
    for (const output_upload_url of [
      { frag_file: "https://s3/presigned-put" },
      null,
      undefined,
    ]) {
      const parsed = NodeExecutionRequestSchema.safeParse({
        run_id: "run-1",
        node_id: "n1",
        inputs: {},
        output_upload_url,
      });
      expect(parsed.success).toBe(true);
    }
  });
});
