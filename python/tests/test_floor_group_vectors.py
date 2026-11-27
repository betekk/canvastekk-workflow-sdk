"""Published cross-renderer floor-grouping vectors for result body 2.2.0."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

CANONICAL = (
    Path(__file__).parents[2]
    / "schemas"
    / "result-body"
    / "model_check.check"
    / "vectors"
    / "floor-groups.json"
)
EXPECTED_CASES = [
    "single_floor_mixed_heights",
    "two_floors_same_check",
    "degenerate_storeys_floor_surface_fallback",
    "unplaced_row_and_usable_z_fallback",
    "cross_floor_path",
]


def _packaged_vectors() -> dict:
    root = resources.files("canvastekk_workflow_sdk").joinpath(
        "data", "schemas", "result-body", "model_check.check", "vectors", "floor-groups.json"
    )
    return json.loads(root.read_text(encoding="utf-8"))


def test_packaged_vectors_match_canonical_and_cover_required_cases() -> None:
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    packaged = _packaged_vectors()
    assert packaged == canonical
    assert packaged["fallback_gap_mm"] == 1500
    assert [case["name"] for case in packaged["cases"]] == EXPECTED_CASES
