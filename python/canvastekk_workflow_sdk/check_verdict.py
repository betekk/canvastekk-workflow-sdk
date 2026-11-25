"""Check verdicts: the one calculation every check node uses (#283, epic tracker#4332).

A check node measures; this module judges. The node marks the inputs that
decide a verdict with ``x-verdict`` and describes each check in its
manifest's ``checks`` map. At run time:

1. :func:`rules_from_inputs` turns the marked inputs' run values into
   :class:`Rule` objects (limits with their tolerance, and filters).
2. The node's ``measure()`` returns :class:`Reading` objects.
3. :func:`judge` classifies every reading, rolls verdicts up per subject,
   per check and for the run, and returns a :class:`JudgedResult` that
   builds the ``model_check.check`` 1.0.0 body, the header ``summary`` and
   the node's inline outputs.

The mark::

    "threshold_mm": {"type": "number", "default": 1000,
                     "x-verdict": {"check": "corridor_width", "role": "LIMIT", "operator": "GTE"}}

Roles: ``LIMIT`` (broken → FAIL), ``WARNING_LIMIT`` (broken → WARNING),
``TOLERANCE`` (widens limits), ``FILTER`` (decides what is checked).
Operators: ``GT``, ``GTE``, ``LT``, ``LTE``, ``EQ``, ``NE``, ``IN``, ``NOT_IN``.
Roll-up everywhere: FAIL > NOT_EVALUABLE > WARNING > PASS; nothing → NOT_EVALUABLE.
Counts are per subject (``subject_id``), never per row. Guide: ``docs/CHECK-VERDICT.md``.
"""

from __future__ import annotations

import enum
import json
import math
import re
import string
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from importlib import resources
from typing import Any, Literal, Protocol

from jsonschema import Draft7Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator

from canvastekk_workflow_sdk.exceptions import NodeOutputValidationError

VERDICT_MARK = "x-verdict"
"""Input-schema extension that marks an input as a verdict variable."""

CHECK_RESULT_SCHEMA = "model_check.check"
"""Result-file label of the body :meth:`JudgedResult.body` builds."""

CHECK_RESULT_SCHEMA_VERSION = "1.0.0"
CHECK_RESULT_SCHEMA_VERSION_2_0_0 = "2.0.0"
"""Version of that body."""

FLOAT_ALLOWANCE = 1e-10
"""Absolute allowance on inclusive numeric bounds (float noise, not a tolerance)."""

CHECK_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

STATEMENT_PLACEHOLDERS: frozenset[str] = frozenset({"element", "label", "actual", "unit", "limits", "broken", "reason"})
"""Placeholders a ``checks[key].statements`` template may use."""


class TekkCheckRoleEnum(str, enum.Enum):  # noqa: UP042 — str mixin keeps JSON values plain
    """What a marked input does for its check."""

    LIMIT = "LIMIT"
    WARNING_LIMIT = "WARNING_LIMIT"
    TOLERANCE = "TOLERANCE"
    FILTER = "FILTER"


class TekkCheckOperatorEnum(str, enum.Enum):  # noqa: UP042
    """How a measured value is compared with a limit (passes when true)."""

    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"


class TekkWorkflowRunVerdictEnum(str, enum.Enum):  # noqa: UP042
    """Outcome of a measurement, a check and a run."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class TekkCheckRoundingEnum(str, enum.Enum):  # noqa: UP042
    """How a measured value is rounded to the check's resolution."""

    HALF_UP = "HALF_UP"
    HALF_EVEN = "HALF_EVEN"
    FLOOR = "FLOOR"
    CEILING = "CEILING"


VERDICT_PRECEDENCE: tuple[str, ...] = ("FAIL", "NOT_EVALUABLE", "WARNING", "PASS")
"""Roll-up order, worst first (D90)."""

_RANK = {verdict: index for index, verdict in enumerate(VERDICT_PRECEDENCE)}
_NUMERIC_OPERATORS = frozenset({"GT", "GTE", "LT", "LTE", "EQ", "NE"})
_EXACT_OPERATORS = frozenset({"EQ", "NE"})
_LIST_OPERATORS = frozenset({"IN", "NOT_IN"})
_JUDGED_KINDS = frozenset({"value", "predicate", "fail_by_name", "not_evaluable"})


class CheckVerdictError(NodeOutputValidationError):
    """A mark, rule or reading breaks the verdict contract (a node programming error)."""


def rollup(verdicts: Iterable[str]) -> str:
    """Combine verdicts, worst first: FAIL > NOT_EVALUABLE > WARNING > PASS.

    Args:
        verdicts: Verdict strings.

    Returns:
        The combined verdict; ``NOT_EVALUABLE`` when there are none.

    Raises:
        CheckVerdictError: On an unknown verdict.
    """
    best: str | None = None
    for verdict in verdicts:
        value = verdict.value if isinstance(verdict, enum.Enum) else verdict
        if value not in _RANK:
            raise CheckVerdictError(f"Unknown verdict {value!r}")
        if best is None or _RANK[value] < _RANK[best]:
            best = value
    return best or "NOT_EVALUABLE"


# --- manifest: checks map ---------------------------------------------------


class CheckResolution(BaseModel):
    """Rounding applied to a measured value before it is compared."""

    model_config = ConfigDict(extra="forbid")

    step: float = Field(gt=0, description="Resolution step, e.g. 1 for whole millimetres.")
    rounding: TekkCheckRoundingEnum = Field(default=TekkCheckRoundingEnum.HALF_UP)


