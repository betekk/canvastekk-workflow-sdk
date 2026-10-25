import { describe, it, expect } from "vitest";
import { join } from "node:path";
import { WorkflowBuilder } from "../src/workflow/builder.js";
import { WorkflowRunner } from "../src/workflow/runner.js";
import { InProcessExecutor } from "../src/workflow/executor.js";

describe("WorkflowRunner", () => {
  it("sequential execution (start → node → end)", async () => {
    const executor = new InProcessExecutor();
    executor.register("echo-v1.0.0", {
      execute: async (inputs, _ctx) => ({ result: inputs.message }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("process", { slug: "echo-v1.0.0" })
      .addEnd("end")
      .connect("start", "process")
      .connect("process", "end")
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec, { message: "hello" });

    expect(result.status).toBe("completed");
    expect(result.node_results).toHaveLength(3);
    expect(result.node_results[1].status).toBe("completed");
  });

  it("parallel execution within a level", async () => {
    const executor = new InProcessExecutor();
    executor.register("node-a-v1", {
      execute: async (_inputs, _ctx) => ({ value: "A" }),
    });
    executor.register("node-b-v1", {
      execute: async (_inputs, _ctx) => ({ value: "B" }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("a", { slug: "node-a-v1" })
      .addNode("b", { slug: "node-b-v1" })
      .addEnd("end")
      .connect("start", "a")
      .connect("start", "b")
      .connect("a", "end")
      .connect("b", "end")
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.node_results.filter((r) => r.status === "completed")).toHaveLength(4);
  });

  it("fail_fast stops on first failure", async () => {
    const executor = new InProcessExecutor();
    executor.register("fail-v1", {
      execute: async () => { throw new Error(" intentional fail"); },
    });
    executor.register("success-v1", {
      execute: async () => ({ ok: true }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("fail", { slug: "fail-v1" })
      .addNode("success", { slug: "success-v1" })
      .addEnd("end")
      .connect("start", "fail")
      .connect("start", "success")
      .connect("fail", "end")
      .connect("success", "end")
      .build();

    const runner = new WorkflowRunner(executor, { errorPolicy: "fail_fast" });
    const result = await runner.run(spec);

    expect(result.status).toBe("failed");
    expect(result.node_results.find((r) => r.node_id === "fail")?.status).toBe("failed");
    expect(result.node_results.some((r) => r.status === "failed")).toBe(true);
  });

  it("continue runs all levels even on failure", async () => {
    const executor = new InProcessExecutor();
    executor.register("fail-v1", {
      execute: async () => { throw new Error("fail"); },
    });
    executor.register("success-v1", {
      execute: async () => ({ ok: true }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("fail", { slug: "fail-v1" })
      .addNode("success", { slug: "success-v1" })
      .addEnd("end")
      .connect("start", "fail")
      .connect("fail", "success")
      .connect("success", "end")
      .build();

    const runner = new WorkflowRunner(executor, { errorPolicy: "continue" });
    const result = await runner.run(spec);

    expect(result.status).toBe("failed");
    expect(result.node_results.find((r) => r.node_id === "fail")?.status).toBe("failed");
    expect(result.node_results.find((r) => r.node_id === "success")?.status).toBe("skipped");
  });

  it("upstream failure marks downstream as skipped", async () => {
    const executor = new InProcessExecutor();
    executor.register("fail-v1", {
      execute: async () => { throw new Error("fail"); },
    });
    executor.register("next-v1", {
      execute: async () => ({ reached: true }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("fail", { slug: "fail-v1" })
      .addNode("next", { slug: "next-v1" })
      .addEnd("end")
      .connect("start", "fail")
      .connect("fail", "next")
      .connect("next", "end")
      .build();

    const runner = new WorkflowRunner(executor, { errorPolicy: "continue" });
    const result = await runner.run(spec);

    expect(result.status).toBe("failed");
    const nextRes = result.node_results.find((r) => r.node_id === "next");
    expect(nextRes?.status).toBe("skipped");
    expect(nextRes?.skipped_reason).toBe("upstream_failed");
  });

  it("Executor registration check (missing slug → failed)", async () => {
    const executor = new InProcessExecutor();

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("unknown", { slug: "unknown-v1" })
      .addEnd("end")
      .connect("start", "unknown")
      .connect("unknown", "end")
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec);

    expect(result.status).toBe("failed");
    const unknownRes = result.node_results.find((r) => r.node_id === "unknown");
    expect(unknownRes?.status).toBe("failed");
    expect(unknownRes?.error).toContain("No executor registered for slug 'unknown-v1'");
  });

  it("Auto-created temp dirs are cleaned up (cleanup: true)", async () => {
    const executor = new InProcessExecutor();
    executor.register("pass-v1", {
      execute: async (inputs, ctx) => ({ output: ctx.outputDir }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("n1", { slug: "pass-v1" })
      .addEnd("end")
      .connect("start", "n1", { fromOutput: "", toInput: "" })
      .connect("n1", "end", { fromOutput: "output", toInput: "dir" })
      .build();

    const runner = new WorkflowRunner(executor, { cleanup: true });
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.output_dir).toBe(null);

    const n1Res = result.node_results.find((r) => r.node_id === "n1");
    expect(n1Res?.outputs?.output).toMatch(/^\/tmp\/wf-runner-/);
  });

  it("Auto-created temp dirs are kept when cleanup: false", async () => {
    const executor = new InProcessExecutor();
    executor.register("pass-v1", {
      execute: async (inputs, ctx) => ({ output: ctx.outputDir }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("n1", { slug: "pass-v1" })
      .addEnd("end")
      .connect("start", "n1", { fromOutput: "", toInput: "" })
      .connect("n1", "end", { fromOutput: "output", toInput: "dir" })
      .build();

    const runner = new WorkflowRunner(executor, { cleanup: false });
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.output_dir).toMatch(/^\/tmp\/wf-runner-/);
    expect(result.node_results.find((r) => r.node_id === "n1")?.outputs?.output).toBe(join(result.output_dir, "n1"));
  });

  it("User-supplied outputDir is NOT cleaned up", async () => {
    const executor = new InProcessExecutor();
    executor.register("pass-v1", {
      execute: async (inputs, ctx) => ({ output: ctx.outputDir }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("n1", { slug: "pass-v1" })
      .addEnd("end")
      .connect("start", "n1", { fromOutput: "", toInput: "" })
      .connect("n1", "end", { fromOutput: "output", toInput: "dir" })
      .build();

    const customDir = "/tmp/custom-runner-dir-test";
    const runner = new WorkflowRunner(executor, { outputDir: customDir, cleanup: true });
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.output_dir).toBe(customDir);
  });

  it("Shared outputDir enables file-passing between nodes", async () => {
    const { writeFileSync, readFileSync, mkdirSync } = await import("node:fs");
    const executor = new InProcessExecutor();
    executor.register("producer-v1", {
      execute: async (inputs, ctx) => {
        mkdirSync(ctx.outputDir, { recursive: true });
        const path = ctx.outputPath("shared.txt");
        writeFileSync(path, "shared content");
        return { sharedFile: path };
      },
    });
    executor.register("consumer-v1", {
      execute: async (inputs) => {
        const content = readFileSync(inputs.sharedFile as string, "utf-8");
        return { consumed: content };
      },
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("producer", { slug: "producer-v1" })
      .addNode("consumer", { slug: "consumer-v1" })
      .addEnd("end")
      .connect("start", "producer")
      .connect("producer", "consumer")
      .connect("consumer", "end")
      .build();

    const customDir = "/tmp/shared-file-test";
    const runner = new WorkflowRunner(executor, { outputDir: customDir });
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.final_outputs).toEqual({ consumed: "shared content" });
  });

  it("NodeResult includes correct metadata (nodeId, slug, status, outputs, durationMs, error, skippedReason)", async () => {
    const executor = new InProcessExecutor();
    executor.register("success-v1", {
      execute: async () => ({ ok: true }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("n1", { slug: "success-v1" })
      .addEnd("end")
      .connect("start", "n1")
      .connect("n1", "end")
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec);

    const n1Res = result.node_results.find((r) => r.node_id === "n1");
    expect(n1Res).toBeDefined();
    expect(n1Res?.node_id).toBe("n1");
    expect(n1Res?.slug).toBe("success-v1");
    expect(n1Res?.status).toBe("completed");
    expect(n1Res?.outputs).toEqual({ ok: true });
    expect(n1Res?.duration_ms).toBeGreaterThanOrEqual(0);
  });

  it("Multiple end nodes aggregate outputs from all end nodes", async () => {
    const executor = new InProcessExecutor();
    executor.register("produce-a", { execute: async () => ({ a: 1 }) });
    executor.register("produce-b", { execute: async () => ({ b: 2 }) });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("n1", { slug: "produce-a" })
      .addNode("n2", { slug: "produce-b" })
      .addEnd("end1")
      .addEnd("end2")
      .connect("start", "n1")
      .connect("start", "n2")
      .connect("n1", "end1", { fromOutput: "", toInput: "" })
      .connect("n2", "end2", { fromOutput: "", toInput: "" })
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec);

    expect(result.status).toBe("completed");
    expect(result.final_outputs).toEqual({ a: 1, b: 2 });
  });

  it("Handles nodeOutputs injection from initial inputs", async () => {
    const executor = new InProcessExecutor();
    executor.register("read-v1", {
      execute: async (inputs, _ctx) => ({ value: inputs.inputKey }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("reader", { slug: "read-v1" })
      .addEnd("end")
      .connect("start", "reader")
      .connect("reader", "end")
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec, { inputKey: "injected" });

    expect(result.status).toBe("completed");
  });
});
describe("WorkflowRunner start-input seeding (DA-1711)", () => {
  it("seeded run inputs reach downstream nodes via wired edges", async () => {
    const executor = new InProcessExecutor();
    executor.register("echo-v1", {
      execute: async (inputs) => ({ message: inputs.pointCloud }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("echo", { slug: "echo-v1" })
      .addEnd("end")
      .connect("start", "echo", { fromOutput: "point_cloud", toInput: "pointCloud" })
      .connect("echo", "end", { fromOutput: "message", toInput: "result" })
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec, { point_cloud: "/tmp/scan.ply" });

    expect(result.status).toBe("completed");
    expect(result.final_outputs).toEqual({ result: "/tmp/scan.ply" });
  });

  it("mis-wired edge fails one node instead of crashing run()", async () => {
    const executor = new InProcessExecutor();
    executor.register("echo-v1", {
      execute: async (inputs) => ({ message: inputs.message ?? "none" }),
    });

    const spec = await new WorkflowBuilder()
      .addStart("start")
      .addNode("echo", { slug: "echo-v1" })
      .addEnd("end")
      .connect("start", "echo", { fromOutput: "missing_key", toInput: "message" })
      .connect("echo", "end", { fromOutput: "message", toInput: "result" })
      .build();

    const runner = new WorkflowRunner(executor);
    const result = await runner.run(spec, { other: "x" });

    expect(result.status).toBe("failed");
    const echoResult = result.node_results.find((r) => r.node_id === "echo");
    expect(echoResult?.status).toBe("failed");
    expect(echoResult?.error).toContain("Input resolution failed");
  });
});
