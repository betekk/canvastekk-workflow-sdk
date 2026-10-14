# Installed-Tool Env Contracts Are Invisible to Invoker-Side Greps

**Confidence:** 1.0 (observed 2026-10-14, ifc deploy run 38508424993; fleet pin sweep epic canvastekk-tracker#3788)

## The pattern

Verifying a fleet rename by grepping invoker repos proves the callers, never the tool. The wave-2 rename swept every repo's source for `REGISTRY_SERVICE_TOKEN` (zero refs — verified per repo), yet ifc's dev deploy failed on v1.3.39: the pinned SDK wheel's `registry-convergence` subcommand kept its own env fallback (`convergence.py:218`), which still read the retired name. Registrations passed (the `register` subcommand read the new name) and convergence failed 270ms later — "no service token" — with the new name sitting right there in the env.

**Invoker-side greps verify the invoking code; the pinned artifact's internal contract needs its own sweep.** Any dependency that reads env, spawns subprocesses, or shells out carries rename surface that `grep -r` over the consumer repo cannot see.

## The rule

When renaming an env var / credential / flag consumed by an installed tool: sweep the tool's source in the same run (or ticket the sweep against the tool's repo before cutting the release that removes the old value), and treat "zero refs in consumer repos" as necessary-but-insufficient.

## Sibling

`convention-invoked-hooks-invisible-to-invoker-greps` (ifc) — same blindness class for convention-invoked hooks; this entry generalizes it to installed-artifact contracts.
