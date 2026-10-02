# PLAN: SDK validate_file_input rejects extension-less downloads (DA-3429)

**Branch**: feat/DA-3429
**Issue**: https://betekk.atlassian.net/browse/DA-3429
**Base**: main

## Acceptance Criteria
- [ ] `validate_file_input` passes when the downloaded file has no suffix (`suffix == ''`), even when the field declares `x-accept`
- [ ] `validate_file_input` still raises for a non-empty suffix not in `x-accept`
- [ ] Unit tests cover both cases; repo gate green (ruff + pytest per ci-python.yml)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/definition.py` (`validate_file_input`) | — | `base.py` auto-download validation (:392), every SDK node handler with `format: file` + `x-accept` inputs (ff-1 `pcd_path`, converter, downsampler, …) | med |
| `python/tests/test_definition.py` (`TestValidateFileInput`) | fix lands | CI gate | low |

Behavior change is strictly narrowing: only the `suffix == ''` case stops raising; every non-empty extension keeps today's strict check. This restores the pre-0.35 tolerance that the FF pipeline's `ensure_las` converter relied on.

## Implementation Phases

### Phase 1: Tolerate extension-less downloads in x-accept validation
- [ ] **1.1** In `validate_file_input` (python/canvastekk_workflow_sdk/definition.py), guard the `x-accept` comparison with `and file_path.suffix` so an empty suffix skips the check, with a comment citing DA-3429 (extension-less DA-3338/DA-3339 emission keys + Content-Disposition naming)
    — **Why:** DA-3339 keys node outputs by field name from the registry-declared extension; url-loader's `buffer` declares none, so downstream SDK downloads legitimately carry no suffix and the strict check hard-fails before the handler's own converter can run
    — **Done when:** the guard is in place and a dotless temp path validates clean against an `x-accept` field
    — **Consumers affected:** all nodes with `x-accept` file inputs (rejection scope narrows)
- [ ] **1.2** Add `test_extensionless_file_passes` to `TestValidateFileInput` (python/tests/test_definition.py): dotless file against `x-accept: ['.txt', '.csv']` must not raise; keep the existing wrong-extension test as the strictness guard
    — **Why:** the tolerance is a deliberate contract change — both sides need pinning
    — **Done when:** both tests pass locally
    — **Consumers affected:** CI gate
- [ ] **1.3** Run the repo gate (ruff check + pytest in python/) and commit + push `fix(sdk): tolerate extension-less file inputs in x-accept validation (DA-3429)`
    — **Why:** the pipeline's push boundary requires a green full gate on the final SHA
    — **Done when:** gate green locally and the commit is pushed to `feat/DA-3429`
    — **Consumers affected:** PR review, DA-3424's SDK pin bump

## Technical Notes
- Root cause chain: url-loader 1.1.1 declares `buffer` output `x-accept: []` → DA-3339 emission key `.../outputs/url-load-1/buffer` (no extension) → engine presigns with `Content-Disposition: filename="buffer"` → SDK BaseNode auto-download names the local file `pcd_path_buffer` → `validate_file_input` raises on suffix `''`. Evidence: dev run `e5aa5f51-47df-4dcb-92e9-8d3ec589ef60` failed at ff-1.
- The engine-side alternative (preserve extension in emission keys / disposition) is a larger cross-repo change (url-loader manifest + engine emission); the SDK tolerance restores the documented pre-0.35 behavior for ALL nodes at once. Follow-up to declare proper output `x-accept` in url-loader's manifest can ride the workflow-nodes repo separately.
- Coordination: DA-3424 (point-cloud-app SDK 0.37.1 pin bump, In Progress) must include this fix once released.

## Dependencies
- None blocking. Coordination note: DA-3424.

## Risks & Mitigation
- **Over-tolerance risk** (a genuinely wrong file type arriving with no extension now passes SDK validation) → mitigated by each node's own content handling (ff's `ensure_las` fails loudly on non-point-cloud content); this was the exact pre-0.35 behavior that production runs relied on.
- **SDK release flow** → patch release per repo release.yml; consumers pin-bump at their own cadence (point-cloud-app via DA-3424 or a follow-up bump).
