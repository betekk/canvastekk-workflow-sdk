"""JSON Schema dialect lint (#113).

Flags constructs a JSON Schema 2020-12 document may not carry, with the
exact `$`-path of the offender. Pure function — wiring into the CLI
`validate` output or the verifier is a deliberate follow-up once the
violation shapes settle.
"""

from __future__ import annotations

from typing import Any

__all__ = ["lint_schema_dialect"]

_PRE_2020_12_SCHEMAS = (
    "http://json-schema.org/draft-07/schema#",
    "http://json-schema.org/draft-04/schema#",
    "http://json-schema.org/draft-06/schema#",
    "https://json-schema.org/draft/2019-09/schema",
)

_CONTAINER_KEYS = ("properties", "$defs", "definitions", "patternProperties")
_LIST_CONTAINER_KEYS = ("prefixItems", "allOf", "anyOf", "oneOf")


def _flag_keyword(
    schema: dict[str, Any],
    path: str,
    keyword: str,
    message: str,
    violations: list[tuple[str, str]],
) -> None:
    if keyword in schema:
        violations.append((f"{path}.{keyword}", message))


def _lint_node(schema: Any, path: str, violations: list[tuple[str, str]]) -> None:
    if not isinstance(schema, dict):
        return

    uri = schema.get("$schema")
    if isinstance(uri, str) and any(uri.startswith(p) for p in _PRE_2020_12_SCHEMAS):
        violations.append((f"{path}.$schema", f"pre-2020-12 dialect URI: {uri}"))

    _flag_keyword(
        schema,
        path,
        "definitions",
        "draft-07 'definitions' is not 2020-12 — use '$defs'",
        violations,
    )
    _flag_keyword(
        schema,
        path,
        "recursiveAnchor",
        "'recursiveAnchor' is 2019-09 — not part of 2020-12",
        violations,
    )
    for key in ("exclusiveMinimum", "exclusiveMaximum"):
        if isinstance(schema.get(key), bool):
            violations.append(
                (f"{path}.{key}", "boolean exclusiveMinimum/Maximum is draft-04 — 2020-12 requires a number")
            )

    deps = schema.get("dependencies")
    if isinstance(deps, dict):
        for dep_key, dep_value in deps.items():
            kind = "dependentRequired" if isinstance(dep_value, list) else "dependentSchemas"
            violations.append(
                (
                    f"{path}.dependencies.{dep_key}",
                    f"draft-07 'dependencies' is not 2020-12 — use '{kind}'",
                )
            )

    for key in _CONTAINER_KEYS:
        child = schema.get(key)
        if isinstance(child, dict):
            for name, sub in child.items():
                _lint_node(sub, f"{path}.{key}.{name}", violations)
    for key in _LIST_CONTAINER_KEYS:
        child = schema.get(key)
        if isinstance(child, list):
            for i, sub in enumerate(child):
                _lint_node(sub, f"{path}.{key}[{i}]", violations)
    items = schema.get("items")
    if isinstance(items, list):
        violations.append((f"{path}.items", "array-form 'items' is draft-07 — 2020-12 uses 'prefixItems'"))
        for i, sub in enumerate(items):
            _lint_node(sub, f"{path}.items[{i}]", violations)
    else:
        _lint_node(items, f"{path}.items", violations)
    _lint_node(
        schema.get("additionalProperties"),
        f"{path}.additionalProperties",
        violations,
    )


def lint_schema_dialect(schema: dict[str, Any]) -> list[tuple[str, str]]:
    """Flag non-2020-12 schema constructs with their `$`-paths.

    Args:
        schema: A JSON Schema dict (e.g. a manifest's ``input_schema``).

    Returns:
        A list of ``(json_path, message)`` tuples; empty when the schema is
        clean 2020-12. Recurses through ``properties``, ``$defs`` (and legacy
        ``definitions``, to surface nested offenders), ``items``,
        ``prefixItems``, combinators, and ``additionalProperties``.
    """
    violations: list[tuple[str, str]] = []
    _lint_node(schema, "$", violations)
    return violations
