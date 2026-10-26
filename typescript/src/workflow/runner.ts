import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { WorkflowDefinitionSpec } from "./models.js";
import type { NodeExecutor } from "./executor.js";
import { computeLevels } from "./level.js";
import { resolveInputs } from "./resolver.js";
import { CONTROL_FLOW_HANDLERS } from "./control-flow.js";
import { ExecutionContext } from "../context.js";

export type ErrorPolicy = "fail_fast" | "continue";

export interface NodeResult {
  node_id: string;
  slug: string;
  status: string;
  outputs?: Record<string, unknown> | null;
  duration_ms: number;
  error?: string | null;
  skipped_reason?: string | null;
}

export interface WorkflowRunResult {
  status: string;
  final_outputs: Record<string, unknown>;
  node_results: NodeResult[];
  duration_ms: number;
  output_dir: string | null;
}

/**
 * Executes workflows locally using a node executor.
 */
export class WorkflowRunner {
  private _executor: NodeExecutor;
  private _errorPolicy: ErrorPolicy;
  private _outputDir: string | null;
  private _cleanup: boolean;
  private _maxConcurrency: number;

  /**
   * Creates a new workflow runner.
   * @param executor - Node executor for running individual nodes
   * @param opts - Runner options
   */
  constructor(
    executor: NodeExecutor,
    opts?: {
      errorPolicy?: ErrorPolicy;
      outputDir?: string;
      cleanup?: boolean;
      maxConcurrency?: number;
    },
  ) {
    this._executor = executor;
    this._errorPolicy = opts?.errorPolicy ?? "fail_fast";
    this._outputDir = opts?.outputDir ?? null;
    this._cleanup = opts?.cleanup ?? true;
    this._maxConcurrency = opts?.maxConcurrency ?? 8;
  }

  /** Runs executor.execute under the per-level concurrency cap:
   * tasks are gathered and awaited in bounded chunks of maxConcurrency. */
  private async gatherWithLimit<T>(tasks: Promise<T>[]): Promise<PromiseSettledResult<T>[]> {
    const results: PromiseSettledResult<T>[] = [];
    for (let i = 0; i < tasks.length; i += this._maxConcurrency) {
      const chunk = tasks.slice(i, i + this._maxConcurrency);
      const settled = await Promise.allSettled(chunk);
      results.push(...settled);
    }
    return results;
  }

