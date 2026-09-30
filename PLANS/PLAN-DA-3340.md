# PLAN: SDK 0.36.0: session-only uploads — remove legacy presigned PUT target

**Branch**: feat/DA-3340
**Issue**: https://betekk.atlassian.net/browse/DA-3340
**Base**: main

## Acceptance Criteria
- [ ] Legacy `str` form removed from the public API (`UploadTarget = UploadSession`); `NodeIOError` raised on legacy targets with message "engine sent deprecated presigned target — upgrade the engine"
- [ ] `UploadSession` upload path unchanged (multipart machinery in `python/.../multipart.py` and `typescript/src/multipart.ts` untouched)
- [ ] TypeScript SDK parity verified (the union exists there: `typescript/src/uploads.ts:33` — same removal applied)
- [ ] node-builder / node-patterns SKILL.md (both `.agents/skills/` mirror and `python/.../data/skills/` bundled copies) and EXTERNAL-AUTHOR-GUIDE.md updated; in-repo version bumped to 0.36.0 (no production release/tag — that stays with the release workflow)

**Requirement note (stated, not hidden):** the ticket's AC #4 says "v1.0.0 released" while Proposed #5 says "Version 0.36.0 — feature bump. No production release yet" and Proposed #6 says the removal lands in 0.36.0. These cannot both hold; this PLAN follows the Proposed section (0.36.0 in-repo bump, docs corrected from "removed in SDK v1.0" to 0.36.0, no tag/release).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/.../uploads.py` (`UploadTarget`, `S3PresignedUploader.upload_file`, warning machinery) | `UploadSession`, `multipart.upload_via_session`, `NodeIOError` | `__init__.py` exports, `request.py` field type, `app.py:_upload_outputs_to_s3`, both test files | high (public API) |
| `python/.../request.py` (`output_upload_url`) | `uploads.UploadTarget` (switches to inline `str \| UploadSession` wire union) | `app.py execute()` parse, `test_multipart_uploads.py::TestSessionHandshake` | high (wire contract — strings must STILL parse; the NodeIOError fires at the upload seam, never a 422) |
| `python/.../__init__.py` exports | `uploads.py` | external node packages (breaking: `LegacyPresignedUploadWarning` export removed) | medium |
| `python/.../app.py` upload seam | uploader | engine response semantics (existing `UPLOAD_FAILED` fail path reused — no new error path) | low |
| `typescript/src/uploads.ts` (`UploadTarget`, `uploadFile`, legacy machinery) | `multipart.uploadViaSession`, `NodeIOError` | `index.ts` exports, `request.ts` comment, `app.ts`, both TS test files | high (public API) |
| `typescript/src/request.ts` (parse union) | `UploadSessionDescriptorSchema` | `app.ts` parse | medium (keep `z.string()` in the parse union — same seam-not-parse rationale) |
| SKILL.md copies (`.agents/skills/` + `python/.../data/skills/`) | — | node authors (repo mirror + `init`-copied bundles); must stay identical | medium (drift risk) |
| Version files (`python/pyproject.toml`, `__init__.py`, `poetry.lock`, `typescript/package.json`, `typescript/src/version.ts`) | — | release workflow (git-cliff), poetry lock hash | medium |

**Scope guard (do NOT touch):** input-side presigned GET download wording and code (`validate_file_input`, `LocalFileServer`, `follow_redirects` guidance) — the legacy removal is output-upload-only; input downloads keep presigned GETs. `multipart.py` / `multipart.ts` session machinery and `UploadSession`/descriptor models stay unchanged.

## Implementation Phases

### Phase 1: Python SDK — session-only UploadTarget
- [x] **1.1** Narrow `UploadTarget = UploadSession` in `python/canvastekk_workflow_sdk/uploads.py` and rewrite its comment: the legacy `str` member is removed (DA-3340); sessions are the only upload target.
    — **Why:** the public alias is the ticket's headline API change; every consumer (request field, protocol, tests) keys off it.
    — **Done when:** `grep -n "UploadTarget = " python/canvastekk_workflow_sdk/uploads.py` shows `UploadSession` only, with a DA-3340 comment.
    — **Consumers affected:** `request.py`, `uploads.py` signatures, `app.py`, tests (all updated in later steps).
    — **Done:** alias is `UploadSession` with DA-3340 comment; files: uploads.py; fixes: none
