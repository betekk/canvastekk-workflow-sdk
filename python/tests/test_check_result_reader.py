"""#288: streaming reader for ``model_check.check`` result files (0.x and 1.0.0)."""

from __future__ import annotations

import json
import tracemalloc
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ijson")

from canvastekk_workflow_sdk.check_result_reader import (  # noqa: E402
    MAX_PAGE_SIZE,
    CheckResultReadError,
    open_check_result,
)

FIXTURES = Path(__file__).parent / "fixtures" / "check_results"
REPORT_346 = FIXTURES / "report_346_entrance_sightline_0.3.0.json"
RULE_0_1_0 = FIXTURES / "model_check_rule_0.1.0.json"

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
    def test_unknown_major_fails_with_a_named_error(self, tmp_path: Path) -> None:
        path = _write_v1(tmp_path / "x.json", [], version="2.0.0")
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
