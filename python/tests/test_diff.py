"""Tests for canvastekk-workflow-sdk manifest diff (DA-1955).

Pins the classification contract mirrored from the engine's
detect_breaking_changes (fastapi_app/services/workflow_definition_service.py):
new required input and removed output are the only breaking signals.

diff_manifests is pure stdlib (no SDK model imports needed here).
"""

from __future__ import annotations

import pytest

from canvastekk_workflow_sdk.diff import ManifestDiff, diff_manifests


def _manifest(**overrides: object) -> dict:
    """Build a minimal manifest dict with optional overrides."""
    base: dict = {
        "slug": "test-node",
        "version": "1.0.0",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "output_schema": {"type": "object", "properties": {}},
    }
    base.update(overrides)
    return base


class TestBreakingClassification:
    """Removed outputs and new required inputs are breaking."""

    def test_removed_output_is_breaking(self) -> None:
        old = _manifest(output_schema={"type": "object", "properties": {"result": {"type": "string"}}})
        new = _manifest(version="2.0.0", output_schema={"type": "object", "properties": {}})

        diff = diff_manifests(old, new)

        assert diff.breaking is True
        assert any("removed output" in entry and "result" in entry for entry in diff.breaking_changes)

    def test_new_required_input_is_breaking(self) -> None:
        old = _manifest(input_schema={"type": "object", "properties": {"msg": {"type": "string"}}, "required": []})
        new = _manifest(
            version="2.0.0",
            input_schema={
                "type": "object",
                "properties": {"msg": {"type": "string"}, "data": {"type": "string"}},
                "required": ["data"],
            },
        )

        diff = diff_manifests(old, new)

        assert diff.breaking is True
        assert any("new required input" in entry and "data" in entry for entry in diff.breaking_changes)

    def test_breaking_with_major_bump_has_no_version_error(self) -> None:
        old = _manifest(output_schema={"type": "object", "properties": {"result": {"type": "string"}}})
        new = _manifest(version="2.0.0", output_schema={"type": "object", "properties": {}})

        diff = diff_manifests(old, new)

        assert diff.breaking is True
        assert not any("MAJOR" in entry for entry in diff.errors)


class TestNonBreakingClassification:
    """Additive input/output and metadata changes are non-breaking."""

    def test_new_optional_input_is_not_breaking(self) -> None:
        old = _manifest(input_schema={"type": "object", "properties": {}, "required": []})
        new = _manifest(
            version="1.1.0",
            input_schema={"type": "object", "properties": {"opt": {"type": "string"}}, "required": []},
        )

        diff = diff_manifests(old, new)

        assert diff.breaking is False
        assert any("new optional input" in entry and "opt" in entry for entry in diff.non_breaking_changes)
        assert diff.breaking_changes == []

    def test_new_output_is_not_breaking(self) -> None:
        old = _manifest(output_schema={"type": "object", "properties": {}})
        new = _manifest(version="1.1.0", output_schema={"type": "object", "properties": {"extra": {"type": "string"}}})

        diff = diff_manifests(old, new)

        assert diff.breaking is False
        assert any("new output" in entry and "extra" in entry for entry in diff.non_breaking_changes)

    def test_metadata_only_change_is_not_breaking(self) -> None:
        old = _manifest(name="Old Title")
        new = _manifest(version="1.0.1", name="New Title")

        diff = diff_manifests(old, new)

        assert diff.breaking is False
        assert any("metadata" in entry and "name" in entry for entry in diff.non_breaking_changes)


