---
title: SDK changes must sweep the root README in the same change
type: anti-pattern
---

# SDK changes must sweep the root README in the same change

Every cross-stack SDK change (feature, removal, rename) must check the ROOT
`README.md` — not just `python/README.md` / `typescript/README.md`. The root
README duplicates API surface (e.g. the former "SDK Compatibility Range"
section advertised `minimum_sdk_version`/`maximum_sdk_version` constructors
long after engine-side law changed).

- **Symptom:** root README teaches removed/stale APIs; new authors copy dead code.
- **Fix:** `grep -rn "<changed-symbol>" README.md` is a mandatory exit-gate leg
  for SDK tickets; update in the same PR.
- **Scope:** root README + both language READMEs + docs/ + data/skills.
