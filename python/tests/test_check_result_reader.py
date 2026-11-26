"""Streaming compact and lossless reads of ``model_check.check`` result files."""

from __future__ import annotations

import json
import tracemalloc
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator

pytest.importorskip("ijson")

from canvastekk_workflow_sdk.check_result_reader import (  # noqa: E402
    MAX_PAGE_SIZE,
    CheckResultReadError,
    open_check_result,
)
from canvastekk_workflow_sdk.check_verdict import CheckSpec, load_check_body_schema  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "check_results"
REPORT_346 = FIXTURES / "report_346_entrance_sightline_0.3.0.json"
RULE_0_1_0 = FIXTURES / "model_check_rule_0.1.0.json"
SCHEMA_V2 = Path(__file__).parents[2] / "schemas/result-body/model_check.check"
GUID = "2h7VCQmP56uPcWBc9vN$1A"

LIMITS = [
    {"input": "min_width_mm", "role": "LIMIT", "operator": "GTE", "value": 900},
    {"input": "max_slope", "role": "LIMIT", "operator": "LTE", "value": 12},
]


def _measurement(index: int, *, check: str = "door_width", verdict: str = "FAIL") -> dict[str, Any]:
    failed = [{"input": "min_width_mm", "side": "BELOW"}] if verdict == "FAIL" else []
    return {
        "check": check,
        "subject_id": f"guid-{index:06d}",
        "kind": "value",
        "element_name": f"Door {index}",
        "file_id": 42,
        "global_ids": [f"guid-{index:06d}"],
        "actual": 850 if verdict == "FAIL" else 950,
        "bound": "LOWER",
        "verdict": verdict,
        "failed_limits": failed,
    }


def _write_v1(
    path: Path,
    measurements: Iterable[dict[str, Any]],
    *,
    checks: list[dict[str, Any]] | None = None,
    version: str = "1.0.0",
    label: str = "model_check.check",
) -> Path:
    header = {
        "result_file_version": "1.0.0",
        "result_schema": label,
        "result_schema_version": version,
        "workflow_run_id": "run-1",
        "generated_at": "2026-11-23T10:00:00.000Z",
        "summary": {"fail_count": 1},
    }
    checks = checks or [
        {
            "check": "door_width",
            "verdict": "FAIL",
            "verdict_counts": {"PASS": 5, "WARNING": 0, "FAIL": 3, "NOT_EVALUABLE": 0},
            "limits_used": LIMITS,
            "filters_used": [],
        }
    ]
    with path.open("w", encoding="utf-8") as out:
        out.write(json.dumps(header)[:-1] + ', "body": {"checks": ' + json.dumps(checks) + ', "measurements": [')
        for index, row in enumerate(measurements):
            out.write(("," if index else "") + json.dumps(row))
        out.write("]}}")
    return path


def _small_v1(tmp_path: Path) -> Path:
    rows = [_measurement(i, verdict="FAIL" if i % 2 == 0 else "PASS") for i in range(10)]
    return _write_v1(tmp_path / "v1.json", rows)


def _header_v2() -> dict[str, Any]:
    return {
        "result_file_version": "1.1.0",
        "result_schema": "model_check.check",
        "result_schema_version": "2.0.0",
        "workflow_run_id": "run-2",
        "workflow_definition": {"id": "width-group-1.2.3", "slug": "width-group", "version": "1.2.3"},
        "inputs": {"min_width": 900},
        "generated_at": "2026-11-23T10:00:00.000Z",
    }


def _body_v2() -> dict[str, Any]:
    return json.loads((SCHEMA_V2 / "examples/nested-2.0.0.json").read_text())


def _write_v2(tmp_path: Path, body: dict[str, Any], *, version: str = "2.0.0") -> Path:
    path = tmp_path / f"{version}.json"
    path.write_text(json.dumps({**_header_v2(), "result_schema_version": version, "body": body}))
    return path


