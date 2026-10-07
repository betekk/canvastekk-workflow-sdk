# Version-stamp tests import the VERSION constant, never a literal

**Source:** #3498 gate (canvastekk-workflow-sdk typescript) · **Date:** 2026-10-07 · **Confidence:** high

Any test asserting the stamped `sdk_version` must
`import { VERSION } from "../src/version.js"` and assert `toBe(VERSION)` —
never a literal. The v0.38.0 release bump broke three tests hardcoded to
"0.37.0" (cli.test.ts, registry.test.ts ×2), blocking a later gate on
pre-existing breakage that CI missed because no typescript-touching PR ran
after the release. Constructor-arg strings (middleware.test.ts) are exempt:
they inject a value, they don't assert the stamp.
