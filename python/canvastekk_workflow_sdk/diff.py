"""Breaking-change classification for workflow node manifests.

Compares two manifest dictionaries (as exported by ``export_definition`` or the
``/manifest`` endpoint) and classifies the differences using the same rules the
CanvasTEKK Workflow Engine applies at registration time:

- a newly **required** input property is breaking;
- a **removed** output property is breaking;
- anything else (new optional input, new output, metadata changes) is
  non-breaking.

The classifier intentionally mirrors the engine's ``detect_breaking_changes``
implementation (``fastapi_app/services/workflow_definition_service.py``) signal
for signal and deliberately does not resolve ``allOf``/nested schema tricks —
keeping the two implementations drift-free matters more than cleverness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VERSION_BUMPS = ("major", "minor", "patch")

_SCHEMA_KEYS = ("input_schema", "output_schema")
_HANDLED_KEYS = _SCHEMA_KEYS + ("slug", "version", "id")


def _version_tuple(version: str) -> tuple[int, ...]:
    """Split a strict ``MAJOR.MINOR.PATCH`` string into an int tuple.

    Args:
        version: The semver string to parse.

    Returns:
        A tuple of three ints.

    Raises:
        ValueError: If the string is not strict ``X.Y.Z``.
    """
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(version)
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def _classify_bump(old_version: str, new_version: str) -> str | None:
    """Classify the version bump between two versions.

    Args:
        old_version: The previous version string.
        new_version: The next version string.

    Returns:
        ``"major"``, ``"minor"``, ``"patch"`` or ``None`` when identical.
    """
    old_t = _version_tuple(old_version)
    new_t = _version_tuple(new_version)
    if new_t == old_t:
        return None
    if new_t[0] != old_t[0]:
        return "major"
    if new_t[1] != old_t[1]:
        return "minor"
    return "patch"


def _schema_block(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    block = manifest.get(key)
    return block if isinstance(block, dict) else {}


@dataclass
class ManifestDiff:
    """Result of comparing two manifest dictionaries.

    Attributes:
        breaking: ``True`` when at least one breaking change was detected.
        breaking_changes: Human-readable breaking change descriptions.
        non_breaking_changes: Human-readable non-breaking change descriptions.
        errors: Conditions that make the diff itself invalid (name mismatch,
            same-version drift, breaking change without a MAJOR bump, missing
            or unparsable versions).
        old_version: The ``version`` field of the old manifest, if present.
        new_version: The ``version`` field of the new manifest, if present.
        version_bump: ``"major"``, ``"minor"``, ``"patch"`` or ``None``.
    """

    breaking: bool = False
    breaking_changes: list[str] = field(default_factory=list)
    non_breaking_changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    old_version: str | None = None
    new_version: str | None = None
    version_bump: str | None = None


def diff_manifests(old: dict[str, Any], new: dict[str, Any]) -> ManifestDiff:
    """Classify the differences between two manifest dictionaries.

    Args:
        old: The previous manifest dictionary.
        new: The next manifest dictionary.

    Returns:
        A :class:`ManifestDiff` describing breaking changes, non-breaking
        changes and error conditions.

    Raises:
        TypeError: If either argument is not a dictionary.
    """
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise TypeError("diff_manifests expects two manifest dictionaries")

    diff = ManifestDiff()
    diff.old_version = old.get("version")
    diff.new_version = new.get("version")

    old_slug = old.get("slug", old.get("name"))
    new_slug = new.get("slug", new.get("name"))
    if old_slug and new_slug and old_slug != new_slug:
        diff.errors.append(f"slug mismatch: '{old_slug}' -> '{new_slug}' (publish a new node, not a new version)")

    bump: str | None = None
    versions_parsed = False
    if diff.old_version is None or diff.new_version is None:
        diff.errors.append("both manifests must carry a 'version' field")
    else:
        try:
            bump = _classify_bump(diff.old_version, diff.new_version)
            diff.version_bump = bump
            versions_parsed = True
        except ValueError:
            diff.errors.append(
                f"versions must be strict MAJOR.MINOR.PATCH (got '{diff.old_version}' -> '{diff.new_version}')"
            )
        else:
            if _version_tuple(str(diff.old_version)) > _version_tuple(str(diff.new_version)):
                diff.errors.append(
                    f"version downgrade: '{diff.old_version}' -> '{diff.new_version}' (publish a higher semver)"
                )

    old_required = set(_schema_block(old, "input_schema").get("required") or [])
    new_required = set(_schema_block(new, "input_schema").get("required") or [])
    new_mandatory = sorted(new_required - old_required)
    for prop in new_mandatory:
        diff.breaking_changes.append(f"new required input '{prop}'")

    old_props = set(_schema_block(old, "input_schema").get("properties") or {})
    new_props = set(_schema_block(new, "input_schema").get("properties") or {})
    for prop in sorted(new_props - old_props - set(new_mandatory)):
        diff.non_breaking_changes.append(f"new optional input '{prop}'")

    old_out = set(_schema_block(old, "output_schema").get("properties") or {})
    new_out = set(_schema_block(new, "output_schema").get("properties") or {})
    for prop in sorted(old_out - new_out):
        diff.breaking_changes.append(f"removed output '{prop}'")
    for prop in sorted(new_out - old_out):
        diff.non_breaking_changes.append(f"new output '{prop}'")

    metadata_keys = sorted({k for k in old if k not in _HANDLED_KEYS} | {k for k in new if k not in _HANDLED_KEYS})
    for key in metadata_keys:
        if old.get(key) != new.get(key):
            diff.non_breaking_changes.append(f"metadata '{key}' changed")

    diff.breaking = bool(diff.breaking_changes)

    if versions_parsed and bump is None and (diff.breaking_changes or diff.non_breaking_changes):
        diff.errors.append(f"same version '{diff.old_version}' but the manifest changed; publish a higher semver")
    if diff.breaking and bump != "major":
        diff.errors.append(
            f"breaking changes require a MAJOR version bump (got '{diff.old_version}' -> '{diff.new_version}')"
        )

    return diff