class TestNestedFindings:
    def test_packaged_schema_matches_canonical_and_keeps_old_write_default(self) -> None:
        schema = load_check_body_schema("2.0.0")
        assert schema == json.loads((SCHEMA_V2 / "2.0.0.json").read_text())
        Draft7Validator.check_schema(schema)
        assert Draft7Validator(schema).is_valid(_body_v2())
        assert load_check_body_schema()["$id"].endswith(":1.0.0")
        assert "description" not in CheckSpec(label="Width").model_dump()
        described = CheckSpec(label="Width", description="The opening's clear width.")
        assert described.model_dump()["description"] == "The opening's clear width."

    @pytest.mark.parametrize("version", ["2.0.0", "2.1.0"])
    def test_keeps_the_nested_indices_raw_facts_and_exact_limits(self, tmp_path: Path, version: str) -> None:
        body = _body_v2()
        reader = open_check_result(_write_v2(tmp_path, body, version=version))
        findings = list(reader.iter_findings())
        assert [(r.workflow_run_id, r.check, r.measurement_index) for r in findings] == [
            ("run-2", "clear_width", 0), ("run-2", "clear_width", 1), ("run-2", "door_height", 0)
        ]
        assert findings[1].measurement == body["checks"][0]["measurements"][1]
        assert findings[1].limits_used == tuple(body["checks"][0]["limits_used"])
        assert findings[2].measurement == body["checks"][1]["measurements"][0]
        assert findings[2].limits_used == ()
        assert reader.header["inputs"] == {"min_width": 900}

    @pytest.mark.parametrize("version", ["2.0.0", "2.1.0"])
    def test_compact_queries_keep_counts_and_only_verified_identity(self, tmp_path: Path, version: str) -> None:
        reader = open_check_result(_write_v2(tmp_path, _body_v2(), version=version))
        assert reader.overview()["checks"][0]["verdict_counts"] == {"PASS": 0, "WARNING": 0, "FAIL": 1, "NOT_EVALUABLE": 0}
        [failed] = reader.failures("clear_width")["items"]
        assert failed["limits"] == [
            {"input": "min_width", "side": "BELOW", "threshold": 900, "operator": "GTE", "margin": -60}
        ]
        assert failed["global_ids"]["ids"] == [GUID]
        assert failed["file_id"] is None
        assert len(reader.element(GUID)["rows"]) == 1
        assert reader.element("0z40zcHTf5xfp$pr$3uZQI")["rows"] == []

    def test_preserves_original_indices_in_the_flat_reader(self, tmp_path: Path) -> None:
        reader = open_check_result(_small_v1(tmp_path))
        fails = [row for row in reader.iter_findings() if row.measurement["verdict"] == "FAIL"]
        assert [row.measurement_index for row in fails] == [0, 2, 4, 6, 8]
        assert fails[0].measurement["bound"] == "LOWER"
        assert fails[0].limits_used == tuple(LIMITS)

    def test_rejects_a_body_without_recorded_row_verdict(self, tmp_path: Path) -> None:
        body = _body_v2()
        del body["checks"][0]["measurements"][0]["verdict"]
        assert not Draft7Validator(load_check_body_schema("2.0.0")).is_valid(body)
        with pytest.raises(CheckResultReadError, match="malformed measurement"):
            list(open_check_result(_write_v2(tmp_path, body)).iter_findings())

    def test_rejects_flat_members_and_duplicate_check_keys(self, tmp_path: Path) -> None:
        body = _body_v2()
        with pytest.raises(CheckResultReadError, match="unexpected member"):
            open_check_result(_write_v2(tmp_path, {**body, "measurements": []})).overview()
        body["checks"].append(body["checks"][0])
        with pytest.raises(CheckResultReadError, match="duplicate check key"):
            list(open_check_result(_write_v2(tmp_path, body)).iter_findings())

    def test_lossless_mode_refuses_legacy_compact_only_files(self) -> None:
        with pytest.raises(CheckResultReadError, match="UNSUPPORTED_RESULT_SCHEMA_VERSION"):
            list(open_check_result(REPORT_346).iter_findings())

    def test_nested_body_requires_layout_1_1_0(self, tmp_path: Path) -> None:
        path = _write_v1(tmp_path / "old-layout.json", [], version="2.0.0")
        with pytest.raises(CheckResultReadError, match="require result-file layout 1.1.0"):
            open_check_result(path)

    def test_overview_does_not_materialize_nested_geometry(self, tmp_path: Path) -> None:
        path = tmp_path / "large-v2.json"
        body = _body_v2()
        row = body["checks"][0]["measurements"][0] | {"extra": {"payload": "x" * 4096}}
        check = {k: v for k, v in body["checks"][0].items() if k != "measurements"}
        with path.open("w") as stream:
            stream.write(json.dumps(_header_v2())[:-1] + ', "body":{"checks":[' + json.dumps(check)[:-1])
            stream.write(', "measurements": [')
            wire = json.dumps(row)
            for i in range(2500):
                stream.write(("," if i else "") + wire)
            stream.write("]}]}}")
        tracemalloc.start()
        try:
            assert open_check_result(path).overview()["checks"][0]["check"] == "clear_width"
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < 3 * 1024 * 1024

    def test_optional_plan_bands_are_additive_and_selected_explicitly(self, tmp_path: Path) -> None:
        body = json.loads((SCHEMA_V2 / "examples/nested-2.1.0.json").read_text())
        schema = load_check_body_schema("2.1.0")
        assert schema == json.loads((SCHEMA_V2 / "2.1.0.json").read_text())
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema)
        validator.validate(body)
        validator.validate(_body_v2())

        plans = body["report_visuals"]
        plan = plans["basin-1-plan"]
        plans["outside-request"] = plan
        plans["invalid-shape"] = {**plan, "z_band_mm": [1400]}
        plans["inverted-band"] = {**plan, "z_band_mm": [1800, 1400]}
        assert not validator.is_valid(body)

        reader = open_check_result(_write_v2(tmp_path, body, version="2.1.0"))
        [finding] = reader.iter_findings()
        assert reader.header["result_schema_version"] == "2.1.0"
        assert finding.measurement_index == 0
        assert finding.measurement["actual"] == 200
        assert finding.measurement["report_visual_refs"] == ["basin-1-plan"]
        requested = {"basin-1-plan", "invalid-shape", "inverted-band", "not-present"}
        assert reader.report_visuals(requested) == {"basin-1-plan": plan}

    def test_invalid_optional_refs_do_not_discard_required_facts(self, tmp_path: Path) -> None:
        body = _body_v2()
        row = body["checks"][0]["measurements"][1]
        row["report_visual_refs"] = ["duplicate", "duplicate"]
        assert not Draft7Validator(load_check_body_schema("2.1.0")).is_valid(body)
        reader = open_check_result(_write_v2(tmp_path, body, version="2.1.0"))
        finding = list(reader.iter_findings())[1]
        assert finding.measurement_index == 1
        assert finding.measurement == {key: value for key, value in row.items() if key != "report_visual_refs"}
        assert reader.report_visuals({"duplicate"}) == {}