- [x] **1.2** Replace the legacy branch in `S3PresignedUploader.upload_file`: delete `_warn_legacy_presigned_upload()`, `LegacyPresignedUploadWarning`, `_operator_warning_lock`/`_operator_warning_emitted`, the `threading` import (its only user), and the single-PUT retry loop; a non-`UploadSession` target now raises `NodeIOError("engine sent deprecated presigned target — upgrade the engine")`.
    — **Why:** fail-loud compliance is the ticket's core behavior; the warning machinery and retry loop exist only for the removed path.
    — **Done when:** `grep -n "LegacyPresignedUploadWarning\|_warn_legacy\|_operator_warning" python/canvastekk_workflow_sdk/uploads.py` returns nothing, and a string target raises the exact NodeIOError (test in 1.6).
    — **Consumers affected:** `__init__.py` export (1.5), tests (1.6).
    — **Done:** legacy branch → exact-message NodeIOError; warning class/machinery, retry loop, `threading`/`time`/`warnings`/`httpx` imports and `_UPLOAD_TIMEOUT_SECONDS` deleted; files: uploads.py; fixes: none
- [x] **1.3** Switch `request.py` `output_upload_url` to the inline wire union `dict[str, str | UploadSession] | None` with a DA-3340 comment explaining parse tolerance: strings must still parse so the upload seam raises NodeIOError, not an opaque 422; update the field description.
    — **Why:** narrowing the field to the (now session-only) `UploadTarget` alias would 422 legacy payloads at parse and make the ticket's required NodeIOError unreachable.
    — **Done when:** `NodeExecutionRequest(output_upload_url={"f": "https://legacy"})` validates, and `TestSessionHandshake` string-parse tests stay green (1.6).
    — **Consumers affected:** `app.py execute()` (no code change — value flows through), CI manifest-schema-stability job (watch item: generated schema shape changes).
    — **Done:** field is inline `str | UploadSession` union with parse-tolerance description; import narrowed to `UploadSession`; files: request.py; fixes: none
- [x] **1.4** Sweep docstrings: `OutputUploader.upload_file`/`upload_outputs`, `S3PresignedUploader` class docstring, `app.py:_upload_outputs_to_s3`, and the output half of `app.py execute()`'s docstring ("Outputs are uploaded via presigned PUT URLs") — sessions only, NodeIOError on legacy. Keep input-presigned-GET wording untouched.
    — **Why:** per project learning, a deprecation must sweep every teaching mention or docs drift from behavior.
    — **Done when:** `grep -n -i "presigned PUT\|legacy" python/canvastekk_workflow_sdk/{uploads,app,request}.py` shows no stale output-path claims (input-GET mentions remain).
    — **Consumers affected:** doc readers; `docs/` sweep is Phase 3.
    — **Done:** protocol + uploader + app docstrings rewritten session-only; input-GET wording untouched; files: uploads.py, app.py; fixes: none
- [x] **1.5** Remove `LegacyPresignedUploadWarning` from `python/canvastekk_workflow_sdk/__init__.py` imports and `__all__` (keep `UploadTarget`, `UploadSession`).
    — **Why:** exporting a deleted class breaks import; dropping the export is the documented breaking change for 0.36.0.
    — **Done when:** `python -c "from canvastekk_workflow_sdk import LegacyPresignedUploadWarning"` fails and `from canvastekk_workflow_sdk import UploadTarget, UploadSession` succeeds.
    — **Consumers affected:** external node packages that import the warning (breaking — covered by the 0.36.0 notice).
    — **Done:** export + `__all__` entry removed; files: __init__.py; fixes: none
