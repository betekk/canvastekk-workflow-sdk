/**
 * Check verdict vocabulary (#283, epic betekk/canvastekk-tracker#4332).
 *
 * TypeScript mirror of the Python `check_verdict` module's vocabulary: the
 * `x-verdict` mark, the role / operator / verdict enums, the roll-up order
 * and the published `model_check.check` body schemas. The verdict step
 * itself (`judge`, `CheckNodeBase`) is Python-only for now: every check node
 * is a Python node. Guide: `docs/CHECK-VERDICT.md`.
 */

import { z } from "zod";

/** Input-schema extension that marks an input as a verdict variable. */
export const VERDICT_MARK = "x-verdict";

/** Result-file label of the check body. */
export const CHECK_RESULT_SCHEMA = "model_check.check";

/** Default writer version for backwards compatibility. */
export const CHECK_RESULT_SCHEMA_VERSION = "1.0.0";

/** Version with findings nested under their owning check. */
export const CHECK_RESULT_SCHEMA_VERSION_2_0_0 = "2.0.0";
export const CHECK_RESULT_SCHEMA_VERSION_2_1_0 = "2.1.0";
export const CHECK_RESULT_SCHEMA_VERSION_2_2_0 = "2.2.0";

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
    description: z.string().min(1).max(2000).nullish(),
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

