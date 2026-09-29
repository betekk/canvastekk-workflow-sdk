# PLAN: TypeScript SDK — multipart upload-session support (DA-2886 parity)

**Branch**: feat/DA-3314
**Issue**: https://betekk.atlassian.net/browse/DA-3314
**Base**: main

## Acceptance Criteria

- [ ] `uploadFile` / `uploadOutputs` accept `string | UploadSessionDescriptor` targets; the descriptor path performs the full DA-2886 session flow (lazy initiate → bounded parallel part PUTs → complete), the string path is byte-identical to today.
- [ ] Wire contract matches python exactly: initiate POST `{"size", "content_type"}` → `{upload_id, part_size, part_urls[]}`; part PUTs with per-part retry mirroring python multipart.py (3 attempts, backoffs 1.0s/2.0s per `multipart.py:49`, any per-attempt error retried — python `_put_one_part` retries any httpx error incl. 4xx); complete POST `{"upload_id", "parts":[{part_number, etag}]}` sorted by part number; abort POST `{"upload_id"}` best-effort on part/resume failure (NOT on complete failure); status GET `{"uploaded_parts":[…]}` drives one reconcile-resume round. ETags normalized like python `_parse_etag` (strip quotes + `W/` prefix, empty → error). Control-plane calls (initiate/complete/abort/status) use a 30s timeout; part PUTs keep the 600s upload timeout.
- [ ] Bounded memory: parts pre-read per batch (default 4 parallel), ceiling = `max_parallel_parts × part_size` buffered bytes.
- [ ] `uploadOutputs` error contract unchanged: present file field with a target whose value is not an existing local file still throws `NodeIOError`; omission still legal.
- [ ] Custom `OutputUploader` implementations keep compiling (interface widening is additive; legacy-only implementations remain legal, string path emits a once-per-process deprecation warning per DA-2886 optics).
- [ ] Unit tests: descriptor happy path (mocked HTTP), legacy passthrough, part-retry then success, resume reconcile, complete-failure (no abort), abort-on-part-failure; legacy suite green.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/src/uploads.ts` (`OutputUploader`, `S3PresignedUploader`, `uploadOutputs`) | new descriptor schema (2.1) | `app.ts:165` router (post-execute output upload); external node packages via `index.ts` exports; canvastekk-ifc-service-app `job-runner.ts:116` (pinned tarball consumer) | medium — public interface widening; additive |
| `typescript/src/request.ts` (`NodeExecutionRequestSchema.output_upload_url`) | new descriptor schema (2.1) | `app.ts:126` inbound safeParse (execute wire); external consumers parse through the same exported schema (`job-runner.ts:106`) | **critical** — without widening, descriptors 400 at the door and the feature is dead on arrival |
| `typescript/src/multipart.ts` (new) | uploads.ts types (descriptor schema) | uploads.ts router branch only | low — new module, no existing consumers |
| ~~`context.ts`~~ | — | grep-verified: zero upload references — NOT a consumer (arch review M2) | — |
| `typescript/src/index.ts` (exports) | both above | external consumers (node packages) | low — additive exports |

## Implementation Phases

### Phase 1: Descriptor contract + multipart client

- [ ] **1.0** Widen `NodeExecutionRequestSchema.output_upload_url` in `typescript/src/request.ts:20` to `z.record(z.union([z.string(), UploadSessionDescriptorSchema]))` (schema imported from uploads.js; no import cycle) + regression test: full execute-request parse with a descriptor value succeeds.
    — **Why:** CRITICAL (arch review C1) — the descriptor currently fails `z.record(z.string())` at `app.ts:126` safeParse → 400 before the uploader ever runs; python widened exactly this field (`request.py:70`). External `job-runner.ts:106` parses through the same exported schema and inherits both bug and fix.
    — **Done when:** a request body with a descriptor target parses; existing string/null cases unchanged; parse test green.
    — **Consumers affected:** `app.ts:126` wire seam; external pinned consumers (additive).
- [ ] **1.1** Add `UploadSessionDescriptor` zod schema + TS interface in `uploads.ts` (kind literal `"multipart-upload-session"`, session_token, initiate_url, complete_url, abort_url, status_url, expires_at?) mirroring python `UploadSession`; widen `UploadTarget = string | UploadSessionDescriptor` and `uploadOutputs`' `uploadUrls` accordingly.
    — **Why:** the descriptor shape is the engine wire contract (DA-2886); the router must accept both target shapes.
    — **Done when:** schema parses a real descriptor payload; legacy strings still typecheck everywhere in the repo.
    — **Consumers affected:** all `uploadFile`/`uploadOutputs` callers (additive).
- [ ] **1.2** New `typescript/src/multipart.ts`: `uploadViaSession(session, filePath, opts)` implementing the python flow — lazy initiate, part-plan validation (0 part URLs → error), batched parallel part PUTs (default 4, chunks pre-read per batch), per-part Content-MD5 + ETag normalization (strip quotes/`W/`, empty → error, parity `_parse_etag`), per-part retry 3 attempts backoffs (1.0, 2.0)s retrying any per-attempt error (python `_put_one_part` parity — includes 4xx; documented deliberate divergence from the legacy path's transient-only rule), control-plane timeout 30s vs part-PUT 600s, parallel parts clamped so buffered bytes stay ≤ 512 MiB (engine part_size default 100MB, min 5MB, no max — `config.py:118,247`), complete with etags sorted by part number, best-effort abort on part/resume failure and I/O error, no abort on complete failure. Keep `OutputUploader.uploadFile` as METHOD syntax (bivariance keeps legacy string-only implementations compiling; property-arrow would break them) + compiled type-fixture test for a legacy-only implementor.
    — **Why:** this is the DA-2886 client contract; mirroring python keeps both SDKs behaviorally identical.
    — **Done when:** module compiles and exports `uploadViaSession`; part batches PUT with explicit Content-Length; complete payload sorted.
    — **Consumers affected:** uploads.ts router (1.3).
- [ ] **1.3** Route in `S3PresignedUploader.uploadFile`: descriptor → `uploadViaSession`; string → legacy single-PUT with a once-per-PROCESS deprecation warning (module-level flag; NOT per-call-site like python — documented divergence; assertion isolated in its own test file because the flag persists across tests in one file); `uploadOutputs` unchanged apart from target type.
    — **Why:** node-developer code needs no changes — the router performs the upload (python parity).
    — **Done when:** mocked string target hits attemptUpload; mocked descriptor hits multipart; warning emitted once.
    — **Consumers affected:** job-runner / SDK-server callers (no code change needed).
- [ ] **1.4** Export `UploadSessionDescriptor` (+ zod schema) from `typescript/src/index.ts`.
    — **Why:** engine-adjacent tooling and custom uploaders need the type.
    — **Done when:** `import { UploadSessionDescriptor } from "@nus-cee/canvastekk-workflow-sdk"` typechecks.
    — **Consumers affected:** external consumers (additive).

### Phase 2: Tests

- [ ] **2.1** `typescript/tests/uploads.test.ts` (extend): legacy string passthrough unchanged; `uploadOutputs` NodeIOError contract intact with widened targets (string + descriptor values).
    — **Why:** guards the no-regression half of AC #1/#4.
    — **Done when:** existing + new assertions green.
    — **Consumers affected:** none.
- [ ] **2.2** New `typescript/tests/multipart.test.ts`: descriptor happy path (initiate → 2 batched parts → complete payload sorted with etags); part-PUT transient failure retried then success; post-retry failure triggers status reconcile then re-PUT of unconfirmed parts; part failure after resume → abort called + error re-raised; complete failure → NO abort; 0 part URLs → error.
    — **Why:** the multipart client is new network code — each lifecycle branch needs a pin.
    — **Done when:** vitest green; http calls asserted via injected request mocks (pattern of existing uploader tests).
    — **Consumers affected:** none.

### Phase 3: Gate + version

- [ ] **3.1** Full gate: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` — all green; append tier=full memo.
    — **Why:** public SDK surface change; exit gate is full.
    — **Done when:** green memo names the final SHA.
    — **Consumers affected:** none.

