"""Streaming reader for ``model_check.check`` result files.

A check's result file can be very large (the 0.x body of one failed check is
51 KB to 845 KB on dev; 1.0.0 grows with every reading). Agents and services
that need to *look inside* one must not load it whole. This module reads a
staged file from disk with a streaming JSON parser:

- :meth:`CheckResultReader.overview`: header, verdict, summary and one entry per
  check (verdict, counts, limits used).
- :meth:`CheckResultReader.failures`: the failing readings of one check, one page
  at a time.
- :meth:`CheckResultReader.element`: every row that concerns one element (GlobalId).
- :meth:`CheckResultReader.iter_findings`: lossless facts for 1.0.0 and grouped bodies.
- :meth:`CheckResultReader.report_visuals`: selected optional drawings, read separately.

Supported shapes (anything else fails with a named :class:`CheckResultReadError`):

- ``model_check.check`` and the older label ``model_check.rule``, any ``0.x``
  version (the body carries ``result.requirements``, ``result.rows``,
  ``measurements.measurements`` and ``instances.instances``);
- ``model_check.check`` ``1.x`` (the verdict standard: ``checks[]`` and
  ``measurements[]`` with ``failed_limits``; #283);
- ``model_check.check`` ``2.0.0`` and ``2.1.0`` (each check owns its measurements).

Requires the optional extra ``reader`` (``pip install canvastekk-workflow-sdk[reader]``),
which installs ``ijson``. Memory stays flat in the file size: the file is scanned
with a pull parser and only the facts being asked for are kept.
"""

from __future__ import annotations

import os
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from typing import IO, Any

from jsonschema import Draft7Validator

from canvastekk_workflow_sdk.check_verdict import (
    CHECK_RESULT_SCHEMA_VERSION,
    CHECK_RESULT_SCHEMA_VERSION_2_1_0,
    GROUPED_CHECK_RESULT_SCHEMA_VERSIONS,
    load_check_body_schema,
)
from canvastekk_workflow_sdk.result_file import (
    RESULT_FILE_VERSION_1_1_0,
    ResultFileFormatError,
    read_result_file_header,
)

CHECK_RESULT_LABEL = "model_check.check"
LEGACY_RESULT_LABEL = "model_check.rule"

#: Most failing items one :meth:`CheckResultReader.failures` call returns.
MAX_PAGE_SIZE = 100
#: Default page size of :meth:`CheckResultReader.failures`.
DEFAULT_PAGE_SIZE = 20
#: Most rows :meth:`CheckResultReader.element` returns.
MAX_ELEMENT_ROWS = 50
#: Identity lists (GlobalIds) are capped per item; the omitted count rides beside the list.
IDENTITY_LIST_CAP = 8

_FAIL = "FAIL"
_CHECK_ITEM = "body.checks.item"
_NESTED_ROWS = f"{_CHECK_ITEM}.measurements"
_SMALL_BODY_MEMBERS_0X = (
    "check_id",
    "rule_id",
    "clause",
    "clause_text",
    "verdict",
    "verdict_counts",
    "requirements",
    "coverage",
    "not_evaluable",
    "config",
)


