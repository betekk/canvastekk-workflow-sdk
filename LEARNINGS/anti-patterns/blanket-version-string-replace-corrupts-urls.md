# Blanket version-string replaces corrupt URL tag/filename pairs

Bumping a pinned artifact URL with `s|v0.40.0|v0.51.0|g` fixes the release
TAG but not the bare filename (0.40.0 without the v) — producing
`.../download/v0.51.0/canvastekk_workflow_sdk-0.40.0-...whl`, a 404 that PR
CI cannot catch (deploy-time scripts only run at deploy). Hit point-cloud
and workflow-nodes in the A2.2 wave; caught in the post-merge audit, not CI.

**Rule:** artifact URL bumps replace the FULL URL (or tag+filename together)
— and grep the result for tag/filename agreement: `grep -E
'v([0-9.]+)/.*-\1-'` style consistency, or simply `grep -c <newver>` twice.
