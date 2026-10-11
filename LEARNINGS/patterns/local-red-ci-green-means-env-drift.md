# Local-red + CI-green = env drift; check installed-vs-lock before filing

Engine full-suite showed 2 "pre-existing dev-red" compat-fields tests; CI
on the same head was green. Root cause: the local venv resolved
canvastekk_workflow_sdk 0.47.2 while poetry.lock pinned 0.48.0 — the tests
assert post-#123 semantics (minimum_sdk_version removed), so any env
behind the lock fails them. Documented them as dev-reds in a PR body;
needed a correcting comment.

**Rule:** before recording "pre-existing baseline failures", diff the
env's installed pins against the lock (`venv python -c "import pkg;
print(pkg.__version__)"`) — CI-green/local-red divergence is env drift
until proven otherwise. Fix is `poetry install` (don't sync shared venvs
mid-flight; parallel sessions).
