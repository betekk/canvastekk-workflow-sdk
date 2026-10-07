"""Tests for canvastekk-workflow-sdk CLI.

Uses subprocess.run to invoke the CLI since it calls sys.exit().

IMPORTANT: Do NOT import canvastekk_workflow_sdk modules directly in the test
module scope — the model_validator will reject format:"binary". Only use
subprocess.run.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYTHON_BIN = Path(sys.executable)
REPO_PYTHON_DIR = Path(__file__).resolve().parents[1]


def _cli_env() -> dict[str, str]:
    """Env that forces the CLI subprocess to import THIS repo's SDK code."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    repo_dir = str(REPO_PYTHON_DIR)
    env["PYTHONPATH"] = f"{repo_dir}{os.pathsep}{existing}" if existing else repo_dir
    return env


def test_validate_valid_definition():
    """Test validating a valid WorkflowNodeManifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary Python file with a valid WorkflowNodeManifest
        test_file = Path(tmpdir) / "test_node.py"
        test_file.write_text("""
from canvastekk_workflow_sdk import WorkflowNodeManifest

definition = WorkflowNodeManifest(
    name="test-node",
    version="1.0.0",
    title="Test Node",
    description="A test node",
    input_schema={"type": "object", "properties": {"input": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
)
""")

        # Run the CLI validate command
        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate", "test_node:definition"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        assert "PASS: Manifest is valid" in result.stdout


def test_validate_with_json_flag():
    """Test validating with --json flag returns valid JSON with valid: true."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary Python file with a valid WorkflowNodeManifest
        test_file = Path(tmpdir) / "test_node.py"
        test_file.write_text("""
from canvastekk_workflow_sdk import WorkflowNodeManifest

definition = WorkflowNodeManifest(
    name="test-node",
    version="1.0.0",
    title="Test Node",
    description="A test node",
    input_schema={"type": "object", "properties": {"input": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
)
""")

        # Run the CLI validate command with --json flag
        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate", "test_node:definition", "--json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )

        # Parse the JSON output
        output = json.loads(result.stdout)
        assert output["valid"] is True, f"Expected valid: true, got {output}"


def test_validate_invalid_path_format():
    """Test validating with invalid path format (missing colon) fails with exit 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary Python file with a valid WorkflowNodeManifest
        test_file = Path(tmpdir) / "test_node.py"
        test_file.write_text("""
from canvastekk_workflow_sdk import WorkflowNodeManifest

definition = WorkflowNodeManifest(
    name="test-node",
    version="1.0.0",
    title="Test Node",
    description="A test node",
    input_schema={"type": "object", "properties": {"input": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
)
""")

        # Run the CLI validate command with invalid path (missing colon)
        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate", "test_node-definition"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, (
            f"Expected exit 1, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        assert "Invalid path" in result.stderr or "Invalid path" in result.stdout


def test_validate_unknown_command():
    """Test unknown command fails with exit 1."""
    result = subprocess.run(
        [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "foo"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"Expected exit 1, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
    )
    assert "Unknown command" in result.stderr


def test_validate_missing_module_path():
    """Test validate command without module path fails with exit 1."""
    result = subprocess.run(
        [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"Expected exit 1, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
    )
    assert "module path required" in result.stderr


def test_version_flag():
    """Test --version flag shows SDK version."""
    result = subprocess.run(
        [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "--version"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
    )
    assert "canvastekk-workflow-sdk" in result.stdout


def test_help_flag():
    """Test --help flag shows usage and exits with 0."""
    result = subprocess.run(
        [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
    )
    assert "Usage:" in result.stdout
    assert "validate" in result.stdout
    assert "--json" in result.stdout
    assert "--version" in result.stdout
    assert "--help" in result.stdout


def _write_manifest(directory: str, filename: str, manifest: dict) -> Path:
    """Write a manifest dict to a JSON file and return its path."""
    path = Path(directory) / filename
    path.write_text(json.dumps(manifest))
    return path


_BASE_MANIFEST = {
    "name": "test-node",
    "version": "1.0.0",
    "input_schema": {"type": "object", "properties": {}, "required": []},
    "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
}


def test_diff_clean_change_exit_0():
    """Test diff with a non-breaking change exits 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = _write_manifest(tmpdir, "old.json", _BASE_MANIFEST)
        new_file = _write_manifest(
            tmpdir,
            "new.json",
            {
                **_BASE_MANIFEST,
                "version": "1.1.0",
                "title": "New Title",
            },
        )

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(old_file), str(new_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        assert "BREAKING" not in result.stdout


def test_diff_breaking_change_exit_1():
    """Test diff with a breaking change exits 1 and reports it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = _write_manifest(tmpdir, "old.json", _BASE_MANIFEST)
        new_file = _write_manifest(
            tmpdir,
            "new.json",
            {**_BASE_MANIFEST, "version": "2.0.0", "output_schema": {"type": "object", "properties": {}}},
        )

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(old_file), str(new_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, (
            f"Expected exit 1, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        assert "BREAKING" in result.stdout
        assert "removed output" in result.stdout


def test_diff_malformed_json_exit_2():
    """Test diff with malformed JSON exits 2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = Path(tmpdir) / "old.json"
        old_file.write_text('{"name": "test-node"')
        new_file = _write_manifest(tmpdir, "new.json", _BASE_MANIFEST)

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(old_file), str(new_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )


def test_diff_missing_file_exit_2():
    """Test diff with a missing file exits 2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = Path(tmpdir) / "does-not-exist.json"
        new_file = _write_manifest(tmpdir, "new.json", _BASE_MANIFEST)

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(old_file), str(new_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )


def test_diff_wrong_arg_count_exit_2():
    """Test diff without exactly two paths exits 2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        only_file = _write_manifest(tmpdir, "only.json", _BASE_MANIFEST)

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(only_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )


def test_diff_json_flag_outputs_valid_json():
    """Test diff --json outputs machine-readable JSON with contract keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_file = _write_manifest(tmpdir, "old.json", _BASE_MANIFEST)
        new_file = _write_manifest(
            tmpdir,
            "new.json",
            {**_BASE_MANIFEST, "version": "1.1.0", "title": "New Title"},
        )

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "diff", str(old_file), str(new_file), "--json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        payload = json.loads(result.stdout)
        assert payload["breaking"] is False
        assert "breaking_changes" in payload
        assert "non_breaking_changes" in payload
        assert payload["old_version"] == "1.0.0"
        assert payload["new_version"] == "1.1.0"


def test_validate_invalid_draft7_schema_exit_1():
    """Test that a structurally-invalid input_schema fails validation (DA-1955)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_node.py"
        test_file.write_text("""
from canvastekk_workflow_sdk import WorkflowNodeManifest

definition = WorkflowNodeManifest(
    name="test-node",
    version="1.0.0",
    title="Test Node",
    description="A test node",
    input_schema={"type": "strng", "properties": {"input": {"type": "string"}}},
    output_schema={"type": "object"},
)
""")

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate", "test_node:definition"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            env=_cli_env(),
        )

        assert result.returncode == 1, (
            f"Expected exit 1, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )
        assert "input_schema" in result.stdout
        assert "draft-7" in result.stdout


def test_validate_valid_draft7_schema_exit_0():
    """Test that well-formed schemas still pass (regression guard)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_node.py"
        test_file.write_text("""
from canvastekk_workflow_sdk import WorkflowNodeManifest

definition = WorkflowNodeManifest(
    name="test-node",
    version="1.0.0",
    title="Test Node",
    description="A test node",
    input_schema={"type": "object", "properties": {"input": {"type": "string"}}, "required": []},
    output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
)
""")

        result = subprocess.run(
            [str(PYTHON_BIN), "-m", "canvastekk_workflow_sdk", "validate", "test_node:definition"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            env=_cli_env(),
        )

        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}"
        )


class TestProbeHostCeiling:
    """#3499: the host-ceiling probe rejects budgets above the node's own
    hard_max_runtime_seconds while the engine-mirror 86400 check is retained."""

    def _manifest(self, *, timeout_seconds: int, hard_max: int | None = None):
        from canvastekk_workflow_sdk import WorkflowNodeManifest

        kwargs: dict = dict(
            slug="echo",
            version="1.0.0",
            name="Echo",
            description="Test",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            timeout_seconds=timeout_seconds,
        )
        if hard_max is not None:
            kwargs["hard_max_runtime_seconds"] = hard_max
        return WorkflowNodeManifest(**kwargs)

    def _probe(self, manifest):
        from canvastekk_workflow_sdk.__main__ import _probe_definition

        return _probe_definition(manifest)

    def test_default_ceiling_applied_when_field_absent(self) -> None:
        report = self._probe(self._manifest(timeout_seconds=7200))
        assert report["valid"] is True
        assert "host-ceiling" in report["probes"]

    def test_7200_accepted_against_default_ceiling(self) -> None:
        assert self._probe(self._manifest(timeout_seconds=7200))["valid"] is True

    def test_7201_rejected_against_default_ceiling(self) -> None:
        report = self._probe(self._manifest(timeout_seconds=7201))
        assert report["valid"] is False
        assert any("hard_max_runtime_seconds" in e for e in report["errors"])

    def test_explicit_override_raises_the_gate(self) -> None:
        report = self._probe(self._manifest(timeout_seconds=9000, hard_max=9000))
        assert report["valid"] is True

    def test_override_below_budget_still_rejected(self) -> None:
        report = self._probe(self._manifest(timeout_seconds=9000, hard_max=8000))
        assert report["valid"] is False

    def test_engine_mirror_86400_still_enforced(self) -> None:
        report = self._probe(self._manifest(timeout_seconds=86401, hard_max=100000))
        assert report["valid"] is False
        assert any("86400" in e for e in report["errors"])
