# PLAN: Remove minimum/maximum_sdk_version + kill the stamp dual-write

**Branch**: feat/123
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/123
**Base**: main

## Acceptance Criteria
- [x] AC1: py + ts registry payloads never emit `minimum_sdk_version`/`maximum_sdk_version`; `sdk_version` stamp retained
- [x] AC2: manifest fields removed from BOTH schemas; a manifest still declaring them parses cleanly (silently dropped — asserted)
- [x] AC3: docs/examples swept: zero live references (grep-verifiable)
- [x] AC4: parity tests updated both stacks in one change; engine#671 merged before release (satisfied — 9954e22)

## Dependency & Consumer Map

| Node | Depends on | Consumers | Risk |
|------|-----------|------------|------|
| `python .../definition.py` (field removal + validator) | engine#671 (merged) | pydantic ignores unknown keys → old manifests parse; to_dict drops the keys | low |
| `python .../registry.py` (merge loop + dual-write removal) | definition | registration payload shape; engine advisory checker dual-reads `sdk_version` (kept) | low |
| `typescript/src/definition.ts` + `registry.ts` (mirror) | same | zod strips unknown; TS mirror payload | low |
| tests py+ts + docs/skills sweep | code | CI, node-builder skill readers | low |

## Implementation Phases

### Phase 1: Python removals
- [x] **1.1** definition.py: remove both fields + `_validate_sdk_versions`; registry.py: drop the two entries from the compat merge loop + the `setdefault("minimum_sdk_version", ...)` dual-write (keep `sdk_version` stamp + docs_url/changelog_url merge); docstrings updated to cite D16/#123.
    — **Why:** AC1+AC2 — provenance never masquerades as a floor; the engine is advisory since #671.
    — **Done when:** payload emits neither key; a manifest declaring them parses with fields dropped (tests).
    — **Consumers affected:** registration payload consumers (engine — advisory reader kept compatible).
    — **Done:** fields+validator+serializer tuple+dual-write removed; payload emits sdk_version only; docstrings cite D16/#123; py 870 green.

### Phase 2: TypeScript mirror
- [x] **2.1** definition.ts: remove both zod fields; registry.ts: remove the two manifestConstraintFields entries + the minimum_sdk_version fallback block (keep the sdk_version stamp).
    — **Why:** AC1 parity — one change, both stacks.
    — **Done when:** mirrored payload tests green.
    — **Consumers affected:** cli mirror + probe.
    — **Done:** zod fields+constraint entries+fallback+drop-list removed; tsc clean; 392 tests green after rewrites.

### Phase 3: Sweep + gate
- [x] **3.1** Grep-sweep every remaining live reference (README, docs/, examples/, data/skills node-builder, tests) — update or remove; grep-verifiable zero (tests that assert the DROP excepted). **Root README.md updated in the same change** (standing rule): rewrite the "SDK Compatibility Range" section (fields removed; docs_url/changelog_url remain; sdk_version is stamped provenance) and soften the "engine uses this to verify SDK compatibility" claim (advisory drift telemetry since engine#671).
    — **Why:** AC3 — deprecation sweeps that miss mentions leave traps (repo learning); the root README is the first thing authors read.
    — **Done when:** `grep -rn minimum_sdk_version` hits only the drop-assertion tests + git history; README carries no removed-field guidance.
    — **Consumers affected:** skill readers; README readers.
    — **Done:** grep-verifiable: remaining refs are drop-pins/caller-data tests only; root README rewritten (Compatibility Range section -> Provenance & Docs Fields; manifest sdk_version claim softened to advisory); language READMEs/docs/examples/skills clean.
- [x] **3.2** Full gate both stacks + LEARNINGS (chained-gate-verification anti-pattern from the engine rounds).
    — **Why:** exit gate unconditional; the verification lesson is a cross-repo keeper.
    — **Done when:** `GATE <sha> tier=full` memo, legs verified independently.
    — **Consumers affected:** future gate runs.
    — **Done:** legs verified individually: ruff check rc=0, tsc rc=0, pytest 870 pass, vitest 392 pass; LEARNINGS sweep in commit.

## Technical Notes
- engine's advisory dual-read (`sdk_version` as legacy floor alias) keeps functioning — the stamp remains.
- pydantic default = ignore extras; zod object strips unknown — old manifests parse. Assert BOTH.
- Release: minor bump (behavioral removal of emitted keys — additive-negative, engine advisory since #671).

## Dependencies
blocked-by engine#671 — MERGED (9954e22). Epic addendum A1 (D16).

## Risks & Mitigations
- Consumer reading the removed keys — only the engine's advisory checker (kept fed by the stamp); pinned by its own tests.
- Parity drift — both stacks land in this one change with mirrored drop-tests.

## Trace
GATE aeeb4bc tier=full lint=t typecheck=t build=- unit=t e2e=n.a
LOG Exit gate (ticket): ruff check rc=0 (verified solo); tsc rc=0 (verified
solo); pytest 870 passed; vitest 392 passed. README swept in-change (standing
rule). Caller-supplied legacy constraint keys remain caller data (passthrough
pinned both stacks).
LOG Standing rule added (user directive): new SDK features ship to both
python/ and typescript/ in the same change — README one-liner + LEARNINGS
pattern + noted on #124. Schema-stability gate classified the removals
BREAKING; major label applied to acknowledge (recorded on #123).
