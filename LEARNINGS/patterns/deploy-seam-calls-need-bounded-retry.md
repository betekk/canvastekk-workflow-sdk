# Pattern: Deploy-Seam Network Calls Need Bounded Retry in the Shared CLI

**Context**: canvastekk-workflow-sdk#242 — four fleet incidents (Nov 3 + Nov 6/7) of whole deploys failing on one 502-window POST
**Confidence**: 0.85
**Scope**: any shared CLI/library invoked as a deploy gate across repos
**Date**: 2026-11-11

## Pattern

The orchestrator's engine-before-nodes ordering guarantees restart windows: any deploy-gated call made in the minutes after an engine deploy walks into intermittent 502s **by design**, not by accident. A single-shot call at that seam turns a covered operation into a failed deploy — and because the gate lives in shared CI tooling, one fix there repairs every consuming repo at once (vs. N per-repo retry wrappers).

The shape that worked (#242): bounded loop around ONLY the gating call (4 attempts, 2/4/8s backoff ≈ +14s worst case); retry classes = HTTP >= 500 + transport errors; terminal 4xx fails fast on attempt one (retrying a 400 masks real contract/auth errors); per-attempt line to stderr so CI logs show the recovery; final failure re-raises into the pre-existing exit-code mapping so downstream scripts' branches stay byte-identical. Safe because the engine's registry is an idempotent upsert by slug — verify that property before copying this pattern to non-idempotent calls.

## Anti-pattern twin

Fixing this in per-repo deploy scripts (the pre-#242 state) — every new node repo re-imports the bug, and the fleet pays a dice-roll per repo per round.
