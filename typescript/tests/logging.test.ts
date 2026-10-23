import { describe, it, expect, vi } from "vitest";
import {
  StructuredJsonFormatter,
  HumanReadableFormatter,
  configureLogging,
  getNodeLogger,
  createLogger,
} from "../src/logging.js";

describe("StructuredJsonFormatter", () => {
  it("formats a log entry as JSON", () => {
    const fmt = new StructuredJsonFormatter();
    const output = fmt.format({
      level: "info",
      logger: "node.echo-1",
      message: "hello",
    });
    const parsed = JSON.parse(output);
    expect(parsed.level).toBe("info");
    expect(parsed.logger).toBe("node.echo-1");
    expect(parsed.message).toBe("hello");
    expect(parsed.timestamp).toBeDefined();
  });

  it("includes extra fields", () => {
    const fmt = new StructuredJsonFormatter();
    const output = fmt.format({
      level: "info",
      logger: "test",
      message: "msg",
      run_id: "run-123",
      node_id: "node-1",
    });
    const parsed = JSON.parse(output);
    expect(parsed.run_id).toBe("run-123");
    expect(parsed.node_id).toBe("node-1");
  });
});

describe("HumanReadableFormatter", () => {
  it("formats a readable log line", () => {
    const fmt = new HumanReadableFormatter();
    const output = fmt.format({
      level: "info",
      logger: "test",
      message: "hello",
    });
    expect(output).toContain("INFO");
    expect(output).toContain("test: hello");
  });

  it("includes run_id prefix when present", () => {
    const fmt = new HumanReadableFormatter();
    const output = fmt.format({
      level: "info",
      logger: "test",
      message: "msg",
      run_id: "run-abcdef123456",
    });
    expect(output).toContain("[run-abcd");
  });
});

describe("configureLogging", () => {
  it("does not throw", () => {
    expect(() => configureLogging()).not.toThrow();
    expect(() => configureLogging({ level: "debug", format: "text" })).not.toThrow();
  });
});

describe("getNodeLogger", () => {
  it("returns a logger with node prefix", () => {
    configureLogging();
    const logger = getNodeLogger("echo-1");
    expect(logger).toBeDefined();
    expect(typeof logger.info).toBe("function");
    expect(typeof logger.error).toBe("function");
    expect(typeof logger.debug).toBe("function");
    expect(typeof logger.warn).toBe("function");
  });
});

describe("createLogger", () => {
  it("creates a named logger", () => {
    configureLogging();
    const logger = createLogger("test-module");
    expect(logger).toBeDefined();
    const spy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
    logger.info("test message");
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
