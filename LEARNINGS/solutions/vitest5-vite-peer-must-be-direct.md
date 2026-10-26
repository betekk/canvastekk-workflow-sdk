Solution: Declare vite directly when upgrading vitest to 5
Scope: project
Confidence: 0.9
Trigger: `npm ci` succeeds after a vitest 5 bump, but `vitest run` fails at startup with `ERR_MODULE_NOT_FOUND: Cannot find package 'vite'` from `nativeModuleRunner`.
Action: Add `vite` to `typescript` devDependencies at the version vitest 5 resolves, regenerate the lock, and re-run `npm ci` plus the test gate.
Context: vitest 5 stops bundling vite and declares it as a required peer; `--legacy-peer-deps` install leaves the absent peer undiagnosed until the runner starts.
Rationale: The lock can contain a `node_modules/vite` entry without rooting it in the project's dependencies, so `npm ci` does not install it; a direct declaration is the minimal stable fix.
Evidence: PR #194 failed locally with the startup error while `package-lock.json` listed vite 8.3.5; adding `"vite": "^8"` made all 435 tests pass and CI merged as c5cdcb4.
Files: typescript/package.json, typescript/package-lock.json
Date: 2026-10-26
