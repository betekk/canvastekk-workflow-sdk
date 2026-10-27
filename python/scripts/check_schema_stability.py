"""Schema stability checker for CanvasTEKK Workflow SDK Pydantic models.

Detects breaking vs additive changes to the public Pydantic model schemas.
Used in CI to enforce that schema-breaking PRs carry the ``major`` semver label.

Usage::

    # Dump all model schemas as JSON to stdout
    poetry run python scripts/check_schema_stability.py dump

    # Diff two previously-dumped schema files (CI mode)
    python3 scripts/check_schema_stability.py diff <base.json> <pr.json>

Exit codes (diff mode):
    0 — no breaking changes, or breaking changes present (CI decides via label)
    2 — internal error

Environment:
    GITHUB_OUTPUT — if set, writes ``breaking=true|false`` for workflow step output.
"""

from __future__ import annotations

import enum
import json
import os
import sys
from typing import Any

MODEL_IMPORTS = """
from canvastekk_workflow_sdk import (
    DeprecationInfo,
    RetryConfig,
    WorkflowNodeManifest,
    WorkflowNodeRole,
    WorkflowNodeStyles,
)
from canvastekk_workflow_sdk.workflow.models import (
    EdgeType,
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowEdgeDefinition,
)
"""

MODELS_TO_CHECK: list[tuple[str, str]] = [
    ("WorkflowNodeManifest", "WorkflowNodeManifest"),
    ("DeprecationInfo", "DeprecationInfo"),
    ("WorkflowNodeStyles", "WorkflowNodeStyles"),
    ("WorkflowNodeRole", "WorkflowNodeRole"),
    ("RetryConfig", "RetryConfig"),
    ("EdgeType", "EdgeType"),
    ("WorkflowDefinitionNode", "WorkflowDefinitionNode"),
    ("WorkflowEdgeDefinition", "WorkflowEdgeDefinition"),
    ("WorkflowDefinitionSpec", "WorkflowDefinitionSpec"),
]

TYPE_RELEVANT_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "$ref",
        "$id",
        "$schema",
        "anyOf",
        "oneOf",
        "allOf",
        "enum",
        "const",
        "format",
        "items",
        "prefixItems",
        "additionalProperties",
        "contains",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        "required",
        "contentMediaType",
        "contentEncoding",
    }
)




