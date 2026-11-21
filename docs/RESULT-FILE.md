# Workflow run result files

A **result file** is one plain JSON document holding a workflow run's result.
The node that produces the result writes it through the SDK writer. The
engine (CWE) checks its header at run end and serves it through
`GET /api/workflows/runs/{run_id}/result-file/download`.

Issue #278 · epic [betekk/canvastekk-tracker#4309](https://github.com/betekk/canvastekk-tracker/issues/4309).

## Who owns what

| Part | Owner | Validated by |
|---|---|---|
| Layout: `result_file_version`, `workflow_run_id`, `generated_at`, key order, `summary` rules | Platform (this SDK) | SDK writer before saving; CWE at run end |
| `result_schema` / `result_schema_version` labels | The app | Shape only (`app.kind`, semver); CWE compares them with the workflow definition |
| `summary` keys and their meaning | The app | Shape only (flat, scalar, `snake_case`, ≤2 KB) |
| `body` | The app | Never validated by the platform |

## Layout 1.0.0

Header keys first, in this order, then `body`:

```json
{
  "result_file_version": "1.0.0",
  "result_schema": "model_check.check",
  "result_schema_version": "0.1.0",
  "workflow_run_id": "3f2a…",
  "generated_at": "2026-11-20T10:00:00.123Z",
  "summary": { "verdict": "FAIL", "fail_count": 14 },
  "body": { }
}
```

| Key | Rule |
|---|---|
| `result_file_version` | `"1.0.0"` (written by the SDK) |
| `result_schema` | `app.kind`, lowercase `snake_case` parts, at least one dot, ≤128 chars |
| `result_schema_version` | `X.Y.Z` (no pre-release), ≤64 chars |
| `workflow_run_id` | The workflow run id. The writer prefers `run_context.workflow_run_id` when the engine sent a run context (#281) and falls back to the node request's `run_id` — which is the same workflow run id once CWE#1440 is live (before that deploy, pre-existing runs may still carry the engine's legacy `run-<uuid>` form) |
| `generated_at` | UTC, ISO 8601, milliseconds, `Z` (written by the SDK) |
| `summary` | Optional. Flat object; keys `^[a-z][a-z0-9_]*$` (≤64 chars); values string, number, boolean or null; ≤2048 bytes as compact UTF-8 JSON |
| `body` | Any JSON value |

Schemas: [`schemas/result-file/1.0.0.json`](../schemas/result-file/1.0.0.json)
and the `__end__.result_file` value
[`schemas/result-file/end-value-1.0.0.json`](../schemas/result-file/end-value-1.0.0.json).
Files are plain JSON (`application/json`), not compressed.

## Writing a result file

Always use the writer. It validates the header and `summary` **before**
writing, writes to a temporary file and renames it into place, so an invalid
input never leaves a file behind (`ResultFileFormatError`, error code
`OUTPUT_VALIDATION_ERROR`).

### Example node (Python)

```python
from canvastekk_workflow_sdk import (
    NodeExecutionContext,
    WorkflowNodeBase,
    WorkflowNodeManifest,
    result_file_output_schema,
    write_result_file,
)


class DoorGapCheck(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        slug="door-gap-check",
        version="1.0.0",
        name="Door gap check",
        description="Checks door gaps and writes the run's result file.",
        input_schema={"type": "object", "properties": {"model": {"type": "string", "format": "file"}}},
        output_schema={
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "result_file": result_file_output_schema("The check result (model_check.check 0.1.0)."),
            },
        },
    )

    def execute(self, inputs: dict, context: NodeExecutionContext) -> dict:
        result = run_check(inputs["model"])  # app logic
        outputs = {"verdict": result["verdict"]}
        outputs.update(
            write_result_file(
                context,
                result_schema="model_check.check",
                result_schema_version="0.1.0",
                summary={"verdict": result["verdict"], "fail_count": result["fail_count"]},
                body=result,
            )
        )
        return outputs
```

`write_result_file` returns `{"result_file": "<local path>"}`; the SDK
uploads it after `execute`, like any other file output.

### Example (TypeScript)

```ts
import { resultFileOutputSchema, writeResultFile } from "@betekk/canvastekk-workflow-sdk";

// output_schema.properties.result_file = resultFileOutputSchema("The check result.");
return {
  verdict: result.verdict,
  ...writeResultFile(context, {
    resultSchema: "model_check.check",
    resultSchemaVersion: "0.1.0",
    summary: { verdict: result.verdict, fail_count: result.failCount },
    body: result,
  }),
};
```

Both runtimes write byte-identical headers for the same input
(`schemas/result-file/golden/`). Keep that true in your own data by using
integers or strings in `summary` (`1.0` prints as `1.0` in Python and `1` in
JavaScript) and avoiding integer-like object keys in `body` (JavaScript
reorders them).

## Manifest convention

A node that produces a result file declares exactly one output named
`result_file` with `result_file_output_schema()` / `resultFileOutputSchema()`:

```json
{ "type": "string", "format": "file", "contentMediaType": "application/json", "x-result-file": true }
```

The manifest rejects any other shape for `result_file`, the `x-result-file`
marker on any other output, and the marker on inputs. CWE uses the marker to
confirm the producer when a workflow definition declares `result_file`.

## Wiring in a workflow definition

The producing node's `result_file` output is wired into the reserved
`__end__.result_file` key. The engine stamps the uploaded file as an `s3://`
pointer (`end-value-1.0.0.json`). The key is deliberately not named `*_path`,
so the engine never inlines the file into run responses.

## Reading the header

`read_result_file_header(stream)` (Python) reads the top-level object one
member at a time and stops at `body`, so a large file is checked without
reading its content (header limit 64 KiB). It rejects files that are not
JSON objects, have no `body`, repeat or misorder header keys, or fail
header validation. CWE uses it for the run-end check.

```python
with open(path, "rb") as handle:
    header = read_result_file_header(handle)
assert header["result_schema"] == "model_check.check"
```

## Versioning

- `result_file_version` changes only with this layout. Released schema files
  are never edited; a new version adds a new file.
- `result_schema_version` is the app's own version. While it is `0.x` there
  is no compatibility promise. From `1.0.0`: adding a field is a minor
  version, renaming or removing one is a major version.
