
/** Log level severity. */
export type LogLevel = "debug" | "info" | "warn" | "error" | "fatal";

/** Structured log entry. */
export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  [key: string]: unknown;
}

/** Formatter input structure. */
interface FormatInput {
  level: string;
  logger: string;
  message: string;
  exception?: string;
  [key: string]: unknown;
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
  fatal: 50,
};

/**
 * Formats log entries as structured JSON.
 */
export class StructuredJsonFormatter {
  /**
   * Formats a log entry as JSON.
   * @param entry - Log entry to format
   * @returns JSON string
   */
  format(entry: FormatInput): string {
    const obj: Record<string, unknown> = {
      timestamp: new Date().toISOString(),
      level: entry.level,
      logger: entry.logger,
      message: entry.message,
    };
    for (const [k, v] of Object.entries(entry)) {
      if (k !== "level" && k !== "logger" && k !== "message" && k !== "timestamp") {
        obj[k] = v;
      }
    }
    return JSON.stringify(obj, (_, v) => (typeof v === "bigint" ? v.toString() : v));
  }
}

/**
 * Formats log entries as human-readable text.
 */
export class HumanReadableFormatter {
  /**
   * Formats a log entry as human-readable text.
   * @param entry - Log entry to format
   * @returns Formatted text string
   */
  format(entry: FormatInput): string {
    const ts = new Date().toISOString().replace("T", " ").substring(0, 19);
    let base = `${ts} [${entry.level.toUpperCase().padStart(7)}] ${entry.logger}: ${entry.message}`;
    const runId = entry.run_id as string | undefined;
    if (runId) {
      base = `[${runId.substring(0, 8)}] ${base}`;
    }
    if (entry.exception) {
      base += "\n" + entry.exception;
    }
    return base;
  }
}

/** Logger interface with standard log levels. */
export type SdkLogger = {
  debug(message: string, extra?: Record<string, unknown>): void;
  info(message: string, extra?: Record<string, unknown>): void;
  warn(message: string, extra?: Record<string, unknown>): void;
  error(message: string, extra?: Record<string, unknown>): void;
};

/** Internal logger configuration. */
interface LoggerConfig {
  name: string;
  formatter: StructuredJsonFormatter | HumanReadableFormatter;
  minLevel: number;
}

const loggers = new Map<string, LoggerConfig>();

/** Reads CANVASTEKK_LOG_LEVEL from env, defaulting to "info". Maps WARNING→warn, CRITICAL→fatal. */
function getEnvLogLevel(): LogLevel {
  const raw = (process.env.CANVASTEKK_LOG_LEVEL ?? "INFO").toUpperCase();
  const map: Record<string, LogLevel> = {
    DEBUG: "debug",
    INFO: "info",
    WARNING: "warn",
    WARN: "warn",
    ERROR: "error",
    CRITICAL: "fatal",
  };
  return map[raw] ?? "info";
}

/** Reads CANVASTEKK_LOG_FORMAT from env, defaulting to "json". */
function getEnvLogFormat(): string {
  // DA-3359: console output is the default; "json" opts into one-line JSON.
  const raw = (process.env.CANVASTEKK_LOG_FORMAT ?? "console").toLowerCase();
  return raw === "json" ? "json" : "console";
}

/**
 * Configures global SDK logging settings.
 * @param opts - Logging options including level and format
 */
export function configureLogging(opts?: { level?: LogLevel; format?: string }): void {
  const level = opts?.level ?? getEnvLogLevel();
  const fmt = opts?.format ?? getEnvLogFormat();
  const formatter = fmt === "json" ? new StructuredJsonFormatter() : new HumanReadableFormatter();
  const minLevel = LOG_LEVELS[level] ?? LOG_LEVELS.info;

  loggers.set("canvastekk_workflow_sdk", { name: "canvastekk_workflow_sdk", formatter, minLevel });
  loggers.set("node.", { name: "node.", formatter, minLevel });
}

/**
 * Writes a log entry if the level meets the minimum threshold.
 *
 * Errors and above go to stderr; everything else goes to stdout.
 *
 * @param config - Logger configuration with formatter and min level
 * @param level - Log level for this entry
 * @param message - Log message
 * @param extra - Additional structured data to include
 */
function writeLog(
  config: LoggerConfig,
  level: LogLevel,
  message: string,
  extra?: Record<string, unknown>,
): void {
  const levelNum = LOG_LEVELS[level];
  if (levelNum < config.minLevel) return;

  const entry: Record<string, unknown> = {
    level,
    logger: config.name,
    message,
    ...extra,
  };
  const output = config.formatter.format(entry as FormatInput);
  if (levelNum >= LOG_LEVELS.error) {
    process.stderr.write(output + "\n");
  } else {
    process.stdout.write(output + "\n");
  }
}

/**
 * Gets or creates a logger config for the given name.
 *
 * Inherits formatter and min level from the parent config
 * (either "node.*" or "canvastekk_workflow_sdk").
 *
 * @param name - Logger name (e.g., "node.my-node")
 * @returns Logger configuration
 */
function getOrCreateConfig(name: string): LoggerConfig {
  let config = loggers.get(name);
  if (!config) {
    const prefix = name.startsWith("node.") ? "node." : "canvastekk_workflow_sdk";
    const parent = loggers.get(prefix);
    if (parent) {
      config = { ...parent, name };
      loggers.set(name, config);
    } else {
      const level = getEnvLogLevel();
      const fmt = getEnvLogFormat();
      config = {
        name,
        formatter: fmt === "text" ? new HumanReadableFormatter() : new StructuredJsonFormatter(),
        minLevel: LOG_LEVELS[level] ?? LOG_LEVELS.info,
      };
      loggers.set(name, config);
    }
  }
  return config;
}

/**
 * Creates a new named logger instance.
 * @param name - Logger name (e.g., "node.my-node")
 * @returns Logger instance
 */
export function createLogger(name: string): SdkLogger {
  return {
    debug(message: string, extra?: Record<string, unknown>) {
      writeLog(getOrCreateConfig(name), "debug", message, extra);
    },
    info(message: string, extra?: Record<string, unknown>) {
      writeLog(getOrCreateConfig(name), "info", message, extra);
    },
    warn(message: string, extra?: Record<string, unknown>) {
      writeLog(getOrCreateConfig(name), "warn", message, extra);
    },
    error(message: string, extra?: Record<string, unknown>) {
      writeLog(getOrCreateConfig(name), "error", message, extra);
    },
  };
}

/**
 * Creates a logger for a specific node.
 * @param nodeId - Node ID
 * @param _runId - Run ID (unused, for API compatibility)
 * @returns Logger instance
 */
export function getNodeLogger(nodeId: string, _runId?: string): SdkLogger {
  return createLogger(`node.${nodeId}`);
}