  /**
   * Executes a workflow specification with the given inputs.
   *
   * Nodes are executed in topological order (levels). The output directory
   * is cleaned up automatically if created by the runner (when `cleanup: true`).
   *
   * @param spec - Workflow specification to execute
   * @param inputs - Initial inputs for the START node
   * @returns Execution result with status, outputs, and node results
   */
  async run(
    spec: WorkflowDefinitionSpec,
    inputs?: Record<string, unknown>,
  ): Promise<WorkflowRunResult> {
    const startTime = performance.now();
    const nodeMap = new Map(spec.nodes.map((n) => [n.id, n]));
    const nodeOutputs: Record<string, Record<string, unknown>> = {};
    const seededOutputs = new Map<string, Record<string, unknown>>();
    const node_results: NodeResult[] = [];
    const failedNodes = new Set<string>();

    let runOutputDir: string;
    let autoCreated = false;

    if (this._outputDir) {
      runOutputDir = this._outputDir;
    } else {
      runOutputDir = mkdtempSync(join(tmpdir(), "wf-runner-"));
      autoCreated = true;
    }

    let status: string;
    let final_outputs: Record<string, unknown>;
    let duration_ms: number;
    let result_output_dir: string | null;

    try {
      const startNodes = spec.nodes.filter((n) => n.slug === "__start__");
      if (startNodes.length > 0) {
        seededOutputs.set(startNodes[0].id, { ...(inputs ?? {}) });
      }

      const levels = computeLevels(spec);

      for (const level of levels) {
        const controlIds: string[] = [];
        const userIds: string[] = [];

        for (const nid of level) {
          const slug = nodeMap.get(nid)!.slug;
          if (slug && slug in CONTROL_FLOW_HANDLERS) {
            controlIds.push(nid);
          } else {
            userIds.push(nid);
          }
        }

        for (const nid of controlIds) {
          const node = nodeMap.get(nid)!;
          const slug = node.slug!;
          const handler = CONTROL_FLOW_HANDLERS[slug];
          let resolved: Record<string, unknown>;
          try {
            resolved = resolveInputs(nid, spec, nodeOutputs);
          } catch (exc) {
            failedNodes.add(nid);
            node_results.push({
              node_id: nid,
              slug,
              status: "failed",
              error: `Input resolution failed: ${exc}`,
              duration_ms: 0,
            });
            continue;
          }
          if (slug === "__start__" && seededOutputs.has(nid)) {
            resolved = { ...resolved, ...seededOutputs.get(nid) };
          }
          const context = new ExecutionContext({ runId: "local", nodeId: nid, outputDir: join(runOutputDir, nid) });
          const t0 = performance.now();
          try {
            const outputs = handler(resolved, context);
            nodeOutputs[nid] = outputs;
            node_results.push({
              node_id: nid,
              slug,
              status: "completed",
              outputs,
              duration_ms: Math.round(performance.now() - t0),
            });
          } catch (exc) {
            failedNodes.add(nid);
            node_results.push({
              node_id: nid,
              slug,
              status: "failed",
              duration_ms: Math.round(performance.now() - t0),
              error: String(exc),
            });
          }
        }

        const tasks: Promise<Record<string, unknown>>[] = [];
        const taskNodeIds: string[] = [];

        for (const nid of userIds) {
          const upstreamFailed = spec.edges.some(
            (e) => e.to_node === nid && failedNodes.has(e.from_node),
          );
          if (upstreamFailed || failedNodes.has(nid)) {
            const node = nodeMap.get(nid)!;
            node_results.push({
              node_id: nid,
              slug: node.slug ?? "",
              status: "skipped",
              skipped_reason: "upstream_failed",
              duration_ms: 0,
            });
            failedNodes.add(nid);
            continue;
          }

          const node = nodeMap.get(nid)!;
          const slug = node.slug;
          if (!slug || !this._executor.has(slug)) {
            node_results.push({
              node_id: nid,
              slug: slug ?? "",
              status: "failed",
              error: slug ? `No executor registered for slug '${slug}'` : "Node has no slug",
              duration_ms: 0,
            });
            failedNodes.add(nid);
            if (this._errorPolicy === "fail_fast") break;
            continue;
          }

          let resolved: Record<string, unknown>;
          try {
            resolved = resolveInputs(nid, spec, nodeOutputs);
          } catch (exc) {
            failedNodes.add(nid);
            node_results.push({
              node_id: nid,
              slug: slug ?? "",
              status: "failed",
              error: `Input resolution failed: ${exc}`,
              duration_ms: 0,
            });
            if (this._errorPolicy === "fail_fast") break;
            continue;
          }
          const context = new ExecutionContext({ runId: "local", nodeId: nid, outputDir: join(runOutputDir, nid) });
          tasks.push(this._executor.execute(slug, resolved, context));
          taskNodeIds.push(nid);
        }

        if (tasks.length > 0) {
          const results = await this.gatherWithLimit(tasks);
          for (let i = 0; i < results.length; i++) {
            const nid = taskNodeIds[i];
            const node = nodeMap.get(nid)!;
            const r = results[i];
            if (r.status === "rejected") {
              failedNodes.add(nid);
              node_results.push({
                node_id: nid,
                slug: node.slug ?? "",
                status: "failed",
                error: String(r.reason),
                duration_ms: 0,
              });
            } else {
              nodeOutputs[nid] = r.value;
              node_results.push({
                node_id: nid,
                slug: node.slug ?? "",
                status: "completed",
                outputs: r.value,
                duration_ms: 0,
              });
            }
          }
        }

        if (this._errorPolicy === "fail_fast" && failedNodes.size > 0) {
          break;
        }
      }

      final_outputs = {};
      for (const n of spec.nodes) {
        if (n.slug === "__end__" && n.id in nodeOutputs) {
          Object.assign(final_outputs, nodeOutputs[n.id]);
        }
      }

      duration_ms = Math.round(performance.now() - startTime);
      status = failedNodes.size === 0 ? "completed" : "failed";
    } finally {
      if (autoCreated && this._cleanup) {
        try {
          rmSync(runOutputDir, { recursive: true, force: true });
        } catch (e) {
          console.warn(`[workflow-runner] Failed to clean up temp dir '${runOutputDir}': ${e}`);
        }
        result_output_dir = null;
      } else {
        result_output_dir = runOutputDir;
      }
    }

    return {
      status,
      final_outputs,
      node_results,
      duration_ms,
      output_dir: result_output_dir,
    };
  }
}
