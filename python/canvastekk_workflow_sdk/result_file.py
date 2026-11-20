"""Workflow run result files: the platform standard (#278, epic tracker#4309).

A result file is one plain JSON document per run, written by the node that
produces the run's result. The SDK owns the **layout**; what goes inside
``body`` belongs to the producing app and is never validated here.

Layout 1.0.0, header keys first and in this order::

    {
      "result_file_version": "1.0.0",
      "result_schema": "model_check.rule",
      "result_schema_version": "0.1.0",
      "workflow_run_id": "...",
      "generated_at": "2026-11-20T10:00:00.000Z",
      "summary": {"verdict": "FAIL", "fail_count": 14},
      "body": {...}
    }

- ``result_schema`` / ``result_schema_version`` are labels the app chooses
  (``app.kind`` + semver). The platform compares them, never interprets them.
- ``summary`` is optional: flat, scalar values, ``snake_case`` keys, at most
  :data:`RESULT_FILE_SUMMARY_MAX_BYTES` as compact UTF-8 JSON.
- ``body`` is any JSON value.

:func:`write_result_file` is the only supported way to produce a file. It
validates the header and ``summary`` first and writes nothing when they are
invalid. :func:`read_result_file_header` reads the header from a stream and
stops at ``body``, so a large file is checked without loading its content.

The canonical JSON Schemas live in the repository's ``schemas/result-file/``
folder and ship in the wheel under ``canvastekk_workflow_sdk/data/schemas``.
"""

from __future__ import annotations

import codecs
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cache
from importlib import resources
from typing import IO, TYPE_CHECKING, Any

from jsonschema import Draft7Validator

from canvastekk_workflow_sdk.exceptions import NodeOutputValidationError

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.node_execution_context import NodeExecutionContext

RESULT_FILE_VERSION = "1.0.0"
"""Version of the platform layout written by this SDK."""

SUPPORTED_RESULT_FILE_VERSIONS: tuple[str, ...] = ("1.0.0",)
"""Layout versions :func:`read_result_file_header` accepts."""

RESULT_FILE_OUTPUT_FIELD = "result_file"
"""Name of the node output (and of the reserved ``__end__`` key) that carries the file."""

RESULT_FILE_MARKER = "x-result-file"
"""Output-schema extension marking the ``result_file`` output (manifest convention)."""

RESULT_FILE_CONTENT_TYPE = "application/json"

RESULT_FILE_DEFAULT_NAME = "result.json"

RESULT_FILE_SUMMARY_MAX_BYTES = 2048
"""Upper bound for ``summary`` as compact UTF-8 JSON."""

RESULT_FILE_HEADER_MAX_BYTES = 65536
"""Upper bound for the header (everything before ``body``) when reading, in decoded characters."""

RESULT_FILE_HEADER_KEYS: tuple[str, ...] = (
    "result_file_version",
    "result_schema",
    "result_schema_version",
    "workflow_run_id",
    "generated_at",
    "summary",
)
"""Header keys in their required order (``summary`` is optional)."""

_SCHEMA_DIR = ("data", "schemas", "result-file")
_READ_CHUNK = 8192
_WHITESPACE = " \t\n\r"


class ResultFileFormatError(NodeOutputValidationError):
    """A result file (or the data meant for one) breaks the platform layout."""


def _schema_text(name: str) -> str:
    root = resources.files("canvastekk_workflow_sdk")
    for part in _SCHEMA_DIR:
        root = root.joinpath(part)
    return root.joinpath(name).read_text(encoding="utf-8")


@cache
def load_result_file_schema(version: str = RESULT_FILE_VERSION) -> dict[str, Any]:
    """Return the packaged layout JSON Schema for ``version``.

    Args:
        version: Layout version, e.g. ``"1.0.0"``.

    Returns:
        The JSON Schema (draft-07) as a dict. Callers must not mutate it.

    Raises:
        ResultFileFormatError: If the version is not supported.
    """
    if version not in SUPPORTED_RESULT_FILE_VERSIONS:
        raise ResultFileFormatError(f"Unsupported result_file_version {version!r}")
    return json.loads(_schema_text(f"{version}.json"))


@cache
def load_result_file_end_value_schema(version: str = RESULT_FILE_VERSION) -> dict[str, Any]:
    """Return the JSON Schema of the reserved ``__end__.result_file`` value.

    Args:
        version: Layout version, e.g. ``"1.0.0"``.

    Returns:
        The JSON Schema (draft-07) as a dict. Callers must not mutate it.
    """
    if version not in SUPPORTED_RESULT_FILE_VERSIONS:
        raise ResultFileFormatError(f"Unsupported result_file_version {version!r}")
    return json.loads(_schema_text(f"end-value-{version}.json"))


