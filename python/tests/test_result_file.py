"""Result file standard (#278): layout, writer, header reader, manifest convention."""

from __future__ import annotations

import io
import json
import tracemalloc
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from canvastekk_workflow_sdk import NodeExecutionContext, NodeOutputValidationError, WorkflowNodeManifest
from canvastekk_workflow_sdk.result_file import (
    RESULT_FILE_HEADER_KEYS,
    RESULT_FILE_OUTPUT_FIELD,
    ResultFileFormatError,
    build_result_file_header,
    load_result_file_end_value_schema,
    load_result_file_schema,
    read_result_file_header,
    result_file_output_schema,
    serialize_result_file_header_prefix,
    validate_result_file_header,
    write_result_file,
)

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO / "schemas" / "result-file"
PACKAGED = REPO / "python" / "canvastekk_workflow_sdk" / "data" / "schemas" / "result-file"
GOLDEN = CANONICAL / "golden"
FIXED = datetime(2026, 11, 20, 10, 0, 0, 123000, tzinfo=UTC)


@pytest.fixture
def ctx(tmp_path: Path) -> NodeExecutionContext:
    return NodeExecutionContext(output_dir=tmp_path / "run-abc" / "check-1", run_id="run-abc", node_id="check-1")


def _write(ctx: NodeExecutionContext, **kw):
    params = {"result_schema": "model_check.rule", "result_schema_version": "0.1.0", "body": {"ok": True}}
    params.update(kw)
    return write_result_file(ctx, **params)


# --- schemas -----------------------------------------------------------------


@pytest.mark.skipif(not CANONICAL.is_dir(), reason="repo checkout only")
@pytest.mark.parametrize("name", ["1.0.0.json", "end-value-1.0.0.json"])
def test_packaged_schemas_equal_canonical(name: str) -> None:
    assert (PACKAGED / name).read_bytes() == (CANONICAL / name).read_bytes()


def test_schemas_are_valid_draft7() -> None:
    Draft7Validator.check_schema(load_result_file_schema())
    Draft7Validator.check_schema(load_result_file_end_value_schema())


def test_end_value_schema_accepts_engine_pointer() -> None:
    validator = Draft7Validator(load_result_file_end_value_schema())
    assert validator.is_valid("s3://bucket/runs/abc/output/result.json")
    assert not validator.is_valid("https://example.com/x.json")
    assert not validator.is_valid({"path": "s3://b/k"})


# --- writer ------------------------------------------------------------------


def test_write_returns_result_file_output_and_valid_document(ctx: NodeExecutionContext) -> None:
    out = _write(ctx, summary={"verdict": "FAIL", "fail_count": 14}, generated_at=FIXED)
    assert list(out) == [RESULT_FILE_OUTPUT_FIELD]
    path = Path(out[RESULT_FILE_OUTPUT_FIELD])
    assert path.parent == ctx.output_dir and path.name == "result.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    Draft7Validator(load_result_file_schema()).validate(doc)
    assert doc["workflow_run_id"] == "run-abc"
    assert doc["generated_at"] == "2026-11-20T10:00:00.123Z"
    assert doc["body"] == {"ok": True}


def test_header_keys_precede_body(ctx: NodeExecutionContext) -> None:
    out = _write(ctx, summary={"verdict": "PASS"}, body={"z": list(range(1000))}, generated_at=FIXED)
    with open(out[RESULT_FILE_OUTPUT_FIELD], "rb") as handle:
        start = handle.read(400).decode("utf-8")
    positions = [start.index(f'"{key}":') for key in RESULT_FILE_HEADER_KEYS]
    assert positions == sorted(positions)
    assert positions[-1] < start.index('"body":')


def test_summary_is_optional(ctx: NodeExecutionContext) -> None:
    doc = json.loads(Path(_write(ctx)[RESULT_FILE_OUTPUT_FIELD]).read_text())
    assert "summary" not in doc


def test_default_generated_at_is_utc_now(ctx: NodeExecutionContext) -> None:
    doc = json.loads(Path(_write(ctx)[RESULT_FILE_OUTPUT_FIELD]).read_text())
    stamp = datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00"))
    assert abs(datetime.now(UTC) - stamp) < timedelta(minutes=1)


def test_generated_at_is_normalised_to_utc(ctx: NodeExecutionContext) -> None:
    plus8 = FIXED.astimezone(timezone(timedelta(hours=8)))
    doc = json.loads(Path(_write(ctx, generated_at=plus8)[RESULT_FILE_OUTPUT_FIELD]).read_text())
    assert doc["generated_at"] == "2026-11-20T10:00:00.123Z"


def test_naive_generated_at_rejected(ctx: NodeExecutionContext) -> None:
    with pytest.raises(ResultFileFormatError):
        _write(ctx, generated_at=datetime(2026, 1, 1))
    assert list(ctx.output_dir.iterdir()) == []