class CheckSpec(BaseModel):
    """One entry of a manifest's ``checks`` map."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200, description="Readable name, e.g. 'Beam length'.")
    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        exclude_if=lambda value: value is None,
        description="What the subcheck evaluates and why it matters.",
    )
    unit: str | None = Field(default=None, max_length=32, description="Unit of measured values, e.g. 'mm'.")
    resolution: CheckResolution | None = Field(default=None)
    statements: dict[TekkWorkflowRunVerdictEnum, str] | None = Field(
        default=None,
        description="Optional per-verdict sentence templates; placeholders from STATEMENT_PLACEHOLDERS.",
    )

    @field_validator("statements")
    @classmethod
    def _validate_placeholders(
        cls, value: dict[TekkWorkflowRunVerdictEnum, str] | None
    ) -> dict[TekkWorkflowRunVerdictEnum, str] | None:
        for verdict, template in (value or {}).items():
            unknown = sorted(set(_placeholders(template)) - STATEMENT_PLACEHOLDERS)
            if unknown:
                raise ValueError(
                    f"statement for {verdict.value} uses unknown placeholder(s) {unknown}; "
                    f"allowed: {sorted(STATEMENT_PLACEHOLDERS)}"
                )
        return value


def _placeholders(template: str) -> list[str]:
    try:
        return [name for _, name, _, _ in string.Formatter().parse(template) if name is not None]
    except ValueError as exc:
        raise ValueError(f"statement template is malformed: {exc}") from exc


# --- marks --------------------------------------------------------------------


def _type_set(prop: Mapping[str, Any]) -> set[str]:
    declared = prop.get("type")
    types = set(declared) if isinstance(declared, list) else ({declared} if isinstance(declared, str) else set())
    types.discard("null")
    return types


def _value_kind(prop: Mapping[str, Any]) -> str | None:
    """Classify an input: ``number``, ``string``, ``boolean``, ``string_list`` or None."""
    types = _type_set(prop)
    if types and types <= {"number", "integer"}:
        return "number"
    if types == {"string"}:
        return "string"
    if types == {"boolean"}:
        return "boolean"
    if types == {"array"}:
        items = prop.get("items")
        if isinstance(items, Mapping) and _type_set(items) == {"string"}:
            return "string_list"
    return None


_ALLOWED_OPERATORS: dict[str, frozenset[str]] = {
    "number": _NUMERIC_OPERATORS,
    "string": _EXACT_OPERATORS,
    "boolean": _EXACT_OPERATORS,
    "string_list": _LIST_OPERATORS,
}


def _mark_checks(mark: Mapping[str, Any]) -> list[str]:
    value = mark.get("check")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return list(value)
    return []


def marked_inputs(input_schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{input name: property schema}`` for every input carrying ``x-verdict``."""
    properties = input_schema.get("properties") if isinstance(input_schema, Mapping) else None
    if not isinstance(properties, Mapping):
        return {}
    return {
        name: dict(prop)
        for name, prop in properties.items()
        if isinstance(prop, Mapping) and prop.get(VERDICT_MARK) is not None
    }


