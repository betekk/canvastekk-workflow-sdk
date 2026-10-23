/**
 * Manifest diff classification (DA-1955).
 *
 * Mirrors the engine's detect_breaking_changes signal-for-signal: new
 * required inputs and removed outputs are the only breaking signals. No
 * allOf/oneOf resolution by design — engine parity over cleverness.
 */

/** Result of comparing two node manifests. */
export interface ManifestDiff {
  breaking: boolean;
  breakingChanges: string[];
  nonBreakingChanges: string[];
  errors: string[];
  oldVersion: string | null;
  newVersion: string | null;
  versionBump: "major" | "minor" | "patch" | null;
}

const HANDLED_KEYS: Set<string> = new Set(["input_schema", "output_schema", "slug", "version", "id"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function versionTuple(version: string): [number, number, number] {
  const parts = version.split(".");
  if (parts.length !== 3 || !parts.every((p) => /^\d+$/.test(p))) {
    throw new Error(`version must be strict MAJOR.MINOR.PATCH, got '${version}'`);
  }
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

function compareVersionTuples(
  a: [number, number, number],
  b: [number, number, number],
): number {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

function classifyBump(oldVersion: string, newVersion: string): "major" | "minor" | "patch" | null {
  const [oldMajor, oldMinor, oldPatch] = versionTuple(oldVersion);
  const [newMajor, newMinor, newPatch] = versionTuple(newVersion);
  if (newMajor !== oldMajor) return "major";
  if (newMinor !== oldMinor) return "minor";
  if (newPatch !== oldPatch) return "patch";
  return null;
}

function schemaBlock(manifest: Record<string, unknown>, key: string): Record<string, unknown> {
  const block = manifest[key];
  return isRecord(block) ? block : {};
}

function propertiesKeys(schema: Record<string, unknown>): Set<string> {
  const properties = schema["properties"];
  if (!isRecord(properties)) return new Set();
  return new Set(Object.keys(properties));
}

function requiredSet(schema: Record<string, unknown>): Set<string> {
  const required = schema["required"];
  if (!Array.isArray(required)) return new Set();
  return new Set(required.filter((r): r is string => typeof r === "string"));
}

/**
 * Classify changes between two exported manifest JSON objects.
 *
 * @param oldManifest - Previous manifest (parsed JSON object)
 * @param newManifest - New manifest (parsed JSON object)
 * @returns Diff result with breaking/non-breaking changes and errors
 */
export function diffManifests(
  oldManifest: unknown,
  newManifest: unknown,
): ManifestDiff {
  if (!isRecord(oldManifest) || !isRecord(newManifest)) {
    throw new TypeError("diffManifests expects two JSON objects");
  }

  const diff: ManifestDiff = {
    breaking: false,
    breakingChanges: [],
    nonBreakingChanges: [],
    errors: [],
    oldVersion: null,
    newVersion: null,
    versionBump: null,
  };

  const oldSlug = oldManifest["slug"] ?? oldManifest["name"];
  const newSlug = newManifest["slug"] ?? newManifest["name"];
  if (typeof oldSlug === "string" && typeof newSlug === "string" && oldSlug !== newSlug) {
    diff.errors.push(`slug mismatch: '${oldSlug}' -> '${newSlug}' (publish a new node, not a new version)`);
  }

  const oldVersion = oldManifest["version"];
  const newVersion = newManifest["version"];
  let versionsParsed = false;
  if (typeof oldVersion !== "string" || typeof newVersion !== "string") {
    diff.errors.push("both manifests must carry a 'version' field");
  } else {
    diff.oldVersion = oldVersion;
    diff.newVersion = newVersion;
    try {
      diff.versionBump = classifyBump(oldVersion, newVersion);
      versionsParsed = true;
      if (compareVersionTuples(versionTuple(oldVersion), versionTuple(newVersion)) > 0) {
        diff.errors.push(
          `version downgrade: '${oldVersion}' -> '${newVersion}' (publish a higher semver)`,
        );
      }
    } catch (error) {
      diff.errors.push(error instanceof Error ? error.message : String(error));
    }
  }

  const oldInput = schemaBlock(oldManifest, "input_schema");
  const newInput = schemaBlock(newManifest, "input_schema");
  const oldRequired = requiredSet(oldInput);
  const newRequired = requiredSet(newInput);
  for (const prop of newRequired) {
    if (!oldRequired.has(prop)) {
      diff.breakingChanges.push(`new required input '${prop}'`);
    }
  }

  const oldInputProps = propertiesKeys(oldInput);
  const newInputProps = propertiesKeys(newInput);
  for (const prop of newInputProps) {
    if (!oldInputProps.has(prop) && !newRequired.has(prop)) {
      diff.nonBreakingChanges.push(`new optional input '${prop}'`);
    }
  }

  const oldOutputProps = propertiesKeys(schemaBlock(oldManifest, "output_schema"));
  const newOutputProps = propertiesKeys(schemaBlock(newManifest, "output_schema"));
  for (const prop of oldOutputProps) {
    if (!newOutputProps.has(prop)) {
      diff.breakingChanges.push(`removed output '${prop}'`);
    }
  }
  for (const prop of newOutputProps) {
    if (!oldOutputProps.has(prop)) {
      diff.nonBreakingChanges.push(`new output '${prop}'`);
    }
  }

  const metadataKeys = new Set([...Object.keys(oldManifest), ...Object.keys(newManifest)]);
  for (const key of metadataKeys) {
    if (HANDLED_KEYS.has(key)) continue;
    if (JSON.stringify(oldManifest[key]) !== JSON.stringify(newManifest[key])) {
      diff.nonBreakingChanges.push(`metadata '${key}' changed`);
    }
  }

  diff.breaking = diff.breakingChanges.length > 0;

  if (
    versionsParsed &&
    diff.versionBump === null &&
    (diff.breakingChanges.length > 0 || diff.nonBreakingChanges.length > 0)
  ) {
    diff.errors.push(
      `same version '${String(oldVersion)}' but the manifest changed; publish a higher semver`,
    );
  }
  if (diff.breaking && diff.versionBump !== "major") {
    diff.errors.push(
      `breaking changes require a MAJOR version bump (got '${String(oldVersion)}' -> '${String(newVersion)}')`,
    );
  }

  return diff;
}