class TestVersionRules:
    """Same-version drift and breaking-without-MAJOR are errors."""

    def test_same_version_with_change_is_error(self) -> None:
        old = _manifest(name="Old")
        new = _manifest(name="New")

        diff = diff_manifests(old, new)

        assert diff.breaking is False
        assert any("same version" in entry for entry in diff.errors)

    def test_same_version_identical_is_clean(self) -> None:
        old = _manifest()
        new = _manifest()

        diff = diff_manifests(old, new)

        assert diff.breaking is False
        assert diff.breaking_changes == []
        assert diff.non_breaking_changes == []
        assert diff.errors == []

    def test_breaking_with_minor_bump_is_error(self) -> None:
        old = _manifest(output_schema={"type": "object", "properties": {"result": {"type": "string"}}})
        new = _manifest(version="1.1.0", output_schema={"type": "object", "properties": {}})

        diff = diff_manifests(old, new)

        assert diff.breaking is True
        assert any("MAJOR version bump" in entry for entry in diff.errors)

    def test_version_bump_classification(self) -> None:
        assert diff_manifests(_manifest(), _manifest(version="2.0.0")).version_bump == "major"
        assert diff_manifests(_manifest(), _manifest(version="1.1.0")).version_bump == "minor"
        assert diff_manifests(_manifest(), _manifest(version="1.0.1")).version_bump == "patch"
        assert diff_manifests(_manifest(), _manifest()).version_bump is None

    def test_versions_recorded_on_result(self) -> None:
        diff = diff_manifests(_manifest(), _manifest(version="1.1.0"))

        assert diff.old_version == "1.0.0"
        assert diff.new_version == "1.1.0"


class TestErrorCases:
    """Malformed inputs surface as errors, not exceptions (where reasonable)."""

    def test_slug_mismatch_detected_from_registry_shaped_manifests(self) -> None:
        """Registry-shaped inputs (export_definition output) carry identity under "name"."""
        old = {"name": "old-node", "version": "1.0.0", "input_schema": {}, "output_schema": {}}
        new = {"name": "new-node", "version": "2.0.0", "input_schema": {}, "output_schema": {}}

        diff = diff_manifests(old, new)

        assert any("slug mismatch" in entry for entry in diff.errors)

    def test_name_mismatch_is_error(self) -> None:
        old = _manifest(slug="old-node")
        new = _manifest(slug="new-node", version="2.0.0")

        diff = diff_manifests(old, new)

        assert any("slug mismatch" in entry for entry in diff.errors)

    def test_missing_version_is_error(self) -> None:
        old = {"slug": "test-node", "input_schema": {}}
        new = _manifest(version="1.1.0")

        diff = diff_manifests(old, new)

        assert any("version" in entry for entry in diff.errors)

    def test_non_strict_version_is_error(self) -> None:
        old = _manifest(version="1.0")
        new = _manifest(version="1.1")

        diff = diff_manifests(old, new)

        assert any("MAJOR.MINOR.PATCH" in entry for entry in diff.errors)

    def test_non_dict_input_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            diff_manifests("not a dict", _manifest())  # type: ignore[arg-type]

    def test_non_dict_second_input_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            diff_manifests(_manifest(), ["not", "a", "dict"])  # type: ignore[arg-type]


class TestManifestDiffDefaults:
    """The result dataclass defaults support falsy construction."""

    def test_defaults(self) -> None:
        diff = ManifestDiff()

        assert diff.breaking is False
        assert diff.breaking_changes == []
        assert diff.non_breaking_changes == []
        assert diff.errors == []
        assert diff.old_version is None
        assert diff.new_version is None
        assert diff.version_bump is None


class TestVersionDowngradeAndParseGating:
    """DA-1955 review fixes: downgrade detection + parsed-version error gating."""

    def test_version_downgrade_is_error(self) -> None:
        old = {"slug": "n", "version": "2.0.0", "input_schema": {}}
        new = {"slug": "n", "version": "1.0.0", "input_schema": {}}
        diff = diff_manifests(old, new)

        assert diff.errors == ["version downgrade: '2.0.0' -> '1.0.0' (publish a higher semver)"]

    def test_unparsable_version_no_same_version_error(self) -> None:
        old = {"slug": "n", "version": "1.0", "input_schema": {}}
        new = {"slug": "n", "version": "1.0", "input_schema": {}, "name": "T"}
        diff = diff_manifests(old, new)

        assert len(diff.errors) == 1
        assert "MAJOR.MINOR.PATCH" in diff.errors[0]
        assert "same version" not in diff.errors[0]

    def test_missing_version_no_same_version_error(self) -> None:
        old = {"slug": "n", "input_schema": {}}
        new = {"slug": "n", "input_schema": {}, "name": "T"}
        diff = diff_manifests(old, new)

        assert diff.errors == ["both manifests must carry a 'version' field"]
