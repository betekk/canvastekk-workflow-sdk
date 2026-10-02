"""Tests for WorkflowNodeManifest and RetryConfig models."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from canvastekk_workflow_sdk import (
    DeprecationInfo,
    RetryConfig,
    WorkflowNodeManifest,
    WorkflowNodeRole,
    WorkflowNodeStyles,
)
from canvastekk_workflow_sdk.definition import export_definition


class TestRetryConfig:
    """Tests for RetryConfig model."""

    def test_default_values(self) -> None:
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_attempts == 1
        assert config.initial_delay_ms == 1000
        assert config.backoff_multiplier == 2.0
        assert config.max_delay_ms == 30000

    def test_custom_values(self) -> None:
        """Test custom retry configuration."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay_ms=500,
            backoff_multiplier=1.5,
            max_delay_ms=10000,
        )
        assert config.max_attempts == 3
        assert config.initial_delay_ms == 500
        assert config.backoff_multiplier == 1.5
        assert config.max_delay_ms == 10000

    def test_validation_max_attempts_minimum(self) -> None:
        """Test that max_attempts must be at least 1."""
        with pytest.raises(ValueError):
            RetryConfig(max_attempts=0)

    def test_validation_backoff_multiplier_minimum(self) -> None:
        """Test that backoff_multiplier must be at least 1.0."""
        with pytest.raises(ValueError):
            RetryConfig(backoff_multiplier=0.5)


class TestWorkflowNodeRole:
    """Tests for WorkflowNodeRole enum."""

    def test_enum_values(self) -> None:
        assert WorkflowNodeRole.START.value == "start"
        assert WorkflowNodeRole.END.value == "end"
        assert WorkflowNodeRole.ERROR_GATE.value == "error_gate"
        assert WorkflowNodeRole.OPERATION.value == "operation"

    def test_default_role_is_operation(self) -> None:
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.role == WorkflowNodeRole.OPERATION

    def test_explicit_role(self) -> None:
        definition = WorkflowNodeManifest(
            slug="start",
            version="1.0.0",
            name="Start",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            role=WorkflowNodeRole.START,
        )
        assert definition.role == WorkflowNodeRole.START


