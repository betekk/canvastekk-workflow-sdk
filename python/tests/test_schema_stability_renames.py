"""Schema-stability rename normalization (ADR 0001, #271).

The CI schema-stability job diffs pydantic dumps by class name; ADR 0001's
renames would otherwise classify as breaking even though payload schemas are
structurally identical. This test pins the normalization: a base dump under
pre-rename names diffs clean against the current tree, and the guard's teeth
stay — a structural delta on a renamed model still classifies breaking.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = REPO / "python"


def _dump() -> dict:
    out = subprocess.run(
        [sys.executable, "scripts/check_schema_stability.py", "dump"],
        cwd=PY,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def _to_legacy_names(dump: dict) -> str:
    """Reverse-map the ADR 0001 renames — an old-world base dump."""
    text = json.dumps(dump)
    for new, old in {
        "WorkflowNodeManifestContract": "NodeContract",
        "WorkflowNodeContractCapabilities": "ContractCapabilities",
        "WorkflowNodeRetryConfig": "RetryConfig",
        "WorkflowNodeDeprecationInfo": "DeprecationInfo",
    }.items():
        text = text.replace(f'"{new}"', f'"{old}"').replace(
            f"#/$defs/{new}", f"#/$defs/{old}"
        )
    return text


def _diff(tmp_path: Path, pr: dict, base: dict | None = None) -> str:
    legacy_base = tmp_path / "base.json"
    pr_dump = tmp_path / "pr.json"
    legacy_base.write_text(_to_legacy_names(base if base is not None else pr))
    pr_dump.write_text(json.dumps(pr))
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_stability.py", "diff", str(legacy_base), str(pr_dump)],
        cwd=PY,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_renamed_models_diff_clean_against_legacy_base(tmp_path: Path) -> None:
    assert "BREAKING" not in _diff(tmp_path, _dump())


def test_structural_delta_on_renamed_model_still_breaks(tmp_path: Path) -> None:
    base = _dump()
    pr = _dump()
    # Remove a required field from a renamed model in the PR dump — the
    # normalization must NOT swallow a real structural change.
    pr["WorkflowNodeManifest"]["properties"].pop("slug")
    assert "BREAKING" in _diff(tmp_path, pr, base=base)