BAD_CASES = {
    "nested summary": {"summary": {"counts": {"fail": 1}}},
    "list in summary": {"summary": {"ids": [1, 2]}},
    "camelCase summary key": {"summary": {"failCount": 1}},
    "kebab summary key": {"summary": {"fail-count": 1}},
    "summary not an object": {"summary": ["verdict"]},
    "summary over 2 KB": {"summary": {"note": "x" * 2100}},
    "summary NaN": {"summary": {"ratio": float("nan")}},
    "label without dot": {"result_schema": "modelcheck"},
    "label with capitals": {"result_schema": "Model_check.rule"},
    "label with hyphen": {"result_schema": "model-check.rule"},
    "version not semver": {"result_schema_version": "1.0"},
    "version with prerelease": {"result_schema_version": "1.0.0-rc.1"},
    "body not JSON": {"body": {"when": datetime(2026, 1, 1)}},
    "body NaN": {"body": {"x": float("inf")}},
}


@pytest.mark.parametrize("case", sorted(BAD_CASES))
def test_invalid_input_rejected_and_no_file_written(ctx: NodeExecutionContext, case: str) -> None:
    with pytest.raises(ResultFileFormatError) as info:
        _write(ctx, **BAD_CASES[case])
    assert isinstance(info.value, NodeOutputValidationError)
    assert info.value.error_code == "OUTPUT_VALIDATION_ERROR"
    assert list(ctx.output_dir.iterdir()) == []


def test_summary_exactly_at_limit_accepted(ctx: NodeExecutionContext) -> None:
    filler = 2048 - len('{"note":""}')
    _write(ctx, summary={"note": "x" * filler})


def test_summary_limit_counts_utf8_bytes(ctx: NodeExecutionContext) -> None:
    with pytest.raises(ResultFileFormatError):
        _write(ctx, summary={"note": "é" * 1100})  # 2200 bytes, 1100 characters


def test_custom_filename_and_traversal(ctx: NodeExecutionContext) -> None:
    out = _write(ctx, filename="check.result.json")
    assert Path(out[RESULT_FILE_OUTPUT_FIELD]).name == "check.result.json"
    with pytest.raises(ValueError):
        _write(ctx, filename="../escape.json")


# --- header validation -------------------------------------------------------


def test_validate_rejects_unknown_and_missing_keys() -> None:
    header = build_result_file_header(
        result_schema="a.b", result_schema_version="1.0.0", workflow_run_id="r", generated_at=FIXED
    )
    with pytest.raises(ResultFileFormatError):
        validate_result_file_header({**header, "extra": 1})
    missing = dict(header)
    missing.pop("workflow_run_id")
    with pytest.raises(ResultFileFormatError) as info:
        validate_result_file_header(missing)
    assert info.value.errors
    with pytest.raises(ResultFileFormatError):
        validate_result_file_header({**header, "result_file_version": "2.0.0"})
    with pytest.raises(ResultFileFormatError):
        validate_result_file_header({**header, "body": {}})


# --- header reader -----------------------------------------------------------


def _doc(header_extra: str = "", body: str = '{"x":1}') -> bytes:
    return (
        '{"result_file_version":"1.0.0","result_schema":"model_check.rule","result_schema_version":"0.1.0",'
        f'"workflow_run_id":"r1","generated_at":"2026-11-20T10:00:00.000Z"{header_extra},"body":{body}}}'
    ).encode()


def test_reader_returns_header_written_by_writer(ctx: NodeExecutionContext) -> None:
    out = _write(ctx, summary={"verdict": "FAIL", "pass_count": 9}, generated_at=FIXED)
    with open(out[RESULT_FILE_OUTPUT_FIELD], "rb") as handle:
        header = read_result_file_header(handle)
    assert header["summary"] == {"verdict": "FAIL", "pass_count": 9}
    assert "body" not in header


def test_reader_accepts_text_stream_and_whitespace() -> None:
    pretty = json.dumps(json.loads(_doc(',"summary":{"n":12345}')), indent=2)
    assert read_result_file_header(io.StringIO(pretty))["summary"] == {"n": 12345}


def test_reader_handles_values_split_across_chunks() -> None:
    long_id = "r" * 100
    data = _doc().replace(b'"r1"', f'"{long_id}"'.encode())

    class Trickle(io.RawIOBase):
        def __init__(self, raw: bytes) -> None:
            self._raw = io.BytesIO(raw)

        def read(self, size: int = -1) -> bytes:
            return self._raw.read(3)

    assert read_result_file_header(Trickle(data))["workflow_run_id"] == long_id


