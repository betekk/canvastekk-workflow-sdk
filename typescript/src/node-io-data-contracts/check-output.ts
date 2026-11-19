/**
 * Check-node output-contract builder (DA-3359).
 *
 * Opt-in module surface for compliance-check nodes. `app.ts` / `base-node.ts`
 * never import this module (pinned by tests/contracts-check-output.test.ts) —
 * nothing here is on the core execution path. Mirrors the Python
 * `contracts.build_check_output_schema` exactly (same JSON Schema output).
 */

export const DEFAULT_CHECK_VERDICTS: readonly string[] = ["PASS", "FAIL", "NOT_EVALUABLE"];

export interface CheckOutputOptions {
  /** When true, sets additionalProperties:false on the root and on `result`. */
  closed?: boolean;
}

export function buildCheckOutputSchema(
  verdicts: readonly string[] = DEFAULT_CHECK_VERDICTS,
  resultDescription = "Check result summary.",
  opts: CheckOutputOptions = {},
): Record<string, unknown> {
  const vocab = [...verdicts];
  const closed = opts.closed === true;

  const result: Record<string, unknown> = {
    type: "object",
    description: resultDescription,
    properties: {
      verdict: { type: "string", enum: vocab },
    },
    required: ["verdict"],
  };
  if (closed) {
    result.additionalProperties = false;
  }

  const root: Record<string, unknown> = {
    type: "object",
    properties: {
      verdict: {
        type: "string",
        enum: vocab,
        description: "Headline verdict for the subject, emitted verbatim from the check.",
      },
      verdict_counts: {
        type: "object",
        additionalProperties: { type: "integer", minimum: 0 },
        description: "Count of measured subjects per verdict; absent keys mean zero.",
      },
      result,
      error: {
        type: ["object", "null"],
        description:
          "Error detail when the node failed before producing a verdict; null (or absent) on a normal run.",
      },
    },
    required: ["verdict", "result"],
  };
  if (closed) {
    root.additionalProperties = false;
  }
  return root;
}

export function validateVerdictFields(
  payload: Record<string, unknown>,
  verdicts: readonly string[] = DEFAULT_CHECK_VERDICTS,
): void {
  const vocab = new Set(verdicts);
  const headline = payload.verdict;
  if (typeof headline !== "string" || !vocab.has(headline)) {
    throw new Error(
      `verdict ${String(headline)} is not in the check vocabulary ${JSON.stringify([...verdicts])}`,
    );
  }
  const result = payload.result;
  if (typeof result !== "object" || result === null) {
    throw new Error("check payload must carry a 'result' object");
  }
  const resultVerdict = (result as Record<string, unknown>).verdict;
  if (typeof resultVerdict !== "string" || !vocab.has(resultVerdict)) {
    throw new Error(
      `result.verdict ${String(resultVerdict)} is not in the check vocabulary ${JSON.stringify([...verdicts])}`,
    );
  }
}
