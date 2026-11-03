# Sibling Module Bypasses the Shared Auth Fn — Strictening Misses It

**Category**: anti-patterns · **Confidence**: High · **Scope**: canvastekk-workflow-sdk registry/convergence (generalizes)
**Date**: 2026-11-03 · **Ticket**: betekk/canvastekk-workflow-sdk#239

`convergence.py` `_get_json`/`_delete` hard-coded `X-Service-Token` headers
(canvastekk-workflow-sdk convergence.py:173/179 at dev@730f113) instead of routing
through `_registry_auth_header` — so every improvement to the shared helper (ctk_
Bearer dispatch #133, and the #239 strict rotation error) silently skipped the
convergence path, which kept sending a header the engine had already retired
(#3760). Nothing in the shared fn's diff touched convergence.py.

Law: when strictening/hardening a shared guard, grep siblings for
**reimplementation** (the literal wire format / header string), not just callers
of the function. `grep -rn "<header-or-format-literal>" --include="*.py" --include="*.ts" | grep -v <shared fn>`
— any hit outside the shared fn is a bypass that will keep the old behavior
alive no matter how correct the choke point becomes.

Caught in #239 Step 5 survey (plan step 1.2); the deny-default lesson
(authz-param-deny-default-breaks-internal-callers) covers un-enumerated callers;
this is the complementary trap — enumerated callers are fine, the duplicate
implementation is the leak.
