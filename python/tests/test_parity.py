"""Parity guard (#239): the python/typescript mirror must not drift apart.

The two runtimes are one SDK in two languages: registry auth, the diff
engine, and the CLI are maintained as name-mirrored twins (snake_case ↔
camelCase). This test pins that convention so forgetting it is a red test,
not a support ticket (LEARNINGS: copy-derived-definitions-drift-apart).

Scoped to the MIRROR MODULES (registry/diff/cli) on purpose: the packages
carry ~70 legitimate idiom asymmetries elsewhere (zod ``*Schema`` twins,
type aliases, helpers) — full-package-set equality would be a
blanket-approval noise machine, not a guard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PY = REPO / "python" / "canvastekk_workflow_sdk"
TS = REPO / "typescript" / "src"
PY_MAIN = PY / "__main__.py"

pytestmark = pytest.mark.skipif(not TS.is_dir(), reason="typescript/src absent (e.g. wheel-only checkout)")


def _ts_exports(path: Path) -> set[str]:
    """Runtime-value exports (function/const/class) of a TS module."""
    return set(re.findall(r"export\s+(?:async\s+)?(?:function|const|class)\s+(\w+)", path.read_text()))


def _py_public(path: Path) -> set[str]:
    """Public module-level names (def/class/UPPER constants, annotated too)."""
    src = path.read_text()
    names = set(re.findall(r"^(?:def|class) (\w+)", src, re.M))
    names |= set(re.findall(r"^([A-Z][A-Z0-9_]*)(?::[^=\n]+)?\s*=", src, re.M))
    return {n for n in names if not n.startswith("_")}


# ---------------------------------------------------------------------------
# (a) The mirror cluster: explicit pairs. Every pair must exist on BOTH sides.
# ---------------------------------------------------------------------------
MIRROR_PAIRS: dict[tuple[str, str], dict[str, str]] = {
    ("registry.py", "registry.ts"): {
        "registry_auth_header": "registryAuthHeader",
        "invalid_ctk_reason": "invalidCtkReason",
        "register_node": "registerNode",
        "fetch_published_definition": "fetchPublishedDefinition",
        "diff_against_published": "diffAgainstPublished",
        "build_registry_payload": "buildRegistryPayload",
        "ENGINE_NON_COMPARISON_FIELDS": "ENGINE_NON_COMPARISON_FIELDS",
        "CTK_PREFIX": "CTK_PREFIX",
        "CTK_BODY_LENGTH": "CTK_BODY_LENGTH",
    },
    ("diff.py", "diff.ts"): {
        "diff_manifests": "diffManifests",
    },
    ("__main__.py", "cli.ts"): {
        "main": "cliMain",
    },
}

# Documented asymmetries inside the mirror modules. Adding an entry here
# without a comment naming the reason should fail review.
PY_ONLY = {
    # py exposes the validator's alphabet; ts keeps its Set private.
    "CTK_BODY_ALPHABET",
    # py result/error are classes; ts shapes are types/interfaces (not runtime exports).
    "RegisterNodeResult",
    "RegistrationError",
    # py diff internals are data/typedefs; ts inlines them.
    "ManifestDiff",
    "VERSION_BUMPS",
    # invoke-type gates: py uses module constants; ts uses a private Set in registry.ts.
    "VALID_INVOKE_TYPES",
    "UNSUPPORTED_INVOKE_TYPES",
}
TS_ONLY = {
    # exported by #237 for the probe wiring; py keeps _version_tuple private (visibility asymmetry, accepted).
    "versionTuple",
    "compareVersionTuples",
    # ts result accessors; py's RegisterNodeResult is dict-like instead.
    "registerNodeResultGet",
    "registerNodeResultHas",
    "extractNodeData",
    # ts-only convenience (writes the payload to a file); py does this in scripts/.
    "exportDefinition",
    # exported on ts for tests/API; py keeps the _-prefixed twins private (accepted visibility asymmetry).
    "applyRegistryDiff",
    "buildEngineRequest",
    "probeManifest",
}


@pytest.mark.parametrize("module_pair", MIRROR_PAIRS.items(), ids=lambda p: p[0][0])
def test_mirror_pairs_exist_on_both_sides(module_pair: tuple[tuple[str, str], dict[str, str]]) -> None:
    (py_mod, ts_mod), pairs = module_pair
    py_names = _py_public(PY / py_mod)
    ts_names = _ts_exports(TS / ts_mod)
    missing_py = sorted(set(pairs) - py_names)
    missing_ts = sorted(set(pairs.values()) - ts_names)
    assert not missing_py, f"{py_mod} lost mirror names: {missing_py} (pairs: {pairs})"
    assert not missing_ts, f"{ts_mod} lost mirror names: {missing_ts} (pairs: {pairs})"


def test_no_unlisted_names_in_mirror_modules() -> None:
    """Drift alarm: a NEW public name in a mirror module must join the pairs
    table (or the documented allowlist) — never appear silently."""
    for (py_mod, ts_mod), pairs in MIRROR_PAIRS.items():
        leftover_py = _py_public(PY / py_mod) - set(pairs) - PY_ONLY
        leftover_ts = _ts_exports(TS / ts_mod) - set(pairs.values()) - TS_ONLY
        assert not leftover_py, f"{py_mod} has unlisted public names: {sorted(leftover_py)}"
        assert not leftover_ts, f"{ts_mod} has unlisted exports: {sorted(leftover_ts)}"


# ---------------------------------------------------------------------------
# (b) CLI surface: shared commands carry the same flags in both usage texts.
# ---------------------------------------------------------------------------
CLI_SURFACE: dict[str, list[str]] = {
    "register": ["--manifest", "--engine-url", "--invoke-url", "--name-suffix", "--json"],
    "probe": ["--manifest", "--engine-url", "--json"],
}


def _usage_lines(source: str, command: str) -> list[str]:
    """Quoted string literals that document `command`'s usage line."""
    return [lit for lit in re.findall(r'"([^"]*)"', source) if lit.lstrip().startswith(f"{command} ")]


