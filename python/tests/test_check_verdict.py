"""Tests for the check verdict functions (#283)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from canvastekk_workflow_sdk.check_verdict import (
    CheckResolution,
    CheckSpec,
    CheckVerdictError,
    Reading,
    Rule,
    judge,
    load_check_body_schema,
    marked_input_values,
    rollup,
    rules_from_inputs,
    verdict_mark_errors,
)

CANONICAL_BODY = Path(__file__).resolve().parents[2] / "schemas" / "result-body" / "model_check.check" / "1.0.0.json"


def _num(name: str, check: str, role: str, operator: str | None = None, default=None, **extra) -> dict:
    mark = {"check": check, "role": role}
    if operator:
        mark["operator"] = operator
    mark.update(extra)
    prop = {"type": "number", "x-verdict": mark}
    if default is not None:
        prop["default"] = default
    return {name: prop}


def _schema(*props: dict) -> dict:
    merged: dict = {}
    for p in props:
        merged.update(p)
    return {"type": "object", "properties": merged}


BEAM_SCHEMA = _schema(
    _num("beam_length_min", "beam_length", "LIMIT", "GTE", 1000),
    _num("beam_length_max", "beam_length", "LIMIT", "LT", 6500),
    {
        "beam_length_warn_max": {
            "type": ["number", "null"],
            "default": None,
            "x-verdict": {"check": "beam_length", "role": "WARNING_LIMIT", "operator": "LTE"},
        }
    },
    _num(
        "beam_length_tolerance", "beam_length", "TOLERANCE", None, 0, applies_to=["beam_length_min", "beam_length_max"]
    ),
    {
        "include_cantilevers": {
            "type": "boolean",
            "default": True,
            "x-verdict": {"check": "beam_length", "role": "FILTER"},
        }
    },
)
BEAM_CHECKS = {"beam_length": CheckSpec(label="Beam length", unit="mm", resolution=CheckResolution(step=1))}


# --- schema and roll-up ---------------------------------------------------------


def test_packaged_body_schema_equals_canonical() -> None:
    assert load_check_body_schema() == json.loads(CANONICAL_BODY.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(load_check_body_schema())


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        (["PASS", "FAIL"], "FAIL"),
        (["PASS", "NOT_EVALUABLE"], "NOT_EVALUABLE"),
        (["WARNING", "NOT_EVALUABLE"], "NOT_EVALUABLE"),
        (["FAIL", "NOT_EVALUABLE"], "FAIL"),
        (["PASS", "WARNING"], "WARNING"),
        (["PASS", "PASS"], "PASS"),
        ([], "NOT_EVALUABLE"),
    ],
)
def test_rollup_precedence(verdicts: list[str], expected: str) -> None:
    assert rollup(verdicts) == expected


def test_rollup_rejects_unknown() -> None:
    with pytest.raises(CheckVerdictError):
        rollup(["MAYBE"])


# --- marks ------------------------------------------------------------------------


def test_beam_marks_are_valid() -> None:
    assert verdict_mark_errors(BEAM_SCHEMA, BEAM_CHECKS) == []


@pytest.mark.parametrize(
    ("schema", "checks", "fragment"),
    [
        (_schema(_num("a", "c", "LIMIT", "GTE")), {}, "not declared"),
        (_schema(_num("a", "c", "LIMIT", "IN")), {"c": {"label": "C"}}, "does not fit a number"),
        (_schema(_num("a", "c", "LIMIT")), {"c": {"label": "C"}}, "operator must be one of"),
        (_schema(_num("a", "c", "FILTER", "EQ")), {"c": {"label": "C"}}, "takes no operator"),
        (_schema(_num("a", "c", "BOUND", "EQ")), {"c": {"label": "C"}}, "role must be one of"),
        (_schema(_num("a", "c", "WARNING_LIMIT", "GTE")), {"c": {"label": "C"}}, "no LIMIT"),
        (
            _schema(_num("a", "c", "LIMIT", "GTE"), _num("t", "c", "TOLERANCE", None, 0, applies_to=["zz"])),
            {"c": {"label": "C"}},
            "not a numeric limit",
        ),
        (
            _schema(
                _num("a", "c", "LIMIT", "GTE"),
                _num("t1", "c", "TOLERANCE", None, 0),
                _num("t2", "c", "TOLERANCE", None, 0),
            ),
            {"c": {"label": "C"}},
            "two tolerances",
        ),
        (_schema(_num("a", "c", "LIMIT", "GTE"), _num("t", "c", "TOLERANCE", None, -1)), {"c": {"label": "C"}}, ">= 0"),
        (_schema(_num("a", "c", "LIMIT", "GTE", ignore_case=True)), {"c": {"label": "C"}}, "ignore_case"),
        (_schema(_num("a", "c", "LIMIT", "GTE", applies_to=["a"])), {"c": {"label": "C"}}, "only for TOLERANCE"),
        (_schema(_num("a", "Bad-Key", "LIMIT", "GTE")), {"Bad-Key": {"label": "C"}}, "snake_case"),
        (
            {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "x-verdict": {"check": "c", "role": "LIMIT", "operator": "GTE", "x": 1}}
                },
            },
            {"c": {"label": "C"}},
            "unknown key",
        ),
        (
            {
                "type": "object",
                "properties": {"a": {"type": "object", "x-verdict": {"check": "c", "role": "LIMIT", "operator": "EQ"}}},
            },
            {"c": {"label": "C"}},
            "number, string, boolean or string-list",
        ),
    ],
)
def test_mark_errors(schema: dict, checks: dict, fragment: str) -> None:
    problems = verdict_mark_errors(schema, checks)
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize(
    ("prop", "ok"),
    [
        ({"type": "string", "x-verdict": {"check": "c", "role": "LIMIT", "operator": "EQ", "ignore_case": True}}, True),
        ({"type": "string", "x-verdict": {"check": "c", "role": "LIMIT", "operator": "GT"}}, False),
        ({"type": "boolean", "x-verdict": {"check": "c", "role": "LIMIT", "operator": "NE"}}, True),
        (
            {
                "type": "array",
                "items": {"type": "string"},
                "x-verdict": {"check": "c", "role": "LIMIT", "operator": "NOT_IN"},
            },
            True,
        ),
        (
            {
                "type": "array",
                "items": {"type": "string"},
                "x-verdict": {"check": "c", "role": "LIMIT", "operator": "EQ"},
            },
            False,
        ),
        (
            {
                "type": "array",
                "items": {"type": "integer"},
                "x-verdict": {"check": "c", "role": "LIMIT", "operator": "IN"},
            },
            False,
        ),
    ],
)
def test_operator_fits_type(prop: dict, ok: bool) -> None:
    problems = verdict_mark_errors({"type": "object", "properties": {"a": prop}}, {"c": {"label": "C"}})
    assert (problems == []) is ok, problems


def test_one_input_may_feed_several_checks() -> None:
    schema = _schema(
        {
            "w": {
                "type": "number",
                "default": 1000,
                "x-verdict": {"check": ["entrance_width", "lobby_width"], "role": "LIMIT", "operator": "GTE"},
            }
        }
    )
    checks = {"entrance_width": {"label": "E"}, "lobby_width": {"label": "L"}}
    assert verdict_mark_errors(schema, checks) == []
    rules = rules_from_inputs(schema, {})
    assert sorted(r.check for r in rules) == ["entrance_width", "lobby_width"]


def test_statement_placeholders_checked() -> None:
    CheckSpec(label="A", statements={"FAIL": "{element}: {label} is {actual} {unit}"})
    with pytest.raises(ValueError, match="unknown placeholder"):
        CheckSpec(label="A", statements={"FAIL": "{element} {nope}"})


# --- rules ------------------------------------------------------------------------


def test_rules_override_beats_default_and_null_warning_dropped() -> None:
    rules = rules_from_inputs(BEAM_SCHEMA, {"beam_length_max": 7000, "beam_length_tolerance": 5})
    by_input = {r.input: r for r in rules}
    assert by_input["beam_length_min"].value == 1000
    assert by_input["beam_length_max"].value == 7000
    assert "beam_length_warn_max" not in by_input
    assert by_input["beam_length_min"].tolerance == 5.0
    assert by_input["include_cantilevers"].role == "FILTER"


def test_tolerance_applies_only_to_named_limits() -> None:
    rules = rules_from_inputs(BEAM_SCHEMA, {"beam_length_warn_max": 6000, "beam_length_tolerance": 5})
    by_input = {r.input: r for r in rules}
    assert by_input["beam_length_warn_max"].tolerance == 0.0


def test_tolerance_defaults_to_every_numeric_limit_of_its_check() -> None:
    schema = _schema(
        _num("lo", "c", "LIMIT", "GTE", 1), _num("hi", "c", "LIMIT", "LTE", 9), _num("t", "c", "TOLERANCE", None, 2)
    )
    assert {r.input: r.tolerance for r in rules_from_inputs(schema, {})} == {"lo": 2.0, "hi": 2.0}


def test_const_input_is_a_fixed_rule() -> None:
    schema = _schema(
        {"visible": {"type": "boolean", "const": False, "x-verdict": {"check": "c", "role": "LIMIT", "operator": "EQ"}}}
    )
    (rule,) = rules_from_inputs(schema, {"visible": True})
    assert rule.value is False and rule.fixed is True
    assert rule.as_limit_used()["fixed"] is True


@pytest.mark.parametrize(
    ("schema", "inputs"),
    [
        (_schema(_num("a", "c", "LIMIT", "GTE")), {}),
        (_schema(_num("a", "c", "LIMIT", "GTE")), {"a": "big"}),
        (_schema(_num("a", "c", "LIMIT", "GTE", 1), _num("t", "c", "TOLERANCE", None, 0)), {"t": -1}),
    ],
)
def test_rules_reject_bad_values(schema: dict, inputs: dict) -> None:
    with pytest.raises(CheckVerdictError):
        rules_from_inputs(schema, inputs)


def test_marked_input_values_are_the_verdict_inputs_only() -> None:
    schema = dict(BEAM_SCHEMA)
    schema["properties"] = {**BEAM_SCHEMA["properties"], "model_file": {"type": "string"}}
    values = marked_input_values(schema, {"beam_length_max": 7000, "model_file": "x.ifc"})
    assert values == {
        "beam_length_min": 1000,
        "beam_length_max": 7000,
        "beam_length_warn_max": None,
        "beam_length_tolerance": 0,
        "include_cantilevers": True,
    }


# --- readings -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        lambda: Reading(kind="value", check="c", subject_id=None, actual=1),
        lambda: Reading.fail_by_name("c", subject_id="s", reason_code="lower_case"),
        lambda: Reading.value("c", subject_id="s", alternatives={"a": 1}),
        lambda: Reading.value("c", subject_id="s", alternatives={"a": 1}, straddle_code="X", bound="LOWER"),
        lambda: Reading.value("c", subject_id="s", alternatives={}, straddle_code="X"),
        lambda: Reading.value("c", subject_id="s", alternatives={"a": 1}, straddle_code="datum-straddle"),
    ],
)
def test_reading_constructor_guards(build) -> None:
    with pytest.raises(CheckVerdictError):
        build()


# --- judging --------------------------------------------------------------------------


def _one(operator: str, limit, actual, tolerance: float = 0.0, **rule) -> str:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=limit, operator=operator, tolerance=tolerance, **rule)]
    reading = (
        Reading.value("c", subject_id="s", actual=actual)
        if isinstance(actual, (int, float)) and not isinstance(actual, bool)
        else Reading.predicate("c", subject_id="s", actual=actual)
    )
    return judge(rules, [reading], {"c": {"label": "C"}}).measurements[0].verdict


@pytest.mark.parametrize(
    ("operator", "limit", "actual", "tolerance", "expected"),
    [
        ("GT", 10, 10, 0, "FAIL"),
        ("GT", 10, 10.5, 0, "PASS"),
        ("GT", 10, 9, 2, "PASS"),
        ("GTE", 10, 10, 0, "PASS"),
        ("GTE", 10, 9.9999999999, 0, "PASS"),
        ("GTE", 10, 9.9, 0, "FAIL"),
        ("GTE", 10, 9, 1, "PASS"),
        ("LT", 10, 10, 0, "FAIL"),
        ("LT", 10, 11, 2, "PASS"),
        ("LTE", 10, 10, 0, "PASS"),
        ("LTE", 10, 10.1, 0, "FAIL"),
        ("EQ", 500, 500, 0, "PASS"),
        ("EQ", 500, 501, 0, "FAIL"),
        ("EQ", 500, 501, 2, "PASS"),
        ("NE", 500, 500, 0, "FAIL"),
        ("NE", 500, 501, 2, "FAIL"),
        ("NE", 500, 503, 2, "PASS"),
    ],
)
def test_numeric_operators_with_tolerance(operator, limit, actual, tolerance, expected) -> None:
    assert _one(operator, limit, actual, tolerance) == expected


@pytest.mark.parametrize(
    ("operator", "limit", "actual", "ignore_case", "expected"),
    [
        ("EQ", "Concrete", "concrete", True, "PASS"),
        ("EQ", "Concrete", "concrete", False, "FAIL"),
        ("NE", "Steel", "Concrete", False, "PASS"),
        ("EQ", True, True, False, "PASS"),
        ("EQ", False, True, False, "FAIL"),
        ("IN", ["FR60", "FR120"], "fr60", True, "PASS"),
        ("IN", ["FR60", "FR120"], "FR30", False, "FAIL"),
        ("NOT_IN", ["FR30"], "FR60", False, "PASS"),
        ("NOT_IN", ["FR30"], "FR30", False, "FAIL"),
    ],
)
def test_text_boolean_and_list_operators(operator, limit, actual, ignore_case, expected) -> None:
    assert _one(operator, limit, actual, ignore_case=ignore_case) == expected


@pytest.mark.parametrize(
    ("operator", "actual", "side"),
    [("GTE", 5, "BELOW"), ("LTE", 15, "ABOVE"), ("EQ", 5, "BELOW"), ("EQ", 15, "ABOVE"), ("NE", 10, "EQUAL")],
)
def test_failure_sides(operator, actual, side) -> None:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=10, operator=operator)]
    judged = judge(rules, [Reading.value("c", subject_id="s", actual=actual)], {"c": {"label": "C"}})
    assert judged.measurements[0].failed_limits == [{"input": "lim", "side": side}]


def test_resolution_rounds_half_up_before_comparing() -> None:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=800, operator="GTE")]
    checks = {"c": CheckSpec(label="C", unit="mm", resolution=CheckResolution(step=1))}
    judged = judge(
        rules,
        [Reading.value("c", subject_id="a", actual=799.5), Reading.value("c", subject_id="b", actual=799.4)],
        checks,
    )
    assert [(m.actual, m.verdict) for m in judged.measurements] == [(800, "PASS"), (799, "FAIL")]
    assert judged.body()["measurements"][0]["actual_raw"] == 799.5


def test_type_mismatch_is_a_programming_error() -> None:
    with pytest.raises(CheckVerdictError):
        _one("GTE", 10, "ten")


# bounds: a LOWER bound means the true value is at least the reading
@pytest.mark.parametrize(
    ("operator", "limit", "actual", "bound", "expected", "code"),
    [
        ("GTE", 400, 450, "LOWER", "PASS", None),  # true value >= 450 >= 400: settled
        ("GTE", 400, 350, "LOWER", "FAIL", "C_NOT_SETTLED"),  # could still reach 400
        ("LTE", 400, 450, "LOWER", "FAIL", None),  # already above: settled fail
        ("LTE", 400, 350, "UPPER", "PASS", None),
        ("GTE", 400, 350, "UPPER", "FAIL", None),
        ("EQ", 400, 350, "LOWER", "FAIL", "C_NOT_SETTLED"),
        ("EQ", 400, 450, "LOWER", "FAIL", None),
    ],
)
def test_bound_settles_or_fails_by_name(operator, limit, actual, bound, expected, code) -> None:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=limit, operator=operator)]
    judged = judge(rules, [Reading.value("c", subject_id="s", actual=actual, bound=bound)], {"c": {"label": "C"}})
    row = judged.measurements[0]
    assert row.verdict == expected
    assert row.reason_code == code
    assert row.verdict_caveat == {"bound": bound, "reading": actual}


def test_alternatives_agree_or_straddle() -> None:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=1600, operator="GTE")]
    checks = {"c": {"label": "C"}}
    agree = judge(
        rules,
        [
            Reading.value(
                "c", subject_id="s", alternatives={"opening": 1700, "leaf": 1650}, straddle_code="DATUM_STRADDLE"
            )
        ],
        checks,
    )
    assert agree.measurements[0].verdict == "PASS"
    straddle = judge(
        rules,
        [
            Reading.value(
                "c", subject_id="s", alternatives={"opening": 1700, "leaf": 1550}, straddle_code="DATUM_STRADDLE"
            )
        ],
        checks,
    )
    row = straddle.measurements[0]
    assert (row.verdict, row.reason_code) == ("FAIL", "DATUM_STRADDLE")
    assert "opening 1700 (PASS)" in (row.reason or "")


def test_fail_by_name_and_not_evaluable_rows() -> None:
    rules = [Rule(check="c", input="lim", role="LIMIT", value=1, operator="GTE")]
    judged = judge(
        rules,
        [
            Reading.fail_by_name("c", subject_id="a", reason_code="NO_DOOR_FOUND", reason="no door"),
            Reading.not_evaluable("c", subject_id="b", reason_code="CONFIDENCE_BELOW_MINIMUM"),
        ],
        {"c": {"label": "C"}},
    )
    body = judged.body()["measurements"]
    assert [m["verdict"] for m in body] == ["FAIL", "NOT_EVALUABLE"]
    assert body[0]["reason"] == {"code": "NO_DOOR_FOUND", "message": "no door"}
    assert "actual" not in body[0]


def test_counts_are_per_subject_across_rows_and_checks() -> None:
    rules = [
        Rule(check="width", input="w", role="LIMIT", value=100, operator="EQ"),
        Rule(check="depth", input="d", role="LIMIT", value=10, operator="EQ"),
    ]
    checks = {"width": {"label": "W"}, "depth": {"label": "D"}}
    judged = judge(
        rules,
        [
            Reading.value("width", subject_id="basin-1", actual=100),
            Reading.value("depth", subject_id="basin-1", actual=8),
            Reading.value("width", subject_id="basin-2", actual=100),
            Reading.value("depth", subject_id="basin-2", actual=10),
        ],
        checks,
    )
    assert judged.subject_counts == {"PASS": 1, "WARNING": 0, "FAIL": 1, "NOT_EVALUABLE": 0}
    assert {c.check: c.verdict_counts["FAIL"] for c in judged.checks} == {"width": 0, "depth": 1}
    assert judged.verdict == "FAIL"


def test_check_without_readings_is_not_evaluable() -> None:
    rules = [Rule(check="a", input="x", role="LIMIT", value=1, operator="GTE")]
    judged = judge(rules, [Reading.value("a", subject_id="s", actual=2)], {"a": {"label": "A"}, "b": {"label": "B"}})
    by_check = {c.check: c for c in judged.checks}
    assert by_check["a"].verdict == "PASS"
    assert by_check["b"].verdict == "NOT_EVALUABLE"
    assert by_check["b"].not_evaluated_reason == {"code": "NO_SUBJECTS_IN_SCOPE"}
    assert judged.verdict == "NOT_EVALUABLE"


def test_observations_are_never_counted() -> None:
    rules = [Rule(check="a", input="x", role="LIMIT", value=1, operator="GTE")]
    judged = judge(
        rules,
        [Reading.value("a", subject_id="s", actual=2), Reading.observation("a", extra={"band": "AT_RECOMMENDED"})],
        {"a": {"label": "A"}},
    )
    assert judged.subject_counts["PASS"] == 1
    assert judged.body()["observations"] == [{"check": "a", "kind": "observation", "band": "AT_RECOMMENDED"}]


def test_unknown_check_and_policy() -> None:
    rules = [Rule(check="a", input="x", role="LIMIT", value=1, operator="GTE")]
    with pytest.raises(CheckVerdictError, match="does not declare"):
        judge(rules, [Reading.value("zz", subject_id="s", actual=1)], {"a": {"label": "A"}})

    class OnlyIdentityDoubt:
        def check_reading(self, reading: Reading) -> None:
            if reading.kind == "not_evaluable" and not reading.reason_code.endswith("_BELOW_CONFIDENCE_THRESHOLD"):
                raise CheckVerdictError(f"{reading.reason_code} must fail by name")

    with pytest.raises(CheckVerdictError, match="must fail by name"):
        judge(
            rules,
            [Reading.not_evaluable("a", subject_id="s", reason_code="DOOR_UNRESOLVED")],
            {"a": {"label": "A"}},
            policy=OnlyIdentityDoubt(),
        )


def test_predicate_needs_a_rule() -> None:
    with pytest.raises(CheckVerdictError, match="no LIMIT"):
        judge([], [Reading.predicate("a", subject_id="s", actual=True)], {"a": {"label": "A"}})


def test_beam_example_matches_the_plan() -> None:
    """canvastekk-frontend-nextjs PLANS/PLAN-model-checker-v2.md section 5.6.7."""
    inputs = {
        "beam_length_max": 7000,
        "beam_length_warn_max": 6000,
        "beam_length_tolerance": 5,
        "include_cantilevers": False,
    }
    judged = judge(
        rules_from_inputs(BEAM_SCHEMA, inputs),
        [
            Reading.value(
                "beam_length", subject_id="B7", actual=3000, element_name="Beam B7", file_id=11, global_ids=["2O2Fr"]
            ),
            Reading.value("beam_length", subject_id="B12", actual=6800, element_name="Beam B12"),
            Reading.value("beam_length", subject_id="B3", actual=900, element_name="Beam B3"),
            Reading.not_evaluable(
                "beam_length", subject_id="B9", reason_code="NO_AXIS_GEOMETRY", reason="no axis geometry"
            ),
        ],
        BEAM_CHECKS,
    )
    assert judged.summary() == {
        "verdict": "FAIL",
        "pass_count": 1,
        "warning_count": 1,
        "fail_count": 1,
        "not_evaluable_count": 1,
    }
    body = judged.body()
    assert body["checks"][0]["filters_used"] == [{"input": "include_cantilevers", "value": False}]
    assert [m["failed_limits"] for m in body["measurements"]] == [
        [],
        [{"input": "beam_length_warn_max", "side": "ABOVE"}],
        [{"input": "beam_length_min", "side": "BELOW"}],
        [],
    ]
    assert judged.inline_outputs()["requirement_verdicts"] == {"beam_length": "FAIL"}


# --- cross-referenced checks (#285, D90) ---------------------------------------------


def _wash_basin_judge(*extra_readings: Reading):
    rules = [Rule(check="corridor_width", input="w_min", role="LIMIT", value=1200, operator="GTE")]
    checks = {"corridor_width": {"label": "Corridor width"}, "wash_basin_corridor_width": {"label": "Basin corridor"}}
    readings = [
        Reading.value("corridor_width", subject_id="c-1", actual=1500),
        Reading.cross_reference(
            "wash_basin_corridor_width",
            measured_by="corridor_width",
            reason_code="CORRIDOR_WIDTH_MEASURED_BY_CHECK_7",
            reason="Measured by check 07.",
        ),
        *extra_readings,
    ]
    return judge(rules, readings, checks)


def test_cross_referenced_check_counts_nowhere_in_the_run() -> None:
    judged = _wash_basin_judge()
    by_check = {c.check: c for c in judged.checks}
    crossed = by_check["wash_basin_corridor_width"]
    assert crossed.verdict == "NOT_EVALUABLE"
    assert crossed.cross_reference == "corridor_width"
    assert crossed.not_evaluated_reason == {
        "code": "CORRIDOR_WIDTH_MEASURED_BY_CHECK_7",
        "message": "Measured by check 07.",
    }
    assert crossed.verdict_counts == {"PASS": 0, "WARNING": 0, "FAIL": 0, "NOT_EVALUABLE": 0}
    assert judged.verdict == "PASS"
    assert judged.subject_counts == {"PASS": 1, "WARNING": 0, "FAIL": 0, "NOT_EVALUABLE": 0}
    assert judged.summary()["verdict"] == "PASS"
    assert judged.inline_outputs()["requirement_verdicts"]["wash_basin_corridor_width"] == "NOT_EVALUABLE"
    body = judged.body()
    entry = next(c for c in body["checks"] if c["check"] == "wash_basin_corridor_width")
    assert entry["cross_reference"] == "corridor_width"
    assert entry["not_evaluated_reason"]["code"] == "CORRIDOR_WIDTH_MEASURED_BY_CHECK_7"
    assert not any(m["check"] == "wash_basin_corridor_width" for m in body["measurements"])
    Draft7Validator(json.loads(CANONICAL_BODY.read_text())).validate(body)


def test_without_cross_reference_an_empty_check_still_rolls_up() -> None:
    judged = judge(
        [Rule(check="a", input="x", role="LIMIT", value=1, operator="GTE")],
        [Reading.value("a", subject_id="s", actual=2)],
        {"a": {"label": "A"}, "b": {"label": "B"}},
    )
    assert judged.verdict == "NOT_EVALUABLE"
    assert all("cross_reference" not in c for c in judged.body()["checks"])


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"measured_by": "Corridor", "reason_code": "X"}, "snake_case measured_by"),
        ({"measured_by": "wash_basin_corridor_width", "reason_code": "X"}, "to itself"),
        ({"measured_by": "corridor_width", "reason_code": "bad code"}, "UPPER_SNAKE_CASE"),
    ],
)
def test_cross_reference_reading_is_validated(kwargs: dict, fragment: str) -> None:
    with pytest.raises(CheckVerdictError, match=fragment):
        Reading.cross_reference("wash_basin_corridor_width", **kwargs)


@pytest.mark.parametrize(
    ("reading", "fragment"),
    [
        (Reading.value("wash_basin_corridor_width", subject_id="b-1", actual=1), "both a cross_reference"),
        (
            Reading.cross_reference("wash_basin_corridor_width", measured_by="corridor_width", reason_code="AGAIN"),
            "more than one",
        ),
    ],
)
def test_cross_referenced_check_takes_no_other_readings(reading: Reading, fragment: str) -> None:
    with pytest.raises(CheckVerdictError, match=fragment):
        _wash_basin_judge(reading)


def test_cross_reference_to_an_undeclared_check_is_refused() -> None:
    with pytest.raises(CheckVerdictError, match="does not declare"):
        judge(
            [],
            [Reading.cross_reference("b", measured_by="zzz", reason_code="X")],
            {"b": {"label": "B"}},
        )


def test_body_extra_is_written_and_validates() -> None:
    judged = _wash_basin_judge()
    body = judged.body(extra={"measurements": {"sets": []}, "instances": [{"gid": "g"}]})
    assert body["extra"] == {"measurements": {"sets": []}, "instances": [{"gid": "g"}]}
    Draft7Validator(json.loads(CANONICAL_BODY.read_text())).validate(body)
    assert "extra" not in judged.body()
    with pytest.raises(CheckVerdictError, match="must be an object"):
        judged.body(extra=["not", "a", "dict"])  # type: ignore[arg-type]
