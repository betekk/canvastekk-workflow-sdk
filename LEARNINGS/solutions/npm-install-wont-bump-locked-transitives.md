# `npm install` Never Bumps Locked In-Range Transitives — Advisory Fixes Need `npm update <pkg>`

Date: 2026-10-10 · Confidence: high · Scope: all npm projects

## Summary

`npm install` only adds missing packages; a locked transitive stays pinned even
when a fixed version satisfies the parent's declared range. After upgrading a
direct dep, `npm audit` can still flag transitives whose patches are in-range
(`package-lock.json` is authoritative). Fix per package:
`npm update <pkg>` bumps it within the declared range and rewrites the lock.

## Evidence

- #102: fast-uri 3.1.2 (8 advisories, all patched ≤3.1.8) stayed locked after
  `npm install` under ajv 8.20.0 (`fast-uri: ^3.0.1` — 3.1.8 satisfies it).
  `npm update fast-uri` moved the lock to 3.1.8; audit went to 0.
- Contrast: qs 6.16.0 was NOT in-range for express 4's `~6.15.1` — no lock
  command can fix that; only the parent-range change (express ^5.3) could.

## Rule of thumb

Audit lists a transitive → check the fix version against the parent's range:
in-range → `npm update <pkg>`; out-of-range → bump the parent (breaking) or
accept the risk explicitly.