@cache
def _header_validator(version: str) -> Draft7Validator:
    schema = dict(load_result_file_schema(version))
    schema["required"] = [key for key in schema["required"] if key != "body"]
    properties = dict(schema["properties"])
    properties.pop("body", None)
    schema["properties"] = properties
    return Draft7Validator(schema)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _format_generated_at(value: datetime | None) -> str:
    moment = value if value is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        raise ResultFileFormatError("generated_at must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_result_file_header(header: Mapping[str, Any]) -> dict[str, Any]:
    """Check a header (every layout key except ``body``).

    Checks the layout schema, the supported ``result_file_version`` and the
    ``summary`` byte limit. ``body`` must not be part of ``header``.

    Args:
        header: The header mapping.

    Returns:
        A plain-dict copy of the header.

    Raises:
        ResultFileFormatError: With one entry per problem in ``errors``.
    """
    if not isinstance(header, Mapping):
        raise ResultFileFormatError("Result file header must be a JSON object")
    data = dict(header)
    if "body" in data:
        raise ResultFileFormatError("Result file header must not contain body")
    version = data.get("result_file_version")
    if version not in SUPPORTED_RESULT_FILE_VERSIONS:
        raise ResultFileFormatError(
            f"Unsupported result_file_version {version!r}; supported: {list(SUPPORTED_RESULT_FILE_VERSIONS)}"
        )
    errors = [
        {"path": "/".join(str(p) for p in err.absolute_path) or "(root)", "message": err.message}
        for err in sorted(_header_validator(version).iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    summary = data.get("summary")
    if isinstance(summary, dict) and not errors:
        try:
            size = len(_compact(summary).encode("utf-8"))
        except ValueError as exc:
            errors.append({"path": "summary", "message": f"summary is not valid JSON: {exc}"})
        else:
            if size > RESULT_FILE_SUMMARY_MAX_BYTES:
                errors.append(
                    {
                        "path": "summary",
                        "message": f"summary is {size} bytes; the limit is {RESULT_FILE_SUMMARY_MAX_BYTES}",
                    }
                )
    if errors:
        raise ResultFileFormatError(
            "Result file header is invalid: " + "; ".join(f"{e['path']}: {e['message']}" for e in errors),
            errors=errors,
        )
    return data


def build_result_file_header(
    *,
    result_schema: str,
    result_schema_version: str,
    workflow_run_id: str,
    summary: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build and validate a header in the required key order.

    Args:
        result_schema: App label for the body's shape, e.g. ``"model_check.rule"``.
        result_schema_version: Semver of that shape, e.g. ``"0.1.0"``.
        workflow_run_id: The run id (``context.run_id``).
        summary: Optional flat key-value pairs.
        generated_at: Timezone-aware timestamp; defaults to now (UTC).

    Returns:
        The validated header dict (no ``body``).

    Raises:
        ResultFileFormatError: If any header value breaks the layout.
    """
    header: dict[str, Any] = {
        "result_file_version": RESULT_FILE_VERSION,
        "result_schema": result_schema,
        "result_schema_version": result_schema_version,
        "workflow_run_id": workflow_run_id,
        "generated_at": _format_generated_at(generated_at),
    }
    if summary is not None:
        header["summary"] = dict(summary) if isinstance(summary, Mapping) else summary
    return validate_result_file_header(header)


def serialize_result_file_header_prefix(header: Mapping[str, Any]) -> str:
    """Return the file text up to and including ``"body":``.

    Exposed so both runtimes can be compared byte for byte (golden tests).

    Args:
        header: A validated header.

    Returns:
        ``{"result_file_version":...,"body":`` with keys in layout order.
    """
    parts = [f"{_compact(key)}:{_compact(header[key])}" for key in RESULT_FILE_HEADER_KEYS if key in header]
    return "{" + ",".join(parts) + ',"body":'


def write_result_file(
    context: NodeExecutionContext,
    *,
    result_schema: str,
    result_schema_version: str,
    body: Any,
    summary: Mapping[str, Any] | None = None,
    filename: str = RESULT_FILE_DEFAULT_NAME,
    generated_at: datetime | None = None,
) -> dict[str, str]:
    """Write the run's result file and return it as the ``result_file`` output.

    The header and ``summary`` are validated **before** anything is written;
    ``body`` is encoded to a temporary file that is renamed into place only
    when encoding succeeded, so a failure never leaves a file behind.

    Usage inside ``execute``::

        outputs = {"verdict": verdict}
        outputs.update(write_result_file(context, result_schema="model_check.rule",
                                         result_schema_version="0.1.0", body=result,
                                         summary={"verdict": verdict}))
        return outputs

    Declare the output with :func:`result_file_output_schema`.

    Args:
        context: The node execution context (supplies ``run_id`` and the output folder).
        result_schema: App label for the body's shape.
        result_schema_version: Semver of that shape.
        body: Any JSON-serializable value (app-owned; not validated).
        summary: Optional flat key-value pairs (≤2 KB).
        filename: File name inside the context's output folder.
        generated_at: Timezone-aware timestamp; defaults to now (UTC).

    Returns:
        ``{"result_file": "<local path>"}``; the SDK uploads it after ``execute``.

    Raises:
        ResultFileFormatError: Invalid header, ``summary`` or non-JSON ``body``.
    """
    header = build_result_file_header(
        result_schema=result_schema,
        result_schema_version=result_schema_version,
        workflow_run_id=context.run_id,
        summary=summary,
        generated_at=generated_at,
    )
    target = context.output_path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".result-file-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialize_result_file_header_prefix(header))
            encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            for chunk in encoder.iterencode(body):
                handle.write(chunk)
            handle.write("}")
        os.replace(tmp_name, target)
    except (TypeError, ValueError) as exc:
        _remove_quietly(tmp_name)
        raise ResultFileFormatError(f"Result file body is not valid JSON: {exc}") from exc
    except BaseException:
        _remove_quietly(tmp_name)
        raise
    return {RESULT_FILE_OUTPUT_FIELD: str(target)}


def _remove_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def result_file_output_schema(description: str | None = None) -> dict[str, Any]:
    """Return the output-schema property that declares a node's result file.

    Use it as ``output_schema["properties"]["result_file"]``. The manifest
    rejects any other shape for an output named ``result_file``.

    Args:
        description: Optional field description.

    Returns:
        ``{"type": "string", "format": "file", "contentMediaType": "application/json", "x-result-file": True}``
        plus ``description`` when given.
    """
    schema: dict[str, Any] = {
        "type": "string",
        "format": "file",
        "contentMediaType": RESULT_FILE_CONTENT_TYPE,
        RESULT_FILE_MARKER: True,
    }
    if description:
        schema["description"] = description
    return schema


def result_file_declaration_errors(properties: Mapping[str, Any], *, schema_name: str) -> list[str]:
    """Return manifest problems with the result-file convention (empty = fine).

    Rules: an output named ``result_file`` must be a single JSON file output
    marked ``x-result-file: true``; the marker is legal only on that output;
    input schemas never carry it.

    Args:
        properties: ``input_schema``/``output_schema`` ``properties``.
        schema_name: ``"input_schema"`` or ``"output_schema"``.

    Returns:
        Human-readable problems.
    """
    problems: list[str] = []
    for name, prop in properties.items():
        if not isinstance(prop, Mapping):
            continue
        marked = prop.get(RESULT_FILE_MARKER) is not None
        if schema_name != "output_schema":
            if marked:
                problems.append(f"Input field '{name}' must not carry '{RESULT_FILE_MARKER}' (outputs only).")
            continue
        if name == RESULT_FILE_OUTPUT_FIELD:
            if not (
                prop.get("type") == "string"
                and prop.get("format") == "file"
                and prop.get(RESULT_FILE_MARKER) is True
                and prop.get("contentMediaType", RESULT_FILE_CONTENT_TYPE) == RESULT_FILE_CONTENT_TYPE
            ):
                problems.append(
                    f"Output '{RESULT_FILE_OUTPUT_FIELD}' is reserved for the result file: declare it with "
                    "result_file_output_schema() / resultFileOutputSchema() (type string, format file, contentMediaType application/json, "
                    f"'{RESULT_FILE_MARKER}': true). See docs/RESULT-FILE.md."
                )
        elif marked:
            problems.append(f"Output '{name}' carries '{RESULT_FILE_MARKER}'; only '{RESULT_FILE_OUTPUT_FIELD}' may.")
    return problems


def read_result_file_header(
    stream: IO[bytes] | IO[str],
    *,
    max_header_bytes: int = RESULT_FILE_HEADER_MAX_BYTES,
) -> dict[str, Any]:
    """Read and validate the header of a result file, stopping at ``body``.

    Parses the top-level object one member at a time and returns as soon as
    the ``body`` key is reached, so ``body`` is never read. Header keys after
    ``body`` are a layout breach and surface as missing keys.

    Args:
        stream: Binary (UTF-8) or text stream positioned at the start.
        max_header_bytes: Give up if the header is longer than this many decoded characters.

    Returns:
        The validated header dict (no ``body``).

    Raises:
        ResultFileFormatError: Not JSON, not an object, missing ``body``,
            duplicate or misordered keys, oversized or invalid header.
    """
    reader = _IncrementalReader(stream, max_header_bytes)
    reader.expect("{")
    header: dict[str, Any] = {}
    while True:
        reader.skip_ws()
        if reader.peek() == "}":
            raise ResultFileFormatError("Result file has no body")
        key = reader.decode_value()
        if not isinstance(key, str):
            raise ResultFileFormatError("Result file is not valid JSON (object key expected)")
        reader.expect(":")
        if key == "body":
            break
        if key in header:
            raise ResultFileFormatError(f"Result file repeats header key {key!r}")
        header[key] = reader.decode_value()
        reader.skip_ws()
        separator = reader.next_char()
        if separator == "}":
            raise ResultFileFormatError("Result file has no body")
        if separator != ",":
            raise ResultFileFormatError("Result file is not valid JSON (',' expected)")
    missing = [k for k in RESULT_FILE_HEADER_KEYS if k != "summary" and k not in header]
    if missing:
        raise ResultFileFormatError(
            f"Result file header is invalid: header keys must come before body; missing {missing}"
        )
    order = [k for k in header if k in RESULT_FILE_HEADER_KEYS]
    if order != [k for k in RESULT_FILE_HEADER_KEYS if k in header]:
        raise ResultFileFormatError(f"Result file header keys are out of order: {order}")
    return validate_result_file_header(header)


class _IncrementalReader:
    """Minimal pull parser over a stream, enough for top-level members."""

    def __init__(self, stream: IO[bytes] | IO[str], limit: int) -> None:
        self._stream = stream
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._pos = 0
        self._consumed = 0
        self._eof = False
        self._limit = limit
        self._json = json.JSONDecoder()

    def _fill(self) -> bool:
        if self._eof:
            return False
        chunk = self._stream.read(_READ_CHUNK)
        if not chunk:
            self._eof = True
            tail = self._decoder.decode(b"", final=True) if not isinstance(chunk, str) else ""
            if tail:
                self._buffer += tail
                return True
            return False
        text = chunk if isinstance(chunk, str) else self._decoder.decode(chunk)
        if self._pos:
            self._consumed += self._pos
            self._buffer = self._buffer[self._pos :]
            self._pos = 0
        self._buffer += text
        if self._consumed + len(self._buffer) > self._limit + _READ_CHUNK:
            raise ResultFileFormatError(f"Result file header is longer than {self._limit} bytes")
        return True

    def _check_limit(self) -> None:
        if self._consumed + self._pos > self._limit:
            raise ResultFileFormatError(f"Result file header is longer than {self._limit} bytes")

    def skip_ws(self) -> None:
        while True:
            while self._pos < len(self._buffer) and self._buffer[self._pos] in _WHITESPACE:
                self._pos += 1
            if self._pos < len(self._buffer) or not self._fill():
                self._check_limit()
                return

    def peek(self) -> str:
        self.skip_ws()
        if self._pos >= len(self._buffer):
            raise ResultFileFormatError("Result file ended early")
        return self._buffer[self._pos]

    def next_char(self) -> str:
        char = self.peek()
        self._pos += 1
        return char

    def expect(self, char: str) -> None:
        if self.next_char() != char:
            raise ResultFileFormatError(f"Result file is not valid JSON ({char!r} expected)")

    def decode_value(self) -> Any:
        self.skip_ws()
        while True:
            try:
                value, end = self._json.raw_decode(self._buffer, self._pos)
            except json.JSONDecodeError:
                if not self._fill():
                    raise ResultFileFormatError("Result file ended early or is not valid JSON") from None
                continue
            if end >= len(self._buffer) and not self._eof and self._fill():
                continue  # a number may continue in the next chunk
            self._pos = end
            self._check_limit()
            return value


__all__ = [
    "RESULT_FILE_CONTENT_TYPE",
    "RESULT_FILE_DEFAULT_NAME",
    "RESULT_FILE_HEADER_KEYS",
    "RESULT_FILE_HEADER_MAX_BYTES",
    "RESULT_FILE_MARKER",
    "RESULT_FILE_OUTPUT_FIELD",
    "RESULT_FILE_SUMMARY_MAX_BYTES",
    "RESULT_FILE_VERSION",
    "SUPPORTED_RESULT_FILE_VERSIONS",
    "ResultFileFormatError",
    "build_result_file_header",
    "load_result_file_end_value_schema",
    "load_result_file_schema",
    "read_result_file_header",
    "result_file_declaration_errors",
    "result_file_output_schema",
    "serialize_result_file_header_prefix",
    "validate_result_file_header",
    "write_result_file",
]
