/**
 * Check verdict vocabulary (#283, epic betekk/canvastekk-tracker#4332).
 *
 * TypeScript mirror of the Python `check_verdict` module's vocabulary: the
 * `x-verdict` mark, the role / operator / verdict enums, the roll-up order
 * and the published `model_check.check` 1.0.0 body schema. The verdict step
 * itself (`judge`, `CheckNodeBase`) is Python-only for now: every check node
 * is a Python node. Guide: `docs/CHECK-VERDICT.md`.
 */

import { z } from "zod";

/** Input-schema extension that marks an input as a verdict variable. */
export const VERDICT_MARK = "x-verdict";

/** Result-file label of the check body. */
export const CHECK_RESULT_SCHEMA = "model_check.check";

/** Version of that body. */
export const CHECK_RESULT_SCHEMA_VERSION = "1.0.0";

/** What a marked input does for its check. */
export const TekkCheckRoleEnum = {
  LIMIT: "LIMIT",
  WARNING_LIMIT: "WARNING_LIMIT",
  TOLERANCE: "TOLERANCE",
  FILTER: "FILTER",
} as const;
export type TekkCheckRole = (typeof TekkCheckRoleEnum)[keyof typeof TekkCheckRoleEnum];

/** How a measured value is compared with a limit (passes when true). */
export const TekkCheckOperatorEnum = {
  GT: "GT",
  GTE: "GTE",
  LT: "LT",
  LTE: "LTE",
  EQ: "EQ",
  NE: "NE",
  IN: "IN",
  NOT_IN: "NOT_IN",
} as const;
export type TekkCheckOperator = (typeof TekkCheckOperatorEnum)[keyof typeof TekkCheckOperatorEnum];

/** Outcome of a measurement, a check and a run. */
export const TekkWorkflowRunVerdictEnum = {
  PASS: "PASS",
  WARNING: "WARNING",
  FAIL: "FAIL",
  NOT_EVALUABLE: "NOT_EVALUABLE",
} as const;
export type TekkWorkflowRunVerdict = (typeof TekkWorkflowRunVerdictEnum)[keyof typeof TekkWorkflowRunVerdictEnum];

/** How a measured value is rounded to the check's resolution. */
export const TekkCheckRoundingEnum = {
  HALF_UP: "HALF_UP",
  HALF_EVEN: "HALF_EVEN",
  FLOOR: "FLOOR",
  CEILING: "CEILING",
} as const;

/** Roll-up order, worst first (D90). */
export const VERDICT_PRECEDENCE: readonly TekkWorkflowRunVerdict[] = ["FAIL", "NOT_EVALUABLE", "WARNING", "PASS"];

/** Placeholders a `checks[key].statements` template may use. */
export const STATEMENT_PLACEHOLDERS: readonly string[] = ["element", "label", "actual", "unit", "limits", "broken", "reason"];

/**
 * Combine verdicts, worst first: FAIL > NOT_EVALUABLE > WARNING > PASS.
 *
 * @param verdicts - Verdict strings.
 * @returns The combined verdict; `NOT_EVALUABLE` when there are none.
 * @throws {Error} On an unknown verdict.
 */
export function rollupVerdicts(verdicts: Iterable<string>): TekkWorkflowRunVerdict {
  let best: number | null = null;
  for (const verdict of verdicts) {
    const rank = VERDICT_PRECEDENCE.indexOf(verdict as TekkWorkflowRunVerdict);
    if (rank < 0) throw new Error(`Unknown verdict ${JSON.stringify(verdict)}`);
    if (best === null || rank < best) best = rank;
  }
  return best === null ? "NOT_EVALUABLE" : VERDICT_PRECEDENCE[best];
}

/** One entry of a manifest's `checks` map (mirror of Python `CheckSpec`). */
export const CheckSpecSchema = z
  .object({
    label: z.string().min(1).max(200),
    unit: z.string().max(32).nullish(),
    resolution: z
      .object({
        step: z.number().positive(),
        rounding: z.enum(["HALF_UP", "HALF_EVEN", "FLOOR", "CEILING"]).default("HALF_UP"),
      })
      .strict()
      .nullish(),
    statements: z.record(z.enum(["PASS", "WARNING", "FAIL", "NOT_EVALUABLE"]), z.string()).nullish(),
  })
  .strict();
export type CheckSpec = z.infer<typeof CheckSpecSchema>;

