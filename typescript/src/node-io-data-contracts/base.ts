import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

/** Current contract version. */
export const NODE_IO_DATA_CONTRACT_VERSION = "1.0.0";

/** Base data for all contract types. */
export interface NodeIoDataContractData {
  contract_version: string;
  source_node?: string | null;
  source_file?: string | null;
  [key: string]: unknown;
}

/**
 * Saves data to a JSON file.
 * @param data - Data to save
 * @param path - File path
 */
export function saveJson(data: Record<string, unknown>, path: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(data, null, 2));
}

/**
 * Loads data from a JSON file.
 * @param path - File path
 * @returns Parsed data
 */
export function loadJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf-8"));
}
