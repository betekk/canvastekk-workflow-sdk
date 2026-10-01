# Release Bump Script Misses a New Version-Source Leaf

**Category:** anti-pattern (with solution) · **Confidence:** high · **Scope:** any multi-language repo with a release-stamping script
**Date:** 2026-10-02 · **Ticket:** DA-3425

## Symptom

The v0.37.1 python wheel shipped with `METADATA Version: 0.37.1` but an internal
`canvastekk_workflow_sdk/_version.py` saying `__version__ = "0.37.0"`. Every
consumer installing "0.37.1" stamped `sdk_version: 0.37.0` in manifests and
health endpoints — silently defeating the DA-3359 stamped-manifest contract.

## Root cause

`scripts/bump_versions.py` bumps an enumerated `VERSION_FILES` set. DA-3359
introduced a NEW single-source-of-truth leaf (`_version.py`) but the release
script's enumeration was never widened — the wheel's build metadata (pyproject)
was bumped while the runtime stamp (leaf) froze at the previous release.

## Rule

Adding, moving, or splitting any `__version__` / `VERSION` / `RELEASE_DATE`
source file REQUIRES updating the release-bump script's enumeration in the
same change. The 4-file invariant documented in older PLANs (DA-1955) went
stale the moment DA-3359 added the fifth file.

## Verification recipe (caught this in the wild)

Never trust METADATA alone — unzip the released wheel and diff the code-level
stamp against the tag:

```bash
curl -sSL -o s.whl "<wheel-url>"
python3 -c "import zipfile; z=zipfile.ZipFile('s.whl'); \
  print([l for l in z.read([n for n in z.namelist() if n.endswith('METADATA')][0]).decode().splitlines() if l.startswith('Version:')]); \
  print(z.read('canvastekk_workflow_sdk/_version.py').decode())"
```

A dependency-bump gate should assert installed `__version__ == the pinned
version` after `poetry install` (the engine's DA-3419 run caught it exactly
this way: `poetry run python -c "... assert v == '0.37.1'"`).
