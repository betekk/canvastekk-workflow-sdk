"""Registry convergence against the workflow-engine registry (DA-3086).

SDK absorption of the per-repo convergence scripts (lineage: DA-3070 IFC ->
DA-3071 CWN -> DA-3084 CRS — the third copy fired the absorb trigger).
Deploy-time semantics, unchanged from the absorbed copies:

Single source: node-slugs.txt (repo root). At deploy time this script:

1. Lists active nodes from the workflow-engine registry.
2. Drains (soft-retires) actives that are ALL of:
     - declared in the git history of node-slugs.txt (HEAD ancestry only),
     - absent from node-slugs.txt@HEAD (a slug still in the file is never
       retired — prod staging deliberately unstages slugs),
     - owned by THIS deploy: the active registration's invoke_url matches
       ``<function-url>/nodes/<slug>/execute``. The registry's shared
       service-token identity cannot discriminate repos by owner, so the
       invoke_url clause is what makes draining safe (a CWN-registered twin
       carries a different function URL and is never touched).
3. Asserts the branch-resolved staged set (``$NODE_SLUGS``) is present in
   the registry — presence-only (``staged ⊆ actives``), never equality: the
   registry legitimately hosts other repos' nodes.

Stdlib only — the deploy runner has no poetry/venv (unlike CI).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PAGE_SIZE = 100


def load_declared(path: str | Path) -> list[str]:
    """Slugs from node-slugs.txt: one per line, # comments and blanks ignored."""
    return load_declared_from_text(Path(path).read_text(encoding="utf-8"))


def canonical_from_invoke_url(invoke_url: str | None, invoke_base: str) -> str | None:
    """The canonical slug iff invoke_url belongs to THIS deploy's invoke base.

    Registrations post ``<function-url>/nodes/<canonical-slug>/execute``;
    registry slugs carry a deploy-suffix (``-lambda``), so the invoke_url is
    the authoritative canonical-slug mapping.
    """
    if not invoke_url or not invoke_base:
        return None
    base = invoke_base.rstrip("/")
    prefix = f"{base}/nodes/"
    if not invoke_url.startswith(prefix):
        return None
    rest = invoke_url[len(prefix) :]
    if not rest.endswith("/execute"):
        return None
    return rest[: -len("/execute")] or None


def fetch_actives(registry_base: str, token: str) -> list[dict]:
    """All active registry records, paginating page/total_pages."""
    base = registry_base.rstrip("/")
    actives: list[dict] = []
    page = 0
    total_pages = 1
    while page < total_pages:
        url = f"{base}/api/workflows/nodes?status=active&size={PAGE_SIZE}&page={page}"
        data = _get_json(url, token)
        actives.extend(data.get("content", []))
        pg = data.get("page", {}) or {}
        total_pages = int(pg.get("total_pages") or 1)
        page += 1
    return actives


def history_slugs(slugs_file: str | Path) -> set[str]:
    """Every slug that ever appeared in node-slugs.txt at HEAD ancestry.

    ``git log HEAD -- <file>`` lists only shipped commits; commits from
    unmerged branches never enter the drain candidate set.
    """
    file_path = Path(slugs_file).resolve()
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(file_path.parent),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    rel = file_path.relative_to(top).as_posix()
    log = subprocess.run(
        ["git", "log", "HEAD", "--format=%H", "--", rel],
        cwd=top,
        capture_output=True,
        text=True,
        check=True,
    )
    slugs: set[str] = set()
    for sha in log.stdout.split():
        show = subprocess.run(
            ["git", "show", f"{sha}:{rel}"],
            cwd=top,
            capture_output=True,
            text=True,
            check=False,
        )
        if show.returncode != 0:
            continue
        slugs.update(load_declared_from_text(show.stdout))
    return slugs


def load_declared_from_text(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def compute_drain(
    actives: list[dict],
    history: set[str],
    declared: set[str],
    invoke_base: str,
) -> list[dict]:
    """Active records satisfying the four-clause drain predicate."""
    drain = []
    for node in actives:
        canonical = canonical_from_invoke_url(node.get("invoke_url"), invoke_base)
        if canonical is None:
            continue
        if canonical in history and canonical not in declared:
            drain.append(node)
    return drain


def drain(registry_base: str, token: str, records: list[dict], dry_run: bool) -> None:
    base = registry_base.rstrip("/")
    for node in records:
        ident = node.get("name") or node.get("slug")
        if dry_run:
            print(f"[dry-run] would soft-retire: {ident}")
            continue
        url = f"{base}/api/workflows/nodes/by-name/{urllib.parse.quote(str(ident), safe='')}"
        _delete(url, token)
        print(f"drained: {ident}")


def assert_staged(
    staged: list[str],
    actives: list[dict],
    invoke_base: str,
) -> None:
    """Presence-only: every staged canonical slug must own an active registration."""
    owned = {canonical_from_invoke_url(node.get("invoke_url"), invoke_base) for node in actives}
    missing = [s for s in staged if s not in owned]
    if missing:
        print("::error::convergence assert FAILED — staged slugs missing from registry:")
        for s in missing:
            print(f"  missing: {s}")
        print(f"staged({len(staged)}): {' '.join(sorted(staged))}")
        raise SystemExit(1)
    print(f"convergence OK — staged {len(staged)}/{len(staged)} present in registry")


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Service-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _delete(url: str, token: str) -> None:
    req = urllib.request.Request(url, method="DELETE", headers={"X-Service-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-base", required=True)
    parser.add_argument(
        "--invoke-base",
        required=True,
        help="https://<INVOKE_BASE> - resolved by the step from ${LAMBDA_INVOKE_DOMAIN:-$FUNCTION_URL} exactly as the register step does",
    )
    parser.add_argument("--slugs-file", required=True)
    parser.add_argument(
        "--token",
        default=None,
        help="service token; defaults to $CANVASTEKK_NODE_REGISTRATION_KEY",
    )
    parser.add_argument(
        "--staged",
        default=None,
        help="branch-resolved slugs; defaults to the file content",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    token = args.token or (
        os.environ.get("CANVASTEKK_NODE_REGISTRATION_KEY") or os.environ.get("CANVASTEKK_REGISTRY_TOKEN", "")
    )
    if not token:
        print("::error::no service token (pass --token or set CANVASTEKK_NODE_REGISTRATION_KEY)")
        return 2

    declared_list = load_declared(args.slugs_file)
    staged = args.staged.split() if args.staged is not None else declared_list
    declared = set(declared_list)
    history = history_slugs(args.slugs_file)
    actives = fetch_actives(args.registry_base, token)

    candidates = compute_drain(actives, history, declared, args.invoke_base)
    print(
        f"registry actives: {len(actives)}; declared: {len(declared)}; "
        f"history: {len(history)}; drain candidates: {len(candidates)}"
    )
    drain(args.registry_base, token, candidates, args.dry_run)

    drained_names = {node.get("name") for node in candidates}
    assert_staged(
        staged,
        [node for node in actives if node.get("name") not in drained_names],
        args.invoke_base,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