class TestOverview:
    def test_0_3_0_report_346(self) -> None:
        overview = open_check_result(REPORT_346).overview()
        assert overview["source"] == {
            "result_schema": "model_check.check",
            "result_schema_version": "0.3.0",
            "result_file_version": "1.0.0",
        }
        assert overview["verdict"] == "FAIL"
        [check] = overview["checks"]
        assert check["check"] == "no_entrance_sightline_from_lobby_mouth"
        assert check["verdict_counts"] == {"PASS": 44, "FAIL": 1}
        assert check["failing"] == 1
        assert overview["context"]["clause"] == "2.1.1(a)"

    def test_old_label_model_check_rule_0_1_0_is_readable(self) -> None:
        overview = open_check_result(RULE_0_1_0).overview()
        assert overview["source"]["result_schema"] == "model_check.rule"
        assert overview["verdict"] == "FAIL"

    def test_1_0_0_and_0_x_share_the_check_entry_shape(self, tmp_path: Path) -> None:
        legacy = open_check_result(REPORT_346).overview()["checks"][0]
        current = open_check_result(_small_v1(tmp_path)).overview()
        assert set(current["checks"][0]) <= set(legacy) | {"cross_reference"}
        assert {"check", "verdict", "verdict_counts", "failing", "limits_used", "filters_used"} <= set(legacy)
        assert current["verdict"] == "FAIL"
        assert current["checks"][0]["limits_used"] == LIMITS
        assert current["checks"][0]["failing"] == 3
        assert set(current) >= {"source", "workflow_run_id", "generated_at", "summary", "verdict", "checks"}


class TestFailures:
    def test_0_x_item_joins_row_and_names_the_element(self) -> None:
        page = open_check_result(REPORT_346).failures()
        assert page["total"] == 1
        assert page["next_offset"] is None
        [item] = page["items"]
        assert item["check"] == "no_entrance_sightline_from_lobby_mouth"
        assert item["element_name"] == "Wash basin, female toilet"
        assert item["global_ids"]["ids"] == ["1Ajhyyp0g0KH$kaFYBGvul"]
        assert item["reason"]["message"].startswith("Screen the fixture")

    def test_1_0_0_pages_in_file_order(self, tmp_path: Path) -> None:
        reader = open_check_result(_small_v1(tmp_path))
        first = reader.failures("door_width", offset=0, limit=2)
        assert first["total"] == 5
        assert [i["subject_id"] for i in first["items"]] == ["guid-000000", "guid-000002"]
        assert first["next_offset"] == 2
        last = reader.failures("door_width", offset=4, limit=2)
        assert [i["subject_id"] for i in last["items"]] == ["guid-000008"]
        assert last["next_offset"] is None

    def test_1_0_0_item_carries_threshold_and_margin(self, tmp_path: Path) -> None:
        [item] = open_check_result(_small_v1(tmp_path)).failures("door_width", limit=1)["items"]
        assert item["actual"] == 850
        assert item["limits"] == [
            {"input": "min_width_mm", "side": "BELOW", "threshold": 900, "operator": "GTE", "margin": -50}
        ]
        assert item["element_name"] == "Door 0"
        assert item["file_id"] == 42

    def test_other_check_key_returns_nothing(self, tmp_path: Path) -> None:
        page = open_check_result(_small_v1(tmp_path)).failures("no_such_check")
        assert page["total"] == 0
        assert page["items"] == []

    def test_limit_is_capped_and_offset_clamped(self, tmp_path: Path) -> None:
        page = open_check_result(_small_v1(tmp_path)).failures(offset=-5, limit=10_000)
        assert page["offset"] == 0
        assert page["limit"] == MAX_PAGE_SIZE


