/**
 * Metric data for a single node execution.
 */
export interface NodeExecutionMetric {
  runId: string;
  nodeId: string;
  nodeName: string;
  status: string;
  durationMs: number;
  errorType?: string;
  errorCode?: string;
  tokenUsage: number;
  timestamp: number;
}

/**
 * Creates an execution metric with current timestamp.
 * @param opts - Metric data without timestamp
 * @returns Complete execution metric
 */
export function createNodeExecutionMetric(opts: Omit<NodeExecutionMetric, "timestamp">): NodeExecutionMetric {
  return { ...opts, timestamp: Date.now() / 1000 };
}

/**
 * Converts an execution metric to a dictionary.
 * @param metric - Execution metric to convert
 * @returns Dictionary with snake_case keys
 */
export function nodeExecutionMetricToDict(metric: NodeExecutionMetric): Record<string, unknown> {
  return {
    run_id: metric.runId,
    node_id: metric.nodeId,
    node_name: metric.nodeName,
    status: metric.status,
    duration_ms: metric.durationMs,
    error_type: metric.errorType ?? null,
    error_code: metric.errorCode ?? null,
    token_usage: metric.tokenUsage,
    timestamp: metric.timestamp,
  };
}

/**
 * Collects and aggregates execution metrics.
 */
export class NodeExecutionMetricsCollector {
  private _metrics: NodeExecutionMetric[] = [];
  private _maxRecords: number;

  /**
   * Creates a new metrics collector.
   * @param maxRecords - Maximum number of metrics to store (default: 10000)
   */
  constructor(maxRecords = 10000) {
    this._maxRecords = maxRecords;
  }

  /**
   * Records an execution metric.
   * @param metric - Execution metric to record
   */
  record(metric: NodeExecutionMetric): void {
    this._metrics.push(metric);
    if (this._metrics.length > this._maxRecords) {
      this._metrics = this._metrics.slice(-this._maxRecords);
    }
  }

  /**
   * Gets summary statistics for recorded metrics.
   * @param lastN - Only include last N metrics (optional)
   * @returns Summary statistics dictionary
   */
  getSummary(lastN?: number): Record<string, unknown> {
    const metrics = lastN ? this._metrics.slice(-lastN) : this._metrics;
    if (metrics.length === 0) {
      return { total_executions: 0 };
    }

    const passCount = metrics.filter((m) => m.status === "pass").length;
    const failCount = metrics.filter((m) => m.status === "fail").length;
    const durations = metrics.map((m) => m.durationMs);

    return {
      total_executions: metrics.length,
      pass_count: passCount,
      fail_count: failCount,
      success_rate: passCount / metrics.length,
      avg_duration_ms: durations.reduce((a, b) => a + b, 0) / durations.length,
      min_duration_ms: durations.reduce((a, b) => Math.min(a, b)),
      max_duration_ms: durations.reduce((a, b) => Math.max(a, b)),
      total_token_usage: metrics.reduce((sum, m) => sum + m.tokenUsage, 0),
    };
  }

  /**
   * Clears all collected metrics.
   */
  clear(): void {
    this._metrics = [];
  }
}
