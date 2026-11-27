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


def _number(value: object) -> float | int | None:
    return value if type(value) in (int, float) else None


def _paths(measurement: dict) -> list[dict]:
    representation = measurement.get("viewer_representation") or {}
    return [
        primitive
        for primitive in representation.get("primitives") or []
        if primitive.get("kind") == "path_polyline"
        and len(primitive.get("geometry", {}).get("points_model_mm") or []) >= 2
    ]


def _anchor(measurement: dict) -> float | int | None:
    explicit = _number((measurement.get("spatial_context") or {}).get("anchor_z_mm"))
    if explicit is not None:
        return explicit
    primitives = (measurement.get("viewer_representation") or {}).get("primitives") or []
    z_values = [
        _number(point[2])
        for primitive in primitives
        for point in primitive.get("geometry", {}).get("points_model_mm") or []
    ]
    usable = [value for value in z_values if value is not None]
    return min(usable) if usable else None


def _number_text(value: float | int) -> str:
    return f"{value:.12g}"


def _clip_path(points: list[list[float | int]], low: float | int, high: float | int) -> list[list[float | int]]:
    clipped: list[list[float | int]] = []

    def add(point: list[float | int]) -> None:
        if not clipped or point != clipped[-1]:
            clipped.append(point)

    for first, second in zip(points, points[1:], strict=False):
        z0, z1 = first[2], second[2]
        if z0 == z1:
            if low <= z0 <= high:
                add(first)
                add(second)
            continue
        enter, leave = (low - z0) / (z1 - z0), (high - z0) / (z1 - z0)
        start, end = max(0.0, min(enter, leave)), min(1.0, max(enter, leave))
        if start > end:
            continue
        for ratio in ((start, end) if start != end else (start,)):
            add([round(value + (other - value) * ratio, 9) for value, other in zip(first, second, strict=True)])
    return clipped


def _reference_groups(case: dict, fallback_gap_mm: int) -> dict:
    storeys = sorted(case["spatial_reference"]["storeys"], key=lambda storey: storey["elevation_mm"])
    by_ref = {storey["ref"]: storey for storey in storeys}
    measurements = case["measurements"]
    degenerate = len({storey["elevation_mm"] for storey in storeys}) <= 1
    groups: dict[str, dict] = {}
    homes: dict[str, str] = {}
    unplaced: list[str] = []

    def put(key: str, storey: dict | None, elevation: float | int, subject: str) -> None:
        if key not in groups:
            suffix = _number_text(elevation)
            groups[key] = {
                "key": key,
                "storey_ref": storey["ref"] if storey else None,
                "name": storey["name"] if storey else f"Floor {suffix} mm",
                "elevation_mm": elevation,
                "subject_ids": [],
            }
        groups[key]["subject_ids"].append(subject)
        homes[subject] = key

    if degenerate:
        placed = []
        for measurement in measurements:
            surface = _number((measurement.get("spatial_context") or {}).get("floor_surface", {}).get("elevation_mm"))
            if surface is None:
                unplaced.append(measurement["subject_id"])
            else:
                placed.append((surface, measurement["subject_id"]))
        previous = None
        for elevation, subject in sorted(placed, key=lambda entry: entry[0]):
            if previous is None or elevation - previous > fallback_gap_mm:
                key = f"floor:{_number_text(elevation)}"
            put(key, None, elevation if key not in groups else groups[key]["elevation_mm"], subject)
            previous = elevation
    else:
        for measurement in measurements:
            subject = measurement["subject_id"]
            context = measurement.get("spatial_context") or {}
            anchor = _anchor(measurement)
            ref = (context.get("storey_below") or {}).get("ref")
            storey = by_ref.get(ref)
            if storey is None and anchor is not None:
                below = [entry for entry in storeys if entry["elevation_mm"] <= anchor]
                storey = below[-1] if below else None
            if storey is None:
                unplaced.append(subject)
                continue
            surface = _number((context.get("floor_surface") or {}).get("elevation_mm"))
            put(f"storey:{storey['ref']}", storey, surface if surface is not None else storey["elevation_mm"], subject)

    clips = []
    if not degenerate:
        for measurement in measurements:
            home = homes.get(measurement["subject_id"])
            if home is None:
                continue
            home_storey = by_ref[home.removeprefix("storey:")]
            for path in _paths(measurement):
                points = path["geometry"]["points_model_mm"]
                path_clips = []
                for index, storey in enumerate(storeys):
                    low = storey["elevation_mm"]
                    high = storeys[index + 1]["elevation_mm"] if index + 1 < len(storeys) else max(
                        low, max(point[2] for point in points)
                    )
                    clipped = _clip_path(points, low, high)
                    if len(clipped) >= 2:
                        path_clips.append((storey, clipped))
                if len(path_clips) < 2:
                    continue
                for storey, clipped in path_clips:
                    clips.append({
                        "group_key": f"storey:{storey['ref']}",
                        "primitive_id": path["primitive_id"],
                        "points_model_mm": clipped,
                        "continuation_label": None if storey["ref"] == home_storey["ref"] else (
                            f"Continues from {home_storey['name']}"
                        ),
                    })
    return {"groups": list(groups.values()), "unplaced_subject_ids": unplaced, "clips": clips}


def test_packaged_vectors_match_canonical_and_cover_required_cases() -> None:
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    packaged = _packaged_vectors()
    assert packaged == canonical
    assert packaged["fallback_gap_mm"] == 1500
    assert [case["name"] for case in packaged["cases"]] == EXPECTED_CASES


def test_python_reference_grouping_passes_every_published_vector() -> None:
    vectors = _packaged_vectors()
    for case in vectors["cases"]:
        assert _reference_groups(case, vectors["fallback_gap_mm"]) == case["expected"], case["name"]
