# X-API-Key slot carries run tokens; retirement by env removal (#3825)

**Category:** decision
**Confidence:** high
**Scope:** canvastekk-workflow-sdk (consumed by CWE #3826 + 6 node repos)
**Date:** 2026-10-17

The engine→node credential swap keeps the wire header (`X-API-Key`) and
changes only its semantics: engine-minted `cwnt_v1.` run tokens, verified
centrally by the engine (SDK `NodeAuth.central()`). Dual-accept is the
constructor default (`legacy_key_env_var="CANVASTEKK_API_KEY"`) so the
legacy leg is INERT whenever the env var is unset — fleet retirement
(#3838) is env removal, not a code change or redeploy of constructors.
`auth.py:78-196` (`_CentralAuth`), `node_token.py` (mint/verify),
`docs/NODE-TOKEN-CONTRACT.md` is normative.

Companion decision: transport errors are NEVER cached (a recovered engine
must immediately serve verdicts); definitive `valid:false` IS cached 60s.