- [x] **1.6** Rewrite Python tests: `test_uploads.py` — delete/convert legacy single-PUT suites (`TestUploadRetry`, `TestUploadWireFormat`, `upload_file` PUT tests, string-target `upload_outputs` tests) to session-fake equivalents; `test_multipart_uploads.py` — convert `test_string_target_takes_legacy_put_path` to assert the exact NodeIOError, delete `TestDeprecationWarning` (4 tests), keep `TestSessionHandshake` and `TestMachinery`; add a test that a legacy string reaching `upload_outputs` fails the response as `UPLOAD_FAILED` at the app seam.
    — **Why:** tests are the executable proof of AC #1 and #2; dead legacy suites would fail or lie.
    — **Done when:** `python -m poetry run pytest` exits 0 from `python/` with no legacy-path test remaining (`grep -rn "LegacyPresignedUploadWarning" python/tests/` empty).
    — **Consumers affected:** coverage signal carried by CI.
    — **Done:** test_uploads.py rewritten (legacy rejection + session-routing suites; retry/wire-format suites deleted); TestDeprecationWarning deleted, string test converted to exact-message NodeIOError; unmocked seam test `test_legacy_string_target_fails_with_upload_failed` added; files: test_uploads.py, test_multipart_uploads.py, test_app.py; fixes: ruff F401 unused MagicMock import
- [x] **1.7** Run the light gate in `python/`: `python -m poetry run ruff check canvastekk_workflow_sdk/ tests/` + `python -m poetry run pytest`.
    — **Why:** phase-scoped verification before stacking Phase 2.
    — **Done when:** both commands exit 0.
    — **Consumers affected:** CI parity (same commands).
    — **Done:** ruff clean; pytest 763 passed (fresh-venv `poetry install` was the only environment fix); fixes: none (lint fix counted in 1.6)

### Phase 2: TypeScript SDK parity
- [x] **2.1** In `typescript/src/uploads.ts`: set `export type UploadTarget = UploadSessionDescriptor`; make `uploadFile` throw `new NodeIOError("engine sent deprecated presigned target — upgrade the engine")` for string targets before the session path; delete `warnLegacyPresignedUpload`, `_legacyWarningEmitted`, `attemptUpload`, `isTransientError`, `TRANSIENT_ERRNO_CODES`, `UPLOAD_TIMEOUT_MS`, and the now-unused `node:http`/`node:https` imports; update `OutputUploader`/`uploadOutputs` doc comments.
    — **Why:** the union exists in TS (`uploads.ts:33`) — ticket AC #3 requires the same removal; the deleted machinery is single-PUT-only.
    — **Done when:** `grep -n "warnLegacyPresignedUpload\|attemptUpload\|isTransientError" typescript/src/uploads.ts` is empty and `tsc --noEmit` (2.4) passes.
    — **Consumers affected:** `index.ts` exports (2.2), TS tests (2.3).
    — **Done:** full-file rewrite — session-only type, exact-message NodeIOError guard, single-PUT machinery + http/https imports deleted; files: uploads.ts; fixes: none
- [x] **2.2** Remove `UploadHttpError` (class in `uploads.ts` + its `index.ts` export) — its only producer was the deleted single-PUT path; keep the parse union in `request.ts` (`z.union([z.string(), UploadSessionDescriptorSchema])`) and update its DA-3314 comment to state the DA-3340 seam rationale.
    — **Why:** leaving a never-thrown exported error class is dead public API; the parse-union comment otherwise teaches the old string-target semantics.
    — **Done when:** `grep -rn "UploadHttpError" typescript/src/` is empty and `grep -n "z.string()" typescript/src/request.ts` still matches.
    — **Consumers affected:** external TS consumers importing `UploadHttpError` (breaking — 0.36.0 notice).
    — **Done:** class + export deleted; request.ts parse union kept with DA-3340 seam comment; files: uploads.ts, index.ts, request.ts; fixes: none
