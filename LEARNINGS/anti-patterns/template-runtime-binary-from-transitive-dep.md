# Template Runtime Binary Must Not Ride a Transitive Dependency

Date: 2026-10-10 · Confidence: high · Scope: SDK templates, Dockerfiles, scaffolds

## Summary

The node-builder skill's Dockerfile template ran `CMD ["uvicorn", ...]` while
installing only `canvastekk-workflow-sdk` — uvicorn arrived as the SDK's hard
transitive. Demoting uvicorn to a `[serve]` extra (#102) would have silently
broken every generated node image: the build succeeds, the container fails at
start. Any template that executes a binary must declare it where the binary is
consumed (template install line or the scaffolded project's deps), never rely
on a dependency-of-a-dependency.

## Evidence

- SKILL.md Dockerfile block: `RUN pip install canvastekk-workflow-sdk>=0.5.2`
  followed by `CMD ["uvicorn", "handler:app", ...]` (fixed to install uvicorn
  explicitly; pyproject snippets gained `"uvicorn>=0.54"`).
- Same family as the producer-side rule: a consumer needs a producer, not just
  a parse seam (cf. anti-patterns/widened-wire-field-needs-producer-wiring).

## Check

When removing/demoting ANY dependency, grep templates and scaffolds for the
binaries it provides before merging.