class CheckResultReadError(Exception):
    """A result file this reader cannot read; ``code`` is a stable upper-case name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _ijson() -> Any:
    try:
        import ijson  # noqa: PLC0415 — optional extra, imported on use
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise CheckResultReadError(
            "READER_UNAVAILABLE",
            "ijson is not installed; install the extra: pip install canvastekk-workflow-sdk[reader]",
        ) from exc
    return ijson


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if isinstance(value, int) or float(value).is_integer() else value


def _margin(actual: Any, threshold: Any) -> int | float | None:
    """Signed ``actual - threshold``; the failing side says which direction is wrong."""
    a, t = _number(actual), _number(threshold)
    if a is None or t is None:
        return None
    diff = a - t
    return int(diff) if float(diff).is_integer() else round(diff, 3)


def _ids(values: Any) -> dict[str, Any]:
    ids = [str(v) for v in _list(values) if v is not None]
    return {"ids": ids[:IDENTITY_LIST_CAP], "omitted": max(0, len(ids) - IDENTITY_LIST_CAP)}


def _collect(path: str, targets: set[str]) -> dict[str, Any]:
    """One streaming pass that builds only the members named in ``targets``.

    ``targets`` are ijson prefixes such as ``body.result.requirements``. The pass
    stops as soon as every target has been built.
    """
    ijson = _ijson()
    from ijson.common import ObjectBuilder  # noqa: PLC0415

    found: dict[str, Any] = {}
    builder: ObjectBuilder | None = None
    target = ""
    depth = 0
    with open(path, "rb") as stream:
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if builder is None:
                if prefix not in targets or prefix in found:
                    continue
                if event in ("start_map", "start_array"):
                    builder, target, depth = ObjectBuilder(), prefix, 1
                    builder.event(event, value)
                elif event not in ("map_key", "end_map", "end_array"):
                    found[prefix] = value
                    if len(found) == len(targets):
                        break
                continue
            builder.event(event, value)
            if event in ("start_map", "start_array"):
                depth += 1
            elif event in ("end_map", "end_array"):
                depth -= 1
                if depth == 0:
                    found[target] = builder.value
                    builder = None
                    if len(found) == len(targets):
                        break
    return found


def _items(path: str, prefix: str) -> Iterator[dict[str, Any]]:
    ijson = _ijson()
    with open(path, "rb") as stream:
        for item in ijson.items(stream, prefix, use_float=True):
            yield _dict(item)


@cache
def _part_validator(version: str, part: str) -> Draft7Validator:
    schema = load_check_body_schema(version)
    definition = schema["definitions"][part] if version in GROUPED_CHECK_RESULT_SCHEMA_VERSIONS else (
        schema["properties"]["checks" if part == "check" else "measurements"]["items"]
    )
    return Draft7Validator(schema).evolve(schema=definition)


def _validate_part(value: Any, version: str, part: str) -> None:
    error = next(_part_validator(version, part).iter_errors(value), None)
    if error is not None:
        raise CheckResultReadError("INVALID_RESULT_FILE", f"malformed {part} in {version} body")


def _grouped_checks(path: str, version: str) -> Iterator[dict[str, Any]]:
    """Stream each check descriptor, keeping the measurement array marker but not its rows."""
    ijson = _ijson()
    allowed = load_check_body_schema(version)["properties"]
    found_checks = False

    def descriptors(stream: IO[bytes]) -> Iterator[tuple[str, str, Any]]:
        nonlocal found_checks
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if prefix == "body" and event == "map_key" and value not in allowed:
                raise CheckResultReadError("INVALID_RESULT_FILE", f"unexpected member in {version} body")
            if prefix == "body.checks" and event == "start_array":
                found_checks = True
            if not prefix.startswith(f"{_NESTED_ROWS}."):
                yield prefix, event, value

    seen: set[str] = set()
    try:
        with open(path, "rb") as stream:
            for check in ijson.items(descriptors(stream), _CHECK_ITEM):
                _validate_part(check, version, "check")
                if check["check"] in seen:
                    raise CheckResultReadError("INVALID_RESULT_FILE", f"duplicate check key in {version} body")
                seen.add(check["check"])
                yield check
    except ijson.JSONError as exc:
        raise CheckResultReadError("INVALID_RESULT_FILE", "malformed result body JSON") from exc
    if not found_checks:
        raise CheckResultReadError("INVALID_RESULT_FILE", f"missing checks array in {version} body")


def _grouped_rows(path: str, version: str) -> Iterator[tuple[int, int, dict[str, Any]]]:
    """Stream one nested reading at a time with its original check ordinal and index."""
    ijson = _ijson()
    check_index = -1
    measurement_index = 0

    def track(stream: IO[bytes]) -> Iterator[tuple[str, str, Any]]:
        nonlocal check_index, measurement_index
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if prefix == _CHECK_ITEM and event == "start_map":
                check_index += 1
                measurement_index = 0
            yield prefix, event, value

    try:
        with open(path, "rb") as stream:
            for row in ijson.items(track(stream), f"{_NESTED_ROWS}.item"):
                if (
                    version == CHECK_RESULT_SCHEMA_VERSION_2_1_0
                    and isinstance(row, dict)
                    and "report_visual_refs" in row
                    and not _part_validator(version, "report_visual_refs").is_valid(row["report_visual_refs"])
                ):
                    del row["report_visual_refs"]
                _validate_part(row, version, "measurement")
                yield check_index, measurement_index, row
                measurement_index += 1
    except ijson.JSONError as exc:
        raise CheckResultReadError("INVALID_RESULT_FILE", "malformed result body JSON") from exc


@dataclass(frozen=True)
class CheckFinding:
    """A finding reference, its original measurement facts, and the recorded check limits."""

    workflow_run_id: str
    check: str
    measurement_index: int
    measurement: dict[str, Any]
    limits_used: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _Layout:
    """Which body shape a file carries."""

    kind: str  # "grouped" (2.0.0/2.1.0), "verdict" (1.x), or "legacy" (0.x)
    schema: str
    version: str


class CheckResultReader:
    """Read one staged ``model_check.check`` result file without loading it whole.

    Args:
        path: Path of a result file on disk.

    Raises:
        CheckResultReadError: ``INVALID_RESULT_FILE`` (unreadable or bad layout),
            ``UNSUPPORTED_RESULT_SCHEMA`` (not a model-check label),
            ``UNSUPPORTED_RESULT_SCHEMA_VERSION`` (a major this reader does not know),
            ``READER_UNAVAILABLE`` (extra not installed).
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = os.fspath(path)
        self._header = self._read_header()
        self._layout = self._resolve_layout(self._header)

    # ------------------------------------------------------------------ header

    def _read_header(self) -> dict[str, Any]:
        try:
            with open(self._path, "rb") as stream:
                return read_result_file_header(stream)
        except OSError as exc:
            raise CheckResultReadError("INVALID_RESULT_FILE", f"cannot read result file: {exc.strerror}") from exc
        except ResultFileFormatError as exc:
            raise CheckResultReadError("INVALID_RESULT_FILE", str(exc)) from exc

    @staticmethod
    def _resolve_layout(header: dict[str, Any]) -> _Layout:
        schema = str(header.get("result_schema"))
        version = str(header.get("result_schema_version"))
        if schema not in (CHECK_RESULT_LABEL, LEGACY_RESULT_LABEL):
            raise CheckResultReadError(
                "UNSUPPORTED_RESULT_SCHEMA",
                f"result_schema {schema!r} is not {CHECK_RESULT_LABEL!r} (or the older {LEGACY_RESULT_LABEL!r})",
            )
        major = version.split(".", 1)[0]
        if major == "0":
            return _Layout("legacy", schema, version)
        if major == "1" and schema == CHECK_RESULT_LABEL:
            return _Layout("verdict", schema, version)
        if version in GROUPED_CHECK_RESULT_SCHEMA_VERSIONS and schema == CHECK_RESULT_LABEL:
            if header["result_file_version"] != RESULT_FILE_VERSION_1_1_0:
                raise CheckResultReadError("INVALID_RESULT_FILE", f"{version} check bodies require result-file layout 1.1.0")
            return _Layout("grouped", schema, version)
        raise CheckResultReadError(
            "UNSUPPORTED_RESULT_SCHEMA_VERSION",
            f"{schema} {version} is not readable: this reader knows 0.x and (for {CHECK_RESULT_LABEL}) 1.x, 2.0.0 and 2.1.0",
        )

    @property
    def header(self) -> dict[str, Any]:
        """The validated result-file header (everything before ``body``)."""
        return dict(self._header)

    def _check_records(self) -> Iterator[dict[str, Any]]:
        if self._layout.kind == "grouped":
            return _grouped_checks(self._path, self._layout.version)
        return _items(self._path, _CHECK_ITEM)

    def _judged_rows(self, checks: list[dict[str, Any]]) -> Iterator[tuple[str, int, dict[str, Any]]]:
        if self._layout.kind == "grouped":
            for group, index, row in _grouped_rows(self._path, self._layout.version):
                if not 0 <= group < len(checks):
                    raise CheckResultReadError("INVALID_RESULT_FILE", "measurement outside its check")
                yield checks[group]["check"], index, row
            return
        for index, row in enumerate(_items(self._path, "body.measurements.item")):
            yield row.get("check"), index, row

    def iter_findings(self) -> Iterator[CheckFinding]:
        """Yield findings with flat 1.0.0 or check-local grouped indices in file order.

        Unknown formats or malformed findings raise ``CheckResultReadError``.
        A missing limit or element identity is never filled from a guess.
        Malformed optional drawing references are omitted.
        """
        version = self._layout.version
        if version not in (CHECK_RESULT_SCHEMA_VERSION, *GROUPED_CHECK_RESULT_SCHEMA_VERSIONS):
            raise CheckResultReadError("UNSUPPORTED_RESULT_SCHEMA_VERSION", f"lossless findings are unavailable in {version}")
        checks = list(self._check_records())
        limits: dict[str, tuple[dict[str, Any], ...]] = {}
        for record in checks:
            if version == CHECK_RESULT_SCHEMA_VERSION:
                _validate_part(record, version, "check")
            key = record["check"]
            if key in limits:
                raise CheckResultReadError("INVALID_RESULT_FILE", "duplicate check key in result body")
            limits[key] = tuple(_list(record.get("limits_used")))
        run_id = self._header["workflow_run_id"]
        for check, index, row in self._judged_rows(checks):
            if version == CHECK_RESULT_SCHEMA_VERSION:
                _validate_part(row, version, "measurement")
                if check not in limits:
                    raise CheckResultReadError("INVALID_RESULT_FILE", "finding has no recorded check")
            yield CheckFinding(run_id, check, index, row, limits[check])

    def report_visuals(self, visual_ids: Collection[str]) -> dict[str, dict[str, Any]]:
        """Read requested, valid plan bands keyed by their IDs in this result file.

        Missing, malformed, and repeated drawings are omitted. Older body versions
        have no embedded drawings. Finding and header reads do not use this method.
        """
        version = self._layout.version
        if not visual_ids or version != CHECK_RESULT_SCHEMA_VERSION_2_1_0:
            return {}
        ijson = _ijson()
        validator = _part_validator(version, "plan_band")
        selected: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        try:
            with open(self._path, "rb") as stream:
                for name, drawing in ijson.kvitems(stream, "body.report_visuals", use_float=True):
                    if not name or name not in visual_ids:
                        continue
                    if name in seen:
                        selected.pop(name, None)
                        continue
                    seen.add(name)
                    if validator.is_valid(drawing):
                        min_x, min_y, max_x, max_y = drawing["crop_xy_mm"]
                        bottom, top = drawing["z_band_mm"]
                        if min_x < max_x and min_y < max_y and bottom < top:
                            selected[name] = drawing
        except ijson.JSONError as exc:
            raise CheckResultReadError("INVALID_RESULT_FILE", "malformed result body JSON") from exc
        return selected

    # ---------------------------------------------------------------- overview

    def overview(self) -> dict[str, Any]:
        """Header facts, the run verdict and one entry per check.

        Returns:
            ``source`` (labels and versions), ``workflow_run_id``, ``workflow_definition``,
            ``generated_at``, ``verdict``, ``summary`` and ``checks``: per check its key,
            ``verdict``, ``verdict_counts``, ``limits_used``, ``filters_used`` and ``failing``
            (failing subject count). For 0.x files, ``context`` carries the clause text,
            coverage, not-evaluable summary and config the run used.
        """
        header = self._header
        out: dict[str, Any] = {
            "source": {
                "result_schema": self._layout.schema,
                "result_schema_version": self._layout.version,
                "result_file_version": header.get("result_file_version"),
            },
            "workflow_run_id": header.get("workflow_run_id"),
            "workflow_definition": header.get("workflow_definition"),
            "generated_at": header.get("generated_at"),
            "summary": header.get("summary"),
        }
        if self._layout.kind != "legacy":
            checks = [self._check_entry_1x(c) for c in self._check_records()]
            out["verdict"] = header.get("verdict") or _rollup(c["verdict"] for c in checks)
            out["checks"] = checks
            return out
        found = _collect(
            self._path,
            {"body.verdict", "body.verdict_counts"} | {f"body.result.{k}" for k in _SMALL_BODY_MEMBERS_0X},
        )
        result = {k: found.get(f"body.result.{k}") for k in _SMALL_BODY_MEMBERS_0X}
        out["verdict"] = found.get("body.verdict") or result["verdict"] or _dict(header.get("summary")).get("verdict")
        out["checks"] = [self._check_entry_0x(key, _dict(rec)) for key, rec in _dict(result["requirements"]).items()]
        out["context"] = {
            "check_id": result["check_id"],
            "rule_id": result["rule_id"],
            "clause": result["clause"],
            "clause_text": result["clause_text"],
            "verdict_counts": _dict(found.get("body.verdict_counts") or result["verdict_counts"]),
            "coverage": result["coverage"],
            "not_evaluable": _not_evaluable(result["not_evaluable"]),
            "config": result["config"],
        }
        return out

    @staticmethod
    def _check_entry_1x(check: dict[str, Any]) -> dict[str, Any]:
        counts = _dict(check.get("verdict_counts"))
        return {
            "check": check.get("check"),
            "verdict": check.get("verdict"),
            "verdict_counts": counts,
            "failing": counts.get(_FAIL, 0),
            "limits_used": _list(check.get("limits_used")),
            "filters_used": _list(check.get("filters_used")),
            "not_evaluated_reason": check.get("not_evaluated_reason"),
            "cross_reference": check.get("cross_reference"),
        }

    @staticmethod
    def _check_entry_0x(key: str, record: dict[str, Any]) -> dict[str, Any]:
        counts = _dict(record.get("verdict_counts"))
        threshold = _number(record.get("threshold_mm"))
        return {
            "check": key,
            "verdict": record.get("verdict"),
            "verdict_counts": counts,
            "failing": counts.get(_FAIL, 0),
            "limits_used": [{"input": "threshold_mm", "role": "LIMIT", "operator": None, "value": threshold}]
            if threshold is not None
            else [],
            "filters_used": [],
            "not_evaluated_reason": None,
            "cross_reference": None,
            "text": record.get("text"),
            "status": record.get("status"),
        }

    # ---------------------------------------------------------------- failures

    def failures(self, check: str | None = None, offset: int = 0, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        """Failing readings of one check (or all checks), one page at a time.

        Args:
            check: Check key (as in :meth:`overview`); ``None`` for every check.
            offset: Items to skip (0-based, in file order for 1.x/2.0.0; sorted by check, element and row for 0.x).
            limit: Page size, 1 to :data:`MAX_PAGE_SIZE`.

        Returns:
            ``check``, ``total``, ``offset``, ``limit``, ``next_offset`` (``None`` on the last page)
            and ``items``. Each item: ``check``, ``subject_id``, ``element_name``, ``global_ids``
            (capped, with ``omitted``), ``file_id``, ``actual``, ``limits`` (each ``input``,
            ``threshold``, ``margin`` = ``actual - threshold``, plus ``side`` or ``comparator``) and ``reason``.
        """
        offset = max(0, int(offset))
        limit = min(MAX_PAGE_SIZE, max(1, int(limit)))
        if self._layout.kind != "legacy":
            total, items = self._failures_judged(check, offset, limit)
        else:
            total, items = self._failures_0x(check, offset, limit)
        end = offset + len(items)
        return {
            "check": check,
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": end if end < total else None,
            "items": items,
        }

    @staticmethod
    def _limit_values(checks: Iterable[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        """Per check key: limit input name to its ``limits_used`` entry."""
        table: dict[str, dict[str, dict[str, Any]]] = {}
        for check in checks:
            table[str(check.get("check"))] = {
                str(limit.get("input")): _dict(limit) for limit in _list(check.get("limits_used"))
            }
        return table

    def _failures_judged(self, check: str | None, offset: int, limit: int) -> tuple[int, list[dict[str, Any]]]:
        checks = list(self._check_records())
        limits = self._limit_values(checks)
        total = 0
        page: list[dict[str, Any]] = []
        for key, _, row in self._judged_rows(checks):
            if row.get("verdict") != _FAIL or (check is not None and key != check):
                continue
            if offset <= total < offset + limit:
                page.append(self._compact_judged_item(key, row, limits.get(str(key), {})))
            total += 1
        return total, page

    def _failures_0x(self, check: str | None, offset: int, limit: int) -> tuple[int, list[dict[str, Any]]]:
        measurements, rows_seen = self._failing_measurements_0x()
        failing_rows = self._failing_rows_0x(rows_seen, measurements)
        needed = {m["global_id"] for m in measurements if m["global_id"]} | {
            gid for r in failing_rows.values() for gid in r["subject_ids"]["ids"][:1]
        }
        identities = self._identities_0x(needed)
        requirements = _dict(_collect(self._path, {"body.result.requirements"}).get("body.result.requirements"))
        items = _join_0x(measurements, failing_rows, identities, requirements)
        if check is not None:
            items = [i for i in items if i["check"] == check]
        return len(items), items[offset : offset + limit]

    def _failing_measurements_0x(self) -> tuple[list[dict[str, Any]], set[str]]:
        failing: list[dict[str, Any]] = []
        for measurement in _items(self._path, "body.measurements.measurements.item"):
            meta = _dict(measurement.get("metadata"))
            if meta.get("verdict") != _FAIL:
                continue
            gid = meta.get("global_id")
            subjects = [str(s) for s in _list(meta.get("subject_global_ids")) if s]
            failing.append(
                {
                    "check": meta.get("requirement_key") or meta.get("requirement") or measurement.get("name"),
                    "global_id": gid if isinstance(gid, str) else (subjects[0] if subjects else None),
                    "actual": _number(meta.get("value_mm", measurement.get("value"))),
                    "threshold": _number(meta.get("threshold_mm")),
                    "comparator": meta.get("comparator"),
                    "confidence": measurement.get("confidence"),
                    "reason_code": meta.get("reason_code"),
                    "row_id": meta.get("row_id"),
                    "subject_global_ids": subjects,
                    "unit": measurement.get("unit"),
                }
            )
        return failing, {str(m["row_id"]) for m in failing if m["row_id"]}

    def _failing_rows_0x(self, row_ids: set[str], measurements: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Rows that fail on their own, plus the rows a failing measurement points at."""
        rows: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(_items(self._path, "body.result.rows.item")):
            if row.get("verdict") != _FAIL and str(row.get("row_id")) not in row_ids:
                continue
            reason = _dict(row.get("reason"))
            rows[str(row.get("row_id") or f"#{index}")] = {
                "row_id": row.get("row_id"),
                "verdict": row.get("verdict"),
                "requirement": row.get("requirement"),
                "subject_id": row.get("subject_id"),
                "subject_label": row.get("subject_label"),
                "actual": _number(row.get("value_mm")),
                "threshold": _number(row.get("threshold_mm")),
                "comparator": row.get("comparator"),
                "reason_code": row.get("reason_code") or reason.get("reason_code"),
                "what_would_resolve_it": reason.get("what_would_resolve_it"),
                "subject_ids": _ids(row.get("subject_global_ids")),
            }
        return rows

    def _identities_0x(self, global_ids: set[str]) -> dict[str, dict[str, str]]:
        index: dict[str, dict[str, str]] = {}
        if not global_ids:
            return index
        for instance in _items(self._path, "body.instances.instances.item"):
            meta = _dict(instance.get("metadata"))
            gid = meta.get("ifc_global_id") or meta.get("global_id")
            if isinstance(gid, str) and gid in global_ids and gid not in index:
                index[gid] = {
                    "name": str(meta.get("ifc_name") or instance.get("class_name") or ""),
                    "entity": str(meta.get("ifc_entity") or instance.get("class_name") or ""),
                }
        return index

    # ----------------------------------------------------------------- element

    def element(self, global_id: str, limit: int = MAX_ELEMENT_ROWS) -> dict[str, Any]:
        """Every reading about one element, wherever it appears.

        Args:
            global_id: The element's IFC GlobalId.
            limit: Most rows returned, 1 to :data:`MAX_ELEMENT_ROWS`.

        Returns:
            ``global_id``, ``identity`` (name and entity when the file has them), ``rows``
            (same item shape as :meth:`failures`, any verdict) and ``truncated``.
        """
        limit = min(MAX_ELEMENT_ROWS, max(1, int(limit)))
        if self._layout.kind != "legacy":
            checks = list(self._check_records())
            limits = self._limit_values(checks)
            rows: list[dict[str, Any]] = []
            total = 0
            name: str | None = None
            for key, _, row in self._judged_rows(checks):
                if self._layout.kind == "grouped":
                    matches = row.get("element_id_type") == "ifc_guid" and row.get("element_id") == global_id
                else:
                    gids = [str(g) for g in _list(row.get("global_ids"))]
                    matches = global_id in gids or row.get("subject_id") == global_id
                if not matches:
                    continue
                name = name or row.get("element_name")
                if total < limit:
                    item = self._compact_judged_item(key, row, limits.get(str(key), {}))
                    item["verdict"] = row.get("verdict")
                    rows.append(item)
                total += 1
            identity = {"name": name} if name else None
            return {"global_id": global_id, "identity": identity, "rows": rows, "truncated": total > len(rows)}
        measurements: list[dict[str, Any]] = []
        total = 0
        for measurement in _items(self._path, "body.measurements.measurements.item"):
            meta = _dict(measurement.get("metadata"))
            subjects = [str(s) for s in _list(meta.get("subject_global_ids"))]
            if meta.get("global_id") != global_id and global_id not in subjects:
                continue
            if total < limit:
                measurements.append(
                    {
                        "check": meta.get("requirement_key") or meta.get("requirement") or measurement.get("name"),
                        "verdict": meta.get("verdict"),
                        "actual": _number(meta.get("value_mm", measurement.get("value"))),
                        "threshold": _number(meta.get("threshold_mm")),
                        "comparator": meta.get("comparator"),
                        "confidence": measurement.get("confidence"),
                        "row_id": meta.get("row_id"),
                    }
                )
            total += 1
        identity = self._identities_0x({global_id}).get(global_id)
        return {
            "global_id": global_id,
            "identity": identity,
            "rows": measurements,
            "truncated": total > len(measurements),
        }

    def _compact_judged_item(
        self, key: str, row: dict[str, Any], limits: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        if self._layout.kind == "grouped":
            identity = row.get("element_id") if row.get("element_id_type") == "ifc_guid" else None
            row = {
                **row, "check": key, "global_ids": [identity] if identity else [],
                "file_id": row.get("element_id_source_file"),
            }
        return _item_1x(row, limits)


def open_check_result(path: str | os.PathLike[str] | IO[bytes]) -> CheckResultReader:
    """Open a staged result file for bounded reading.

    Args:
        path: Path of the file on disk (a stream is not accepted: the reader makes several passes).

    Returns:
        A :class:`CheckResultReader`.
    """
    if hasattr(path, "read"):
        raise CheckResultReadError("INVALID_RESULT_FILE", "pass a file path; the reader needs several passes")
    return CheckResultReader(path)  # type: ignore[arg-type]


def _rollup(verdicts: Iterable[Any]) -> str | None:
    seen = {v for v in verdicts if v}
    for verdict in ("FAIL", "NOT_EVALUABLE", "WARNING", "PASS"):
        if verdict in seen:
            return verdict
    return None


def _not_evaluable(value: Any) -> list[dict[str, Any]]:
    facts = [
        {
            "reason_code": _dict(entry).get("reason_code"),
            "missing_input": _dict(entry).get("missing_input"),
            "what_would_resolve_it": _dict(entry).get("what_would_resolve_it"),
            "subject_global_ids": _ids(_dict(entry).get("subject_global_ids")),
        }
        for entry in _list(value)
    ]
    facts.sort(key=lambda fact: str(fact.get("reason_code") or ""))
    return facts


def _item_1x(row: dict[str, Any], limits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actual = row.get("actual")
    failed = []
    for failed_limit in _list(row.get("failed_limits")):
        name = str(_dict(failed_limit).get("input"))
        used = limits.get(name, {})
        failed.append(
            {
                "input": name,
                "side": _dict(failed_limit).get("side"),
                "threshold": used.get("value"),
                "operator": used.get("operator"),
                "margin": _margin(actual, used.get("value")),
            }
        )
    return {
        "check": row.get("check"),
        "subject_id": row.get("subject_id"),
        "element_name": row.get("element_name"),
        "global_ids": _ids(row.get("global_ids")),
        "file_id": row.get("file_id"),
        "actual": actual,
        "limits": failed,
        "reason": row.get("reason"),
    }


def _join_0x(
    measurements: list[dict[str, Any]],
    rows: dict[str, dict[str, Any]],
    identities: dict[str, dict[str, str]],
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    """Failing items of a 0.x file: failing measurements, then failing rows no measurement covers."""
    single = next(iter(requirements), None) if len(requirements) == 1 else None
    items: list[dict[str, Any]] = []
    seen_rows: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()

    def emit(measurement: dict[str, Any] | None, row: dict[str, Any] | None, gid: str | None) -> None:
        row_id = (measurement or {}).get("row_id") or (row or {}).get("row_id")
        if isinstance(row_id, str) and row_id in seen_rows:
            return
        check = (measurement or {}).get("check") or (row or {}).get("requirement") or single
        pair = (str(check), str(gid))
        if gid is not None and pair in seen_pairs:
            return
        row = row or (rows.get(str(row_id)) if row_id else None)
        who = identities.get(gid or "", {})
        actual = (measurement or {}).get("actual")
        if actual is None:
            actual = (row or {}).get("actual")
        threshold = (measurement or {}).get("threshold")
        if threshold is None:
            threshold = (row or {}).get("threshold")
        comparator = (measurement or {}).get("comparator") or (row or {}).get("comparator")
        subject_ids = (row or {}).get("subject_ids") or _ids((measurement or {}).get("subject_global_ids"))
        items.append(
            {
                "check": check,
                "subject_id": (row or {}).get("subject_id") or gid,
                "element_name": who.get("name") or (row or {}).get("subject_label"),
                "entity": who.get("entity"),
                "global_ids": subject_ids if subject_ids["ids"] else _ids([gid] if gid else []),
                "file_id": None,
                "actual": actual,
                "limits": [
                    {
                        "input": "threshold_mm",
                        "threshold": threshold,
                        "comparator": comparator,
                        "margin": _margin(actual, threshold),
                    }
                ]
                if threshold is not None
                else [],
                "reason": {
                    "code": (measurement or {}).get("reason_code") or (row or {}).get("reason_code"),
                    "message": (row or {}).get("what_would_resolve_it"),
                }
                if ((measurement or {}).get("reason_code") or (row or {}).get("reason_code"))
                else None,
                "row_id": row_id,
                "confidence": (measurement or {}).get("confidence"),
            }
        )
        if isinstance(row_id, str):
            seen_rows.add(row_id)
        if gid is not None:
            seen_pairs.add(pair)

    for measurement in measurements:
        row = rows.get(str(measurement["row_id"])) if measurement["row_id"] else None
        gid = measurement["global_id"]
        if gid is None and row is not None and row["subject_ids"]["ids"]:
            gid = row["subject_ids"]["ids"][0]
        emit(measurement, row, gid)
    for row in rows.values():
        if row["verdict"] != _FAIL or (isinstance(row["row_id"], str) and row["row_id"] in seen_rows):
            continue
        ids = row["subject_ids"]["ids"]
        gid = (
            ids[0] if ids else (row["subject_id"] if isinstance(row["subject_id"], str) and row["subject_id"] else None)
        )
        emit(None, row, gid)
    items.sort(key=lambda i: (str(i.get("check") or ""), str(i["global_ids"]["ids"][:1]), str(i.get("row_id") or "")))
    return items
