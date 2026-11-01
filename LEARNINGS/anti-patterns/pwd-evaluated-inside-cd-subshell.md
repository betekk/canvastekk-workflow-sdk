# Anti-pattern: `$PWD` and relative paths evaluated inside a `cd`-subshell

**Category: anti-patterns** · **Confidence: high** · **Scope: bash scripting** · **Date: 2026-11-01**

`npm install "$PWD/${TGZ##*/}"` inside `(cd "$WORK" && …)` resolves `$PWD`
to `$WORK` — the subshell already moved — so the tarball path pointed at a
nonexistent file and the script failed with an opaque exit 254. Command
substitutions (`$(cd "$(dirname "$f")" && pwd)`) inherit the same moved cwd
when nested inside the subshell, so the "fallback" computed the same broken
path twice.

Fix shape: capture absolute paths BEFORE entering the subshell — or better,
remove the problem: `npm pack --pack-destination "$WORK"` then install from
`"$WORK"/pkg-*.tgz`, no cross-directory reference at all.

Seen in `typescript/scripts/pack-test.sh` (sdk#225), cost one debug round
with `bash -x`.
