import { describe, it, expect, vi } from "vitest";
import {
  WorkflowNodeManifestSchema,
  WorkflowNodeRoleSchema,
  DeprecationInfoSchema,
  getNodeId,
  getFileInputFields,
  getFileOutputFields,
  validateFileInput,
  effectiveRuntimeSeconds,
} from "../src/definition.js";
import { NodeValidationError } from "../src/exceptions.js";
import { diffManifests } from "../src/diff.js";

const validDefinition = {
  slug: "my-node",
  version: "1.0.0",
  name: "My Node",
  description: "A test node",
  input_schema: {
    type: "object",
    properties: {
      message: { type: "string" },
    },
  },
  output_schema: {
    type: "object",
    properties: {
      result: { type: "string" },
    },
  },
};

describe("WorkflowNodeManifestSchema", () => {
  it("parses a valid definition", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.slug).toBe("my-node");
    expect(def.version).toBe("1.0.0");
    expect(def.name).toBe("My Node");
    expect(def.token_cost).toBe(0.0);
    expect(def.category).toBe("utility");
    expect(def.timeout_seconds).toBe(30);
    expect(def.role).toBe("operation");
    expect(def.styles).toBeNull();
  });

  it("rejects invalid slug name", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({ ...validDefinition, slug: "MyNode" }),
    ).toThrow(/lowercase slug/);
  });

  it("rejects name with leading hyphen", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({ ...validDefinition, slug: "-node" }),
    ).toThrow(/lowercase slug/);
  });

  it("rejects name with trailing hyphen", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({ ...validDefinition, slug: "node-" }),
    ).toThrow(/lowercase slug/);
  });

  it("rejects invalid semver version", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({ ...validDefinition, version: "1.0" }),
    ).toThrow(/semantic version/);
  });

  it("rejects format: binary (DA-894)", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        input_schema: {
          type: "object",
          properties: {
            file: { type: "string", format: "binary" },
          },
        },
      }),
    ).toThrow(/binary.*no longer supported/);
  });

  it("rejects file field with non-string type", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        input_schema: {
          type: "object",
          properties: {
            file: { type: "object", format: "file" },
          },
        },
      }),
    ).toThrow(/format 'file' but type is/);
  });

  it("accepts file field with type string", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      input_schema: {
        type: "object",
        properties: {
          modelFile: {
            type: "string",
            format: "file",
            "x-accept": [".ply", ".las"],
            "x-maxSizeBytes": 1073741824,
          },
        },
      },
    });
    expect(def.input_schema).toBeDefined();
  });

  it("strips manual id", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      id: "manual-id",
    });
    expect(def).not.toHaveProperty("id");
  });

  it("applies default retry config", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.default_retry.max_attempts).toBe(1);
    expect(def.default_retry.initial_delay_ms).toBe(1000);
    expect(def.default_retry.backoff_multiplier).toBe(2.0);
    expect(def.default_retry.max_delay_ms).toBe(30000);
  });

  it("accepts styles with color and icon", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      styles: { icon: "Brain", color: "emerald" },
    });
    expect(def.styles?.icon).toBe("Brain");
    expect(def.styles?.color).toBe("emerald");
  });

  it("rejects invalid color preset", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        styles: { icon: "Box", color: "not-a-color" },
      }),
    ).toThrow();
  });
});

describe("getNodeId", () => {
  it("derives id from name and version", () => {
    expect(getNodeId({ slug: "segment", version: "1.2.0" })).toBe(
      "segment-v1.2.0",
    );
  });
});

describe("getFileInputFields", () => {
  it("returns file input field names", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      input_schema: {
        type: "object",
        properties: {
          text: { type: "string" },
          model: { type: "string", format: "file" },
          data: { type: "string", format: "file" },
        },
      },
    });
    expect(getFileInputFields(def)).toEqual(["model", "data"]);
  });

  it("returns empty array when no file inputs", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(getFileInputFields(def)).toEqual([]);
  });
});

describe("getFileOutputFields", () => {
  it("returns file output field names", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      output_schema: {
        type: "object",
        properties: {
          result: { type: "string" },
          outputFile: { type: "string", format: "file" },
        },
      },
    });
    expect(getFileOutputFields(def)).toEqual(["outputFile"]);
  });
});

