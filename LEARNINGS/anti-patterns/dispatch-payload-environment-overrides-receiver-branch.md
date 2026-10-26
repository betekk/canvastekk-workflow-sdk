Anti-pattern: A dispatch payload environment overrides the receiver’s branch policy
Scope: project
Confidence: 0.9
Trigger: A sender workflow hardcodes `client_payload.environment` while the receiver resolves its deployment environment as `client_payload.environment || github.ref_name`.
Action: Dispatch to the lowest environment the receiver’s branch is allowed to deploy to, or omit the payload field so branch policy decides.
Context: SDK prod releases notified CWN with `environment: "prod"` even though the dispatch ran on CWN’s `dev` branch.
Detail: CWN’s `stack-env` job honors the payload first, so the prod value forced a forbidden prod deployment request from dev; GitHub environment protection then blocked the run before deploy.
Rationale: Branch protections protect the receiver, but an explicit payload bypasses the branch-default intent and turns every release notification into a blocked prod attempt.
Evidence: SDK run 40300183865 sent the prod payload; CWN run 40300454678 failed with “Branch ‘dev’ is not allowed to deploy to prod”; #212 changes the payload to uat.
Files: .github/workflows/release.yml, betekk/canvastekk-workflow-nodes/.github/workflows/deploy-lambda.yml
Date: 2026-10-26