- [x] **2.3** Rewrite TS tests: convert `uploads-deprecation.test.ts` to assert NodeIOError on string targets (rename file/suite to match DA-3340 semantics), delete/convert legacy single-PUT cases in `uploads.test.ts` to session fakes.
    — **Why:** executable proof of TS parity (AC #3).
    — **Done when:** `npm test` exits 0 from `typescript/` with no string-target success-path test remaining.
    — **Consumers affected:** coverage signal.
    — **Done:** uploads-deprecation.test.ts deleted (superseded by DA-3340 rejection suite); uploads.test.ts rewritten with session server fixture + fail-loud suites; legacy-uploader-fixture.ts re-pinned on the session-only contract (string-only uploader now correctly fails typecheck); files: uploads.test.ts, uploads-deprecation.test.ts (deleted), legacy-uploader-fixture.ts; fixes: app.ts call-site cast + fixture rewrite (typecheck catches)
- [x] **2.4** Run the light gate in `typescript/`: `npm run lint && npm run typecheck && npm run typecheck:tests && npm test && npm run build`.
    — **Why:** phase-scoped verification matching CI.
    — **Done when:** all five commands exit 0.
    — **Consumers affected:** CI parity.
    — **Done:** lint + typecheck + typecheck:tests clean; vitest 343 passed; tsup build (incl. DTS) green; fixes: none beyond 2.3's

### Phase 3: Docs + skills sweep (all copies) + examples
- [x] **3.1** Update `canvastekk-node-builder/SKILL.md` in BOTH copies (`.agents/skills/` and `python/canvastekk_workflow_sdk/data/skills/`): line ~217 comment (`"<UploadSession | presigned URL>"`), the upload-targets section (~675-682) — sessions only, legacy string raises `NodeIOError`, correct "removed in SDK v1.0" to "removed in SDK 0.36.0" (ticket item 6), delete the warning-silencing recipe.
    — **Why:** the ticket names this file twice (items 4 and 6); both copies must stay identical (project learning on mirror drift).
    — **Done when:** `diff` of the two copies is empty and `grep -n "v1.0" <copy>` has no upload-target removal claim.
    — **Consumers affected:** node authors, `init`-copied bundles.
    — **Done:** comment + File Outputs section rewritten session-only with 0.36.0 removal note; silencing recipe replaced by fail-loud contract; copies byte-identical (`diff -q` clean); files: both builder SKILL.md copies; fixes: none
- [x] **3.2** Update `canvastekk-node-patterns/SKILL.md` in BOTH copies: rewrite the "Upload targets: `str | UploadSession`" section (~954-959) to session-only + NodeIOError behavior.
    — **Why:** ticket item 4 names this file; the section teaches the removed union.
    — **Done when:** both copies identical; section no longer mentions the deprecated string target as usable.
    — **Consumers affected:** node authors.
    — **Done:** section retitled "Upload target: UploadSession" with DA-3340 rejection note; copies byte-identical; files: both patterns SKILL.md copies; fixes: none
- [x] **3.3** Update `docs/EXTERNAL-AUTHOR-GUIDE.md` (~277-278): sessions are the only target; plain-string targets from an unupgraded engine fail with `NodeIOError` — no warning, no silencing; removal version 0.36.0.
    — **Why:** the external-author contract must match shipped behavior or authors debug against fiction.
    — **Done when:** `grep -n "LegacyPresignedUploadWarning\|still work" docs/EXTERNAL-AUTHOR-GUIDE.md` is empty.
    — **Consumers affected:** external node package authors.
    — **Done:** section retitled "session-only since v0.36.0"; bullets rewritten (removal + NodeIOError + no-fallback); files: EXTERNAL-AUTHOR-GUIDE.md; fixes: none
- [x] **3.4** Sweep `README.md` (the "Upload Retry" section ~358-364 — single-PUT retry is gone; describe session retry) and `examples/echo_node/` (README output-upload wording ~8-10, ~47, any handler/test/example payload using a string upload target) to session descriptors; then repo-wide grep sweep for stale output-upload claims.
    — **Why:** deprecation sweep must cover every mention, not just the sections being rewritten (project learning); examples that send string targets would now demonstrate a guaranteed failure.
    — **Done when:** `grep -rn -i "LegacyPresignedUploadWarning" --include='*.md' --include='*.py' --include='*.ts' . | grep -v PLANS/ | grep -v LEARNINGS/` returns nothing, and input-presigned-GET wording is intact.
    — **Consumers affected:** README readers, example users.
    — **Done:** README Upload Retry → session retry; echo_node README bullet + curl payload → session descriptor; found-and-fixed two extra stragglers the sweep surfaced (python/README.md:455 Output Upload section, typescript/README.md:414 Output Upload section); input-side presigned-GET wording (builder SKILL.md:770, README download sections) left intact; fixes: none
- [x] **3.5** Run the light gate on docs-only changes: markdown link/reference sanity (`grep -n` the edited anchors) + confirm no code files changed in this phase (`git diff --stat` scoped).
    — **Why:** docs-only phase needs a proportionate check, not the full suite.
    — **Done when:** no code diffs in the phase commit; referenced symbols/files in docs exist.
    — **Consumers affected:** none (docs).
    — **Done:** repo-wide sweeps exit empty (warning class, UploadHttpError, "removed in v1.0", stale-phrase patterns); `git diff --name-only` shows 9 docs files only; fixes: none

### Phase 4: Version 0.36.0 + ticket exit gate (full)
- [ ] **4.1** Bump versions to 0.36.0: `python/pyproject.toml`, `python/canvastekk_workflow_sdk/__init__.py` `__version__`, `typescript/package.json`, `typescript/src/version.ts`.
    — **Why:** ticket item 5 — feature bump marking the breaking removal; done in-repo, no tag.
    — **Done when:** `grep -n "0.36.0" python/pyproject.toml python/canvastekk_workflow_sdk/__init__.py typescript/package.json typescript/src/version.ts` matches all four.
    — **Consumers affected:** release workflow (next prep is version-noop), poetry lock (4.2).
- [ ] **4.2** Refresh `python/poetry.lock` with `python -m poetry lock` (2.x preserves pinned deps) and verify the diff touches only the project version/hash lines.
    — **Why:** the lock records the package's own version; a stale lock fails `poetry install` consistency checks in CI.
    — **Done when:** `git diff python/poetry.lock` shows only version/content-hash lines.
    — **Consumers affected:** CI install steps.
- [ ] **4.3** Run the ticket exit gate — full tier, both SDKs: Python `ruff check` + `pytest`; TS `lint`, `typecheck`, `typecheck:tests`, `test`, `build`.
    — **Why:** the run's last gate is full (pipeline contract); the whole surface changed across two SDKs.
    — **Done when:** every command exits 0; gate memo written into the PLAN trace block with the final implementation SHA.
    — **Consumers affected:** Step 9 review-fix re-gate and Step 10a gate citation.
- [ ] **4.4** Land the breaking-change notice in commit messages: the removal phase commit uses `feat(sdk)!: ...` + `BREAKING CHANGE:` footer (legacy presigned PUT target removed; `LegacyPresignedUploadWarning`/`UploadHttpError` exports deleted) so git-cliff renders `(**BREAKING**)` in the eventual 0.36.0 entry — the "changelog notice for external authors" is commit-carried, no manual CHANGELOG.md edit (generated at release).
    — **Why:** CHANGELOG.md is git-cliff-generated at release time; the footer is the only correct injection point.
    — **Done when:** `git log --format=%B -1 <removal-commit>` contains the footer.
    — **Consumers affected:** external authors reading the 0.36.0 changelog.

## Technical Notes
- Exact NodeIOError message (both SDKs): `engine sent deprecated presigned target — upgrade the engine`.
- Python seam behavior already exists: `app.py:425-436` converts any upload exception into `status="fail"`, `error_code="UPLOAD_FAILED"` — no new error path needed.
- Keep `UploadSession`/descriptor models and `multipart.py`/`multipart.ts` byte-identical (AC #2).
- `.agents/skills/` and `python/.../data/skills/` copies must end byte-identical per file (mirror learning).
- Input-side presigned GET downloads are out of scope — sweep wording carefully (vocabulary-overapply learning).
- Watch item: CI "Manifest schema stability" job generates schemas base-vs-PR; the `output_upload_url` annotation change alters generated shape — if it fails, the intentional wire-tolerant change is documented here and in 1.3's comment.

## Dependencies
- blocked-by DA-3338 — **satisfied** (JIRA Done; engine merge `3dca9d1e` on `origin/dev`, deployed per ticket context).
- None external.

## Risks & Mitigation
- **Breaking public API** (warning class + TS `UploadHttpError` exports removed) → 0.36.0 feature bump + `BREAKING CHANGE` footer (4.4); ticket explicitly chooses fail-loud removal.
- **Schema-stability CI job** may flag the `output_upload_url` schema delta → parse tolerance keeps the wire contract accepting both shapes; if the job fails, cite 1.3's rationale in the PR and adjust only if the job compares execute-request models (verify at review).
- **Docs drift between SKILL.md copies** → 3.1/3.2 end with an explicit `diff` check.
- **Hidden legacy-path tests** surfacing late → repo-wide grep sweep in 3.4 covers `*.py`/`*.ts`/`*.md`; test dirs grepped in 1.6/2.3.

## Gate Trace
(appended per phase by the executor)