class TestWorkflowNodeManifest:
    """Tests for WorkflowNodeManifest model."""

    def test_minimal_definition(self) -> None:
        """Test creating a minimal node definition."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Returns input unchanged",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.id == "echo-v1.0.0"
        assert definition.slug == "echo"
        assert definition.version == "1.0.0"
        assert definition.name == "Echo"
        assert definition.token_cost == 0.0
        assert definition.category == "utility"
        assert definition.timeout_seconds == 30
        assert definition.role == WorkflowNodeRole.OPERATION

    def test_full_definition(self) -> None:
        """Test creating a full node definition with all fields."""
        definition = WorkflowNodeManifest(
            slug="segmentation",
            version="2.0.0",
            name="Point Cloud Segmentation",
            description="Segments point cloud into semantic classes",
            input_schema={
                "type": "object",
                "properties": {
                    "pointcloud_path": {"type": "string"},
                },
                "required": ["pointcloud_path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "instances_path": {"type": "string"},
                },
            },
            token_cost=5.0,
            default_retry=RetryConfig(max_attempts=3),
            category="inference",
            timeout_seconds=300,
        )
        assert definition.token_cost == 5.0
        assert definition.default_retry.max_attempts == 3
        assert definition.category == "inference"
        assert definition.timeout_seconds == 300

    def test_to_dict(self) -> None:
        """Test converting definition to dictionary."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Returns input unchanged",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        data = definition.to_dict()
        assert isinstance(data, dict)
        assert data["id"] == "echo-v1.0.0"
        assert data["slug"] == "echo"
        assert "default_retry" in data

    def test_control_flow_node(self) -> None:
        """Test creating a node with explicit role."""
        definition = WorkflowNodeManifest(
            slug="if",
            version="1.0.0",
            name="IF Condition",
            description="Conditional branching",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            category="control-flow",
            role=WorkflowNodeRole.START,
            token_cost=0.0,
        )
        assert definition.role == WorkflowNodeRole.START
        assert definition.category == "control-flow"
        assert definition.token_cost == 0.0

    def test_file_input_fields_with_file(self) -> None:
        """Test file_input_fields returns fields with format: file."""
        definition = WorkflowNodeManifest(
            slug="upload",
            version="1.0.0",
            name="Upload Node",
            description="Accepts file uploads",
            input_schema={
                "type": "object",
                "properties": {
                    "point_cloud": {"type": "string", "format": "file", "description": "Point cloud file"},
                    "threshold": {"type": "number", "default": 0.5},
                    "mask": {"type": "string", "format": "file"},
                },
            },
            output_schema={"type": "object"},
        )
        assert sorted(definition.file_input_fields) == ["mask", "point_cloud"]

    def test_file_input_fields_no_file(self) -> None:
        """Test file_input_fields returns empty list when no file fields."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="No file inputs",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
            output_schema={"type": "object"},
        )
        assert definition.file_input_fields == []

    def test_file_input_fields_empty_schema(self) -> None:
        """Test file_input_fields with schema that has no properties."""
        definition = WorkflowNodeManifest(
            slug="empty",
            version="1.0.0",
            name="Empty",
            description="No properties",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.file_input_fields == []

    def test_has_file_inputs_true(self) -> None:
        """Test has_file_inputs returns True when file fields exist."""
        definition = WorkflowNodeManifest(
            slug="upload",
            version="1.0.0",
            name="Upload Node",
            description="Accepts file uploads",
            input_schema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "file"},
                },
            },
            output_schema={"type": "object"},
        )
        assert definition.has_file_inputs is True

    def test_has_file_inputs_false(self) -> None:
        """Test has_file_inputs returns False when no file fields."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="No file inputs",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            output_schema={"type": "object"},
        )
        assert definition.has_file_inputs is False

    def test_file_output_fields_with_file(self) -> None:
        """Test file_output_fields returns fields with format: file in output_schema."""
        definition = WorkflowNodeManifest(
            slug="segmentation",
            version="1.0.0",
            name="Segmentation",
            description="Produces file output",
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {
                    "result_path": {"type": "string", "format": "file"},
                    "summary": {"type": "string"},
                    "mask_path": {"type": "string", "format": "file"},
                },
            },
        )
        assert sorted(definition.file_output_fields) == ["mask_path", "result_path"]

    def test_file_output_fields_no_file(self) -> None:
        """Test file_output_fields returns empty list when no file output fields."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="No file outputs",
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        )
        assert definition.file_output_fields == []

    def test_file_output_fields_empty_schema(self) -> None:
        """Test file_output_fields with output_schema that has no properties."""
        definition = WorkflowNodeManifest(
            slug="empty",
            version="1.0.0",
            name="Empty",
            description="No properties in output",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.file_output_fields == []

    def test_file_input_fields_does_not_detect_binary(self) -> None:
        """Test that file_input_fields does NOT detect format: binary (breaking change)."""
        with pytest.raises(ValueError, match="format 'binary'"):
            WorkflowNodeManifest(
                slug="old",
                version="1.0.0",
                name="Old",
                description="Uses old binary format",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                    },
                },
                output_schema={"type": "object"},
            )

    def test_model_validator_rejects_binary_format(self) -> None:
        """Test that WorkflowNodeManifest rejects format: binary at definition time."""
        with pytest.raises(ValueError, match="no longer supported"):
            WorkflowNodeManifest(
                slug="bad",
                version="1.0.0",
                name="Bad",
                description="Uses binary",
                input_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "string", "format": "binary"},
                    },
                },
                output_schema={"type": "object"},
            )

    def test_model_validator_rejects_file_with_wrong_type(self) -> None:
        """Test that WorkflowNodeManifest rejects format: file with non-string type."""
        with pytest.raises(ValueError, match="must have type 'string'"):
            WorkflowNodeManifest(
                slug="bad",
                version="1.0.0",
                name="Bad",
                description="Wrong type",
                input_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "object", "format": "file"},
                    },
                },
                output_schema={"type": "object"},
            )

    def test_to_dict_contains_file_format(self) -> None:
        """Test that to_dict() preserves format: file in schemas."""
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "file"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string", "format": "file"},
                },
            },
        )
        data = definition.to_dict()
        assert data["input_schema"]["properties"]["file"]["format"] == "file"
        assert data["output_schema"]["properties"]["result"]["format"] == "file"


class TestExportDefinition:
    """Tests for export_definition function (Phase 3)."""

    def test_export_definition_creates_registry_compatible_json(self) -> None:
        """Test that export_definition creates registry-compatible JSON."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test Node",
            description="A test node",
            input_schema={
                "type": "object",
                "properties": {"input": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "properties": {"output": {"type": "string"}},
            },
            category="utility",
            timeout_seconds=60,
            token_cost=5.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            result_path = export_definition(definition, output_path)

            assert result_path == output_path
            assert output_path.exists()

            data = json.loads(output_path.read_text())
            assert data["name"] == "test"
            assert data["version"] == "1.0.0"
            assert data["label"] == "Test Node"
            assert data["description"] == "A test node"
            assert data["category"] == "utility"
            assert data["input_schema"] == definition.input_schema
            assert data["output_schema"] == definition.output_schema
            assert data["invoke_type"] == "http"
            assert "invoke_url" not in data
            assert data["token_cost"] == 5.0
            assert data["timeout_seconds"] == 60

    def test_export_definition_maps_title_to_label(self) -> None:
        """Test that title field is mapped to label."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="My Test Node",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)

            data = json.loads(output_path.read_text())
            assert "label" in data
            assert data["label"] == "My Test Node"
            assert "title" not in data

    def test_export_definition_maps_default_retry_to_retry(self) -> None:
        """Test that default_retry field is mapped to retry."""
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_ms=500,
            backoff_multiplier=1.5,
            max_delay_ms=10000,
        )
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            default_retry=retry_config,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)

            data = json.loads(output_path.read_text())
            assert "retry" in data
            assert data["retry"]["max_attempts"] == 3
            assert data["retry"]["initial_delay_ms"] == 500
            assert data["retry"]["backoff_multiplier"] == 1.5
            assert data["retry"]["max_delay_ms"] == 10000

    def test_export_definition_includes_all_required_fields(self) -> None:
        """Test that export_definition includes all required fields."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)

            data = json.loads(output_path.read_text())
            required_fields = [
                "name",
                "version",
                "label",
                "description",
                "category",
                "input_schema",
                "output_schema",
                "invoke_type",
                "token_cost",
                "timeout_seconds",
                "retry",
                "tags",
                "styles",
            ]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

    def test_export_definition_with_custom_invoke_type(self) -> None:
        """Test that custom invoke_type is included."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, invoke_type="lambda")

            data = json.loads(output_path.read_text())
            assert data["invoke_type"] == "lambda"

    def test_export_definition_with_invoke_url(self) -> None:
        """Test that invoke_url is included when provided."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, invoke_url="https://node.example.com")

            data = json.loads(output_path.read_text())
            assert data["invoke_url"] == "https://node.example.com"

    def test_export_definition_with_custom_tags(self) -> None:
        """Test that custom tags are included."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        tags = ["machine-learning", "segmentation", "point-cloud"]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, tags=tags)

            data = json.loads(output_path.read_text())
            assert data["tags"] == tags

    def test_export_definition_with_custom_styles(self) -> None:
        """Test that custom styles override definition.styles."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        custom_styles = {"icon": "Brain", "color": "emerald"}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, styles=custom_styles)

            data = json.loads(output_path.read_text())
            assert data["styles"] == custom_styles

    def test_export_definition_uses_definition_styles_when_not_overridden(self) -> None:
        """Test that definition.styles is used when not overridden."""
        styles = WorkflowNodeStyles(icon="Box", color="blue")
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            styles=styles,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)

            data = json.loads(output_path.read_text())
            assert data["styles"] == {"icon": "Box", "color": "blue"}

    def test_export_definition_with_constraints(self) -> None:
        """Test that constraints are included when provided."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        constraints = {"gpu_required": True, "memory_gb": 8}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, constraints=constraints)

            data = json.loads(output_path.read_text())
            assert data["constraints"]["gpu_required"] is True
            assert data["constraints"]["memory_gb"] == 8
            # DA-3359: the stamp always rides along
            assert data["constraints"].get("sdk_version") == definition.sdk_version

    def test_export_definition_with_node_status(self) -> None:
        """Test that node_status is included."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path, node_status="inactive")

            data = json.loads(output_path.read_text())
            assert data["node_status"] == "inactive"

    def test_export_definition_creates_parent_directories(self) -> None:
        """Test that export_definition creates parent directories."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "test.json"
            export_definition(definition, output_path)

            assert output_path.exists()
            data = json.loads(output_path.read_text())
            assert data["name"] == "test"

    def test_export_definition_writes_formatted_json(self) -> None:
        """Test that export_definition writes formatted JSON with newlines."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)

            content = output_path.read_text()
            assert content.endswith("\n")
            assert "\n" in content


