#!/usr/bin/env bash
# Pack + install-without-express smoke test (#225).
#
# Proves the published artifact shape: the root entry imports cleanly in a
# clean install with NO express present (express is an optional peer, not a
# dependency), and the ./express subpath fails while naming the missing
# package. Run from CI (ci-typescript.yml) or locally: bash scripts/pack-test.sh
set -euo pipefail
cd "$(dirname "$0")/.."

npm run build >/dev/null
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

npm pack --pack-destination "$WORK" >/dev/null 2>&1
PKG_TGZ="$(echo "$WORK"/betekk-canvastekk-workflow-sdk-*.tgz)"
[ -f "$PKG_TGZ" ] || { echo "FAIL: npm pack produced no tarball" >&2; exit 1; }

(cd "$WORK" && npm install --silent "$PKG_TGZ" >/dev/null 2>&1)
PKG="$WORK/node_modules/@betekk/canvastekk-workflow-sdk"
[ -d "$PKG" ] || { echo "FAIL: package did not install" >&2; exit 1; }

node --input-type=module -e "
const root = await import('$PKG/dist/index.js');
if (typeof root.BaseNode !== 'function') { throw new Error('root import missing BaseNode'); }
if (typeof root.NodeAuth !== 'function') { throw new Error('root import missing NodeAuth'); }
if (typeof root.TekkNodeAuth !== 'function') { throw new Error('root import missing TekkNodeAuth'); }
console.log('root import OK without express');
"

if node --input-type=module -e "await import('$PKG/dist/express.js');" 2>"$WORK/express-err.txt"; then
  echo "FAIL: ./express subpath imported even though express is not installed" >&2
  exit 1
fi
if ! grep -q "express" "$WORK/express-err.txt"; then
  echo "FAIL: ./express failure does not name the missing package:" >&2
  cat "$WORK/express-err.txt" >&2
  exit 1
fi
echo "./express subpath fails clearly without express (optional peer honored)"
