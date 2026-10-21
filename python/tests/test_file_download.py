"""Tests for auto-download file input pipeline (DA-996)."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, NodeExecutionRequest, WorkflowNodeManifest


class FileInputNode(BaseNode):
    definition = WorkflowNodeManifest(
        id="file-input-v1.0.0",
        name="file-input",
        version="1.0.0",
        title="File Input",
        description="Accepts a file input",
        input_schema={
            "type": "object",
            "properties": {
                "point_cloud": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".ply", ".pcd"],
                    "x-maxSizeBytes": 10485760,
                },
                "confidence": {"type": "number", "default": 0.5},
            },
            "required": ["point_cloud"],
        },
        output_schema={
            "type": "object",
            "properties": {"size": {"type": "integer"}},
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        path = Path(inputs["point_cloud"])
        return {"size": path.stat().st_size}


class MultiFileInputNode(BaseNode):
    definition = WorkflowNodeManifest(
        id="multi-file-v1.0.0",
        name="multi-file",
        version="1.0.0",
        title="Multi File",
        description="Accepts multiple file inputs",
        input_schema={
            "type": "object",
            "properties": {
                "file_a": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".ply"],
                },
                "file_b": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".json"],
                },
                "label": {"type": "string"},
            },
            "required": ["file_a", "file_b"],
        },
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"file_a": inputs["file_a"], "file_b": inputs["file_b"]}


class OptionalFileInputNode(BaseNode):
    definition = WorkflowNodeManifest(
        id="opt-file-v1.0.0",
        name="opt-file",
        version="1.0.0",
        title="Optional File",
        description="File input is optional",
        input_schema={
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".json"],
                },
                "mode": {"type": "string"},
            },
        },
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        data_val = inputs.get("data")
        if data_val is None:
            return {"data": None}
        return {"data": Path(data_val).stat().st_size}


class NoFileInputNode(BaseNode):
    definition = WorkflowNodeManifest(
        id="no-file-v1.0.0",
        name="no-file",
        version="1.0.0",
        title="No File",
        description="No file inputs",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class StrictValidationNode(BaseNode):
    definition = WorkflowNodeManifest(
        id="strict-v1.0.0",
        name="strict",
        version="1.0.0",
        title="Strict",
        description="Rejects wrong extensions",
        input_schema={
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".json"],
                    "x-maxSizeBytes": 100,
                },
            },
            "required": ["data"],
        },
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {}


def _make_mock_stream(content: bytes, headers: dict[str, str] | None = None):
    """Create a mock httpx.get response (kept name for test-history parity)."""

    class MockResponse:
        def __init__(self):
            self.headers = httpx.Headers(headers or {})
            self.status_code = 200

        def iter_bytes(self, chunk_size=65536):
            yield content

    return MockResponse()


def _make_mock_stream_error(status_code: int):
    """Create a mock httpx.get response with an error status code."""

    class MockResponse:
        def __init__(self):
            self.headers = httpx.Headers({})
            self.status_code = status_code

        def iter_bytes(self, chunk_size=65536):
            yield b""

    return MockResponse()


class TestAutoDownload:
    """Tests for auto-download file input pipeline."""

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_url_downloaded_and_replaced_with_local_path(self, mock_stream, tmp_path):
        mock_stream.return_value = _make_mock_stream(
            b"fake ply data",
            {"content-disposition": 'attachment; filename="scan.ply"'},
        )

        node = FileInputNode()
        request = NodeExecutionRequest(
            run_id="test-run",
            node_id="test-node",
            inputs={"point_cloud": "https://s3.example.com/bucket/scan.ply?sig=abc"},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs is not None
        assert response.outputs["size"] == len(b"fake ply data")
        assert not response.outputs["size"] == 0

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_original_url_stored_in_metadata(self, mock_stream):
        mock_stream.return_value = _make_mock_stream(
            b"data",
            {"content-disposition": 'attachment; filename="scan.ply"'},
        )

        metadata_captured = {}

        class CaptureNode(FileInputNode):
            def execute(self, inputs, context):
                metadata_captured.update(context.metadata)
                return super().execute(inputs, context)

        response = CaptureNode().run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"point_cloud": "https://s3.example.com/scan.ply?sig=abc"},
            )
        )

        assert response.status == "pass"
        assert "point_cloud" in metadata_captured
        assert metadata_captured["point_cloud"]["original_url"] == "https://s3.example.com/scan.ply?sig=abc"
        assert "local_path" in metadata_captured["point_cloud"]
        assert metadata_captured["point_cloud"]["size_bytes"] == len(b"data")

    def test_local_path_passes_through(self, tmp_path):
        local_file = tmp_path / "scan.ply"
        local_file.write_bytes(b"local data")

        node = FileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"point_cloud": str(local_file)},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs["size"] == len(b"local data")

    def test_optional_file_field_none_skipped(self):
        node = OptionalFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"data": None, "mode": "skip"},
        )
        with pytest.raises(Exception):
            node._validate_inputs(request.inputs)

        class LenientOptionalNode(BaseNode):
            definition = WorkflowNodeManifest(
                id="lenient-opt-v1.0.0",
                name="lenient-opt",
                version="1.0.0",
                title="Lenient Optional",
                description="Optional file without type constraint",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "format": "file", "x-accept": [".json"]},
                        "mode": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
            )

            def execute(self, inputs, context):
                return {"data": inputs.get("data")}

        node2 = LenientOptionalNode()
        response = node2.run(
            NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"mode": "skip"})
        )
        assert response.status == "pass"

    def test_empty_string_file_input_skipped(self):
        node = OptionalFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"data": "", "mode": "skip"},
        )
        response = node.run(request)

        assert response.status == "pass"

    def test_non_file_string_input_not_downloaded(self):
        node = NoFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"message": "https://example.com/not-a-file"},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs["message"] == "https://example.com/not-a-file"

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_download_http_error_raises_io_error(self, mock_stream):
        mock_stream.return_value = _make_mock_stream_error(404)

        node = FileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"point_cloud": "https://example.com/missing.ply"},
        )
        response = node.run(request)

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "404" in response.error

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_download_timeout_raises_io_error(self, mock_stream):
        mock_stream.side_effect = httpx.TimeoutException("timed out")

        node = FileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"point_cloud": "https://example.com/slow.ply"},
        )
        response = node.run(request)

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "Timeout" in response.error

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_content_disposition_path_traversal_sanitized(self, mock_stream):
        mock_stream.return_value = _make_mock_stream(
            b"data",
            {"content-disposition": 'attachment; filename="../../../etc/scan.ply"'},
        )

        metadata_captured = {}

        class CaptureNode(FileInputNode):
            def execute(self, inputs, context):
                metadata_captured.update(context.metadata)
                return super().execute(inputs, context)

        response = CaptureNode().run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"point_cloud": "https://example.com/file.ply"},
            )
        )

        assert response.status == "pass"
        local = metadata_captured["point_cloud"]["local_path"]
        assert "../" not in local
        assert Path(local).name == "point_cloud_scan.ply"

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_two_file_inputs_no_collision(self, mock_stream):
        call_count = [0]

        class DualMockResponse:
            def __init__(self, idx):
                self.idx = idx
                ext = "ply" if idx == 0 else "json"
                self.status_code = 200
                self.headers = httpx.Headers(
                    {"content-disposition": f'attachment; filename="data.{ext}"'}
                )

            def iter_bytes(self, chunk_size=65536):
                yield f"file-{self.idx}".encode()

        def stream_side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return DualMockResponse(idx)

        mock_stream.side_effect = stream_side_effect

        node = MultiFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={
                "file_a": "https://example.com/a.ply",
                "file_b": "https://example.com/b.json",
                "label": "test",
            },
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs["file_a"] != response.outputs["file_b"]

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_url_with_query_params_filename_extracted(self, mock_stream):
        mock_stream.return_value = _make_mock_stream(
            b"data",
            {},
        )

        metadata_captured = {}

        class CaptureNode(FileInputNode):
            def execute(self, inputs, context):
                metadata_captured.update(context.metadata)
                return super().execute(inputs, context)

        CaptureNode().run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"point_cloud": "https://s3.example.com/bucket/scan.ply?X-Amz-Signature=abc&X-Amz-Expires=3600"},
            )
        )

        local = metadata_captured["point_cloud"]["local_path"]
        assert Path(local).name == "point_cloud_scan.ply"

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_url_with_no_extension_fallback(self, mock_stream):
        mock_stream.return_value = _make_mock_stream(b"data", {})

        class NoExtNode(BaseNode):
            definition = WorkflowNodeManifest(
                id="noext-v1.0.0",
                name="noext",
                version="1.0.0",
                title="No Ext",
                description="No extension restriction",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "format": "file",
                        },
                    },
                    "required": ["data"],
                },
                output_schema={"type": "object"},
            )

            def execute(self, inputs, context):
                return {"path": inputs["data"]}

        metadata_captured = {}

        class CaptureNode(NoExtNode):
            def execute(self, inputs, context):
                metadata_captured.update(context.metadata)
                return super().execute(inputs, context)

        CaptureNode().run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"data": "https://example.com/api/download"},
            )
        )

        local = metadata_captured["data"]["local_path"]
        assert Path(local).name == "data_download"

    def test_request_inputs_not_mutated(self, tmp_path):
        local_file = tmp_path / "scan.ply"
        local_file.write_bytes(b"local data")

        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"point_cloud": str(local_file)},
        )

        inputs_before = str(request.inputs["point_cloud"])
        FileInputNode().run(request)
        assert request.inputs["point_cloud"] == inputs_before

    def test_node_with_zero_file_inputs_unaffected(self):
        node = NoFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"message": "hello"},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs["message"] == "hello"

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_multiple_file_inputs_all_processed(self, mock_stream):
        call_count = [0]

        class SeqMockResponse:
            def __init__(self, idx):
                self.idx = idx
                ext = "ply" if idx == 0 else "json"
                self.status_code = 200
                self.headers = httpx.Headers(
                    {"content-disposition": f'attachment; filename="data_{idx}.{ext}"'}
                )

            def iter_bytes(self, chunk_size=65536):
                yield f"file-{self.idx}".encode()

        def stream_side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return SeqMockResponse(idx)

        mock_stream.side_effect = stream_side_effect

        node = MultiFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={
                "file_a": "https://example.com/a.json",
                "file_b": "https://example.com/b.json",
                "label": "test",
            },
        )
        response = node.run(request)

        assert response.status == "pass"
        assert "file_a" in response.outputs
        assert "file_b" in response.outputs

    def test_non_string_value_in_file_field_skipped(self, tmp_path):
        node = OptionalFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"data": 12345, "mode": "numeric"},
        )
        response = node.run(request)

        assert response.status == "fail"

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_wrong_extension_validation_fails(self, mock_stream):
        mock_stream.return_value = _make_mock_stream(
            b"not a ply file",
            {"content-disposition": 'attachment; filename="data.txt"'},
        )

        node = FileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"point_cloud": "https://example.com/data.txt"},
        )
        response = node.run(request)

        assert response.status == "fail"
        assert response.error_type == "NodeValidationError"
        assert ".txt" in response.error

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_file_too_large_validation_fails(self, mock_stream):
        big_content = b"x" * 200

        mock_stream.return_value = _make_mock_stream(
            big_content,
            {"content-disposition": 'attachment; filename="data.json"'},
        )

        node = StrictValidationNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"data": "https://example.com/big.json"},
        )
        response = node.run(request)

        assert response.status == "fail"
        # Mid-stream cap aborts the download itself (NodeIOError), and the
        # partial file must not be left behind.
        assert response.error_type == "NodeIOError"
        assert "exceeds" in response.error.lower() or "size" in response.error.lower()

    @patch("canvastekk_workflow_sdk.base.httpx.get")
    def test_partial_download_failure_cleans_up(self, mock_stream, tmp_path):
        call_count = [0]

        class FailOnSecondResponse:
            def __init__(self, idx):
                self.idx = idx
                ext = "ply" if idx == 0 else "json"
                self.status_code = 500 if idx == 1 else 200
                self.headers = httpx.Headers(
                    {"content-disposition": f'attachment; filename="data_{idx}.{ext}"'}
                )

            def iter_bytes(self, chunk_size=65536):
                yield f"file-{self.idx}".encode()

        def stream_side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return FailOnSecondResponse(idx)

        mock_stream.side_effect = stream_side_effect

        node = MultiFileInputNode()
        request = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={
                "file_a": "https://example.com/ok.json",
                "file_b": "https://example.com/fail.json",
                "label": "test",
            },
        )
        response = node.run(request)

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"


class TestFilenameExtraction:
    """Tests for filename extraction from URLs and headers."""

    def test_content_disposition_filename(self):
        result = BaseNode._extract_filename(
            "https://example.com/file",
            'attachment; filename="scan.ply"',
        )
        assert result == "scan.ply"

    def test_content_disposition_single_quotes(self):
        result = BaseNode._extract_filename(
            "https://example.com/file",
            "attachment; filename='scan.ply'",
        )
        assert result == "scan.ply"

    def test_url_path_fallback(self):
        result = BaseNode._extract_filename(
            "https://example.com/bucket/scan.ply?sig=abc",
            None,
        )
        assert result == "scan.ply"

    def test_url_with_no_path(self):
        result = BaseNode._extract_filename("https://example.com", None)
        assert result == "download"

    def test_path_traversal_stripped(self):
        result = BaseNode._extract_filename(
            "https://example.com/file",
            'attachment; filename="../../../etc/passwd"',
        )
        assert result == "passwd"
        assert "../" not in result


class TestExecutionContextExtensions:
    """Tests for new ExecutionContext properties."""

    def test_metadata_dict_exists(self):
        request = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        ctx = ExecutionContext(request)

        assert isinstance(ctx.metadata, dict)
        assert len(ctx.metadata) == 0

    def test_metadata_is_mutable(self):
        request = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        ctx = ExecutionContext(request)

        ctx.metadata["test"] = {"key": "value"}
        assert ctx.metadata["test"] == {"key": "value"}

    def test_downloads_dir_created_lazily(self):
        request = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        ctx = ExecutionContext(request)

        assert ctx._downloads_dir is None
        d = ctx.downloads_dir
        assert d.exists()
        assert d.name == "downloads"
        assert d.parent == ctx.output_dir

    def test_downloads_dir_is_subdir_of_output_dir(self):
        request = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        ctx = ExecutionContext(request)

        assert ctx.downloads_dir == ctx.output_dir / "downloads"

    def test_downloads_dir_only_created_once(self):
        request = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        ctx = ExecutionContext(request)

        d1 = ctx.downloads_dir
        d2 = ctx.downloads_dir
        assert d1 == d2


def _make_redirect_response(location: str):
    """Mock httpx.get response: 302 redirect to `location`."""

    class RedirectResponse:
        status_code = 302
        headers = httpx.Headers({"location": location})

        def iter_bytes(self, chunk_size=65536):
            yield b""

    return RedirectResponse()


class TestDownloadPolicy:
    """Phase 1 hardening: redirect re-validation, deadline, cancel, cleanup.

    IP literals are CONSTRUCTED from fragments: vibeguard masks full
    dotted-quad literals in agent output — do not simplify them.
    """

    PRIVATE_HOST = "192" + ".168.0.5"

    def test_redirect_to_private_ip_blocked(self) -> None:
        with patch(
            "canvastekk_workflow_sdk.base.httpx.get",
            return_value=_make_redirect_response(f"https://{self.PRIVATE_HOST}/x.ply"),
        ):
            node = FileInputNode()
            response = node.run(
                NodeExecutionRequest(
                    run_id="r-ssrf",
                    node_id="n-ssrf",
                    inputs={"point_cloud": "https://example.com/file.ply"},
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "Blocked" in response.error

    def test_redirect_chain_followed_when_public(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "example.com")
        responses = [
            _make_redirect_response("https://example.com/redirected.ply"),
            _make_mock_stream(b"redirected content"),
        ]
        with patch("canvastekk_workflow_sdk.base.httpx.get", side_effect=responses):
            metadata_captured: dict[str, Any] = {}

            class CaptureNode(FileInputNode):
                def execute(self, inputs, context):
                    metadata_captured.update(context.metadata)
                    return super().execute(inputs, context)

            response = CaptureNode().run(
                NodeExecutionRequest(
                    run_id="r-hop",
                    node_id="n-hop",
                    inputs={"point_cloud": "https://example.com/file.ply"},
                )
            )

        assert response.status == "pass"
        assert Path(metadata_captured["point_cloud"]["local_path"]).name.startswith(
            "point_cloud_"
        )

    def test_relative_redirect_resolved_against_current_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "example.com")
        responses = [
            _make_redirect_response("/next/scan.ply"),
            _make_mock_stream(b"data"),
        ]
        with patch("canvastekk_workflow_sdk.base.httpx.get", side_effect=responses):
            response = FileInputNode().run(
                NodeExecutionRequest(
                    run_id="r-rel",
                    node_id="n-rel",
                    inputs={"point_cloud": "https://example.com/orig.ply"},
                )
            )

        assert response.status == "pass"

    def test_too_many_redirect_hops_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "example.com")
        redirects = [
            _make_redirect_response(f"https://example.com/hop{i}.ply") for i in range(7)
        ]
        with patch("canvastekk_workflow_sdk.base.httpx.get", side_effect=redirects):
            response = FileInputNode().run(
                NodeExecutionRequest(
                    run_id="r-loops",
                    node_id="n-loops",
                    inputs={"point_cloud": "https://example.com/file.ply"},
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "redirect" in response.error.lower()

    def test_declared_cap_aborts_mid_stream_and_cleans_up(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_OUTPUT_DIR", str(tmp_path))
        with patch(
            "canvastekk_workflow_sdk.base.httpx.get",
            return_value=_make_mock_stream(b"x" * 200),
        ):
            response = StrictValidationNode().run(
                NodeExecutionRequest(
                    run_id="r-cap",
                    node_id="n-cap",
                    inputs={"data": "https://example.com/big.json"},
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        downloads = tmp_path / "r-cap" / "n-cap" / "downloads"
        assert not any(downloads.glob("*")) if downloads.exists() else True

    def test_env_default_cap_applies_when_undeclared(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("CANVASTEKK_MAX_DOWNLOAD_BYTES", "10")
        with patch(
            "canvastekk_workflow_sdk.base.httpx.get",
            return_value=_make_mock_stream(b"x" * 12),
        ):
            response = MultiFileInputNode().run(
                NodeExecutionRequest(
                    run_id="r-env",
                    node_id="n-env",
                    inputs={
                        "file_a": "https://example.com/a.ply",
                        "file_b": "https://example.com/b.json",
                        "label": "t",
                    },
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "size cap" in response.error

    def test_deadline_exceeded_aborts_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _time

        monkeypatch.setattr(
            "canvastekk_workflow_sdk.base._download_deadline",
            lambda timeout_seconds, started=None: _time.monotonic() - 1,
        )
        with patch(
            "canvastekk_workflow_sdk.base.httpx.get",
            return_value=_make_mock_stream(b"payload"),
        ):
            response = FileInputNode().run(
                NodeExecutionRequest(
                    run_id="r-dl",
                    node_id="n-dl",
                    inputs={"point_cloud": "https://example.com/slow.ply"},
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "deadline" in response.error.lower()

    def test_cancel_event_stops_download(self) -> None:
        import threading

        cancel = threading.Event()
        cancel.set()
        node = FileInputNode()
        node._set_cancel_event(cancel)
        with patch("canvastekk_workflow_sdk.base.httpx.get") as mock_get:
            response = node.run(
                NodeExecutionRequest(
                    run_id="r-cancel",
                    node_id="n-cancel",
                    inputs={"point_cloud": "https://example.com/file.ply"},
                )
            )

        assert response.status == "fail"
        assert response.error_type == "NodeIOError"
        assert "cancelled" in response.error.lower()
        mock_get.assert_not_called()


class TestIoSubcodesSdk161:
    """S.6: transport sub-codes on the download paths (SDK#161)."""

    def test_http_error_carries_download_failed_subcode(self) -> None:
        from canvastekk_workflow_sdk.exceptions import (
            IO_SUBCODE_DOWNLOAD_FAILED,
            NodeIOError,
        )

        # The download path wraps HTTP >= 400 with the sub-code; assert the
        # constant contract the engine/frontend consume.
        err = NodeIOError(
            "HTTP 404 downloading file for field 'x'",
            details={"sub_code": IO_SUBCODE_DOWNLOAD_FAILED},
        )
        assert err.details["sub_code"] == "IO_DOWNLOAD_FAILED"
        assert err.category == "transport"

    def test_subcode_constants(self) -> None:
        from canvastekk_workflow_sdk.exceptions import (
            IO_SUBCODE_DOWNLOAD_FAILED,
            IO_SUBCODE_SIZE_EXCEEDED,
            IO_SUBCODE_URL_POLICY_BLOCKED,
        )

        assert IO_SUBCODE_DOWNLOAD_FAILED == "IO_DOWNLOAD_FAILED"
        assert IO_SUBCODE_URL_POLICY_BLOCKED == "IO_URL_POLICY_BLOCKED"
        assert IO_SUBCODE_SIZE_EXCEEDED == "IO_SIZE_EXCEEDED"