def verdict_mark_errors(
    input_schema: Mapping[str, Any],
    checks: Mapping[str, Any] | None,
) -> list[str]:
    """Return problems with a node's ``x-verdict`` marks and ``checks`` map (empty = fine).

    Node-side rules (D85, D88): mark shape; known check keys; the operator
    fits the input's type; ``ignore_case`` only on text; ``TOLERANCE`` is a
    number with ``applies_to`` naming numeric limits of the same check; at
    most one tolerance per limit; a marked check other than pure filters
    has a ``LIMIT``; check keys are snake_case.

    Args:
        input_schema: The node's input JSON Schema.
        checks: The manifest ``checks`` map (``CheckSpec`` or dict values), or None.

    Returns:
        Human-readable problems.
    """
    problems: list[str] = []
    check_keys = set(checks or {})
    for key in sorted(check_keys):
        if not CHECK_KEY_PATTERN.fullmatch(key):
            problems.append(f"checks key {key!r} must be snake_case (^[a-z][a-z0-9_]*$).")
    marks = marked_inputs(input_schema)
    roles_by_check: dict[str, list[tuple[str, str, str | None]]] = {}
    tolerated: dict[str, str] = {}
    for name, prop in marks.items():
        mark = prop[VERDICT_MARK]
        where = f"Input '{name}' {VERDICT_MARK}"
        if not isinstance(mark, Mapping):
            problems.append(f"{where} must be an object.")
            continue
        unknown_keys = sorted(set(mark) - {"check", "role", "operator", "ignore_case", "applies_to"})
        if unknown_keys:
            problems.append(f"{where} has unknown key(s) {unknown_keys}.")
        mark_checks = _mark_checks(mark)
        if not mark_checks:
            problems.append(f"{where}.check must be a check key or a non-empty list of check keys.")
        for check in mark_checks:
            if check not in check_keys:
                problems.append(f"{where}.check {check!r} is not declared in the manifest's checks map.")
        role = mark.get("role")
        if role not in TekkCheckRoleEnum.__members__:
            problems.append(f"{where}.role must be one of {list(TekkCheckRoleEnum.__members__)}.")
            continue
        operator = mark.get("operator")
        kind = _value_kind(prop)
        if role in ("LIMIT", "WARNING_LIMIT"):
            if operator not in TekkCheckOperatorEnum.__members__:
                problems.append(f"{where}.operator must be one of {list(TekkCheckOperatorEnum.__members__)}.")
            elif kind is None:
                problems.append(f"{where}: a {role} needs a number, string, boolean or string-list input.")
            elif operator not in _ALLOWED_OPERATORS[kind]:
                problems.append(
                    f"{where}.operator {operator} does not fit a {kind} input; "
                    f"allowed: {sorted(_ALLOWED_OPERATORS[kind])}."
                )
        elif operator is not None:
            problems.append(f"{where}: role {role} takes no operator.")
        if mark.get("ignore_case") is not None:
            if not isinstance(mark.get("ignore_case"), bool):
                problems.append(f"{where}.ignore_case must be a boolean.")
            elif kind not in ("string", "string_list") or role not in ("LIMIT", "WARNING_LIMIT"):
                problems.append(f"{where}.ignore_case applies only to text limits.")
        if mark.get("applies_to") is not None and role != "TOLERANCE":
            problems.append(f"{where}.applies_to is only for TOLERANCE.")
        if role == "TOLERANCE":
            if kind != "number":
                problems.append(f"{where}: a TOLERANCE must be a number input.")
            default = prop.get("default")
            if isinstance(default, (int, float)) and not isinstance(default, bool) and default < 0:
                problems.append(f"{where}: a TOLERANCE default must be >= 0.")
        for check in mark_checks:
            roles_by_check.setdefault(check, []).append((name, role, kind))
    for name, prop in marks.items():
        mark = prop.get(VERDICT_MARK)
        if not isinstance(mark, Mapping) or mark.get("role") != "TOLERANCE":
            continue
        for check in _mark_checks(mark):
            numeric_limits = {
                n for n, r, k in roles_by_check.get(check, []) if r in ("LIMIT", "WARNING_LIMIT") and k == "number"
            }
            applies_to = mark.get("applies_to")
            if applies_to is None:
                targets = {n for n, r, k in roles_by_check.get(check, []) if r == "LIMIT" and k == "number"}
            elif isinstance(applies_to, list) and all(isinstance(v, str) for v in applies_to):
                targets = set(applies_to)
                for target in sorted(targets - numeric_limits):
                    problems.append(
                        f"Input '{name}' {VERDICT_MARK}.applies_to names '{target}', "
                        f"which is not a numeric limit of check {check!r}."
                    )
            else:
                problems.append(f"Input '{name}' {VERDICT_MARK}.applies_to must be a list of input names.")
                targets = set()
            for target in sorted(targets & numeric_limits):
                previous = tolerated.get(f"{check}/{target}")
                if previous and previous != name:
                    problems.append(
                        f"Limit '{target}' of check {check!r} has two tolerances: '{previous}' and '{name}'."
                    )
                tolerated[f"{check}/{target}"] = name
    for check, entries in sorted(roles_by_check.items()):
        roles = {role for _, role, _ in entries}
        if roles - {"FILTER"} and "LIMIT" not in roles:
            problems.append(f"Check {check!r} has verdict inputs but no LIMIT.")
    return problems


# --- rules --------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One limit or filter of a check, with the value this run uses."""

    check: str
    input: str
    role: str
    value: Any
    operator: str | None = None
    tolerance: float | int = 0
    ignore_case: bool = False
    fixed: bool = False

    def as_limit_used(self) -> dict[str, Any]:
        """Return the ``limits_used`` entry of the body."""
        entry: dict[str, Any] = {
            "input": self.input,
            "role": self.role,
            "operator": self.operator,
            "value": self.value,
            "tolerance": self.tolerance,
        }
        if self.ignore_case:
            entry["ignore_case"] = True
        if self.fixed:
            entry["fixed"] = True
        return entry


def _resolved_value(name: str, prop: Mapping[str, Any], inputs: Mapping[str, Any]) -> tuple[Any, bool]:
    if "const" in prop:
        return prop["const"], True
    if name in inputs:
        return inputs[name], False
    return prop.get("default"), False