## Technical Notes

- Python reference: `python/canvastekk_workflow_sdk/multipart.py` (`upload_via_session`, `_initiate`, `_put_one_part`, `_reconcile_resume`, `_abort_session`; defaults: retry 3 × [0.5, 1]s, resume_attempts 1, max_parallel_parts 4) and `uploads.py` (`UploadSession` model + legacy deprecation optics).
- TS HTTP style: reuse the repo's node:http(s) fixed-length-stream pattern from `attemptUpload` (S3 rejects chunked PUTs). Parts are buffered chunks (bounded), so `Content-Length` = chunk length.
- Part PUTs carry per-part Content-MD5 (python parity) — compute via `node:crypto` hash of the chunk.
- Legacy deprecation: `console.warn` once per process (optics parity; python uses warnings + logger).
- Version bump + release tagging happen at merge time per repo release flow (cliff.toml); consumer bump (ifc app `package.json` tarball pin) is a separate post-release PR — noted on DA-3314, not in this diff.

## Dependencies

- None blocked. Related: DA-3313 (engine async stamp — transport-independent), DA-2886/DA-2887 (contract origin).

## Risks & Mitigations

- **Public interface widening**: additive union — custom uploaders implementing only strings still satisfy the widened contract only if the interface allows it; keep `uploadFile` signature `string | UploadSessionDescriptor` and document that custom implementations MAY keep strings (python parity).
- **S3 chunked-encoding rejection**: all PUTs (parts included) set explicit `Content-Length` (existing repo pattern).
- **Memory ceiling**: chunk reads are bounded per batch (4 × part_size), mirroring python's ThreadPoolExecutor batch reads.
