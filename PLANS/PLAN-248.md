# PLAN: Stream file-input downloads before enforcing byte caps

**Branch**: feat/248
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/248
**Base**: dev

## Acceptance Criteria
- [ ] File downloads stream to disk without whole-object response buffering
- [ ] Content-length and running-byte caps reject over-limit input during transfer
- [ ] Redirect SSRF checks, cancellation, deadline, and partial-file cleanup remain intact
- [ ] Tests cover declared and undeclared content lengths, over-cap streams, and cleanup
- [ ] Existing file-input tests and SDK conformance suites pass
- **Post-merge release (orchestrator-owned):** a final SDK release is published with the Python wheel and checksum so CASA can pin the new SDK asset; the exact tag is commented on #248

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/base.py::_download_one` | Existing `validate_external_url`, filename, cancellation, deadline, and error contracts | `_prepare_file_inputs`, every Python node with file inputs, CASA infer Lambda | high |
| `python/tests/test_file_download.py` | Streaming `_download_one` implementation | Python CI, redirect/cap/cancellation/cleanup regression coverage | med |
| `python/tests/test_conformance.py` and the full Python suite | Unchanged public SDK contracts | SDK conformance and release confidence | med |
| `.github/workflows/release.yml` (unchanged) | Merged implementation on `dev`, then a `patch`-labeled `dev → prod` promotion | Final version tag, wheel/checksum release assets, CASA pin | med |

The only production-code consumer in this repository is `_prepare_file_inputs`; its public input, metadata, and error behavior must remain unchanged. External Python nodes inherit `BaseNode`, so streaming and response cleanup must be fixed in this shared method rather than in individual nodes. TypeScript is explicitly out of scope because it already uses streaming `fetch` and this ticket verifies no separate TypeScript defect.

## Implementation Phases

### Phase 1: Streaming download and regression coverage

- [ ] **1.1** Replace the buffered `httpx.get` call in `_download_one` with a scoped `httpx.stream("GET", ...)` response, keeping redirect validation, headers, byte caps, cancellation, deadline, metadata, and partial-file cleanup inside the existing flow and closing every response on success or failure
    — **Why:** `httpx.get` reads the body before the current cap checks; a streaming response is the root-cause fix for every Python node and ensures redirect/error responses are closed promptly
    — **Done when:** response bytes are iterated directly into the local file without whole-object buffering, declared content length is rejected before body iteration, running-byte overflow is rejected during iteration, and all pre-existing policy branches remain present
    — **Consumers affected:** `_prepare_file_inputs`, Python file-input nodes, CASA infer Lambda memory and bandwidth use
- [ ] **1.2** Convert the file-download test doubles and patches to the streaming API and add focused coverage for declared and undeclared lengths, pre-iteration rejection, over-cap cleanup, and response closure across success, redirect, and failure paths
    — **Why:** the existing mocks patch the buffered API and therefore cannot prove streaming behavior; explicit pre-iteration and cleanup assertions prevent a syntactic API swap that still reads or leaks the body
    — **Done when:** the focused file-download tests prove both cap mechanisms, no partial file remains after over-cap failures, response context managers exit on every exercised path, and existing redirect/cancellation/deadline/filename/metadata tests pass unchanged in behavior
    — **Consumers affected:** Python CI and maintainers relying on the file-input regression suite

### Phase 2: Full SDK verification and ticket exit gate

- [ ] **2.1** Run scoped Ruff checks, Python compile checks, the complete Python test suite (including file-input and conformance tests), and wheel/sdist builds; tick all pre-release acceptance criteria and append the final-SHA full gate memo
    — **Why:** this changes shared network and security-sensitive behavior inherited by external nodes, and the ticket exit gate is unconditionally full before review and PR creation
    — **Done when:** Ruff, compile checks, all Python tests, and both package builds pass on the final implementation tree; `PLANS/PLAN-248.md` records exact evidence and `GATE <short-sha> tier=full` for the pushed implementation SHA
    — **Consumers affected:** PR gate citation, SDK maintainers, downstream release consumers

## Post-merge release follow-through

After the implementation PR merges to `dev`, the pipeline orchestrator will create a `patch`-labeled `dev → prod` promotion PR, watch and merge it only when green, then verify the Release workflow publishes a final tag with the Python wheel, wheel checksum, and TypeScript tarball. The orchestrator will comment the verified tag on #248. Version files remain frozen because release CI stamps them ephemerally from the tag; both the implementation PR and the promotion PR carry the `patch` label.

This release action is intentionally outside the implementation executor's pre-merge checkbox scope. It is required ticket follow-through, not an optional release note.

## Technical Notes

- Preserve the 64 KiB chunk size and `_HTTPX_DOWNLOAD_TIMEOUT` behavior; the fix concerns response buffering, not a new tuning surface.
- `httpx.stream` yields headers before body iteration, allowing the declared `content-length` check to reject without reading the object. The running counter remains mandatory for missing or inaccurate content lengths.
- Redirects remain manual with `follow_redirects=False`; every `Location` hop continues through `validate_external_url` and the existing hop limit.
- The CASA infer Lambda target has 10240 MB memory and 8192 MB ephemeral storage, with 500 MiB / 60-minute audio inputs in scope. Streaming bounds response memory by chunks rather than object size.
- No TypeScript, workflow-definition, CASA node, or public SDK schema changes are planned.

## Dependencies

- Parent epic: betekk/canvastekk-tracker#4223.
- Final asset publication depends on the existing `dev → prod` promotion and Release workflow; a dev prerelease tag alone does not satisfy the release criterion.

## Risks & Mitigation

- **A mock-only API swap hides real buffering or response leaks** → use context-managed response doubles with explicit iteration and exit assertions; retain the SDK's real local-server download tests in the full suite.
- **Redirect responses remain open across hops** → keep each response inside the streaming context manager and assert closure on redirect and error tests.
- **Missing or false content length bypasses the declared-size check** → retain the running-byte guard and test a chunked over-cap body without a content-length header.
- **Cleanup behavior regresses when indentation changes** → preserve the existing `BaseException` unlink guard and assert empty download directories after both declared and running-cap rejection.
- **Only a dev prerelease is minted** → complete the post-merge `dev → prod` promotion and verify final release assets before reporting the ticket fully released.

## Trace
