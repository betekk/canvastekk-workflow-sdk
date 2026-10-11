"""schema_dialect lint tests (#113)."""

from __future__ import annotations

from canvastekk_workflow_sdk.schema_dialect import lint_schema_dialect


def test_clean_2020_12_schema_returns_empty() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "count": {"type": "integer", "exclusiveMinimum": 0},
            "nested": {"$ref": "#/$defs/thing"},
        },
        "$defs": {"thing": {"type": "string"}},
    }
    assert lint_schema_dialect(schema) == []


def test_draft07_schema_uri_flagged() -> None:
    violations = lint_schema_dialect({"$schema": "http://json-schema.org/draft-07/schema#"})
    assert len(violations) == 1
    path, message = violations[0]
    assert path == "$.$schema"
    assert "draft-07" in message


def test_definitions_flagged_with_path() -> None:
    schema = {
        "properties": {
            "inner": {"definitions": {"legacy": {"type": "string"}}},
        },
    }
    violations = lint_schema_dialect(schema)
    assert violations == [
        ("$.properties.inner.definitions", "draft-07 'definitions' is not 2020-12 — use '$defs'"),
    ]


def test_dependencies_split_by_shape() -> None:
    schema = {
        "dependencies": {
            "credit_card": ["billing_address"],  # array form -> dependentRequired
            "status": {"type": "object"},  # schema form -> dependentSchemas
        },
    }
    messages = dict(lint_schema_dialect(schema))
    assert "use 'dependentRequired'" in messages["$.dependencies.credit_card"]
    assert "use 'dependentSchemas'" in messages["$.dependencies.status"]


def test_boolean_exclusive_minimum_flagged() -> None:
    violations = lint_schema_dialect({"exclusiveMinimum": True})
    assert violations == [
        ("$.exclusiveMinimum", "boolean exclusiveMinimum/Maximum is draft-04 — 2020-12 requires a number"),
    ]


def test_array_form_items_flagged_and_recursed() -> None:
    schema = {"items": [{"definitions": {"x": 1}}, {"type": "string"}]}
    violations = lint_schema_dialect(schema)
    assert any(p == "$.items" for p, _ in violations)
    assert ("$.items[0].definitions", "draft-07 'definitions' is not 2020-12 — use '$defs'") in violations


def test_recursive_anchor_flagged() -> None:
    assert lint_schema_dialect({"recursiveAnchor": True}) == [
        ("$.recursiveAnchor", "'recursiveAnchor' is 2019-09 — not part of 2020-12"),
    ]