class TestValidateFileInput:
    """Tests for WorkflowNodeManifest.validate_file_input()."""

    def _make_definition(self, **schema_overrides):
        props = {
            "file": {
                "type": "string",
                "format": "file",
                "x-accept": [".txt", ".csv"],
                "x-maxSizeBytes": 1000,
            },
        }
        props.update(schema_overrides)
        return WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object", "properties": props},
            output_schema={"type": "object"},
        )

    def test_valid_file_passes(self, tmp_path) -> None:
        definition = self._make_definition()
        f = tmp_path / "data.txt"
        f.write_text("hello")
        definition.validate_file_input("file", f)

    def test_rejects_wrong_extension(self, tmp_path) -> None:
        definition = self._make_definition()
        f = tmp_path / "data.json"
        f.write_text("{}")
        with pytest.raises(Exception, match="not allowed"):
            definition.validate_file_input("file", f)

    def test_extensionless_file_passes(self, tmp_path) -> None:
        # DA-3429: extension-less artifacts (e.g. DA-3339 emission keys named
        # by field, Content-Disposition filenames without an extension) must
        # not hard-fail the x-accept check — the handler's own content
        # handling stays responsible for correctness.
        definition = self._make_definition()
        f = tmp_path / "pcd_path_buffer"
        f.write_text("binary-ish content")
        definition.validate_file_input("file", f)

    def test_rejects_oversized_file(self, tmp_path) -> None:
        definition = self._make_definition()
        f = tmp_path / "data.txt"
        f.write_bytes(b"x" * 2000)
        with pytest.raises(Exception, match="exceeds maximum"):
            definition.validate_file_input("file", f)

    def test_passes_when_no_extensions_defined(self, tmp_path) -> None:
        props = {
            "file": {
                "type": "string",
                "format": "file",
            },
        }
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object", "properties": props},
            output_schema={"type": "object"},
        )
        f = tmp_path / "data.xyz"
        f.write_text("anything")
        definition.validate_file_input("file", f)


