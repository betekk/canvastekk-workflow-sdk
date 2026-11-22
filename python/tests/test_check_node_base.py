"""Tests for layout 1.1.0, CheckNodeBase, the manifest checks map and registration (#283)."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator

from canvastekk_workflow_sdk import (
    CheckNodeBase,
    NodeExecutionContext,
    NodeExecutionRequest,
    Reading,
    WorkflowNodeBase,
    WorkflowNodeManifest,
    build_workflow_node_registry_payload,
    check_node_conformance_errors,
)
from canvastekk_workflow_sdk.check_verdict import load_check_body_schema
from canvastekk_workflow_sdk.result_file import (
    RESULT_FILE_HEADER_KEYS_BY_VERSION,
    RESULT_FILE_OUTPUT_FIELD,
    ResultFileFormatError,
    build_result_file_header,
    load_result_file_schema,
    read_result_file_header,
    result_file_output_schema,
    serialize_result_file_header_prefix,
    write_result_file,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "schemas" / "result-file"
GOLDEN = CANONICAL / "golden"

RUN_CONTEXT = {
    "run_context_version": "1.0.0",
    "workflow_run_id": "3b2cfd18-0000-4000-8000-000000000001",
    "workflow_definition_id": "model-checker-beam-length-v1.0.0",
    "workflow_definition_slug": "model-checker-beam-length",
    "workflow_definition_version": "1.0.0",
}


def _context(tmp_path: Path, run_context: dict | None = RUN_CONTEXT) -> NodeExecutionContext:
    payload: dict[str, Any] = {"run_id": RUN_CONTEXT["workflow_run_id"], "node_id": "check-1"}
    if run_context is not None:
        payload["run_context"] = run_context
    request = NodeExecutionRequest.model_validate(payload)
    return NodeExecutionContext(request=request, output_dir=tmp_path / "out")


# --- layout 1.1.0 -------------------------------------------------------------------


def test_packaged_1_1_0_schema_equals_canonical() -> None:
    assert load_result_file_schema("1.1.0") == json.loads((CANONICAL / "1.1.0.json").read_text(encoding="utf-8"))
    Draft7Validator.check_schema(load_result_file_schema("1.1.0"))


def test_1_1_0_header_keys_are_1_0_0_plus_three() -> None:
    old, new = RESULT_FILE_HEADER_KEYS_BY_VERSION["1.0.0"], RESULT_FILE_HEADER_KEYS_BY_VERSION["1.1.0"]
    assert set(new) - set(old) == {"workflow_definition", "inputs", "verdict"}
    assert [k for k in new if k in old] == list(old)


def test_write_1_1_0_stamps_definition_from_run_context_and_round_trips(tmp_path: Path) -> None:
    out = write_result_file(
        _context(tmp_path),
        result_schema="model_check.check",
        result_schema_version="1.0.0",
        body={"checks": [], "measurements": []},
        summary={"verdict": "PASS"},
        result_file_version="1.1.0",
        inputs={"threshold_mm": 1000},
        verdict="PASS",
    )
    text = Path(out[RESULT_FILE_OUTPUT_FIELD]).read_text(encoding="utf-8")
    header = read_result_file_header(io.StringIO(text))
    assert header["workflow_definition"] == {
        "id": "model-checker-beam-length-v1.0.0",
        "slug": "model-checker-beam-length",
        "version": "1.0.0",
    }
    assert header["inputs"] == {"threshold_mm": 1000}
    assert header["verdict"] == "PASS"
    assert text.index('"inputs"') < text.index('"generated_at"') < text.index('"verdict"') < text.index('"summary"')


def test_1_1_0_without_run_context_omits_workflow_definition(tmp_path: Path) -> None:
    out = write_result_file(
        _context(tmp_path, run_context=None),
        result_schema="model_check.check",
        result_schema_version="1.0.0",
        body={},
        result_file_version="1.1.0",
    )
    header = read_result_file_header(io.BytesIO(Path(out[RESULT_FILE_OUTPUT_FIELD]).read_bytes()))
    assert "workflow_definition" not in header


@pytest.mark.parametrize(
    "kwargs",
    [
        {"verdict": "PASS"},  # 1.1.0 key on the default 1.0.0 layout
        {"result_file_version": "1.1.0", "verdict": "MAYBE"},
        {"result_file_version": "1.1.0", "inputs": {"big": "x" * 17000}},
        {"result_file_version": "1.1.0", "workflow_definition": {"id": "a", "slug": "b"}},
        {"result_file_version": "9.9.9"},
    ],
)
def test_invalid_1_1_0_rejected_and_nothing_written(tmp_path: Path, kwargs: dict) -> None:
    ctx = _context(tmp_path)
    with pytest.raises(ResultFileFormatError):
        write_result_file(ctx, result_schema="model_check.check", result_schema_version="1.0.0", body={}, **kwargs)
    assert not any(ctx.output_dir.glob("*")) if ctx.output_dir.exists() else True


def test_reader_rejects_misordered_1_1_0_header() -> None:
    header = build_result_file_header(
        result_schema="a.b",
        result_schema_version="1.0.0",
        workflow_run_id="r",
        result_file_version="1.1.0",
        verdict="FAIL",
    )
    good = serialize_result_file_header_prefix(header)
    bad = good.replace('"verdict":"FAIL",', "").replace(
        '"result_schema":"a.b",', '"result_schema":"a.b","verdict":"FAIL",'
    )
    with pytest.raises(ResultFileFormatError, match="out of order"):
        read_result_file_header(io.StringIO(bad + "{}}"))


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="repo checkout only")
def test_golden_1_1_0_bytes(tmp_path: Path) -> None:
    case = json.loads((GOLDEN / "input-1.1.0.json").read_text(encoding="utf-8"))
    out = write_result_file(
        NodeExecutionContext(output_dir=tmp_path / case["workflow_run_id"] / "n", run_id=case["workflow_run_id"]),
        result_schema=case["result_schema"],
        result_schema_version=case["result_schema_version"],
        summary=case["summary"],
        body=case["body"],
        generated_at=datetime.fromisoformat(case["generated_at"].replace("Z", "+00:00")),
        result_file_version=case["result_file_version"],
        workflow_definition=case["workflow_definition"],
        inputs=case["inputs"],
        verdict=case["verdict"],
    )
    expected = (GOLDEN / "expected-1.1.0.json").read_bytes().rstrip(b"\n")
    assert Path(out[RESULT_FILE_OUTPUT_FIELD]).read_bytes() == expected
    document = json.loads(expected)
    assert not list(Draft7Validator(load_result_file_schema("1.1.0")).iter_errors(document))
    assert not list(Draft7Validator(load_check_body_schema()).iter_errors(document["body"]))


# --- manifest -------------------------------------------------------------------------

BEAM_INPUTS = {
    "type": "object",
    "properties": {
        "beam_length_min": {
            "type": "number",
            "default": 1000,
            "x-verdict": {"check": "beam_length", "role": "LIMIT", "operator": "GTE"},
        },
        "beam_length_warn_max": {
            "type": ["number", "null"],
            "default": None,
            "x-verdict": {"check": "beam_length", "role": "WARNING_LIMIT", "operator": "LTE"},
        },
    },
}
BEAM_OUTPUTS = {
    "type": "object",
    "properties": {
        "result_file": result_file_output_schema(),
        "verdict": {"type": "string"},
        "verdict_counts": {"type": "object"},
        "requirement_verdicts": {"type": "object"},
    },
}


def _beam_manifest(**overrides: Any) -> WorkflowNodeManifest:
    data: dict[str, Any] = {
        "slug": "ifc-beam-length",
        "version": "1.0.0",
        "name": "Beam length",
        "description": "Measures each beam's length.",
        "input_schema": BEAM_INPUTS,
        "output_schema": BEAM_OUTPUTS,
        "checks": {"beam_length": {"label": "Beam length", "unit": "mm", "resolution": {"step": 1}}},
    }
    data.update(overrides)
    return WorkflowNodeManifest(**data)


def test_manifest_without_checks_serializes_unchanged() -> None:
    manifest = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="d",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    assert "checks" not in manifest.to_dict()
    assert "checks" not in build_workflow_node_registry_payload(manifest)


def test_manifest_with_checks_serializes_and_registers_them() -> None:
    manifest = _beam_manifest()
    assert manifest.to_dict()["checks"]["beam_length"]["unit"] == "mm"
    payload = build_workflow_node_registry_payload(manifest)
    assert payload["checks"] == {
        "beam_length": {"label": "Beam length", "unit": "mm", "resolution": {"step": 1.0, "rounding": "HALF_UP"}}
    }


def test_manifest_rejects_mark_without_declared_check() -> None:
    with pytest.raises(ValueError, match="not declared"):
        _beam_manifest(checks={"other": {"label": "Other"}})


def test_manifest_rejects_mark_without_checks_map() -> None:
    with pytest.raises(ValueError, match="Invalid verdict marks"):
        _beam_manifest(checks=None)


# --- CheckNodeBase -------------------------------------------------------------------------


class BeamNode(CheckNodeBase):
    manifest = _beam_manifest()

    def measure(self, inputs: dict[str, Any], context: NodeExecutionContext) -> list[Reading]:
        return [
            Reading.value("beam_length", subject_id="B7", actual=3000.4, element_name="Beam B7"),
            Reading.value("beam_length", subject_id="B3", actual=900, element_name="Beam B3"),
        ]


def test_check_node_writes_a_valid_1_1_0_file_and_inline_outputs(tmp_path: Path, monkeypatch) -> None:
    progress: list[tuple[float, str]] = []
    ctx = _context(tmp_path)
    monkeypatch.setattr(ctx, "report_progress", lambda p, m="": progress.append((p, m)))
    outputs = BeamNode().execute({"beam_length_warn_max": 2500}, ctx)
    assert [m for _, m in progress] == ["Measuring", "Judging", "Writing result"]
    assert outputs["verdict"] == "FAIL"
    assert outputs["verdict_counts"] == {"PASS": 0, "WARNING": 1, "FAIL": 1, "NOT_EVALUABLE": 0}
    assert outputs["requirement_verdicts"] == {"beam_length": "FAIL"}
    data = json.loads(Path(outputs[RESULT_FILE_OUTPUT_FIELD]).read_text(encoding="utf-8"))
    assert not list(Draft7Validator(load_result_file_schema("1.1.0")).iter_errors(data))
    assert data["result_schema"] == "model_check.check" and data["result_schema_version"] == "1.0.0"
    assert data["inputs"] == {"beam_length_min": 1000, "beam_length_warn_max": 2500}
    assert data["verdict"] == "FAIL"
    assert data["summary"]["warning_count"] == 1
    assert data["body"]["measurements"][0]["actual"] == 3000


def test_check_node_cannot_override_execute() -> None:
    with pytest.raises(TypeError, match="must not override execute"):

        class Bad(CheckNodeBase):
            manifest = _beam_manifest()

            def measure(self, inputs, context):
                return []

            def execute(self, inputs, context):  # type: ignore[override]
                return {}


def test_check_node_needs_checks_map() -> None:
    with pytest.raises(TypeError, match="checks"):

        class NoChecks(CheckNodeBase):
            manifest = WorkflowNodeManifest(
                slug="x",
                version="1.0.0",
                name="X",
                description="d",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def measure(self, inputs, context):
                return []


def test_marked_plain_node_is_rejected_at_class_creation() -> None:
    with pytest.raises(TypeError, match="does not subclass CheckNodeBase"):

        class Plain(WorkflowNodeBase):
            manifest = _beam_manifest()

            def execute(self, inputs, context):
                return {}


def test_conformance_helper() -> None:
    assert check_node_conformance_errors(BeamNode) == []

    class Unmarked(WorkflowNodeBase):
        manifest = WorkflowNodeManifest(
            slug="u",
            version="1.0.0",
            name="U",
            description="d",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        def execute(self, inputs, context):
            return {}

    assert check_node_conformance_errors(Unmarked) == []
    fake = type("Fake", (), {"manifest": _beam_manifest()})
    assert check_node_conformance_errors(fake) == [
        "Fake marks inputs with x-verdict but does not subclass CheckNodeBase"
    ]


def test_legacy_format_calls_the_hook(tmp_path: Path) -> None:
    calls: list[str] = []

    class Legacy(CheckNodeBase):
        manifest = _beam_manifest()
        result_body_format = "legacy"

        def measure(self, inputs, context):
            return [Reading.value("beam_length", subject_id="B1", actual=1500)]

        def write_legacy_result(self, judged, inputs, context):
            calls.append(judged.verdict)
            return {"result_file": "legacy.json", "verdict": "KEEP-MINE"}

    outputs = Legacy().execute({}, _context(tmp_path))
    assert calls == ["PASS"]
    assert outputs["verdict"] == "KEEP-MINE"  # the hook's own keys win
    assert outputs["requirement_verdicts"] == {"beam_length": "PASS"}


def test_legacy_without_hook_raises(tmp_path: Path) -> None:
    class Legacy(CheckNodeBase):
        manifest = _beam_manifest()
        result_body_format = "legacy"

        def measure(self, inputs, context):
            return [Reading.value("beam_length", subject_id="B1", actual=1500)]

    with pytest.raises(NotImplementedError):
        Legacy().execute({}, _context(tmp_path))


def test_measure_must_return_readings(tmp_path: Path) -> None:
    class Wrong(CheckNodeBase):
        manifest = _beam_manifest()

        def measure(self, inputs, context):
            return [{"check": "beam_length"}]

    with pytest.raises(Exception, match="Reading objects"):
        Wrong().execute({}, _context(tmp_path))


def test_check_node_runs_through_the_sdk_request_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NODE_OUTPUT_DIR", str(tmp_path))
    request = NodeExecutionRequest.model_validate(
        {"run_id": "r-9", "node_id": "check-1", "inputs": {}, "run_context": {**RUN_CONTEXT, "workflow_run_id": "r-9"}}
    )
    response = BeamNode().run(request)
    assert response.status == "pass", response
    assert response.outputs["verdict"] == "FAIL"