class TestElement:
    def test_1_0_0_returns_every_row_about_the_element(self, tmp_path: Path) -> None:
        rows = [_measurement(1), _measurement(1, check="door_swing", verdict="PASS"), _measurement(2)]
        reader = open_check_result(_write_v1(tmp_path / "e.json", rows))
        result = reader.element("guid-000001")
        assert [r["check"] for r in result["rows"]] == ["door_width", "door_swing"]
        assert result["identity"] == {"name": "Door 1"}
        assert result["truncated"] is False

    def test_0_x_returns_measurements_of_the_element(self) -> None:
        result = open_check_result(REPORT_346).element("1Ajhyyp0g0KH$kaFYBGvul")
        assert result["rows"]
        assert result["rows"][0]["check"] == "no_entrance_sightline_from_lobby_mouth"

    def test_unknown_element_is_empty(self, tmp_path: Path) -> None:
        result = open_check_result(_small_v1(tmp_path)).element("nope")
        assert result["rows"] == []


class TestRefusals:
    @pytest.mark.parametrize("version", ["2.2.0", "3.0.0"])
    def test_unknown_version_fails_with_a_named_error(self, tmp_path: Path, version: str) -> None:
        path = _write_v1(tmp_path / "x.json", [], version=version)
        with pytest.raises(CheckResultReadError) as info:
            open_check_result(path)
        assert info.value.code == "UNSUPPORTED_RESULT_SCHEMA_VERSION"

    def test_old_label_at_1_x_fails(self, tmp_path: Path) -> None:
        path = _write_v1(tmp_path / "x.json", [], label="model_check.rule")
        with pytest.raises(CheckResultReadError) as info:
            open_check_result(path)
        assert info.value.code == "UNSUPPORTED_RESULT_SCHEMA_VERSION"

    def test_unknown_label_fails(self, tmp_path: Path) -> None:
        path = _write_v1(tmp_path / "x.json", [], label="model_check.suggestion")
        with pytest.raises(CheckResultReadError) as info:
            open_check_result(path)
        assert info.value.code == "UNSUPPORTED_RESULT_SCHEMA"

    def test_not_a_result_file_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "junk.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CheckResultReadError) as info:
            open_check_result(path)
        assert info.value.code == "INVALID_RESULT_FILE"

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        with pytest.raises(CheckResultReadError) as info:
            open_check_result(tmp_path / "absent.json")
        assert info.value.code == "INVALID_RESULT_FILE"

    def test_a_stream_is_refused(self, tmp_path: Path) -> None:
        with (tmp_path / "s.json").open("w+b") as stream, pytest.raises(CheckResultReadError):
            open_check_result(stream)


class TestMemory:
    #: Peak Python allocation allowed while reading the 60k-row file below (measured 0.7 MB). The file is about 13 MB;
    #: a whole-document load needs several hundred MB. Raise this only with a reason.
    PEAK_LIMIT_BYTES = 4 * 1024 * 1024
    ROWS = 60_000

    def _big(self, tmp_path: Path) -> Path:
        rows = (_measurement(i, verdict="FAIL" if i % 7 == 0 else "PASS") for i in range(self.ROWS))
        return _write_v1(tmp_path / "big.json", rows)

    def test_reading_a_large_file_stays_under_the_limit(self, tmp_path: Path) -> None:
        path = self._big(tmp_path)
        assert path.stat().st_size > 10 * 1024 * 1024
        tracemalloc.start()
        try:
            reader = open_check_result(path)
            overview = reader.overview()
            page = reader.failures("door_width", offset=1000, limit=50)
            element = reader.element("guid-059997")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert overview["checks"][0]["check"] == "door_width"
        assert page["total"] == len(range(0, self.ROWS, 7))
        assert len(page["items"]) == 50
        assert [r["check"] for r in element["rows"]] == ["door_width"]
        assert peak < self.PEAK_LIMIT_BYTES, f"peak {peak / 1e6:.1f} MB"