const bodyV1 = {
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

/** Published `model_check.check` 1.0.0 contract (cross-language parity tested). */
export const MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0: Readonly<Record<string, unknown>> = bodyV1;

const {
  check: _check, global_ids: _globalIds, file_id: _fileId, ...readingFields
} = bodyV1.properties.measurements.items.properties;
const checkFields = bodyV1.properties.checks.items.properties;

const bodyV2 = {
  $schema: bodyV1.$schema,
  $id: "urn:canvastekk:result-body:model_check.check:2.0.0",
  title: "model_check.check body 2.0.0",
  description: "Each check owns its original measurement array. Counts are per subject, never per row. Use result-file layout 1.1.0; derive an omitted limit only from the pinned rules and the inputs used by that run.",
  type: "object",
  required: ["checks"],
  additionalProperties: false,
  properties: {
    checks: { type: "array", items: { $ref: "#/definitions/check" } },
    observations: bodyV1.properties.observations,
    extra: { type: "object" },
  },
  definitions: {
    ...bodyV1.definitions,
    check: {
      type: "object",
      required: ["check", "verdict", "verdict_counts", "measurements"],
      additionalProperties: false,
      properties: {
        ...checkFields,
        measurements: { type: "array", items: { $ref: "#/definitions/measurement" } },
      },
    },
    measurement: {
      type: "object",
      required: ["subject_id", "kind", "verdict"],
      additionalProperties: false,
      dependencies: {
        element_id: ["element_id_type"],
        element_id_type: ["element_id"],
        element_id_source_file: ["element_id", "element_id_type"],
      },
      properties: {
        ...readingFields,
        element_name: { type: "string" },
        element_id: { type: "string", pattern: "^[0-3][0-9A-Za-z_$]{21}$" },
        element_id_type: { const: "ifc_guid" },
        element_id_source_file: {
          description: "Original stored file ID when the producer verifies it. Never infer this from the subject or drawing.",
          oneOf: [{ type: "integer", minimum: 1 }, { type: "string", minLength: 1 }],
        },
        viewer_representation: {
          type: "object",
          required: ["schema_version", "primitives"],
          properties: {
            schema_version: { type: "integer", minimum: 1 },
            primitives: { type: "array", items: { type: "object" } },
          },
        },
      },
    },
  },
};

/** Published `model_check.check` 2.0.0 contract with locally nested findings. */
export const MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0: Readonly<Record<string, unknown>> = bodyV2;

/** Published `model_check.check` 2.1.0 contract with optional plan-band drawings. */
export const MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0: Readonly<Record<string, unknown>> = {
  ...bodyV2,
  $id: "urn:canvastekk:result-body:model_check.check:2.1.0",
  title: "model_check.check body 2.1.0",
  description: "Grouped check findings with optional, file-local drawing references. Uses result-file layout 1.1.0.",
  properties: {
    ...bodyV2.properties,
    report_visuals: {
      type: "object",
      propertyNames: { type: "string", minLength: 1 },
      additionalProperties: { $ref: "#/definitions/plan_band" },
    },
  },
  definitions: {
    ...bodyV2.definitions,
    measurement: {
      ...bodyV2.definitions.measurement,
      properties: {
        ...bodyV2.definitions.measurement.properties,
        report_visual_refs: { $ref: "#/definitions/report_visual_refs" },
      },
    },
    report_visual_refs: {
      description: "Drawing identifiers in this result body's report_visuals map.",
      type: "array",
      uniqueItems: true,
      items: { type: "string", minLength: 1 },
    },
    point_xy_mm: { type: "array", minItems: 2, maxItems: 2, items: { type: "number" } },
    plan_band: {
      description: "Projected context in the same model-space millimetres as the finding overlay.",
      type: "object",
      additionalProperties: false,
      required: ["kind", "crop_xy_mm", "z_band_mm", "layers"],
      properties: {
        kind: { const: "plan_band" },
        crop_xy_mm: {
          description: "Crop bounds in [min X, min Y, max X, max Y] order. Model-space millimetres: the finding's viewer-representation footprint padded by 1000 mm on every side.",
          type: "array", minItems: 4, maxItems: 4, items: { type: "number" },
        },
        z_band_mm: {
          description: "Actual clipping elevations in [bottom, top] order. Model-space millimetres: bottom = the finding's lowest viewer-representation point - 100 mm, top = its highest viewer-representation point + 100 mm.",
          type: "array", minItems: 2, maxItems: 2, items: { type: "number" },
        },
        layers: {
          description: "Named layers of polygons, each with an exterior ring followed by any holes.",
          type: "object",
          additionalProperties: {
            type: "array",
            items: {
              type: "array", minItems: 1,
              items: { type: "array", minItems: 3, items: { $ref: "#/definitions/point_xy_mm" } },
            },
          },
        },
      },
    },
  },
};

const ifcGuidV22 = { type: "string", pattern: "^[0-3][0-9A-Za-z_$]{21}$" };
const polygonV22 = {
  description: "One polygon: an exterior ring followed by any holes.",
  type: "array",
  minItems: 1,
  items: { type: "array", minItems: 3, items: { $ref: "#/definitions/point_xy_mm" } },
};
const polygonsV22 = { type: "array", items: { $ref: "#/definitions/polygon" } };

/** Published `model_check.check` 2.2.0 contract with layout plans and sourced spatial observations. */
export const MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0: Readonly<Record<string, unknown>> = {
  ...bodyV2,
  $id: "urn:canvastekk:result-body:model_check.check:2.2.0",
  title: "model_check.check body 2.2.0",
  description: "Grouped check findings with optional file-local drawings and sourced spatial observations. Uses result-file layout 1.1.0.",
  properties: {
    ...bodyV2.properties,
    report_visuals: {
      type: "object",
      propertyNames: { type: "string", minLength: 1 },
      additionalProperties: {
        oneOf: [{ $ref: "#/definitions/plan_band" }, { $ref: "#/definitions/layout_plan" }],
      },
    },
    spatial_reference: { $ref: "#/definitions/spatial_reference" },
  },
  definitions: {
    ...bodyV2.definitions,
    measurement: {
      ...bodyV2.definitions.measurement,
      properties: {
        ...bodyV2.definitions.measurement.properties,
        report_visual_refs: { $ref: "#/definitions/report_visual_refs" },
        spatial_context: { $ref: "#/definitions/spatial_context" },
      },
    },
    report_visual_refs: {
      description: "Drawing identifiers in this result body's report_visuals map.",
      type: "array",
      uniqueItems: true,
      items: { type: "string", minLength: 1 },
    },
    source_file_id: {
      oneOf: [{ type: "integer", minimum: 1 }, { type: "string", minLength: 1 }],
    },
    spatial_reference: {
      description: "Optional sourced storey observations. Storey refs are labels, never stored floor-level authority.",
      type: "object",
      additionalProperties: false,
      required: ["source", "storeys"],
      properties: {
        source: { type: "string", minLength: 1 },
        storeys: { type: "array", items: { $ref: "#/definitions/storey" } },
      },
    },
    storey: {
      type: "object",
      additionalProperties: false,
      required: ["ref", "global_id", "name", "source_file_id", "elevation_mm", "elevation_raw_mm"],
      properties: {
        ref: { type: "string", minLength: 1 },
        global_id: ifcGuidV22,
        name: { type: "string", minLength: 1 },
        source_file_id: { $ref: "#/definitions/source_file_id" },
        elevation_mm: {
          description: "Placement-resolved elevation in the same frame and units as finding primitives.",
          type: "number",
        },
        elevation_raw_mm: {
          description: "IFC storey elevation attribute as written, converted to millimetres without placement resolution.",
          type: "number",
        },
      },
    },
    spatial_context: {
      description: "Optional sourced spatial observations for one measurement; absent means not observed.",
      type: "object",
      additionalProperties: false,
      properties: {
        anchor_z_mm: {
          description: "Lowest viewer-representation primitive Z in model-space millimetres.",
          type: "number",
        },
        storey_below: { $ref: "#/definitions/storey_observation" },
        storey_above: { $ref: "#/definitions/storey_observation" },
        floor_surface: { $ref: "#/definitions/floor_surface" },
        region: { $ref: "#/definitions/region_observation" },
      },
    },
    storey_observation: {
      type: "object",
      additionalProperties: false,
      required: ["ref", "offset_mm"],
      properties: {
        ref: { type: "string", minLength: 1 },
        offset_mm: { type: "number" },
      },
    },
    floor_surface: {
      type: "object",
      additionalProperties: false,
      required: ["elevation_mm", "offset_mm", "global_id", "ifc_class", "source"],
      properties: {
        elevation_mm: { type: "number" },
        offset_mm: { type: "number" },
        global_id: ifcGuidV22,
        ifc_class: { type: "string", minLength: 1 },
        source: { type: "string", minLength: 1 },
      },
    },
    region_observation: {
      type: "object",
      additionalProperties: false,
      required: ["id", "gender", "source"],
      properties: {
        id: { type: "string", minLength: 1 },
        gender: { type: "string", minLength: 1 },
        source: { type: "string", minLength: 1 },
      },
    },
    point_xy_mm: { type: "array", minItems: 2, maxItems: 2, items: { type: "number" } },
    crop_xy_mm: {
      description: "Crop bounds in [min X, min Y, max X, max Y] order, in model-space millimetres.",
      type: "array",
      minItems: 4,
      maxItems: 4,
      items: { type: "number" },
    },
    polygon: polygonV22,
    polygons: polygonsV22,
    plan_band: {
      description: "Projected context in the same model-space millimetres as the finding overlay.",
      type: "object",
      additionalProperties: false,
      required: ["kind", "crop_xy_mm", "z_band_mm", "layers"],
      properties: {
        kind: { const: "plan_band" },
        crop_xy_mm: {
          description: "Crop bounds in [min X, min Y, max X, max Y] order. Model-space millimetres: the finding's viewer-representation footprint padded by 1000 mm on every side.",
          type: "array",
          minItems: 4,
          maxItems: 4,
          items: { type: "number" },
        },
        z_band_mm: {
          description: "Actual clipping elevations in [bottom, top] order. Model-space millimetres: bottom = the finding's lowest viewer-representation point - 100 mm, top = its highest viewer-representation point + 100 mm.",
          type: "array",
          minItems: 2,
          maxItems: 2,
          items: { type: "number" },
        },
        layers: {
          description: "Named layers of polygons, each with an exterior ring followed by any holes.",
          type: "object",
          additionalProperties: { $ref: "#/definitions/polygons" },
        },
      },
    },
    layout_plan: {
      description: "Check-level plan context in model-space millimetres. Detail plan bands remain separate finding insets.",
      type: "object",
      additionalProperties: false,
      required: ["kind", "floor_elevation_mm", "cut_z_mm", "crop_xy_mm", "layers"],
      properties: {
        kind: { const: "layout_plan" },
        storey_ref: { type: "string", minLength: 1 },
        floor_elevation_mm: { type: "number" },
        cut_z_mm: { type: "number" },
        crop_xy_mm: { $ref: "#/definitions/crop_xy_mm" },
        layers: {
          type: "object",
          additionalProperties: { $ref: "#/definitions/polygons" },
        },
        fixtures: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["global_id", "footprint"],
            properties: {
              global_id: ifcGuidV22,
              footprint: { $ref: "#/definitions/polygon" },
            },
          },
        },
        regions: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["region_id", "class", "gender", "polygons"],
            properties: {
              region_id: { type: "string", minLength: 1 },
              class: { type: "string", minLength: 1 },
              gender: { type: "string", minLength: 1 },
              polygons: { $ref: "#/definitions/polygons" },
            },
          },
        },
        portals: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["portal_id", "region_id", "mouth_chord", "lobby_polygon"],
            properties: {
              portal_id: { type: "string", minLength: 1 },
              region_id: { type: "string", minLength: 1 },
              mouth_chord: {
                type: "array",
                minItems: 2,
                maxItems: 2,
                items: { $ref: "#/definitions/point_xy_mm" },
              },
              lobby_polygon: { $ref: "#/definitions/polygon" },
            },
          },
        },
        true_north_deg: { type: "number" },
      },
    },
  },
};