/** `model_check.check` body 1.0.0 — must equal `schemas/result-body/model_check.check/1.0.0.json` (test-enforced). */
export const MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0: Readonly<Record<string, unknown>> = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "urn:canvastekk:result-body:model_check.check:1.0.0",
  "title": "model_check.check body 1.0.0",
  "description": "Body of a model-check result file written by the SDK verdict step (CheckNodeBase). checks[] holds one entry per check key with the limits and filters the run used; measurements[] holds one judged row per reading. Counts are per subject (subject_id), never per row.",
  "type": "object",
  "required": [
    "checks",
    "measurements"
  ],
  "definitions": {
    "verdict": {
      "enum": [
        "PASS",
        "WARNING",
        "FAIL",
        "NOT_EVALUABLE"
      ]
    },
    "counts": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "PASS",
        "WARNING",
        "FAIL",
        "NOT_EVALUABLE"
      ],
      "properties": {
        "PASS": {
          "type": "integer",
          "minimum": 0
        },
        "WARNING": {
          "type": "integer",
          "minimum": 0
        },
        "FAIL": {
          "type": "integer",
          "minimum": 0
        },
        "NOT_EVALUABLE": {
          "type": "integer",
          "minimum": 0
        }
      }
    },
    "limit_used": {
      "type": "object",
      "required": [
        "input",
        "role",
        "operator",
        "value"
      ],
      "properties": {
        "input": {
          "type": "string"
        },
        "role": {
          "enum": [
            "LIMIT",
            "WARNING_LIMIT"
          ]
        },
        "operator": {
          "enum": [
            "GT",
            "GTE",
            "LT",
            "LTE",
            "EQ",
            "NE",
            "IN",
            "NOT_IN"
          ]
        },
        "value": {},
        "tolerance": {
          "type": [
            "number",
            "null"
          ],
          "minimum": 0
        },
        "ignore_case": {
          "type": "boolean"
        },
        "fixed": {
          "type": "boolean"
        }
      }
    },
    "filter_used": {
      "type": "object",
      "required": [
        "input",
        "value"
      ],
      "properties": {
        "input": {
          "type": "string"
        },
        "value": {}
      }
    },
    "failed_limit": {
      "type": "object",
      "required": [
        "input",
        "side"
      ],
      "properties": {
        "input": {
          "type": "string"
        },
        "side": {
          "enum": [
            "BELOW",
            "ABOVE",
            "EQUAL",
            "MISMATCH",
            "NOT_IN",
            "IN"
          ]
        }
      }
    },
    "reason": {
      "type": "object",
      "required": [
        "code"
      ],
      "properties": {
        "code": {
          "type": "string",
          "pattern": "^[A-Z][A-Z0-9_]*$"
        },
        "message": {
          "type": "string"
        }
      }
    }
  },
  "properties": {
    "checks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "check",
          "verdict",
          "verdict_counts",
          "limits_used",
          "filters_used"
        ],
        "properties": {
          "check": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$"
          },
          "verdict": {
            "$ref": "#/definitions/verdict"
          },
          "verdict_counts": {
            "$ref": "#/definitions/counts"
          },
          "limits_used": {
            "type": "array",
            "items": {
              "$ref": "#/definitions/limit_used"
            }
          },
          "filters_used": {
            "type": "array",
            "items": {
              "$ref": "#/definitions/filter_used"
            }
          },
          "not_evaluated_reason": {
            "$ref": "#/definitions/reason"
          },
          "cross_reference": {
            "type": "string"
          }
        }
      }
    },
    "measurements": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "check",
          "subject_id",
          "kind",
          "verdict"
        ],
        "properties": {
          "check": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$"
          },
          "subject_id": {
            "type": "string",
            "minLength": 1
          },
          "kind": {
            "enum": [
              "value",
              "predicate",
              "fail_by_name",
              "not_evaluable"
            ]
          },
          "element_name": {
            "type": [
              "string",
              "null"
            ]
          },
          "file_id": {
            "type": [
              "integer",
              "string",
              "null"
            ]
          },
          "global_ids": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "actual": {},
          "actual_raw": {},
          "bound": {
            "enum": [
              "LOWER",
              "UPPER",
              null
            ]
          },
          "alternatives": {
            "type": "object"
          },
          "verdict": {
            "$ref": "#/definitions/verdict"
          },
          "failed_limits": {
            "type": "array",
            "items": {
              "$ref": "#/definitions/failed_limit"
            }
          },
          "reason": {
            "$ref": "#/definitions/reason"
          },
          "verdict_caveat": {
            "type": "object"
          },
          "extra": {
            "type": "object"
          }
        }
      }
    },
    "observations": {
      "type": "array",
      "items": {
        "type": "object"
      }
    }
  }
};