describe("validateFileInput", () => {
  it("throws on disallowed extension", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      input_schema: {
        type: "object",
        properties: {
          model: {
            type: "string",
            format: "file",
            "x-accept": [".ply", ".las"],
          },
        },
      },
    });
    expect(() => validateFileInput(def, "model", "/tmp/file.xyz")).toThrow(
      NodeValidationError,
    );
  });

  it("passes on allowed extension", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      input_schema: {
        type: "object",
        properties: {
          model: {
            type: "string",
            format: "file",
            "x-accept": [".ply", ".las"],
          },
        },
      },
    });
    expect(() => validateFileInput(def, "model", "/tmp/file.ply")).not.toThrow();
  });

  it("passes when no x-accept constraint", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      input_schema: {
        type: "object",
        properties: {
          model: { type: "string", format: "file" },
        },
      },
    });
    expect(() => validateFileInput(def, "model", "/tmp/file.anything")).not.toThrow();
  });
});

describe("WorkflowNodeRoleSchema", () => {
  it("accepts all valid roles", () => {
    for (const role of ["start", "end", "error_gate", "operation"]) {
      expect(WorkflowNodeRoleSchema.parse(role)).toBe(role);
    }
  });

  it("rejects invalid roles", () => {
    expect(() => WorkflowNodeRoleSchema.parse("invalid")).toThrow();
  });

  it("defaults to operation", () => {
    expect(WorkflowNodeRoleSchema.parse(undefined)).toBe("operation");
  });

  it("WorkflowNodeManifestSchema defaults role to operation", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.role).toBe("operation");
  });

  it("WorkflowNodeManifestSchema accepts explicit roles", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      role: "start",
    });
    expect(def.role).toBe("start");
  });
});

describe("WorkflowNodeStylesSchema", () => {
  it("parses styles", async () => {
    const { WorkflowNodeStylesSchema } = await import("../src/definition.js");
    const styles = WorkflowNodeStylesSchema.parse({ icon: "Brain", color: "emerald" });
    expect(styles.icon).toBe("Brain");
    expect(styles.color).toBe("emerald");
  });

  it("parses roles", async () => {
    const { WorkflowNodeRoleSchema } = await import("../src/definition.js");
    expect(WorkflowNodeRoleSchema.parse("start")).toBe("start");
    expect(WorkflowNodeRoleSchema.parse(undefined)).toBe("operation");
  });
});

describe("DeprecationInfoSchema (DA-1582)", () => {
  it("notice is required", () => {
    expect(() => DeprecationInfoSchema.parse({})).toThrow();
  });

  it("optional fields default to null", () => {
    const info = DeprecationInfoSchema.parse({ notice: "use echo-v2" });
    expect(info.notice).toBe("use echo-v2");
    expect(info.deprecated_at).toBeNull();
    expect(info.sunset_date).toBeNull();
    expect(info.replacement_slug).toBeNull();
    expect(info.migration_url).toBeNull();
  });

  it("parses a fully-populated deprecation (dates as ISO strings)", () => {
    const info = DeprecationInfoSchema.parse({
      deprecated_at: "2026-08-01",
      sunset_date: "2027-01-01",
      replacement_slug: "echo-v2",
      migration_url: "https://example.com/migrate",
      notice: "use echo-v2",
    });
    expect(info.deprecated_at).toBe("2026-08-01");
    expect(info.sunset_date).toBe("2027-01-01");
    expect(info.replacement_slug).toBe("echo-v2");
    expect(info.migration_url).toBe("https://example.com/migrate");
  });
});

describe("WorkflowNodeManifestSchema deprecation field (DA-1582)", () => {
  it("defaults deprecation to null", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.deprecation).toBeNull();
  });

  it("parses a manifest with deprecation set", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      deprecation: {
        deprecated_at: "2026-08-01",
        sunset_date: "2027-01-01",
        replacement_slug: "my-node-v2",
        migration_url: "https://example.com/migrate",
        notice: "use my-node-v2",
      },
    });
    expect(def.deprecation?.notice).toBe("use my-node-v2");
    expect(def.deprecation?.sunset_date).toBe("2027-01-01");
    expect(def.deprecation?.replacement_slug).toBe("my-node-v2");
  });
});