def marked_input_values(input_schema: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Return the value each marked input has in this run (input, else const or default).

    This is the 1.1.0 header ``inputs`` value: the verdict inputs only.
    """
    return {name: _resolved_value(name, prop, inputs)[0] for name, prop in marked_inputs(input_schema).items()}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def rules_from_inputs(input_schema: Mapping[str, Any], inputs: Mapping[str, Any]) -> list[Rule]:
    """Build the run's rules from the marked inputs' values.

    The value is the run input, else the schema ``const`` / ``default``. A
    ``WARNING_LIMIT`` without a value is dropped (not wired); a ``LIMIT``
    without one is an error. Each ``TOLERANCE`` is folded into the limits it
    applies to (all numeric ``LIMIT``\\ s of its check when ``applies_to`` is
    omitted).

    Args:
        input_schema: The node's input JSON Schema.
        inputs: The run's validated inputs.

    Returns:
        Limits and filters, in input-schema order.

    Raises:
        CheckVerdictError: A limit has no value or a value of the wrong type,
            or a tolerance is negative.
    """
    marks = marked_inputs(input_schema)
    tolerances: dict[tuple[str, str], float | int] = {}
    for name, prop in marks.items():
        mark = prop[VERDICT_MARK]
        if mark.get("role") != "TOLERANCE":
            continue
        value, _ = _resolved_value(name, prop, inputs)
        if value is None:
            continue
        if not _is_number(value) or value < 0:
            raise CheckVerdictError(f"Tolerance '{name}' must be a number >= 0, got {value!r}")
        for check in _mark_checks(mark):
            targets = mark.get("applies_to")
            if targets is None:
                targets = [
                    n
                    for n, p in marks.items()
                    if check in _mark_checks(p[VERDICT_MARK])
                    and p[VERDICT_MARK].get("role") == "LIMIT"
                    and _value_kind(p) == "number"
                ]
            for target in targets:
                tolerances[(check, target)] = value
    rules: list[Rule] = []
    for name, prop in marks.items():
        mark = prop[VERDICT_MARK]
        role = mark.get("role")
        if role == "TOLERANCE":
            continue
        value, fixed = _resolved_value(name, prop, inputs)
        for check in _mark_checks(mark):
            if role == "FILTER":
                rules.append(Rule(check=check, input=name, role=role, value=value, fixed=fixed))
                continue
            if value is None:
                if role == "WARNING_LIMIT":
                    continue
                raise CheckVerdictError(f"Limit '{name}' of check {check!r} has no value in this run")
            kind = _value_kind(prop)
            if kind == "number" and not _is_number(value):
                raise CheckVerdictError(f"Limit '{name}' must be a number, got {value!r}")
            if kind == "string_list" and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                raise CheckVerdictError(f"Limit '{name}' must be a list of strings, got {value!r}")
            rules.append(
                Rule(
                    check=check,
                    input=name,
                    role=role,
                    value=value,
                    operator=mark.get("operator"),
                    tolerance=tolerances.get((check, name), 0),
                    ignore_case=bool(mark.get("ignore_case", False)),
                    fixed=fixed,
                )
            )
    return rules


# --- readings -----------------------------------------------------------------

ReadingKind = Literal["value", "predicate", "fail_by_name", "not_evaluable", "observation", "scope", "cross_reference"]


@dataclass(frozen=True)
class Reading:
    """What a check node's ``measure()`` reports. Build with the class methods."""

    kind: ReadingKind
    check: str
    subject_id: str | None = None
    actual: Any = None
    bound: Literal["LOWER", "UPPER"] | None = None
    alternatives: Mapping[str, Any] | None = None
    straddle_code: str | None = None
    reason_code: str | None = None
    reason: str | None = None
    element_name: str | None = None
    file_id: int | str | None = None
    global_ids: tuple[str, ...] = ()
    extra: Mapping[str, Any] | None = None
    measured_by: str | None = None

    def __post_init__(self) -> None:
        if self.kind in _JUDGED_KINDS and not self.subject_id:
            raise CheckVerdictError(f"A {self.kind} reading of check {self.check!r} needs a subject_id")
        if self.reason_code is not None and not REASON_CODE_PATTERN.fullmatch(self.reason_code):
            raise CheckVerdictError(f"Reason code {self.reason_code!r} must be UPPER_SNAKE_CASE")
        if self.kind in ("fail_by_name", "not_evaluable", "cross_reference") and not self.reason_code:
            raise CheckVerdictError(f"A {self.kind} reading needs a reason_code")
        if self.kind == "cross_reference":
            if not self.measured_by or not CHECK_KEY_PATTERN.fullmatch(self.measured_by):
                raise CheckVerdictError(
                    f"A cross_reference reading of check {self.check!r} needs a snake_case measured_by"
                )
            if self.measured_by == self.check:
                raise CheckVerdictError(f"Check {self.check!r} cannot be cross-referenced to itself")
        if self.alternatives is not None:
            if not self.alternatives:
                raise CheckVerdictError("alternatives must not be empty")
            if not self.straddle_code:
                raise CheckVerdictError("a reading with alternatives needs a straddle_code")
            if not REASON_CODE_PATTERN.fullmatch(self.straddle_code):
                raise CheckVerdictError(f"Straddle code {self.straddle_code!r} must be UPPER_SNAKE_CASE")
            if self.bound is not None:
                raise CheckVerdictError("a reading cannot carry both bound and alternatives")

    @classmethod
    def value(
        cls,
        check: str,
        *,
        subject_id: str,
        actual: Any = None,
        bound: Literal["LOWER", "UPPER"] | None = None,
        alternatives: Mapping[str, Any] | None = None,
        straddle_code: str | None = None,
        element_name: str | None = None,
        file_id: int | str | None = None,
        global_ids: Sequence[str] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> Reading:
        """A measured value. ``bound`` marks a reading that bounds the true value
        (``LOWER``: the true value is at least ``actual``). ``alternatives``
        holds several readings of the same subject (e.g. datums) that must agree.
        """
        if actual is None and alternatives:
            actual = next(iter(alternatives.values()))
        return cls(
            kind="value",
            check=check,
            subject_id=subject_id,
            actual=actual,
            bound=bound,
            alternatives=dict(alternatives) if alternatives is not None else None,
            straddle_code=straddle_code,
            element_name=element_name,
            file_id=file_id,
            global_ids=tuple(global_ids),
            extra=extra,
        )

    @classmethod
    def predicate(
        cls,
        check: str,
        *,
        subject_id: str,
        actual: bool | str,
        element_name: str | None = None,
        file_id: int | str | None = None,
        global_ids: Sequence[str] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> Reading:
        """A yes/no or text finding, judged against the check's (often fixed) rule."""
        return cls(
            kind="predicate",
            check=check,
            subject_id=subject_id,
            actual=actual,
            element_name=element_name,
            file_id=file_id,
            global_ids=tuple(global_ids),
            extra=extra,
        )

    @classmethod
    def fail_by_name(
        cls,
        check: str,
        *,
        subject_id: str,
        reason_code: str,
        reason: str | None = None,
        element_name: str | None = None,
        file_id: int | str | None = None,
        global_ids: Sequence[str] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> Reading:
        """A present subject the model cannot support: FAIL with a named reason, no value."""
        return cls(
            kind="fail_by_name",
            check=check,
            subject_id=subject_id,
            reason_code=reason_code,
            reason=reason,
            element_name=element_name,
            file_id=file_id,
            global_ids=tuple(global_ids),
            extra=extra,
        )

    @classmethod
    def not_evaluable(
        cls,
        check: str,
        *,
        subject_id: str,
        reason_code: str,
        reason: str | None = None,
        element_name: str | None = None,
        file_id: int | str | None = None,
        global_ids: Sequence[str] = (),
        extra: Mapping[str, Any] | None = None,
    ) -> Reading:
        """A subject that could not be judged (absent, or identity in doubt)."""
        return cls(
            kind="not_evaluable",
            check=check,
            subject_id=subject_id,
            reason_code=reason_code,
            reason=reason,
            element_name=element_name,
            file_id=file_id,
            global_ids=tuple(global_ids),
            extra=extra,
        )

    @classmethod
    def cross_reference(
        cls,
        check: str,
        *,
        measured_by: str,
        reason_code: str,
        reason: str | None = None,
    ) -> Reading:
        """The whole check is measured by another check (D90, #285).

        The check reports NOT_EVALUABLE with ``reason_code``, its ``checks[]``
        entry carries ``cross_reference: measured_by``, and it is left out of
        the run verdict and the run counts. A check takes either one
        cross-reference reading or judged readings, never both.
        """
        return cls(kind="cross_reference", check=check, reason_code=reason_code, reason=reason, measured_by=measured_by)

    @classmethod
    def observation(cls, check: str, *, extra: Mapping[str, Any], subject_id: str | None = None) -> Reading:
        """Evidence that is shown but never judged or counted."""
        return cls(kind="observation", check=check, subject_id=subject_id, extra=extra)

    @classmethod
    def scope(cls, check: str, *, extra: Mapping[str, Any], subject_id: str | None = None) -> Reading:
        """A scope disposition (what was in or out of scope); never judged or counted."""
        return cls(kind="scope", check=check, subject_id=subject_id, extra=extra)


class VerdictPolicy(Protocol):
    """App rules on readings, e.g. which reason codes may be NOT_EVALUABLE (D99)."""

    def check_reading(self, reading: Reading) -> None:
        """Raise :class:`CheckVerdictError` when the reading breaks the app's rules."""
        ...


# --- judging ------------------------------------------------------------------


def _apply_resolution(value: float, resolution: CheckResolution | None) -> float:
    if resolution is None:
        return value
    step = Decimal(repr(resolution.step))
    quotient = Decimal(repr(value)) / step
    mode = resolution.rounding
    if mode == TekkCheckRoundingEnum.HALF_UP:
        units = (quotient + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR")
    elif mode == TekkCheckRoundingEnum.HALF_EVEN:
        units = quotient.to_integral_value(rounding="ROUND_HALF_EVEN")
    elif mode == TekkCheckRoundingEnum.FLOOR:
        units = quotient.to_integral_value(rounding="ROUND_FLOOR")
    else:
        units = quotient.to_integral_value(rounding="ROUND_CEILING")
    return float(units * step)


def _norm(value: Any, ignore_case: bool) -> Any:
    return value.casefold() if ignore_case and isinstance(value, str) else value


def _rule_fails(rule: Rule, actual: Any) -> str | None:
    """Return the failure side when ``actual`` breaks ``rule``, else None."""
    op = rule.operator
    if op in _LIST_OPERATORS:
        if not isinstance(actual, str):
            raise CheckVerdictError(f"Check {rule.check!r}: {op} needs a text reading, got {actual!r}")
        members = {_norm(v, rule.ignore_case) for v in rule.value}
        inside = _norm(actual, rule.ignore_case) in members
        if op == "IN":
            return None if inside else "NOT_IN"
        return "IN" if inside else None
    if _is_number(rule.value):
        if not _is_number(actual):
            raise CheckVerdictError(f"Check {rule.check!r}: limit '{rule.input}' needs a number, got {actual!r}")
        limit, t = float(rule.value), rule.tolerance
        if op == "GT":
            return None if actual > limit - t else "BELOW"
        if op == "GTE":
            return None if actual >= limit - t - FLOAT_ALLOWANCE else "BELOW"
        if op == "LT":
            return None if actual < limit + t else "ABOVE"
        if op == "LTE":
            return None if actual <= limit + t + FLOAT_ALLOWANCE else "ABOVE"
        if op == "EQ":
            if abs(actual - limit) <= t + FLOAT_ALLOWANCE:
                return None
            return "BELOW" if actual < limit else "ABOVE"
        if op == "NE":
            return None if abs(actual - limit) > t else "EQUAL"
    if op in _EXACT_OPERATORS:
        if type(actual) is not type(rule.value) and not (isinstance(actual, str) and isinstance(rule.value, str)):
            raise CheckVerdictError(
                f"Check {rule.check!r}: limit '{rule.input}' is {type(rule.value).__name__}, reading is {actual!r}"
            )
        equal = _norm(actual, rule.ignore_case) == _norm(rule.value, rule.ignore_case)
        if op == "EQ":
            return None if equal else "MISMATCH"
        return "EQUAL" if equal else None
    raise CheckVerdictError(f"Check {rule.check!r}: operator {op!r} cannot judge {actual!r}")


def _bound_outcome(rule: Rule, actual: float, bound: str) -> tuple[str, str | None]:
    """Classify a bounding reading against one numeric rule.

    Returns ``("pass" | "fail" | "open", side)``: settled pass, settled fail,
    or not decided by the bound.
    """
    side = _rule_fails(rule, actual)
    op = rule.operator
    upward = bound == "LOWER"  # the true value is >= actual
    if op in ("GT", "GTE"):
        if upward:
            return ("pass", None) if side is None else ("open", None)
        return ("fail", side) if side is not None else ("open", None)
    if op in ("LT", "LTE"):
        if upward:
            return ("fail", side) if side is not None else ("open", None)
        return ("pass", None) if side is None else ("open", None)
    if op == "EQ":
        if side == ("ABOVE" if upward else "BELOW"):
            return "fail", side
        return "open", None
    if op == "NE":
        if side is None and ((upward and actual > rule.value) or (not upward and actual < rule.value)):
            return "pass", None
        return "open", None
    return ("pass", None) if side is None else ("fail", side)


@dataclass
class JudgedMeasurement:
    """One judged reading (a row of the body's ``measurements``)."""

    reading: Reading
    verdict: str
    actual: Any = None
    failed_limits: list[dict[str, str]] = field(default_factory=list)
    reason_code: str | None = None
    reason: str | None = None
    verdict_caveat: dict[str, Any] | None = None

    def to_body(self) -> dict[str, Any]:
        """Return the body row."""
        r = self.reading
        row: dict[str, Any] = {
            "check": r.check,
            "subject_id": r.subject_id,
            "kind": r.kind,
            "verdict": self.verdict,
            "failed_limits": list(self.failed_limits),
        }
        if r.element_name is not None:
            row["element_name"] = r.element_name
        if r.file_id is not None:
            row["file_id"] = r.file_id
        if r.global_ids:
            row["global_ids"] = list(r.global_ids)
        if r.kind in ("value", "predicate"):
            row["actual"] = self.actual
            if r.kind == "value" and self.actual != r.actual:
                row["actual_raw"] = r.actual
        if r.bound is not None:
            row["bound"] = r.bound
        if r.alternatives is not None:
            row["alternatives"] = dict(r.alternatives)
        if self.reason_code is not None:
            reason: dict[str, Any] = {"code": self.reason_code}
            if self.reason:
                reason["message"] = self.reason
            row["reason"] = reason
        if self.verdict_caveat is not None:
            row["verdict_caveat"] = self.verdict_caveat
        if r.extra:
            row["extra"] = dict(r.extra)
        return row


@dataclass
class JudgedCheck:
    """One check's outcome (an entry of the body's ``checks``)."""

    check: str
    verdict: str
    verdict_counts: dict[str, int]
    limits_used: list[dict[str, Any]]
    filters_used: list[dict[str, Any]]
    not_evaluated_reason: dict[str, str] | None = None
    cross_reference: str | None = None
    """The check that measures this one (#285); such a check counts nowhere in the run."""

    def to_body(self) -> dict[str, Any]:
        """Return the body entry."""
        entry: dict[str, Any] = {
            "check": self.check,
            "verdict": self.verdict,
            "verdict_counts": dict(self.verdict_counts),
            "limits_used": list(self.limits_used),
            "filters_used": list(self.filters_used),
        }
        if self.not_evaluated_reason is not None:
            entry["not_evaluated_reason"] = dict(self.not_evaluated_reason)
        if self.cross_reference is not None:
            entry["cross_reference"] = self.cross_reference
        return entry


def _empty_counts() -> dict[str, int]:
    return {"PASS": 0, "WARNING": 0, "FAIL": 0, "NOT_EVALUABLE": 0}


def _count_subjects(rows: Iterable[JudgedMeasurement]) -> dict[str, int]:
    by_subject: dict[str, list[str]] = {}
    for row in rows:
        by_subject.setdefault(str(row.reading.subject_id), []).append(row.verdict)
    counts = _empty_counts()
    for verdicts in by_subject.values():
        counts[rollup(verdicts)] += 1
    return counts


@dataclass
class JudgedResult:
    """Everything :func:`judge` decided."""

    checks: list[JudgedCheck]
    measurements: list[JudgedMeasurement]
    observations: list[Reading]
    verdict: str
    subject_counts: dict[str, int]

    def summary(self) -> dict[str, Any]:
        """Return the header ``summary`` (counts are subjects, D92a)."""
        return {
            "verdict": self.verdict,
            "pass_count": self.subject_counts["PASS"],
            "warning_count": self.subject_counts["WARNING"],
            "fail_count": self.subject_counts["FAIL"],
            "not_evaluable_count": self.subject_counts["NOT_EVALUABLE"],
        }

    def inline_outputs(self) -> dict[str, Any]:
        """Return the node outputs kept beside the result file (D91b)."""
        return {
            "verdict": self.verdict,
            "verdict_counts": dict(self.subject_counts),
            "requirement_verdicts": {c.check: c.verdict for c in self.checks},
        }

    def body(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return the ``model_check.check`` 1.0.0 body, validated against its schema.

        Args:
            extra: The check's viewer evidence, written as the body's top-level
                ``extra`` (#285); omitted when ``None``.

        Raises:
            CheckVerdictError: When the body breaks the published schema.
        """
        body: dict[str, Any] = {
            "checks": [c.to_body() for c in self.checks],
            "measurements": [m.to_body() for m in self.measurements],
        }
        if self.observations:
            body["observations"] = [
                {
                    "check": o.check,
                    "kind": o.kind,
                    **({"subject_id": o.subject_id} if o.subject_id else {}),
                    **dict(o.extra or {}),
                }
                for o in self.observations
            ]
        if extra is not None:
            if not isinstance(extra, Mapping):
                raise CheckVerdictError(f"body extra must be an object, got {type(extra).__name__}")
            body["extra"] = dict(extra)
        errors = sorted(_body_validator().iter_errors(body), key=lambda e: list(e.absolute_path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.absolute_path) or "(root)"
            raise CheckVerdictError(f"model_check.check body is invalid at {where}: {first.message}")
        return body


@cache
def load_check_body_schema(version: str = CHECK_RESULT_SCHEMA_VERSION) -> dict[str, Any]:
    """Return the packaged ``model_check.check`` body JSON Schema."""
    if version not in (CHECK_RESULT_SCHEMA_VERSION, CHECK_RESULT_SCHEMA_VERSION_2_0_0):
        raise CheckVerdictError(f"Unsupported model_check.check body version {version!r}")
    root = resources.files("canvastekk_workflow_sdk").joinpath("data", "schemas", "result-body", CHECK_RESULT_SCHEMA)
    return json.loads(root.joinpath(f"{version}.json").read_text(encoding="utf-8"))


@cache
def _body_validator() -> Draft7Validator:
    return Draft7Validator(load_check_body_schema())


def _judge_numeric(
    reading: Reading, actual_raw: Any, limits: list[Rule], warnings: list[Rule], spec: CheckSpec | None
) -> JudgedMeasurement:
    if not _is_number(actual_raw):
        raise CheckVerdictError(f"Check {reading.check!r}: a value reading needs a number, got {actual_raw!r}")
    resolution = spec.resolution if spec else None
    actual: float | int = _apply_resolution(float(actual_raw), resolution)
    whole_step = resolution is not None and float(resolution.step).is_integer()
    if float(actual).is_integer() and (isinstance(actual_raw, int) or whole_step):
        actual = int(actual)
    if reading.bound is None:
        failed = [(r, s) for r in limits if (s := _rule_fails(r, actual)) is not None]
        if failed:
            return JudgedMeasurement(reading, "FAIL", actual, [{"input": r.input, "side": s} for r, s in failed])
        warned = [(r, s) for r in warnings if (s := _rule_fails(r, actual)) is not None]
        if warned:
            return JudgedMeasurement(reading, "WARNING", actual, [{"input": r.input, "side": s} for r, s in warned])
        return JudgedMeasurement(reading, "PASS", actual)
    outcomes = [(r, *_bound_outcome(r, actual, reading.bound)) for r in limits]
    caveat = {"bound": reading.bound, "reading": actual}
    settled_fail = [(r, s) for r, o, s in outcomes if o == "fail"]
    if settled_fail:
        return JudgedMeasurement(
            reading,
            "FAIL",
            actual,
            [{"input": r.input, "side": s or "BELOW"} for r, s in settled_fail],
            verdict_caveat=caveat,
        )
    if any(o == "open" for _, o, _ in outcomes):
        return JudgedMeasurement(
            reading,
            "FAIL",
            actual,
            reason_code=f"{reading.check.upper()}_NOT_SETTLED",
            reason=f"The reading bounds the value ({reading.bound.lower()} bound) but does not settle the rule.",
            verdict_caveat=caveat,
        )
    warned: list[tuple[Rule, str | None]] = []
    for rule in warnings:
        outcome, side = _bound_outcome(rule, actual, reading.bound)
        if outcome == "fail":
            warned.append((rule, side))
    if warned:
        return JudgedMeasurement(
            reading,
            "WARNING",
            actual,
            [{"input": r.input, "side": s or "ABOVE"} for r, s in warned],
            verdict_caveat=caveat,
        )
    return JudgedMeasurement(reading, "PASS", actual, verdict_caveat=caveat)


def _judge_reading(reading: Reading, rules: list[Rule], spec: CheckSpec | None) -> JudgedMeasurement:
    if reading.kind == "fail_by_name":
        return JudgedMeasurement(reading, "FAIL", reason_code=reading.reason_code, reason=reading.reason)
    if reading.kind == "not_evaluable":
        return JudgedMeasurement(reading, "NOT_EVALUABLE", reason_code=reading.reason_code, reason=reading.reason)
    limits = [r for r in rules if r.role == "LIMIT"]
    warnings = [r for r in rules if r.role == "WARNING_LIMIT"]
    if not limits:
        raise CheckVerdictError(f"Check {reading.check!r} has no LIMIT to judge a {reading.kind} reading against")
    if reading.kind == "predicate":
        failed = [(r, s) for r in limits if (s := _rule_fails(r, reading.actual)) is not None]
        if failed:
            return JudgedMeasurement(
                reading, "FAIL", reading.actual, [{"input": r.input, "side": s} for r, s in failed]
            )
        warned = [(r, s) for r in warnings if (s := _rule_fails(r, reading.actual)) is not None]
        if warned:
            return JudgedMeasurement(
                reading, "WARNING", reading.actual, [{"input": r.input, "side": s} for r, s in warned]
            )
        return JudgedMeasurement(reading, "PASS", reading.actual)
    if reading.alternatives is None:
        return _judge_numeric(reading, reading.actual, limits, warnings, spec)
    judged = {name: _judge_numeric(reading, raw, limits, warnings, spec) for name, raw in reading.alternatives.items()}
    verdicts = {j.verdict for j in judged.values()}
    first = next(iter(judged.values()))
    if len(verdicts) == 1:
        failed: list[dict[str, str]] = []
        for j in judged.values():
            for item in j.failed_limits:
                if item not in failed:
                    failed.append(item)
        return JudgedMeasurement(reading, first.verdict, first.actual, failed)
    readings = ", ".join(f"{name} {j.actual} ({j.verdict})" for name, j in judged.items())
    return JudgedMeasurement(
        reading,
        "FAIL",
        first.actual,
        reason_code=reading.straddle_code,
        reason=f"The alternative readings disagree: {readings}.",
    )


def judge(
    rules: Sequence[Rule],
    readings: Sequence[Reading],
    checks: Mapping[str, Any],
    policy: VerdictPolicy | None = None,
) -> JudgedResult:
    """Judge every reading and roll verdicts up per subject, check and run.

    Args:
        rules: From :func:`rules_from_inputs`.
        readings: From the node's ``measure()``.
        checks: The manifest ``checks`` map (every key gets a check entry,
            NOT_EVALUABLE when it has no judged readings).
        policy: Optional app rules applied to every reading first.

    Returns:
        The :class:`JudgedResult`.

    Raises:
        CheckVerdictError: A reading names an unknown check, breaks the
            policy, or does not fit its check's rules.
    """
    specs: dict[str, CheckSpec | None] = {}
    for key, spec in checks.items():
        specs[key] = spec if isinstance(spec, CheckSpec) or spec is None else CheckSpec.model_validate(spec)
    rules_by_check: dict[str, list[Rule]] = {}
    for rule in rules:
        rules_by_check.setdefault(rule.check, []).append(rule)
    measurements: list[JudgedMeasurement] = []
    observations: list[Reading] = []
    crossed: dict[str, Reading] = {}
    for reading in readings:
        if reading.kind != "cross_reference":
            continue
        if reading.check in crossed:
            raise CheckVerdictError(f"Check {reading.check!r} has more than one cross_reference reading")
        crossed[reading.check] = reading
    mixed = sorted({r.check for r in readings if r.kind in _JUDGED_KINDS} & set(crossed))
    if mixed:
        raise CheckVerdictError(f"Checks {mixed} have both a cross_reference reading and judged readings")
    for reading in readings:
        if reading.check not in specs:
            raise CheckVerdictError(f"Reading names check {reading.check!r}, which the manifest does not declare")
        if policy is not None:
            policy.check_reading(reading)
        if reading.kind in ("observation", "scope"):
            observations.append(reading)
            continue
        if reading.kind == "cross_reference":
            if reading.measured_by not in specs:
                raise CheckVerdictError(
                    f"Check {reading.check!r} is measured by {reading.measured_by!r}, which the manifest does not declare"
                )
            continue
        measurements.append(_judge_reading(reading, rules_by_check.get(reading.check, []), specs[reading.check]))
    judged_checks: list[JudgedCheck] = []
    for key in specs:
        check_rules = rules_by_check.get(key, [])
        cross = crossed.get(key)
        if cross is not None:
            reason = {"code": str(cross.reason_code), **({"message": cross.reason} if cross.reason else {})}
            judged_checks.append(
                JudgedCheck(
                    check=key,
                    verdict="NOT_EVALUABLE",
                    verdict_counts=_empty_counts(),
                    limits_used=[r.as_limit_used() for r in check_rules if r.role in ("LIMIT", "WARNING_LIMIT")],
                    filters_used=[{"input": r.input, "value": r.value} for r in check_rules if r.role == "FILTER"],
                    not_evaluated_reason=reason,
                    cross_reference=cross.measured_by,
                )
            )
            continue
        rows = [m for m in measurements if m.reading.check == key]
        counts = _count_subjects(rows)
        judged_checks.append(
            JudgedCheck(
                check=key,
                verdict=rollup(rollup(v) for v in _verdicts_by_subject(rows).values()),
                verdict_counts=counts,
                limits_used=[r.as_limit_used() for r in check_rules if r.role in ("LIMIT", "WARNING_LIMIT")],
                filters_used=[{"input": r.input, "value": r.value} for r in check_rules if r.role == "FILTER"],
                not_evaluated_reason=None if rows else {"code": "NO_SUBJECTS_IN_SCOPE"},
            )
        )
    return JudgedResult(
        checks=judged_checks,
        measurements=measurements,
        observations=observations,
        # D90 (#285): a cross-referenced check counts nowhere; its owner carries the result.
        verdict=rollup(c.verdict for c in judged_checks if c.cross_reference is None),
        subject_counts=_count_subjects(measurements),
    )


def _verdicts_by_subject(rows: Iterable[JudgedMeasurement]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row.reading.subject_id), []).append(row.verdict)
    return grouped


__all__ = [
    "CHECK_RESULT_SCHEMA",
    "CHECK_RESULT_SCHEMA_VERSION",
    "CHECK_RESULT_SCHEMA_VERSION_2_0_0",
    "FLOAT_ALLOWANCE",
    "STATEMENT_PLACEHOLDERS",
    "VERDICT_MARK",
    "VERDICT_PRECEDENCE",
    "CheckResolution",
    "CheckSpec",
    "CheckVerdictError",
    "JudgedCheck",
    "JudgedMeasurement",
    "JudgedResult",
    "Reading",
    "Rule",
    "TekkCheckOperatorEnum",
    "TekkCheckRoleEnum",
    "TekkCheckRoundingEnum",
    "TekkWorkflowRunVerdictEnum",
    "VerdictPolicy",
    "judge",
    "load_check_body_schema",
    "marked_input_values",
    "marked_inputs",
    "rollup",
    "rules_from_inputs",
    "verdict_mark_errors",
]
