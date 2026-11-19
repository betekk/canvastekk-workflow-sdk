import { describe, it, expect } from "vitest";
import { validateWorkflowDefinition } from "../src/workflow/validation.js";

describe("validate", () => {
  it("valid spec passes", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(true);
    expect(result.errors).toHaveLength(0);
    expect(result.orphans).toHaveLength(0);
    expect(result.deadEnds).toHaveLength(0);
  });

  it("missing start node → error", () => {
    const spec = {
      nodes: [
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain("Workflow must have a __start__ node");
  });

  it("multiple start nodes → error", () => {
    const spec = {
      nodes: [
        { id: "start1", slug: "__start__", name: "START", inputs: {} },
        { id: "start2", slug: "__start__", name: "START", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "start2", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain("Workflow must have exactly 1 __start__ node, found 2");
  });

  it("missing end node → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain("Workflow must have at least 1 __end__ node");
  });

  it("duplicate node IDs → error", () => {
    const spec = {
      nodes: [
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "n1", slug: "node-v2", inputs: {} },
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("Duplicate node ID"))).toBe(true);
  });

  it("edge references non-existent node → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "ghost", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("non-existent from_node") || e.includes("non-existent to_node"))).toBe(true);
  });

  it("cycle → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "n2", slug: "node-v2", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "n2", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e3", from_node: "n2", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e4", from_node: "n2", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("cycle"))).toBe(true);
  });

  it("orphan nodes detected", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "orphan", slug: "node-orphan", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.orphans).toContain("orphan");
    expect(result.errors.some((e) => e.includes("Orphan node(s)"))).toBe(true);
  });

  it("dead-end nodes detected", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end1", slug: "__end__", name: "END", inputs: {} },
        { id: "end2", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "n1", to_node: "end1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.orphans).toContain("end2");
    expect(result.errors.some((e) => e.includes("Orphan node(s)"))).toBe(true);
  });

  it("start node with incoming edges → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "n1", to_node: "start", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "start", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("__start__ node must have no incoming edges"))).toBe(true);
  });

  it("end node with outgoing edges → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e2", from_node: "end", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("__end__ node") && e.includes("must have no outgoing edges"))).toBe(true);
  });

  it("duplicate edge IDs → error", () => {
    const spec = {
      nodes: [
        { id: "start", slug: "__start__", name: "START", inputs: {} },
        { id: "n1", slug: "node-v1", inputs: {} },
        { id: "end", slug: "__end__", name: "END", inputs: {} },
      ],
      edges: [
        { id: "e1", from_node: "start", to_node: "n1", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
        { id: "e1", from_node: "n1", to_node: "end", from_output: "", to_input: "", edge_type: "default" as const, condition: null },
      ],
      metadata: {},
    };
    const result = validateWorkflowDefinition(spec);
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("Duplicate edge ID"))).toBe(true);
  });
});