class TestSlugValidation:
    def test_valid_slugs(self) -> None:
        for slug in ["echo", "file-loader", "point-cloud-segment", "a1"]:
            WorkflowNodeManifest(
                slug=slug,
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_single_char_slug(self) -> None:
        WorkflowNodeManifest(
            slug="a",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="Echo",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="has space",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_underscores(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="under_score",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_leading_hyphen(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="-leading",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_trailing_hyphen(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="trailing-",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_numeric_start(self) -> None:
        with pytest.raises(ValueError, match="lowercase slug"):
            WorkflowNodeManifest(
                slug="1numeric",
                version="1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )


class TestSemverValidation:
    def test_valid_versions(self) -> None:
        for v in ["1.0.0", "0.1.0", "10.20.30"]:
            WorkflowNodeManifest(
                slug="test",
                version=v,
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_two_part(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            WorkflowNodeManifest(
                slug="test",
                version="1.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_v_prefix(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            WorkflowNodeManifest(
                slug="test",
                version="v1.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_prerelease(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            WorkflowNodeManifest(
                slug="test",
                version="1.0.0-alpha",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_non_numeric(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            WorkflowNodeManifest(
                slug="test",
                version="abc",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    def test_rejects_leading_zeros(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            WorkflowNodeManifest(
                slug="test",
                version="01.0.0",
                name="Test",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )


class TestIdAutoDerivation:
    def test_id_auto_derived(self) -> None:
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.id == "echo-v1.0.0"

    def test_id_in_to_dict(self) -> None:
        definition = WorkflowNodeManifest(
            slug="echo",
            version="1.2.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert definition.to_dict()["id"] == "echo-v1.2.0"


class TestExportDefinitionNoId:
    def test_export_does_not_include_id(self) -> None:
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)
            data = json.loads(output_path.read_text())
            assert "id" not in data
            assert data["name"] == "test"
            assert data["version"] == "1.0.0"

    def test_export_omits_deprecation_when_none(self) -> None:
        """DA-1582 hardening: export_definition routes through build_registry_payload (CR3)."""
        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)
            data = json.loads(output_path.read_text())
            assert "deprecation" not in data

    def test_export_includes_deprecation_when_set(self) -> None:
        """DA-1582 hardening: export_definition writes the deprecation field (CR3)."""
        from datetime import date

        definition = WorkflowNodeManifest(
            slug="test",
            version="1.0.0",
            name="Test",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            deprecation=DeprecationInfo(
                deprecated_at=date(2026, 8, 1),
                sunset_date=date(2027, 1, 1),
                replacement_slug="test-v2",
                migration_url="https://example.com/migrate",
                notice="use test-v2",
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.json"
            export_definition(definition, output_path)
            data = json.loads(output_path.read_text())
            assert data["deprecation"] == {
                "deprecated_at": "2026-08-01",
                "sunset_date": "2027-01-01",
                "replacement_slug": "test-v2",
                "migration_url": "https://example.com/migrate",
                "notice": "use test-v2",
            }


class TestDeprecationInfo:
    """Tests for DeprecationInfo model (DA-1582)."""

    def test_notice_is_required(self) -> None:
        """notice is the only required field."""
        with pytest.raises(ValueError):
            DeprecationInfo()  # type: ignore[call-arg]

    def test_optional_fields_default_none(self) -> None:
        info = DeprecationInfo(notice="use echo-v2")
        assert info.deprecated_at is None
        assert info.sunset_date is None
        assert info.replacement_slug is None
        assert info.migration_url is None
        assert info.notice == "use echo-v2"

    def test_full_population(self) -> None:
        from datetime import date

        info = DeprecationInfo(
            deprecated_at=date(2026, 8, 1),
            sunset_date=date(2027, 1, 1),
            replacement_slug="echo-v2",
            migration_url="https://example.com/migrate",
            notice="use echo-v2",
        )
        assert info.deprecated_at == date(2026, 8, 1)
        assert info.sunset_date == date(2027, 1, 1)
        assert info.replacement_slug == "echo-v2"
        assert info.migration_url == "https://example.com/migrate"


class TestManifestDeprecationSerialization:
    """DA-1582: deprecation is omitted when None on every serialization path."""

    @staticmethod
    def _minimal() -> WorkflowNodeManifest:
        return WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

    def test_deprecation_defaults_to_none(self) -> None:
        assert self._minimal().deprecation is None

    def test_to_dict_omits_deprecation_when_none(self) -> None:
        assert "deprecation" not in self._minimal().to_dict()

    def test_model_dump_omits_deprecation_when_none(self) -> None:
        assert "deprecation" not in self._minimal().model_dump(mode="json")

    def test_to_dict_includes_deprecation_when_set(self) -> None:
        from datetime import date

        manifest = self._minimal().model_copy(
            update={
                "deprecation": DeprecationInfo(
                    deprecated_at=date(2026, 8, 1),
                    sunset_date=date(2027, 1, 1),
                    replacement_slug="echo-v2",
                    migration_url="https://example.com/migrate",
                    notice="use echo-v2",
                )
            }
        )
        dep = manifest.to_dict()["deprecation"]
        assert dep == {
            "deprecated_at": "2026-08-01",
            "sunset_date": "2027-01-01",
            "replacement_slug": "echo-v2",
            "migration_url": "https://example.com/migrate",
            "notice": "use echo-v2",
        }

    def test_model_dump_includes_deprecation_when_set(self) -> None:
        manifest = self._minimal().model_copy(update={"deprecation": DeprecationInfo(notice="retire soon")})
        assert manifest.model_dump(mode="json")["deprecation"] == {
            "deprecated_at": None,
            "sunset_date": None,
            "replacement_slug": None,
            "migration_url": None,
            "notice": "retire soon",
        }

    def test_model_dump_json_roundtrips_deprecation(self) -> None:
        """DA-1582 hardening: model_dump_json round-trips a deprecated manifest."""
        import json
        from datetime import date

        manifest = self._minimal().model_copy(
            update={
                "deprecation": DeprecationInfo(
                    deprecated_at=date(2026, 8, 1),
                    sunset_date=date(2027, 1, 1),
                    replacement_slug="echo-v2",
                    migration_url="https://example.com/migrate",
                    notice="use echo-v2",
                )
            }
        )
        dumped = json.loads(manifest.model_dump_json())
        assert dumped["deprecation"] == {
            "deprecated_at": "2026-08-01",
            "sunset_date": "2027-01-01",
            "replacement_slug": "echo-v2",
            "migration_url": "https://example.com/migrate",
            "notice": "use echo-v2",
        }

    def test_nested_dates_serialize_as_iso_strings(self) -> None:
        """DA-1582 hardening: dates serialize as ISO strings on the json path (CR2/PR2)."""
        from datetime import date

        manifest = self._minimal().model_copy(
            update={"deprecation": DeprecationInfo(sunset_date=date(2027, 1, 1), notice="x")}
        )
        sunset = manifest.to_dict()["deprecation"]["sunset_date"]
        assert sunset == "2027-01-01"
        assert isinstance(sunset, str)

    def test_model_json_schema_lists_deprecation_as_optional(self) -> None:
        """DA-1582 hardening: stability-gate invariant — schema lists deprecation, not required (CR4)."""
        schema = WorkflowNodeManifest.model_json_schema()
        assert "deprecation" in schema["properties"]
        assert "deprecation" not in schema.get("required", [])


class TestSdkCompatAndDocsFields:
    """DA-1955: optional compat-range and docs fields with drop-when-none serialization."""

    def _minimal(self) -> WorkflowNodeManifest:
        return WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Returns input unchanged",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

    def test_unset_fields_omitted_from_to_dict(self) -> None:
        """Drop-when-none: opting-out nodes serialize byte-identically (no new keys)."""
        data = self._minimal().to_dict()
        for key in ("minimum_sdk_version", "maximum_sdk_version", "docs_url", "changelog_url"):
            assert key not in data

    def test_set_fields_round_trip(self) -> None:
        """Set fields are present and valid after serialization."""
        manifest = self._minimal().model_copy(
            update={
                "minimum_sdk_version": "0.22.0",
                "maximum_sdk_version": "1.0.0",
                "docs_url": "https://example.com/docs",
                "changelog_url": "https://example.com/changelog",
            }
        )
        data = manifest.to_dict()
        assert data["minimum_sdk_version"] == "0.22.0"
        assert data["maximum_sdk_version"] == "1.0.0"
        assert data["docs_url"] == "https://example.com/docs"
        assert data["changelog_url"] == "https://example.com/changelog"

    def test_invalid_sdk_version_rejected(self) -> None:
        """Compat fields must be strict MAJOR.MINOR.PATCH semver."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            WorkflowNodeManifest(
                slug="echo",
                version="1.0.0",
                name="Echo",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                minimum_sdk_version="0.22",
            )

    def test_invalid_sdk_version_prerelease_rejected(self) -> None:
        """Pre-release tags are rejected, matching the version field's strictness."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            WorkflowNodeManifest(
                slug="echo",
                version="1.0.0",
                name="Echo",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                maximum_sdk_version="1.0.0-rc1",
            )

    def test_non_http_url_rejected(self) -> None:
        """docs_url/changelog_url must be http(s)."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            WorkflowNodeManifest(
                slug="echo",
                version="1.0.0",
                name="Echo",
                description="Test",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                docs_url="ftp://example.com/docs",
            )

    def test_fields_optional_in_json_schema(self) -> None:
        """Schema stability gate: new fields listed as optional, never required."""
        schema = WorkflowNodeManifest.model_json_schema()
        for key in ("minimum_sdk_version", "maximum_sdk_version", "docs_url", "changelog_url"):
            assert key in schema["properties"]
            assert key not in schema.get("required", [])


class TestVocabularyCompatibility:
    """DA-2627: legacy construction vocabulary map — determinism rules.

    The manifest identity field is ``slug`` and the display field is ``name``.
    Compatibility is resolved at construction only; the wire never carries the
    legacy ``title`` key or alias identity keys. These tests pin the exact
    trigger rules so a refactor cannot silently loosen them.
    """

    def _kwargs(self, **overrides: object) -> dict:
        base: dict = {
            "version": "1.0.0",
            "description": "d",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }
        base.update(overrides)
        return base

    def test_legacy_name_title_maps_with_warning(self) -> None:
        """Legacy map fires ONLY on slug-absent + name + title (all three conditions)."""
        with pytest.warns(DeprecationWarning, match="slug=<id> and name=<display>"):
            manifest = WorkflowNodeManifest(name="echo", title="Echo", **self._kwargs())

        assert manifest.slug == "echo"
        assert manifest.name == "Echo"
        data = manifest.to_dict()
        assert data["slug"] == "echo"
        assert data["name"] == "Echo"
        assert "title" not in data

    def test_name_only_without_title_is_ambiguous_error(self) -> None:
        """No silent `slug ?? name` fallback: name alone is ambiguous in both vocabularies."""
        with pytest.raises(ValidationError, match="ambiguous"):
            WorkflowNodeManifest(name="echo", **self._kwargs())

    def test_slug_without_display_name_errors(self) -> None:
        """Display name is required in the new vocabulary."""
        with pytest.raises(ValidationError, match="name"):
            WorkflowNodeManifest(slug="echo", **self._kwargs())

    def test_slug_with_title_ignores_title_with_warning(self) -> None:
        """Mixed slug+title: display comes from name=; title ignored with a warning."""
        with pytest.warns(DeprecationWarning, match="title is ignored"):
            manifest = WorkflowNodeManifest(slug="echo", name="Echo", title="Stale", **self._kwargs())

        assert manifest.name == "Echo"
        assert "title" not in manifest.to_dict()

    def test_wire_has_no_alias_identity_keys(self) -> None:
        """Wire output carries the four standard fields + contract fields + slug-derived id."""
        manifest = WorkflowNodeManifest(slug="echo", name="Echo", **self._kwargs())
        data = manifest.to_dict()

        assert data["id"] == "echo-v1.0.0"
        assert data["slug"] == "echo"
        assert data["name"] == "Echo"
        assert data["description"] == "d"
        assert data["version"] == "1.0.0"
        for absent in ("title", "node_name", "node_version"):
            assert absent not in data


class TestStampedSdkVersion:
    """DA-3359: sdk_version is auto-stamped and read-only."""

    def _manifest(self) -> WorkflowNodeManifest:
        return WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

    def test_auto_filled_from_installed_sdk(self) -> None:
        from canvastekk_workflow_sdk import __version__

        assert self._manifest().sdk_version == __version__

    def test_constructor_kwarg_cannot_override(self) -> None:
        """DA-3359 (init=False semantics): a caller-supplied sdk_version is
        dropped — served manifests legitimately carry the key (DA-2887) and
        must load — the stamp always reflects the INSTALLED SDK."""
        m = WorkflowNodeManifest(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            sdk_version="9.9.9",
        )
        assert m.sdk_version != "9.9.9"

    def test_assignment_rejected(self) -> None:
        m = self._manifest()
        with pytest.raises((AttributeError, TypeError, ValueError)):
            m.sdk_version = "9.9.9"  # type: ignore[assignment]
        assert m.sdk_version != "9.9.9"

    def test_dump_includes_stamp(self) -> None:
        dump = self._manifest().model_dump()
        assert dump["sdk_version"]  # non-empty stamp present in serialization