describe("WorkflowNodeManifestSchema compat and docs fields (DA-1955)", () => {
  it("defaults all four fields to null", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.minimum_sdk_version).toBeNull();
    expect(def.maximum_sdk_version).toBeNull();
    expect(def.docs_url).toBeNull();
    expect(def.changelog_url).toBeNull();
  });

  it("parses valid compat and docs values", () => {
    const def = WorkflowNodeManifestSchema.parse({
      ...validDefinition,
      minimum_sdk_version: "0.22.0",
      maximum_sdk_version: "1.0.0",
      docs_url: "https://example.com/docs",
      changelog_url: "https://example.com/changelog",
    });
    expect(def.minimum_sdk_version).toBe("0.22.0");
    expect(def.maximum_sdk_version).toBe("1.0.0");
    expect(def.docs_url).toBe("https://example.com/docs");
    expect(def.changelog_url).toBe("https://example.com/changelog");
  });

  it("rejects non-semver sdk versions", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        minimum_sdk_version: "0.22",
      }),
    ).toThrow();
  });

  it("rejects non-http docs_url", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        docs_url: "ftp://example.com/docs",
      }),
    ).toThrow();
  });
});

describe("WorkflowNodeManifestSchema vocabulary compatibility (DA-2627)", () => {
  it("maps legacy name+title construction with a console warning", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const def = WorkflowNodeManifestSchema.parse({
        name: "echo",
        version: "1.0.0",
        title: "Echo",
        description: "d",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
      });
      expect(def.slug).toBe("echo");
      expect(def.name).toBe("Echo");
      expect("title" in def).toBe(false);
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("slug=<id> and name=<display>"));
    } finally {
      warnSpy.mockRestore();
    }
  });

  it("rejects name-only construction as ambiguous (no slug ?? name fallback)", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        name: "echo",
        version: "1.0.0",
        description: "d",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
      }),
    ).toThrow(/ambiguous/);
  });

  it("rejects slug without display name", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        slug: "echo",
        version: "1.0.0",
        description: "d",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
      }),
    ).toThrow();
  });

  it("ignores title with a warning when slug is present", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const def = WorkflowNodeManifestSchema.parse({
        ...validDefinition,
        title: "Stale",
      });
      expect(def.name).toBe("My Node");
      expect("title" in def).toBe(false);
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("title is ignored"));
    } finally {
      warnSpy.mockRestore();
    }
  });

  it("wire shape: standard fields + slug-derived id, no alias keys", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(getNodeId(def)).toBe("my-node-v1.0.0");
    expect(def.slug).toBe("my-node");
    expect(def.name).toBe("My Node");
    for (const absent of ["title", "node_name", "node_version"] as const) {
      expect(absent in def).toBe(false);
    }
  });
});

describe("WorkflowNodeManifestSchema safeParse parity (DA-2627 review)", () => {
  it("returns a failure result (does not throw) for name-only construction", () => {
    const result = WorkflowNodeManifestSchema.safeParse({
      name: "echo",
      version: "1.0.0",
      description: "d",
      input_schema: { type: "object" },
      output_schema: { type: "object" },
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toMatch(/ambiguous/);
    }
  });

  it("diffManifests flags identity mismatch in registry-shaped (name-keyed) manifests", () => {
    const base = { version: "1.0.0", input_schema: {}, output_schema: {} };
    const diff = diffManifests(
      { name: "old-node", ...base },
      { name: "new-node", version: "2.0.0", input_schema: {}, output_schema: {} },
    );
    expect(diff.errors.some((e) => e.includes("slug mismatch"))).toBe(true);
  });
});

describe("WorkflowNodeManifestSchema host runtime ceiling (DA-3609)", () => {
  it("defaults hard_max_runtime_seconds to 7200", () => {
    const def = WorkflowNodeManifestSchema.parse(validDefinition);
    expect(def.hard_max_runtime_seconds).toBe(7200);
  });

  it("rejects a ceiling below 1", () => {
    const result = WorkflowNodeManifestSchema.safeParse({
      ...validDefinition,
      hard_max_runtime_seconds: 0,
    });
    expect(result.success).toBe(false);
  });

  it("effectiveRuntimeSeconds caps timeout_seconds at the ceiling", () => {
    expect(
      effectiveRuntimeSeconds({ timeout_seconds: 8000, hard_max_runtime_seconds: 7200 }),
    ).toBe(7200);
  });

  it("effectiveRuntimeSeconds keeps a budget under the ceiling", () => {
    expect(
      effectiveRuntimeSeconds({ timeout_seconds: 600, hard_max_runtime_seconds: 7200 }),
    ).toBe(600);
  });

  it("effectiveRuntimeSeconds handles an equal budget and ceiling", () => {
    expect(
      effectiveRuntimeSeconds({ timeout_seconds: 7200, hard_max_runtime_seconds: 7200 }),
    ).toBe(7200);
  });
});