def test_reader_handles_multibyte_split_across_chunks() -> None:
    data = _doc(',"summary":{"note":"' + "é" * 50 + '"}')

    class Odd(io.RawIOBase):
        def __init__(self, raw: bytes) -> None:
            self._raw = io.BytesIO(raw)

        def read(self, size: int = -1) -> bytes:
            return self._raw.read(7)

    assert read_result_file_header(Odd(data))["summary"]["note"] == "é" * 50


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (b"[]", "not valid JSON"),
        (b"not json", "not valid JSON"),
        (_doc()[:60], "ended early"),
        (_doc().replace(b',"body":{"x":1}', b""), "no body"),
        (
            b'{"body":{},"result_file_version":"1.0.0","result_schema":"a.b","result_schema_version":"1.0.0",'
            b'"workflow_run_id":"r","generated_at":"2026-11-20T10:00:00.000Z"}',
            "invalid",
        ),
        (
            _doc()
            .replace(b'"result_schema":"model_check.rule",', b"")
            .replace(b'"generated_at"', b'"result_schema":"model_check.rule","generated_at"'),
            "out of order",
        ),
        (_doc(',"result_schema":"x.y"'), "repeats"),
        (_doc(',"summary":{"a":{"b":1}}'), "invalid"),
        (_doc().replace(b'"1.0.0"', b'"9.0.0"', 1), "Unsupported"),
    ],
)
def test_reader_rejects(data: bytes, fragment: str) -> None:
    with pytest.raises(ResultFileFormatError, match=fragment):
        read_result_file_header(io.BytesIO(data))


def test_reader_rejects_oversized_header() -> None:
    data = _doc(',"summary":{"note":"' + "x" * 100_000 + '"}')
    with pytest.raises(ResultFileFormatError, match="longer than"):
        read_result_file_header(io.BytesIO(data))


def test_reader_does_not_read_a_50mb_body(tmp_path: Path, ctx: NodeExecutionContext) -> None:
    big = tmp_path / "big.json"
    prefix = serialize_result_file_header_prefix(
        build_result_file_header(
            result_schema="model_check.rule",
            result_schema_version="0.1.0",
            workflow_run_id="r1",
            summary={"verdict": "FAIL"},
            generated_at=FIXED,
        )
    )
    with open(big, "w", encoding="utf-8") as handle:
        handle.write(prefix + '{"rows":[')
        row = '{"id":"' + "a" * 90 + '"},'
        for _ in range((50 * 1024 * 1024) // len(row)):
            handle.write(row)
        handle.write('{"id":"end"}]}}')
    assert big.stat().st_size >= 50 * 1024 * 1024

    class Counting(io.FileIO):
        consumed = 0

        def read(self, size: int = -1) -> bytes:
            chunk = super().read(size)
            Counting.consumed += len(chunk)
            return chunk

    tracemalloc.start()
    with Counting(big, "r") as handle:
        header = read_result_file_header(handle)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert header["summary"] == {"verdict": "FAIL"}
    assert Counting.consumed < 64 * 1024
    assert peak < 1024 * 1024


# --- manifest convention -----------------------------------------------------


def _manifest(output_props: dict, input_props: dict | None = None) -> WorkflowNodeManifest:
    return WorkflowNodeManifest(
        slug="result-node",
        version="1.0.0",
        name="Result node",
        description="d",
        input_schema={"type": "object", "properties": input_props or {}},
        output_schema={"type": "object", "properties": output_props},
    )


def test_manifest_accepts_result_file_output() -> None:
    manifest = _manifest({"verdict": {"type": "string"}, "result_file": result_file_output_schema("The result")})
    assert manifest.file_output_fields == ["result_file"]
    assert manifest.output_schema["properties"]["result_file"]["x-result-file"] is True


@pytest.mark.parametrize(
    "props",
    [
        {"result_file": {"type": "string", "format": "file"}},
        {"result_file": {"type": "string"}},
        {"result_file": {"type": "array", "items": {"type": "string", "format": "file"}, "x-result-file": True}},
        {"result_file": {**result_file_output_schema(), "contentMediaType": "text/csv"}},
        {"other": result_file_output_schema()},
    ],
)
def test_manifest_rejects_wrong_declarations(props: dict) -> None:
    with pytest.raises(ValueError, match="result"):
        _manifest(props)


def test_manifest_rejects_marker_on_inputs() -> None:
    with pytest.raises(ValueError, match="outputs only"):
        _manifest({}, input_props={"result_file": result_file_output_schema()})


def test_manifest_without_result_file_unchanged() -> None:
    _manifest({"report": {"type": "string", "format": "file"}})


# --- golden parity (TypeScript asserts the same bytes) -----------------------


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="repo checkout only")
def test_golden_bytes(ctx: NodeExecutionContext) -> None:
    case = json.loads((GOLDEN / "input.json").read_text(encoding="utf-8"))
    out = write_result_file(
        NodeExecutionContext(output_dir=ctx.output_dir.parent / case["workflow_run_id"] / "n"),
        result_schema=case["result_schema"],
        result_schema_version=case["result_schema_version"],
        summary=case["summary"],
        body=case["body"],
        generated_at=datetime.fromisoformat(case["generated_at"].replace("Z", "+00:00")),
    )
    expected = (GOLDEN / "expected.json").read_bytes().rstrip(b"\n")
    assert Path(out[RESULT_FILE_OUTPUT_FIELD]).read_bytes() == expected