def dump_schemas() -> None:
    """Import all registered models and dump their JSON schemas to stdout."""
    namespace: dict[str, Any] = {}
    exec(MODEL_IMPORTS, namespace)

    schemas: dict[str, Any] = {}
    for export_name, local_name in MODELS_TO_CHECK:
        model = namespace[local_name]
        schemas[export_name] = _serialize_model(model)

    json.dump(schemas, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _serialize_model(model: Any) -> dict[str, Any]:
    """Serialize a Pydantic model or Enum to a JSON-schema-ish dict.

    Args:
        model: A Pydantic ``BaseModel`` subclass or an ``Enum`` subclass.

    Returns:
        A JSON-serializable dict representing the model's schema.
    """
    if isinstance(model, type) and issubclass(model, enum.Enum):
        return {
            "_kind": "enum",
            "values": sorted(member.value for member in model),
        }
    schema: dict[str, Any] = model.model_json_schema()
    schema.pop("$defs", None)
    return schema



BREAKING = "BREAKING"
ADDITIVE = "ADDITIVE"


def extract_type_info(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """Extract type-relevant keys from a field's property schema.

    Args:
        prop_schema: The ``properties.<field>`` dict from a JSON schema.

    Returns:
        A filtered dict containing only keys that affect validation.
    """
    return {k: v for k, v in prop_schema.items() if k in TYPE_RELEVANT_KEYS}


def diff_schemas(base_path: str, pr_path: str) -> int:
    """Compare two schema dumps, classify changes, and report.

    Args:
        base_path: Path to the base (main) schema JSON file.
        pr_path: Path to the PR branch schema JSON file.

    Returns:
        0 always (CI decides pass/fail based on ``breaking`` output + label).
    """
    with open(base_path) as f:
        base = json.load(f)
    with open(pr_path) as f:
        pr = json.load(f)

    changes: list[tuple[str, str, str]] = []

    base_models = set(base.keys())
    pr_models = set(pr.keys())

    for model in sorted(base_models - pr_models):
        changes.append((BREAKING, model, "model removed"))

    for model in sorted(pr_models - base_models):
        changes.append((ADDITIVE, model, "model added"))

    for model in sorted(base_models & pr_models):
        changes.extend(_diff_single_model(model, base[model], pr[model]))

    has_breaking = any(c[0] == BREAKING for c in changes)
    additive_changes = [c for c in changes if c[0] == ADDITIVE]
    breaking_changes = [c for c in changes if c[0] == BREAKING]

    print("=" * 60)
    print("Schema Stability Check")
    print(f"  Base: {base_path}")
    print(f"  PR:   {pr_path}")
    print(f"  Models checked: {len(base_models | pr_models)}")
    print("=" * 60)

    if not changes:
        print("\nNo schema changes detected.\n")
    else:
        if breaking_changes:
            print(f"\n{'!' * 3} BREAKING CHANGES ({len(breaking_changes)}):")
            for _, mdl, desc in breaking_changes:
                print(f"  [BREAKING] {mdl}: {desc}")
        if additive_changes:
            print(f"\n{'+' * 3} ADDITIVE CHANGES ({len(additive_changes)}):")
            for _, mdl, desc in additive_changes:
                print(f"  [ADDITIVE] {mdl}: {desc}")
        print()

    if has_breaking:
        print("::warning::Breaking schema changes detected.")
        print("::error::Breaking changes require the 'major' label on this PR.")
        print("::error::Add the 'major' label to acknowledge, or revert the changes.")
    else:
        if additive_changes:
            print("Schema changes are additive only — no breaking changes.\n")
        else:
            print()

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"breaking={'true' if has_breaking else 'false'}\n")

    return 0


def _diff_single_model(
    name: str,
    base_schema: dict[str, Any],
    pr_schema: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """Compare a single model's schema between base and PR.

    Args:
        name: Model name.
        base_schema: Base schema dict.
        pr_schema: PR schema dict.

    Returns:
        List of (severity, model_name, description) tuples.
    """
    changes: list[tuple[str, str, str]] = []

    if base_schema.get("_kind") == "enum" or pr_schema.get("_kind") == "enum":
        base_vals = set(base_schema.get("values", []))
        pr_vals = set(pr_schema.get("values", []))
        for val in sorted(base_vals - pr_vals):
            changes.append((BREAKING, name, f"enum value removed: '{val}'"))
        for val in sorted(pr_vals - base_vals):
            changes.append((ADDITIVE, name, f"enum value added: '{val}'"))
        return changes

    base_props: dict[str, Any] = base_schema.get("properties", {})
    pr_props: dict[str, Any] = pr_schema.get("properties", {})
    base_required: set[str] = set(base_schema.get("required", []))
    pr_required: set[str] = set(pr_schema.get("required", []))

    base_fields = set(base_props.keys())
    pr_fields = set(pr_props.keys())

    for field in sorted(base_fields - pr_fields):
        changes.append((BREAKING, name, f"field '{field}' removed"))

    for field in sorted(pr_fields - base_fields):
        if field in pr_required:
            changes.append((BREAKING, name, f"required field '{field}' added"))
        else:
            changes.append((ADDITIVE, name, f"optional field '{field}' added"))

    common_fields = base_fields & pr_fields
    for field in sorted(common_fields):
        was_required = field in base_required
        is_required = field in pr_required
        if not was_required and is_required:
            changes.append((BREAKING, name, f"field '{field}' became required"))
        elif was_required and not is_required:
            changes.append((ADDITIVE, name, f"field '{field}' became optional"))

    for field in sorted(common_fields):
        base_type = extract_type_info(base_props[field])
        pr_type = extract_type_info(pr_props[field])
        if base_type != pr_type:
            changes.append(
                (
                    BREAKING,
                    name,
                    f"field '{field}' type changed: {_summarize_type(base_type)} -> {_summarize_type(pr_type)}",
                )
            )

    return changes


def _summarize_type(type_info: dict[str, Any]) -> str:
    """Compact one-line representation of a field's type info for error messages."""
    if not type_info:
        return "{}"
    parts: list[str] = []
    for key in sorted(type_info.keys()):
        val = type_info[key]
        if isinstance(val, (dict, list)):
            val = json.dumps(val, sort_keys=True)
        parts.append(f"{key}={val}")
    return "{" + ", ".join(parts) + "}"




def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    mode = sys.argv[1]

    if mode == "dump":
        dump_schemas()
        return 0
    elif mode == "diff":
        if len(sys.argv) != 4:
            print("Usage: check_schema_stability.py diff <base.json> <pr.json>", file=sys.stderr)
            return 2
        return diff_schemas(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown mode: '{mode}'. Use 'dump' or 'diff'.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
