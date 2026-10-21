# A Public Repository Cannot Call a Private Repo's Reusable Workflow

**Category:** anti-pattern · **Confidence:** high (differentially proven in-repo) · **Scope:** any public repo that must call org-internal reusable workflows
**Date:** 2026-10-19 · **Ticket:** betekk/canvastekk-frontend-nextjs#2039

## Symptom

Every workflow run in the repo dies at launch with zero jobs:

> Invalid workflow file: <caller>.yml#L — error parsing called workflow
> ".github/workflows/<caller>.yml" -> "betekk/betekk-gha/.github/workflows/reusable-release.yml@<ANY ref>"
> : workflow was not found

The called file resolves fine through the contents API at the same ref, and
sibling private repos run the identical call green minutes apart. The error
masquerades as a resolution failure and links to the "Access to reusable
workflows" doc — because it IS an access failure: **public callers can only
use reusable workflows hosted in public repositories**.

## How the diagnosis went sideways (avoid this)

The repo-level settings all read as fine (`allowed_actions: all`, no forks,
same org, called repo's Actions access = organization, token perms match the
working repos) — because none of them are the gate. The gate is the CALLER's
visibility. A `gh api repos/... --jq .private` on every repo in the
differential set settles it in seconds; a buggy loop that printed three of
four results hid the one line that mattered.

## Rule

- Public repo + private reusable = "workflow was not found" at ANY ref (tag
  or full SHA) from EVERY workflow file. Check `.private`/`.visibility` on
  BOTH sides before debugging anything else.
- Same-repo calls (`uses: ./.github/workflows/x.yml`) are the access model's
  first-class escape hatch — a vendored copy of the reusable works
  immediately.
- Vendoring into a public repo: scrub organizational commentary (tracker
  refs, runner-pool strategy, internal doc paths) — the mechanics are not
  secrets, the conventions are nobody else's business.

## Evidence

- canvastekk-workflow-sdk (public): v1.4.0 tag, v1.7.2 tag, and a full SHA
  all fail from both a minimal probe workflow and the real caller.
- auth-library / shared-library / CDS / CWE / nodes / ml-service (all
  private): the same refs resolve green the same day, including
  auth-library @v1.7.2 four minutes after the SDK's first failure.
- Fix shipped as canvastekk-workflow-sdk#156 (vendored scrubbed mirror of
  betekk-gha@v1.7.2); first dev push after merge minted v0.55.1-dev.0 green.