@pytest.mark.parametrize("command", CLI_SURFACE, ids=str)
def test_cli_surface_matches(command: str) -> None:
    py_src = PY_MAIN.read_text()
    ts_src = (TS / "cli.ts").read_text()
    for src, runtime in ((py_src, "python"), (ts_src, "typescript")):
        lines = _usage_lines(src, command)
        assert lines, f"{runtime} usage text lost the `{command}` command line"
        joined = " ".join(lines)
        for flag in CLI_SURFACE[command]:
            assert flag in joined, f"{runtime} `{command}` usage lost flag {flag}"


# ---------------------------------------------------------------------------
# (c) Both packages expose a `ctk` bin (#239).
# ---------------------------------------------------------------------------
def test_ctk_bin_on_both_packages() -> None:
    pyproject = (REPO / "python" / "pyproject.toml").read_text()
    scripts = re.search(r"\[tool\.poetry\.scripts\](.*?)(?:\n\[|\Z)", pyproject, re.S)
    assert scripts and re.search(r'^ctk\s*=\s*"canvastekk_workflow_sdk\.__main__:main"', scripts.group(1), re.M), (
        "python package lost the ctk console script"
    )
    pkg = json.loads((REPO / "typescript" / "package.json").read_text())
    assert pkg.get("bin", {}).get("ctk") == "./dist/cli.js", "typescript package lost the ctk bin"


# ---------------------------------------------------------------------------
# (d) The ctk_ shape rule is identical across runtimes (DA-1948 mirror).
#     Arch-review finding: three copies of the constants (CDS + both SDK
#     runtimes) with no guard — this pins the SDK two equal.
# ---------------------------------------------------------------------------
def test_ctk_shape_literals_identical_across_runtimes() -> None:
    py_src = (PY / "registry.py").read_text()
    ts_src = (TS / "registry.ts").read_text()

    def const(src: str, name: str) -> str:
        m = re.search(rf'{name}(?::[^=\n]+)?\s*=\s*(\d+|"[^"]*")', src)
        assert m, f"constant {name} vanished from a runtime's registry module"
        return m.group(1)

    assert const(py_src, "CTK_PREFIX") == const(ts_src, "CTK_PREFIX")
    assert const(py_src, "CTK_BODY_LENGTH") == const(ts_src, "CTK_BODY_LENGTH") == "43"

    py_alpha = re.search(r'CTK_BODY_ALPHABET(?::[^=\n]+)?\s*=\s*frozenset\(\s*"([^"]+)"', py_src)
    ts_alpha = re.search(r"new Set\(\s*\n?\s*\"([^\"]+)\"", ts_src)
    assert py_alpha and ts_alpha, "alphabet literal vanished from a runtime's registry module"
    assert set(py_alpha.group(1)) == set(ts_alpha.group(1)), "ctk_ alphabets drifted between runtimes"
