# PLAN: SDK assistant skill + npx installer + skill leak scrub

**Branch**: feat/144
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/144
**Base**: main

## Acceptance Criteria

- [x] `canvastekk-workflow-sdk-assistant/SKILL.md` exists in `python/canvastekk_workflow_sdk/data/skills/` with a ≤50-word description and a mode dispatch table (create/answer/audit); the contract checklist lives inline
- [x] Dependency rule stated once in the assistant: base `canvastekk-workflow-sdk` default; extras (`[fastapi,serve]`, `[jwt]`, `[keycloak]`) added per rung/auth with one-line reasons; builder templates match
- [x] `grep -rE 'DA-[0-9]+' python/canvastekk_workflow_sdk/data/skills .agents/skills` returns nothing; no `/api/internal` or engine config filenames in any skill
- [x] `diff -r .agents/skills python/canvastekk_workflow_sdk/data/skills` is clean
- [x] `node installer/init.mjs list` shows three skills; `add <skill> --project <probe> --dry-run` writes nothing; a real add writes `.skill-source.json` carrying the SDK version
- [x] AGENTS.md routing template + root README + python/README list the third skill and the npx install path
- [x] `opencode.json` carries an allow entry for the assistant skill
- [x] `cd python/ && poetry run pytest` is green

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/data/skills/canvastekk-workflow-sdk-assistant/SKILL.md` (new) | — | wheel packaging (`data/**/*` include), `init` scaffolding (`__main__.py:387` generic loop), `.agents/skills` mirror, skill-mirror-guard CI, installer `add` | low |
| `.agents/skills/**` mirror (3 skills) | canonical edits land first | skill-mirror-guard CI (`diff -r`), installer source dir, repo-local agent discovery | low |
| `canvastekk-node-builder/SKILL.md` (canonical + mirror) | — | wheel users, mirror guard, routing template | low |
| `canvastekk-node-patterns/SKILL.md` (canonical + mirror) | — | wheel users, mirror guard | low |
| `installer/init.mjs` + root `package.json` (new) | `.agents/skills` populated (mirror edits done) | end users via `npx github:betekk/canvastekk-workflow-sdk` | med |
| `python/canvastekk_workflow_sdk/data/templates/AGENTS.md` | — | `init --agents-md` output (`__main__.py:435`) | low |
| `README.md`, `python/README.md` | skills + installer exist (docs describe reality) | humans | low |
| `opencode.json` | skill dir name fixed | repo authors (OpenCode session perms) | low |
| `python/tests/test_cli_init.py` | new skill dir exists | python CI suite | low |

## Implementation Phases

### Phase 1: Assistant skill (canonical + mirror + test pin)

- [x] **1.1** Write `python/canvastekk_workflow_sdk/data/skills/canvastekk-workflow-sdk-assistant/SKILL.md` — frontmatter (`name` + ≤50-word description with trigger phrases), mode dispatch table, inline contract checklist, CREATE mode (dependency decision table: base default, extras per rung with one-line whys; rung selection; route codegen to builder/patterns), ANSWER mode (standalone quick-reference: imports map, endpoints, env vars, extras, versioning, context API), AUDIT mode (version currency, extras-vs-imports, `validate`/`diff` classification, conformance, PASS/FAIL report)
    — **Why:** this is the deliverable's core; everything else wraps or serves it
    — **Done when:** file parses as frontmatter + markdown; description ≤50 words; body ≤~10KB; `grep -E 'DA-[0-9]|api/internal'` on it is empty
    — **Consumers affected:** wheel `init`, mirror, installer, routing template (names this dir)
    — **Done:** three-mode router written (dispatch table, inline contract, dependency decision table, audit checklist, quick reference); 44-word description, 8168 bytes, zero leak hits; files: data/skills/canvastekk-workflow-sdk-assistant/SKILL.md; fixes: none
- [x] **1.2** Mirror to `.agents/skills/canvastekk-workflow-sdk-assistant/SKILL.md` (byte-identical copy)
    — **Why:** mirror-guard CI and the installer both read `.agents/skills`; canonical and mirror must move together
    — **Done when:** `diff -r .agents/skills python/canvastekk_workflow_sdk/data/skills` clean
    — **Consumers affected:** skill-mirror-guard CI, installer source
    — **Done:** byte-identical copy; `diff -r` clean; files: .agents/skills/canvastekk-workflow-sdk-assistant/SKILL.md; fixes: none
- [x] **1.3** Extend `python/tests/test_cli_init.py` scaffold loop with `canvastekk-workflow-sdk-assistant`
    — **Why:** pins the third skill into the `init` scaffold contract so a future packaging regression fails loudly
    — **Done when:** loop lists three skill ids; `poetry run pytest tests/test_cli_init.py` green
    — **Consumers affected:** python CI suite
    — **Done:** loop extended to three ids; ruff + pytest green (2 passed); files: python/tests/test_cli_init.py; fixes: poetry install for fresh worktree venv (gate fix, root cause: deps uninstalled)

### Phase 2: Leak scrub + dependency restatement (both skills, both copies)

- [x] **2.1** Strip `DA-\d+` references from builder + patterns (canonical and mirror): 5 lines each (builder 747/753/754, patterns 957) — keep the mechanism, drop the ticket IDs (e.g. "rejected with `NodeIOError`" without `(DA-3340)`)
    — **Why:** AC gate — internal ticket IDs must not ship in public skill content
    — **Done when:** `grep -rE 'DA-[0-9]+' python/canvastekk_workflow_sdk/data/skills .agents/skills` empty
    — **Consumers affected:** wheel users, mirror guard
    — **Done:** all 5 lines scrubbed in both copies (mechanism kept, IDs dropped); grep = 0 hits; files: builder + patterns SKILL.md ×2 copies; fixes: none
- [x] **2.2** Restate builder dependency guidance per base-default rule: "Package Installation" section, Step 4 Dockerfile, Step 5 pyproject — base `canvastekk-workflow-sdk` line first, `[fastapi,serve]` as the SDK-served variant with one-line why (base ships without fastapi since 0.43), bump stale `>=0.5.2` floors to `>=0.52`; mirror the file
    — **Why:** AC — templates must match the dependency rule stated in the assistant
    — **Done when:** no `[fastapi,serve]>=0.5.2` remnants; builder guidance agrees with the assistant's decision table; diff -r clean
    — **Consumers affected:** wheel users following templates
    — **Done:** Package Installation section restated (base-first + pointer to assistant table), Dockerfile + both pyproject variants carry the why-comment, checklist + 3 pins bumped to >=0.52; stale-pin grep = 0; mirror re-synced; files: builder SKILL.md ×2 copies; fixes: none

### Phase 3: npx installer

- [x] **3.1** Add root `package.json` — `private: true`, `"type": "module"`, `bin: {"canvastekk-workflow-sdk-skills": "./installer/init.mjs"}`, repository field
    — **Why:** `npx github:betekk/canvastekk-workflow-sdk` resolves the bin from the root manifest
    — **Done when:** `npx --no-install` irrelevant; `node installer/init.mjs` runs; JSON valid
    — **Consumers affected:** end users reviewing the repo
    — **Done:** root manifest with bin + repository; node installer/init.mjs runs; files: package.json; fixes: none
- [x] **3.2** Write `installer/init.mjs` adapted from betekk-skills: `list` / `list installed` / `add <skill> [--project .] [--ref <tag|main>] [--source .] [--dry-run]`; `SKILLS_SRC = .agents/skills`; user scope `~/.agents/skills`; latest `vX.Y.Z` tag router (`git ls-remote` + shallow clone + re-exec); sidecar `.skill-source.json` with version from `python/pyproject.toml` `[project].version`; `--dry-run` prints resolved source→dest, writes nothing
    — **Why:** the one-command install path for repo reviewers without Python
    — **Done when:** smoke test below passes
    — **Consumers affected:** end users; README install section (documents its commands)
    — **Done:** installer adapted (SKILLS_SRC=.agents/skills, user scope ~/.agents/skills, pyproject version stamping, --dry-run, tag router); files: installer/init.mjs; fixes: none
- [x] **3.3** Smoke test: `node installer/init.mjs list` (3 skills); `add canvastekk-workflow-sdk-assistant --project /tmp/opencode/sdk144-probe --dry-run` (writes nothing); real `add` (SKILL.md + `.skill-source.json` with `version: 0.52.5` present); remove probe dir
    — **Why:** installer is new machinery — prove the AC's three behaviors before commit
    — **Done when:** all three assertions observed in output; probe dir cleaned
    — **Consumers affected:** none (probe only)
    — **Done:** list=3 skills; dry-run wrote nothing (probe absent); real add wrote SKILL.md + sidecar version 0.52.5; probe cleaned; files: none (probe only); fixes: none

### Phase 4: Routing, docs, config

- [x] **4.1** Update `python/canvastekk_workflow_sdk/data/templates/AGENTS.md`: creation routes assistant-first (contract gate) then builder/patterns; "Review my node"/validate row → assistant; new SDK Q&A row → assistant
    — **Why:** `init --agents-md` teaches routing; the assistant is now the entry point
    — **Done when:** table rows reference all three skills; template still renders the conventions section
    — **Consumers affected:** every `init --agents-md` consumer
    — **Done:** routing table rebuilt assistant-first (create/review/Q&A rows); tree shows all three skills; files: data/templates/AGENTS.md; fixes: none
- [x] **4.2** Update root `README.md` "AI Agent Setup": skills table 2→3 rows; add npx install block (list / add user-scope / add --project / pinned `#vX.Y.Z`) before the `init` path; keep `init` documented; one line noting `npx skills add`-ready layout (deferred)
    — **Why:** AC — README must list the third skill and the npx path
    — **Done when:** section shows three skills + both install paths; commands match installer flags verbatim
    — **Consumers affected:** public readers
    — **Done:** AI Agent Setup: npx block first (list/add/pin/dry-run/list installed), init kept as wheel path, 3-skill table, global setup via npx user-scope, ecosystem-layout note; files: README.md; fixes: none
- [x] **4.3** Add one pointer line to `python/README.md` directing to the root README's "AI Agent Setup" section (user decision, detection-gate round 1: pointer-line-only — python/README has no skills section today; single canonical listing, no drift)
    — **Why:** SDK-change README sweep rule (root + language READMEs) without duplicating the skills table
    — **Done when:** python/README mentions the bundled agent skills exactly once, pointing at the root section
    — **Consumers affected:** python README readers
    — **Done:** single pointer line after the intro blockquote -> root README AI Agent Setup (user decision round 1); files: python/README.md; fixes: none
- [x] **4.4** Add `{"action": "skill", "resource": "canvastekk-workflow-sdk-assistant", "effect": "allow"}` to `opencode.json` permissions
    — **Why:** AC — repo authors get the mirror-discovered skill without a permission prompt
    — **Done when:** JSON valid; entry present alongside the existing shape
    — **Consumers affected:** repo-author OpenCode sessions
    — **Done:** allow entry added next to the existing permission shape; JSON valid; files: opencode.json; fixes: none

### Phase 5: Exit gate (full tier) + final sync

- [x] **5.1** Run the AC gates as one verification pass: `grep -rE 'DA-[0-9]+'` both skills dirs (empty); `grep -rn 'api/internal\|workflow-definitions.json'` skills dirs (empty); `diff -r .agents/skills python/canvastekk_workflow_sdk/data/skills` (clean); description word count ≤50; body size ≤~10KB; `node installer/init.mjs list` (3 skills); `cd python/ && poetry run pytest` (green)
    — **Why:** the ticket exit gate is full-tier — every AC must be demonstrably green on the final tree
    — **Done when:** all commands observed green; failures fixed and re-run before push
    — **Consumers affected:** PR gate citation
    — **Done:** all AC gates observed green: DA=0, internals=0, mirror clean, 44 words, 8168 bytes, installer lists 3, ruff full pass, pytest 879 passed; files: none (verification); fixes: poetry install -E fastapi to match CI line 106 (fresh venv lacked extras; environmental, not code)
- [x] **5.2** Append the `GATE <short-sha> tier=full` memo line to this PLAN's Trace
    — **Why:** Step 10a PR creation cites this line for the pushed SHA
    — **Done when:** memo names the final implementation SHA
    — **Consumers affected:** PR workflow
    — **Done:** full-tier memo appended to Trace naming the final implementation SHA; carried by the trailing docs-only commit per pipeline Step 9; files: PLANS/PLAN-144.md; fixes: none

## Technical Notes

- Generalization hard rules for the assistant content: no `DA-*` tickets; no engine repo URLs/paths; no `/api/internal/*`; no engine config filenames; engine appears only as "the workflow engine" judging the served contract — requirements, never implementation. Public citations only (package name, GitHub Releases URL, install index URL, CLI commands).
- Dependency rule single home: the assistant's CREATE decision table owns it; builder templates show the outcome with a pointer, never restate the full table.
- Installer version router: plain `vX.Y.Z` regex only — a pre/post PEP 440 tag won't resolve; fallback is `--ref main` (document in usage line, not the README).
- `python/tests/test_cli_init.py` contains `DA-2982` in a docstring — out of AC scope (not a skills dir); leave.
- Mirror edits always in the same change as canonical (skill-mirror-guard CI); no CI file changes needed.

## Dependencies

None — no blocked-by tickets; base `origin/main` @ b1989ce (v0.52.5).

## Risks & Mitigations

- **Installer breaks on edge tags** (PEP 440 suffixes) → `--ref` escape hatch + usage-line note; latest-triple default covers all current tags (`v0.52.5` shape).
- **Assistant body weight creep** (ANSWER mode duplicating builder) → ~10KB budget checked at gate; quick-reference only, deep mechanics pointer.
- **README/installer flag drift** → 4.2 "Done when" requires verbatim command match.
- **Wheel packaging regression** → pyproject `data/**/*` include is recursive; 1.3 test pin catches scaffold loss; full pytest at 5.1.

## Trace

_Planning: PLAN authored from ticket #144 + approved local plan `/home/silentx/.opencode/plan/PLAN-sdk-assistant-skill-and-installer.md`._
GATE 9b20d72 tier=light lint=t typecheck=n.a build=- unit=t e2e=n.a
GATE 59c1320 tier=light lint=n.a typecheck=n.a build=- unit=n.a e2e=n.a
GATE 197097e tier=light lint=n.a typecheck=n.a build=- unit=t e2e=n.a
GATE 41a03a9 tier=light lint=n.a typecheck=n.a build=- unit=n.a e2e=n.a

GATE 5c59daf tier=full lint=t typecheck=n.a build=- unit=t e2e=n.a
LOG full-tier escalation: ticket exit gate (last gate of the run) — unconditional full per gate contract
