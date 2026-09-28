# PLAN: SDK Python — report_progress via shared chokepoint-compatible surfaces

**Branch**: feat/DA-3230
**Issue**: https://betekk.atlassian.net/browse/DA-3230
**Base**: main

## Acceptance Criteria

- [ ] Helper never throws into caller code; safe no-op outside a run
- [ ] Sends `execution_id` + optional percent/message; payload size-capped
- [ ] SDK surface mirrors the shipped TS leg (DA-3232, PR #83): `ExecutionContext.report_progress` upgrade + `BaseNode.report_progress(percent?, message?)`, so node-app shared chokepoints (`load_context`, `to_node_output`, `ErrorOutputNode` — verified to live in node-app repos, not this SDK) wire it in one line on SDK bump *(user-approved scope: SDK-only; original chokepoint/parity ACs noted as node-app-side adoption work on the ticket)*
- [ ] Unit tests cover the no-op path, the happy path, payload caps, and cross-run isolation

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/context.py` — `execution_id` kwarg, `_send_progress_ping`, `_deliver_progress_ping`, `report_progress` upgrade | existing `NodeExecutionRequest.callback_url` (request.py:66); `httpx` (already a dep) | `base.py` `run()` (passes id), file-download progress calls (base.py:387,403), node code calling `context.report_progress`, new `BaseNode.report_progress` | **med** — `report_progress` gains a daemon-thread POST side effect, only when `callback_url` + `execution_id` present; local/dev/test contexts (None callback) log exactly as today |
| `python/canvastekk_workflow_sdk/base.py` — ContextVar set/reset in `run()`, new `report_progress` | context.py changes (Phase 1) | every node subclass incl. node-app `ErrorOutputNode` (additive method, zero signature changes), `app.py` routes, `workflow/executor.py` | low — contextvars set/Token-reset in finally; additive public method |
| `python/tests/test_context.py` + `python/tests/test_base.py` (additions) | both source changes | CI | low |

## Implementation Phases

### Phase 1: ExecutionContext progress ping

- [x] **1.1** Add keyword-only `execution_id: str | None = None` to `ExecutionContext.__init__`; store and expose a read-only `execution_id` property
    — **Why:** the ping must carry the run-scoped `execution_id` the engine validates against its pending async set (engine #495); `run()` already mints one (`str(uuid.uuid4())`, base.py:468) but never hands it to the context
    — **Done when:** `ruff check` green; existing context tests green
    — **Consumers affected:** `base.py` `run()` (Phase 2.2), `_send_progress_ping` (1.2)
    — **Done:** execution_id kwarg + property added; ruff green; 28/28 context tests; files: python/canvastekk_workflow_sdk/context.py; fixes: none

- [x] **1.2** Add module constants `PROGRESS_MESSAGE_MAX_CHARS = 1000`, `PROGRESS_PING_TIMEOUT_S = 5.0`; module-level `_deliver_progress_ping(url: str, payload: dict) -> None` — `httpx.post(url, json=payload, timeout=...)` wrapped in `try/except Exception` → module `logger.warning("Progress ping failed (best-effort, ignored): %s", e)`; private `_send_progress_ping(percent=0, message="")` on `ExecutionContext`: no-op unless `self._request.callback_url` and `self._execution_id` are set; clamp percent [0,100]; truncate message to 1000 chars; normalize trailing slashes off the callback URL; build `{execution_id, percent}` payload (+ `message` key only when non-empty); spawn `threading.Thread(target=_deliver_progress_ping, args=(url, payload), daemon=True).start()` — never raises into caller code
    — **Why:** single POST seam shared by both public surfaces; route derived from the completion `callback_url` + `/progress` per engine #495 — no new env config; daemon thread because `report_progress` is called from sync `execute()` bodies (may run via `asyncio.to_thread`) and must never block or raise; module-level `_deliver_progress_ping` is the monkeypatch seam that keeps the thread path deterministic under pytest
    — **Done when:** unit tests prove (a) no-op without callback_url, (b) no-op without execution_id, (c) happy-path URL/payload, (d) `_deliver_progress_ping` swallows an httpx error and logs, (e) clamp + 1000-char cap, (f) trailing-slash normalization
    — **Consumers affected:** `report_progress` (1.3), `BaseNode.report_progress` (2.3)
    — **Done:** constants + `_deliver_progress_ping` (try/except→warning) + `_send_progress_ping` (guards, clamp, cap, rstrip, daemon thread) implemented; tests (a)–(f) green; files: python/canvastekk_workflow_sdk/context.py, python/tests/test_context.py; fixes: ruff UP037 quoted-annotation autofix

- [x] **1.3** Upgrade `report_progress(progress, message)` (context.py:163): keep the existing log line, then `self._send_progress_ping(int(progress * 100), message)` — the docstring's promised evolution ("Currently logs progress. Future: will send to callback/websocket")
    — **Why:** context-level progress is the pre-existing public API (used by file downloads at base.py:387,403); wiring it to the ping gives engine visibility with zero caller changes; mirrors the shipped TS leg exactly
    — **Done when:** existing context tests still green (log behavior unchanged); ping tests from 1.2 cover the POST side
    — **Consumers affected:** internal file-download progress; node code calling `context.report_progress` — behavior identical when callback_url is None (local dev)
    — **Done:** report_progress now logs then pings; pre-existing progress tests green; files: python/canvastekk_workflow_sdk/context.py; fixes: none

- [x] **2.1** Define module-level `execution_context_var: ContextVar[ExecutionContext | None] = ContextVar("canvastekk_execution_context", default=None)` in `context.py` and import it in `base.py`
    — **Why:** concurrency-safe resolution of "the current run" for a stateless node method — one node instance serves overlapping requests (`asyncio.to_thread`), so instance-held context would cross-run-race; `contextvars` is the Python platform mechanism and propagates into `asyncio.to_thread` (which runs in a copy of the current context) — the exact mirror of the TS leg's `AsyncLocalStorage`
    — **Done when:** defined; `ruff check` green
    — **Consumers affected:** `base.py` `run()` (2.2) and `report_progress` (2.3); no other importers
    — **Done:** `execution_context_var` defined in context.py module header (landed in the Phase 1 commit alongside the ping seam — commit-granularity deviation, noted here for traceability); ruff green; the base.py import lands with Phase 2; files: python/canvastekk_workflow_sdk/context.py; fixes: none

### Phase 2: BaseNode ambient-context helper

- [x] **2.2** In `BaseNode.run()`: pass `execution_id=execution_id` to `ExecutionContext`, then `token = execution_context_var.set(context)` after construction and `execution_context_var.reset(token)` in a `finally` covering the rest of the success path through response construction
    — **Why:** makes the per-run context visible to node code while `execute()` runs — in the handler thread and inside `asyncio.to_thread` workers — with guaranteed cleanup even on exceptions (Token reset); no signature change
    — **Done when:** all existing base/app/deprecation tests green (set/reset is behavior-transparent)
    — **Consumers affected:** every node subclass — zero signature/behavior change
    — **Done:** run() passes execution_id, sets the ContextVar, resets via finally; full base suite green incl. error-path reset test; files: python/canvastekk_workflow_sdk/base.py; fixes: none

- [x] **2.3** Add `BaseNode.report_progress(self, percent: float | None = None, message: str = "") -> None`: read `execution_context_var.get()`; `None` → immediate no-op return; present → delegate to the context's progress ping with `percent if percent is not None else 0`
    — **Why:** the ticket-named one-liner surface (exact snake_case name — Python convention matches the ticket): `self.report_progress(50, "still calculating")` inside `execute()` with nothing else to wire; node-app chokepoints (`load_context`, `ErrorOutputNode.run` delegation, `to_node_output` callers) reach it through the unchanged `execute(inputs, context)` seam
    — **Done when:** unit tests prove (a) calling outside a run is a silent no-op, (b) calling inside `execute()` pings with the run's `execution_id`, (c) two concurrent `run()`s in separate threads each ping their own `execution_id`
    — **Consumers affected:** node authors — new additive API
    — **Done:** BaseNode.report_progress added with full docstring (chokepoint adoption note); tests (a)–(c) + error-path ContextVar reset green; files: python/canvastekk_workflow_sdk/base.py, python/tests/test_base.py; fixes: none

### Phase 3: exit gate

- [ ] **3.1** Run the full gate in `python/`: `poetry run ruff check canvastekk_workflow_sdk/ tests/` + `poetry run pytest`; fix anything red; append the `GATE <sha> tier=full` memo line to this PLAN's trace block
    — **Why:** ticket exit gate — the run's last gate is full per verification-loop-skill
    — **Done when:** both commands green in one sequence on the final tree; memo line appended
    — **Consumers affected:** CI (must stay green post-merge)

## Technical Notes

- Engine contract (nus-cee/canvastekk-workflow-engine#495, DA-3231 pending): `POST {callback_url}/progress` accepting `{execution_id, percent?, message?}`; best-effort — never affects node outcome. Fire-and-forget is safe to merge before the engine route exists (404 = transport error = swallowed + logged).
- `httpx.post` in a daemon thread: `report_progress` stays non-blocking and exception-proof for sync `execute()` bodies; a hung engine is bounded by the 5s httpx timeout. Thread-per-ping is fine at progress-ping frequency (seconds-to-minutes).
- ContextVar set/Token-reset pairs in `run()` guarantee no leakage across reused executor threads (set before work, reset in `finally`).
- Trust boundary: `callback_url` is engine-issued and deliberately NOT run through any SSRF policy — the engine legitimately lives on private/loopback addresses in-cluster (mirrors the TS leg decision, PR #83 review).
- Ceiling (mirrors TS): `report_progress` resolves the ambient context only while `run()` is active; detached post-`execute()` work finds no store — the future async/202 pattern should thread the context explicitly.
- Scope decision (user-approved, 2026-09-29): SDK-only surface. The ticket's chokepoint list (`load_context`, `to_node_output`, `ErrorOutputNode`) was verified to live in node-app repos (canvastekk-ifc-service-app handlers; per-app `_shared/error_output.py`), not this SDK. Adoption is one line per chokepoint on SDK bump; to be noted on the JIRA ticket.

## Dependencies

- DA-3231 (engine progress endpoint) — unmerged; user-approved override (same as DA-3232): pings to a missing route are swallowed and logged.
- DA-3232 (TS leg) — merged (PR #83, squash 7d7800d): this leg mirrors its shipped design for cross-leg parity.
- No new dependencies (`httpx`, `threading`, `contextvars` all already available).

## Risks & Mitigation

- **Risk:** exception escaping the ping path into node logic. **Mitigation:** payload construction is pure; delivery is a daemon thread whose entire body is `try/except Exception`; tests pin the swallow.
- **Risk:** cross-run context bleed on a shared node instance / reused executor thread. **Mitigation:** `contextvars` + Token reset in `finally`; concurrent-threads test pins isolation.
- **Risk:** engine route absent (DA-3231 unmerged). **Mitigation:** by design — transport errors are swallowed and logged.
- **Risk:** daemon-thread pings outliving a short-lived test process. **Mitigation:** tests monkeypatch `_deliver_progress_ping` (no real threads in the suite).

## Trace

<!-- gate memo lines appended during execution -->
- GATE f080ec4 tier=light lint=t typecheck=- build=- unit=t e2e=n.a note="Phase 1 (+2.1): context ping — ruff scoped + pytest test_context 28/28"
