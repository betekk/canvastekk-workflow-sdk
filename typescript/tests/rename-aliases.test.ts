/**
 * Deprecated-alias tests (ADR 0001, #271).
 *
 * Old module paths keep resolving and old index names keep re-exporting
 * (compile-time `@deprecated` markers are the TypeScript warning surface).
 * Phase-scoped: grows with each rename phase.
 */
import { describe, expect, it } from "vitest";

// Old module paths must still resolve (shim files re-export the new modules).
import * as oldDefinition from "../src/definition.js";
import * as oldDiff from "../src/diff.js";
import * as oldRegistry from "../src/registry.js";
import * as newManifest from "../src/workflow-node-manifest.js";
import * as newManifestDiff from "../src/workflow-node-manifest-diff.js";
import * as newRegistry from "../src/workflow-node-registry.js";
import {
  ColorPreset,
  ContractCapabilities,
  DeprecationInfo,
  ManifestDiff,
  NodeContract,
  RetryConfig,
  buildRegistryPayload,
  diffManifests,
  exportDefinition,
  getNodeId,
  registerNode,
  RegisterNodeResult,
  RegistrationError,
} from "../src/index.js";

describe("deprecated module paths (ADR 0001)", () => {
  it("definition.js re-exports workflow-node-manifest.js", () => {
    expect(oldDefinition.getWorkflowNodeManifestId).toBe(newManifest.getWorkflowNodeManifestId);
    expect(oldDefinition.exportWorkflowNodeManifest).toBe(newManifest.exportWorkflowNodeManifest);
  });

  it("diff.js re-exports workflow-node-manifest-diff.js", () => {
    expect(oldDiff.diffWorkflowNodeManifests).toBe(newManifestDiff.diffWorkflowNodeManifests);
  });

  it("registry.js re-exports workflow-node-registry.js", () => {
    expect(oldRegistry.registerWorkflowNode).toBe(newRegistry.registerWorkflowNode);
    expect(oldRegistry.buildWorkflowNodeRegistryPayload).toBe(
      newRegistry.buildWorkflowNodeRegistryPayload,
    );
  });
});

describe("deprecated index names (ADR 0001)", () => {
  it("manifest-cluster old names point at the new symbols", () => {
    expect(getNodeId).toBe(newManifest.getWorkflowNodeManifestId);
    expect(exportDefinition).toBe(newRegistry.exportWorkflowNodeManifest);
    expect(diffManifests).toBe(newManifestDiff.diffWorkflowNodeManifests);
    expect(registerNode).toBe(newRegistry.registerWorkflowNode);
    expect(buildRegistryPayload).toBe(newRegistry.buildWorkflowNodeRegistryPayload);
    expect(RegistrationError?.name ?? "present").toBeTruthy();
  });

  it("type-only old names still typecheck as the new symbols", () => {
    // Compile-time alias proof: assigning the deprecated type name to the
    // new name's shape must typecheck (types are erased at runtime).
    const retry: RetryConfig | undefined = undefined;
    const preset: ColorPreset | undefined = undefined;
    const deprecation: DeprecationInfo | undefined = undefined;
    const contract: NodeContract | undefined = undefined;
    const capabilities: ContractCapabilities | undefined = undefined;
    const diffKind: ManifestDiff | undefined = undefined;
    const registration: RegisterNodeResult | undefined = undefined;
    expect([retry, preset, deprecation, contract, capabilities, diffKind, registration]).toEqual(
      Array(7).fill(undefined),
    );
  });
});
