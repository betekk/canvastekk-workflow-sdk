# Cleanup runs before the red verdict is read

2026-10-12, CRS#110: the merge-notification handler ran the worktree/branch
cleanup batch before reading the watch log — the PR was RED (infra), and the
scene (worktree, local branch, remote branch) was destroyed. Recoverable
only because GitHub keeps `refs/pull/<N>/head` (fetch it, recreate branch).

**Rule:** a cleanup script is a MERGED-verdict action. Sequence: read the
verdict line (`grep -E "MERGED|RED|NO-RED|WATCH-DONE"`), classify, then act.
Never chain `grep verdict; cleanup` in one command where cleanup runs
unconditionally.
