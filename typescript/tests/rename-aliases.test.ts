/**
 * Removed-alias guard tests (ADR 0001, #271 removal; 1.0.0, #272).
 *
 * The old module paths, deprecated index names, and the legacy `definition`
 * class attribute were removed in 1.0.0. These guards FAIL if any of them
 * returns: every old path must reject on import and every old index name
 * must be absent from the index namespace.
 */
import { describe, expect, it } from "vitest";

import * as sdk from "../src/index.js";
import * as newManifest from "../src/workflow-node-manifest.js";
import * as newManifestDiff from "../src/workflow-node-manifest-diff.js";
import * as newRegistry from "../src/workflow-node-registry.js";
import * as newNodeExecutor from "../src/workflow/node-executor.js";

const REMOVED_PATHS = [
  "../src/definition.js",
  "../src/diff.js",
  "../src/registry.js",
  "../src/base-node.js",
  "../src/app.js",
  "../src/request.js",
  "../src/response.js",
  "../src/context.js",
  "../src/protocol.js",
  "../src/uploads.js",
  "../src/multipart.js",
  "../src/workflow/models.js",
  "../src/workflow/executor.js",
] as const;

const REMOVED_INDEX_NAMES = [
  "BaseNode",
  "ExecutionContext",
  "HealthResponse",
  "HealthResponseSchema",
  "NodeExecutionStatus",
  "NodeExecutionStatusSchema",
  "parseNodeExecutionStatus",
  "NODE_PROTOCOL_HEADER",
  "NODE_PROTOCOL_VERSION",
  "PROTOCOL_2_OUTCOMES",
  "outcomeForProtocol",
  "readOutcome",
  "requestedProtocol",
  "MetricsCollector",
  "createExecutionMetric",
  "metricToDict",
  "ExecutionMetric",
  "S3PresignedUploader",
  "getDefaultUploader",
  "UploadSessionDescriptorSchema",
  "OutputUploader",
  "UploadTarget",
  "UploadSessionDescriptor",
  "uploadViaSession",
  "CONTRACT_VERSION",
  "BaseContractData",
  "validate",
  "ValidationResult",
  "NodeResult",
  "ErrorPolicy",
  "NodeExecutor",
  "InProcessExecutor",
  "HttpExecutor",
  "WorkflowExecutionError",
  "WorkflowValidationError",
  "ColorPreset",
  "ColorPresetSchema",
  "RetryConfig",
  "RetryConfigSchema",
  "DeprecationInfo",
  "DeprecationInfoSchema",
  "NodeContract",
  "ContractCapabilities",
  "getNodeId",
  "diffManifests",
  "ManifestDiff",
  "registerNode",
  "RegisterNodeResult",
  "RegistrationError",
  "buildRegistryPayload",
  "exportDefinition",
  "NodeAuth",
] as const;

describe("removed module paths (1.0.0, #272)", () => {
  it.each(REMOVED_PATHS)("old path %s rejects on import", async (path) => {
    await expect(import(/* @vite-ignore */ path as string)).rejects.toBeTruthy();
  });
});

describe("removed index names (1.0.0, #272)", () => {
  it("none of the old names resolve from the index", () => {
    const present = REMOVED_INDEX_NAMES.filter((n) => n in sdk);
    expect(present, `old names still exported: ${present.join(", ")}`).toEqual([]);
  });

  it("canonical names still resolve (non-regression)", () => {
    expect(newManifest.getWorkflowNodeManifestId).toBeTruthy();
    expect(newRegistry.exportWorkflowNodeManifest).toBeTruthy();
    expect(newManifestDiff.diffWorkflowNodeManifests).toBeTruthy();
    expect(newNodeExecutor.InProcessNodeExecutor).toBeTruthy();
    expect(newNodeExecutor.HttpNodeExecutor).toBeTruthy();
  });
});

describe("removed legacy `definition` attribute (1.0.0, #272)", () => {
  it("nodes carry the manifest only through `manifest`", async () => {
    const { WorkflowNodeBase, WorkflowNodeManifestSchema } = await import("../src/index.js");
    class CanonicalNode extends WorkflowNodeBase {
      manifest = {
        slug: "canonical-only",
        version: "1.0.0",
        name: "Canonical Only",
        description: "manifest attribute only",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
      };
      execute(): Record<string, unknown> {
        return {};
      }
    }
    const node = new CanonicalNode();
    expect(WorkflowNodeManifestSchema.parse((node as unknown as { manifest: unknown }).manifest)).toBeTruthy();
    expect((node as unknown as { definition?: unknown }).definition).toBeUndefined();
  });

  it("a legacy `definition`-only class no longer resolves a manifest", async () => {
    const { WorkflowNodeBase, WorkflowNodeManifestSchema } = await import("../src/index.js");
    class LegacyAttrNode extends WorkflowNodeBase {
      definition = {
        slug: "legacy-attr",
        version: "1.0.0",
        name: "Legacy Attr",
        description: "legacy attribute must be inert in 1.0.0",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
      };
      execute(): Record<string, unknown> {
        return {};
      }
    }
    const node = new LegacyAttrNode();
    const self = node as unknown as Record<string, unknown>;
    expect(() =>
      WorkflowNodeManifestSchema.parse(self.manifest),
    ).toThrow();
  });
});
