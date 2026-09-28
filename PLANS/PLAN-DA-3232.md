# PLAN: SDK TypeScript — BaseNode.reportProgress progress-ping helper

**Branch**: feat/DA-3232
**Issue**: https://betekk.atlassian.net/browse/DA-3232
**Base**: main

## Acceptance Criteria

- [ ] `report_progress()` never throws into caller code (swallows and logs transport errors)
- [ ] Safe no-op when no run/callback context is available (local dev, outside a run)
- [ ] Sends `execution_id` + optional percent/message; payload size-capped
- [ ] Unit tests cover the no-op path and the happy path

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/src/context.ts` — `executionId` ctor opt, private `sendProgressPing`, `reportProgress` upgrade | existing `NodeExecutionRequest.callback_url` (request.ts:19) | `base-node.ts` `run()` (passes id), file-download progress calls (base-node.ts:487,505), node code calling `context.reportProgress`, new `BaseNode.reportProgress` | **med** — `reportProgress` gains a network side effect, but only when `callback_url` + `execution_id` are present; local/dev/test contexts (null callback) log exactly as today |
| `typescript/src/base-node.ts` — ALS storage wrap in `run()`, new `reportProgress(percent?, message?)` | context.ts changes (Phase 1) | every node subclass (additive method, zero signature changes), `app.ts` routes, `index.ts` re-exports | low — transparent `AsyncLocalStorage` wrap; additive public method |
| `typescript/tests/context.test.ts` + `typescript/tests/base-node.test.ts` (additions) | both source changes | CI | low |

## Implementation Phases

### Phase 1: ExecutionContext progress ping

- [x] **1.1** Add optional `executionId?: string | null` to `ExecutionContext` constructor opts; store it and expose a readonly `get executionId(): string | null`
    — **Why:** the ping must carry the run-scoped `execution_id` the engine validates against its pending async set (engine #495); `run()` already mints one (`randomUUID()`, base-node.ts:533) but never hands it to the context
    — **Done when:** `npm run typecheck` green; all existing context tests green
    — **Consumers affected:** `base-node.ts` `run()` (Phase 2.2), `sendProgressPing` (1.2)
    — **Done:** executionId ctor opt + getter added (context.ts); typecheck green; 18/18 context tests; files: typescript/src/context.ts; fixes: none

- [x] **1.2** Add private `sendProgressPing(percent?: number, message?: string): void` on `ExecutionContext`: no-op unless `this._request?.callback_url` AND `this._executionId` are set; clamp `percent` to [0,100]; truncate `message` to 1000 chars (engine payload cap, #495 "size-capped payloads"); fire-and-forget `fetch(`${callback_url}/progress`, {method:"POST", headers, body: JSON, signal: AbortSignal.timeout(5000)})` with `.catch(err => this._logger.warn(...))` — never throws, never leaves an unhandled rejection
    — **Why:** single POST seam shared by both public surfaces; the progress route is derived from the completion `callback_url` (`{engine}/callbacks/{run_id}/{node_id}` + `/progress` per engine #495) — no new env config
    — **Done when:** unit tests prove (a) no-op without callback_url, (b) no-op without execution_id, (c) happy-path POST URL/body/headers, (d) transport error swallowed + logged
    — **Consumers affected:** `reportProgress` (1.3), `BaseNode.reportProgress` (2.3)
    — **Done:** `_sendProgressPing` implemented with no-op guards, clamp, 1000-char cap, AbortSignal.timeout(5000), `.catch`→warn; tests (a)–(d) + message-omission + cap/clamp tests all green; files: typescript/src/context.ts, typescript/tests/context.test.ts; fixes: logger stub missing info() in swallow test

- [x] **1.3** Upgrade `reportProgress(progress, message)` (context.ts:125): keep the existing log line, then delegate `this._sendProgressPing(Math.round(progress * 100), message)` — the docstring's promised evolution ("Currently logs progress. Future: will send to callback")
    — **Why:** context-level progress is the pre-existing public API; wiring it to the ping gives file-download progress (base-node.ts:487,505) and node-level `context.reportProgress` calls engine visibility with zero caller changes
    — **Done when:** existing context tests still green (log behavior unchanged); ping tests from 1.2 cover the POST side
    — **Consumers affected:** internal file-download progress; node code calling `context.reportProgress` — behavior identical when no callback_url (local dev)
    — **Done:** reportProgress now logs then pings; pre-existing tests ("reportProgress does not throw") still green; files: typescript/src/context.ts; fixes: none

### Phase 2: BaseNode ambient-context helper

- [x] **2.1** Export `executionContextStorage = new AsyncLocalStorage<ExecutionContext>()` from `context.ts` (import from `node:async_hooks`)
    — **Why:** concurrency-safe resolution of "the current run" for a stateless node method — one node instance serves overlapping HTTP requests, so instance-held context would cross-run-race; `AsyncLocalStorage` is the native Node platform mechanism
    — **Done when:** exported; `npm run typecheck` green
    — **Consumers affected:** `base-node.ts` `run()` (2.2) and `reportProgress` (2.3); no other importers
    — **Done:** storage exported with rationale docstring (context.ts); typecheck green; files: typescript/src/context.ts; fixes: none

- [x] **2.2** In `BaseNode.run()`: pass `executionId` into the `ExecutionContext` ctor, and wrap the post-context try-body (context creation through response construction) in `executionContextStorage.run(context, async () => {...})`
    — **Why:** makes the per-run context visible to node code while `execute()` runs, including awaited continuations, without any signature change
    — **Done when:** all existing base-node/app/deprecation tests green (wrap is behavior-transparent)
    — **Consumers affected:** every node subclass — zero signature/behavior change
    — **Done:** run() passes executionId + wraps try-body via storage.run; full base-node suite green; files: typescript/src/base-node.ts; fixes: none

- [x] **2.3** Add `reportProgress(percent?: number, message?: string): void` on `BaseNode`: read `executionContextStorage.getStore()`; absent → immediate no-op return; present → `ctx` delegates to its progress ping (1.2). JSDoc notes the ticket/engine-issue name `report_progress` is the cross-leg spec name; this leg uses camelCase per house convention (matches existing `context.reportProgress`)
    — **Why:** the ticket-named one-liner surface: `this.reportProgress(50, "still calculating")` inside `execute()` with nothing else to wire
    — **Done when:** unit tests prove (a) calling outside a run is a silent no-op, (b) calling inside `execute()` POSTs with the run's `execution_id`, (c) two interleaved `run()`s each ping their own execution_id
    — **Consumers affected:** node authors — new additive API
    — **Done:** BaseNode.reportProgress added with full JSDoc (ticket-name mapping, no-op semantics); tests (a)–(c) green incl. interleaved-runs isolation; files: typescript/src/base-node.ts, typescript/tests/base-node.test.ts; fixes: eslint unused-args underscore rename

### Phase 3: exit gate

- [ ] **3.1** Run the full gate in `typescript/`: `npm run lint` + `npm run typecheck` + `npm run build` + `npm test` (vitest run); fix anything red; append the `GATE <sha> tier=full` memo line to this PLAN's trace block
    — **Why:** ticket exit gate — the run's last gate is full per verification-loop-skill
    — **Done when:** all four commands green in one sequence on the final tree; memo line appended
    — **Consumers affected:** CI (must stay green post-merge)

## Technical Notes

- Engine contract (nus-cee/canvastekk-workflow-engine#495, DA-3231 pending): `POST {callback_url}/progress` accepting `{execution_id, percent?, message?}`; best-effort — never affects node outcome; engine validates `execution_id` against the pending async set. `estimated_remaining_s` exists engine-side but is out of both SDK tickets' scope.
- `execution_id` provenance: minted SDK-side in `run()` (`randomUUID()`), returned in the response body; async nodes echo it in the completion callback — the ping reuses the same id.
- Payload cap: message truncated to 1000 chars; percent clamped [0,100]; per-ping `AbortSignal.timeout(5000)` so a hung engine can't leak sockets.
- Existing `reportProgress(progress: number /* 0..1 */, message)` signature/semantics preserved — only additive POST side effect when a callback_url is present. The new `BaseNode.reportProgress` takes **percent (0..100)** per the ticket signature.
- Ceiling (ponytail): `BaseNode.reportProgress` resolves the ambient context only while `run()` is active; a call after `execute()` returns (future detached async work) no-ops — the future async/202 pattern should thread the context explicitly.

## Dependencies

- DA-3231 (engine progress endpoint) — unmerged; user-approved override: the helper is fire-and-forget, so a missing engine route is swallowed+logged and never fails a node. Merge order is irrelevant.
- No new npm dependencies (`node:async_hooks` and global `fetch` are built in).

## Risks & Mitigation

- **Risk:** unhandled rejection from the fire-and-forget fetch crashing the process. **Mitigation:** every ping terminates in `.catch(...)` → `logger.warn`; tests pin the swallow.
- **Risk:** cross-run context bleed on a shared node instance. **Mitigation:** `AsyncLocalStorage` (not instance state); interleaved-runs test pins isolation.
- **Risk:** engine route absent (DA-3231 unmerged). **Mitigation:** by design — 404/network errors are transport errors, swallowed and logged.
- **Risk:** naming confusion `reportProgress` (camel, this leg) vs ticket's `report_progress`. **Mitigation:** JSDoc cross-reference on both surfaces.

## Trace

<!-- gate memo lines appended during execution -->
- GATE 069fc55 tier=light lint=t typecheck=t build=- unit=t e2e=n.a note="Phase 1: context ping — eslint scoped + tsc + context.test.ts 18/18"
