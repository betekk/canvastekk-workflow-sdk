# PLAN: SDK release dispatch forces CWN prod deployment

**Branch**: feat/212
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/212
**Base**: dev

## Acceptance Criteria
- [x] The SDK prod release dispatch sends CWN `environment: "uat"` instead of `"prod"`.
- [x] CWN’s own branches and promotion flow remain untouched; the SDK only changes the dispatch payload.
- [x] `release.yml` parses as YAML and the implementation diff is limited to the single dispatch environment value.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/release.yml` Notify Nodes dispatch | SDK prod release outputs; CWN `sdk-released` repository_dispatch contract | `betekk/canvastekk-workflow-nodes` Deploy Lambda `stack-env` environment selection | high |

## Implementation Phases

### Phase 1: Route SDK release dispatches to CWN UAT
- [x] **1.1** Change the Notify Nodes dispatch payload in `.github/workflows/release.yml` from `"environment": "prod"` to `"environment": "uat"`.
    — **Why:** CWN resolves its deployment environment from `client_payload.environment || github.ref_name`, so the current prod payload forces a forbidden prod request from CWN’s dev branch; UAT is the allowed target.
    — **Done when:** the dispatch payload contains `"environment": "uat"`, no other workflow behavior changes, and the scoped diff is exactly one line.
    — **Consumers affected:** CWN `sdk-released` dispatch handling deploys to UAT; CWN prod promotion remains manual and unchanged.
    — **Done:** changed only the Notify Nodes dispatch environment value from prod to uat; parsed-payload and one-line scoped-diff assertions passed; files: `.github/workflows/release.yml`; fixes: forbidden CWN prod deployment request

## Technical Notes
CWN’s `deploy-lambda.yml` already enforces the branch policy; the SDK is the component violating intent by overriding the branch default with prod. The fix is intentionally SDK-only. Local executable checks are YAML parsing plus a parsed-payload assertion that the Notify Nodes client payload targets UAT. PR CI and a future SDK prod release provide the runtime confirmation; the existing failed CWN run 40300454678 is the baseline.

## Dependencies
None.

## Risks & Mitigation
- CWN UAT deployment could fail for unrelated reasons: this change only routes the request; CWN UAT remains the allowed lane and any failure is visible there.
- A future contributor could reintroduce prod: assert through parsed YAML that the dispatch payload has exactly one environment value, `uat`.
- Workflow syntax drift: parse `release.yml` and require a one-line scoped diff.

## Trace

LOG Exit gate (ticket): full — release/deploy configuration is a critical-area anchor.
LOG Full-gate evidence: parsed YAML proves the Notify Nodes client payload targets uat and the scoped workflow diff is exactly one line; TS lint, source/test typechecks, build, and 443 tests passed; Python Ruff, wheel/sdist build, and 959 tests passed. E2E not applicable (no frontend change).
