# urllib URLError catch misses http.client.HTTPException (fail-closed hole)

**Category:** anti-pattern
**Confidence:** high
**Scope:** any urllib-based fail-closed HTTP guard (SDK `_CentralAuth._remote_verify`)
**Date:** 2026-10-17

`urllib.request.urlopen` wraps connection errors in `URLError`, but a
malformed status line or truncated body raises `http.client.HTTPException`
(BadStatusLine, IncompleteRead, ...) UNWRAPPED — an except clause catching
only `URLError/TimeoutError/OSError/ValueError` lets it escape as an
unhandled 500. In a fail-closed auth validator that is a law violation
(reject-with-503), caught in review (#3825 fix commit b93a182): add
`http.client.HTTPException` to the tuple. Grep any `except.*URLError` you
write for this.
