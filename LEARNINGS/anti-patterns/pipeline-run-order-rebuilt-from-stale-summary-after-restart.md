# Pipeline Run Order Rebuilt From a Stale Summary After a Restart

**Date:** 2026-10-11 · **Ticket:** #113/#112 mixup (canvastekk-workflow-sdk)

After a harness restart mid-pipeline, I rebuilt the run order from my own
summary table instead of re-fetching the ticket bodies — and implemented
#112's scope (verifier derives probes) under #113's number (OpenAPI
emission), closing the wrong issue via PR #118's `Closes #113`.

**Rule:** a restart invalidates summary-table state. Re-fetch every ticket
body (`gh issue view`) before claiming the next lane; the body is the only
authoritative scope source. Ledger fix took a reopen, a close-as-done, and a
PLAN rename (f1d3978) — all avoidable with one `gh issue view`.
