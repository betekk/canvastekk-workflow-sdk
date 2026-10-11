# The registry wheel pin is a triple: script + pyproject + lock

CASA (audio-service-app) enforces pin parity by test
(`test_sdk_wheel_pin_consistent_between_pyproject_and_deploy_workflow`):
bumping the register script's SDK wheel URL alone reds CI — the app's
pyproject URL-pin and poetry.lock must move in the same change. Cost one
CI round on CASA#102 (fixed e734298 → merged).

**Rule:** any SDK wheel bump in a repo with a deploy register script
touches all three sites in one commit; grep for the old version string
repo-wide before pushing.
