# Self-hosted exit 127 loading libpythonX.so = runner toolcache corruption

`python3: error while loading shared libraries: libpython3.14.so.1.0` +
exit 127, before any project code runs, on betekk self-hosted runners
(r5/r8, 2026-10-12) = corrupted `actions/setup-python` toolcache
(`…/_work/_tool/Python/<ver>/`), not a diff problem.

**Triage:** reruns are a lottery (pick-runner routes to any idle runner —
healthy ones pass, broken ones 127 again). The fix is ops-side: purge the
bad toolcache dirs and let setup-python reinstall. Distinguish from
diff-reds by the absence of any test/lint output before the crash. A
cancel at `timeout-minutes` with zero errors is the same family.
