"""Tests for output upload functionality (session-only targets since DA-3340)."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from canvastekk_workflow_sdk.exceptions import NodeIOError
from canvastekk_workflow_sdk.response import NodeExecutionResponse
from canvastekk_workflow_sdk.uploads import (
    OutputUploader,
    S3PresignedUploader,
    UploadSession,
    get_default_uploader,
)

#: Exact fail-loud message for a legacy presigned-PUT string target (DA-3340).
LEGACY_TARGET_MESSAGE = "engine sent deprecated presigned target — upgrade the engine"


def _session(**overrides: Any) -> UploadSession:
    fields = {
        "session_token": "tok-1",
        "initiate_url": "https://engine/sessions/tok-1/initiate",
        "complete_url": "https://engine/sessions/tok-1/complete",
        "abort_url": "https://engine/sessions/tok-1/abort",
        "status_url": "https://engine/sessions/tok-1/status",
    }
    fields.update(overrides)
    return UploadSession(**fields)


class MockUploader(OutputUploader):
    """Mock uploader for testing protocol compliance."""

    def __init__(self) -> None:
        self.uploaded: list[tuple[NodeExecutionResponse, dict[str, UploadSession], list[str]]] = []

    def upload_outputs(
        self,
        response: NodeExecutionResponse,
        upload_urls: dict[str, UploadSession],
        file_output_fields: list[str],
    ) -> None:
        self.uploaded.append((response, upload_urls, file_output_fields))


class TestOutputUploaderProtocol:
    """Tests for OutputUploader protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Test that OutputUploader protocol is runtime checkable."""
        uploader = MockUploader()
        assert isinstance(uploader, OutputUploader)

    def test_s3_uploader_implements_protocol(self) -> None:
        """Test that S3PresignedUploader implements OutputUploader protocol."""
        uploader = S3PresignedUploader()
        assert isinstance(uploader, OutputUploader)


class TestLegacyTargetRejection:
    """Fail-loud compliance: a legacy presigned-PUT string never uploads (DA-3340)."""

    def test_upload_file_rejects_legacy_string_target(self, tmp_path: Path) -> None:
        """A string target raises NodeIOError with the upgrade-the-engine message."""
        test_file = tmp_path / "out.bin"
        test_file.write_bytes(b"data")

        with pytest.raises(NodeIOError) as excinfo:
            S3PresignedUploader().upload_file(str(test_file), "https://example.com/presigned")

        assert str(excinfo.value) == LEGACY_TARGET_MESSAGE

    def test_upload_outputs_rejects_legacy_string_target(self, tmp_path: Path) -> None:
        """A legacy string in upload_urls fails upload_outputs before any upload."""
        test_file = tmp_path / "result.ply"
        test_file.write_bytes(b"ply data")
        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": str(test_file)},
            duration_ms=100,
        )

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            with pytest.raises(NodeIOError) as excinfo:
                S3PresignedUploader().upload_outputs(
                    response, {"result_path": "https://example.com/presigned"}, ["result_path"]
                )

        assert str(excinfo.value) == LEGACY_TARGET_MESSAGE
        mock_session_upload.assert_not_called()


class TestS3PresignedUploader:
    """Tests for S3PresignedUploader session-path behavior."""

    def test_upload_file_routes_session_target_to_multipart(self, tmp_path: Path) -> None:
        """A session target takes the multipart client (upload_via_session)."""
        test_file = tmp_path / "result.ply"
        test_file.write_bytes(b"ply data")
        sess = _session()

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            S3PresignedUploader().upload_file(str(test_file), sess)

        mock_session_upload.assert_called_once_with(sess, str(test_file))

    def test_upload_outputs_with_valid_file_and_session(self, tmp_path: Path) -> None:
        """Test upload_outputs with a valid file and session target."""
        uploader = S3PresignedUploader()
        test_file = tmp_path / "result.ply"
        test_file.write_bytes(b"ply data")

        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": str(test_file), "summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        mock_session_upload.assert_called_once()
        assert mock_session_upload.call_args[0][1] == str(test_file)

    def test_upload_outputs_raises_on_non_string_value(self) -> None:
        """A present non-string file-output value fails the node (DA-2337)."""
        uploader = S3PresignedUploader()
        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result": 123, "summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result": _session()}
        file_output_fields = ["result"]

        with pytest.raises(NodeIOError) as excinfo:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        assert "Output field 'result'" in str(excinfo.value)
        assert "not a string" in str(excinfo.value)
        assert excinfo.value.path is None

    def test_upload_outputs_raises_on_nonexistent_file(self) -> None:
        """A present path that does not exist fails the node with path detail (DA-2337)."""
        uploader = S3PresignedUploader()
        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": "/nonexistent/file.ply", "summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with pytest.raises(NodeIOError) as excinfo:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        assert "Output field 'result_path' value is not a local file" in str(excinfo.value)
        assert excinfo.value.path == "/nonexistent/file.ply"

    def test_upload_outputs_raises_on_directory_value(self, tmp_path: Path) -> None:
        """A directory path is not a file — fails like a missing path (DA-2337)."""
        uploader = S3PresignedUploader()
        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": str(tmp_path), "summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with pytest.raises(NodeIOError) as excinfo:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        assert "not a local file" in str(excinfo.value)
        assert excinfo.value.path == str(tmp_path)

    def test_upload_outputs_skips_absent_output_field(self) -> None:
        """An omitted file-output field is skipped, not failed (DA-2337)."""
        uploader = S3PresignedUploader()
        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        mock_session_upload.assert_not_called()

    def test_upload_outputs_partial_failure_orphans_earlier_uploads(self, tmp_path: Path) -> None:
        """A bad later field raises AFTER earlier valid fields uploaded (DA-2337)."""
        uploader = S3PresignedUploader()
        test_file = tmp_path / "good.ply"
        test_file.write_bytes(b"ply data")

        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"good_path": str(test_file), "bad_path": "/nonexistent/bad.ply"},
            duration_ms=100,
        )
        upload_urls = {
            "good_path": _session(session_token="tok-good"),
            "bad_path": _session(session_token="tok-bad"),
        }
        file_output_fields = ["good_path", "bad_path"]

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            with pytest.raises(NodeIOError) as excinfo:
                uploader.upload_outputs(response, upload_urls, file_output_fields)

        assert mock_session_upload.call_count == 1
        assert mock_session_upload.call_args[0][0].session_token == "tok-good"
        assert "bad_path" in str(excinfo.value)

    def test_upload_outputs_skips_missing_urls(self, tmp_path: Path) -> None:
        """Test that upload_outputs skips fields without upload URLs."""
        uploader = S3PresignedUploader()
        test_file = tmp_path / "result.ply"
        test_file.write_bytes(b"ply data")

        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": str(test_file), "summary": "done"},
            duration_ms=100,
        )
        upload_urls: dict[str, UploadSession] = {}
        file_output_fields = ["result_path"]

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        mock_session_upload.assert_not_called()

    def test_upload_outputs_raises_on_upload_failure(self, tmp_path: Path) -> None:
        """Session-path failures raise so the execution fails (DA-1711 4.1)."""
        uploader = S3PresignedUploader()
        test_file = tmp_path / "result.ply"
        test_file.write_bytes(b"ply data")

        response = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result_path": str(test_file), "summary": "done"},
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with patch(
            "canvastekk_workflow_sdk.multipart.upload_via_session",
            side_effect=NodeIOError("part PUT failed"),
        ):
            with pytest.raises(NodeIOError):
                uploader.upload_outputs(response, upload_urls, file_output_fields)

    def test_upload_outputs_with_no_outputs(self) -> None:
        """Test that upload_outputs returns early when outputs is None."""
        uploader = S3PresignedUploader()
        response = NodeExecutionResponse.failure(
            execution_id="exec-1",
            error="test error",
            error_type="ValueError",
            duration_ms=100,
        )
        upload_urls = {"result_path": _session()}
        file_output_fields = ["result_path"]

        with patch("canvastekk_workflow_sdk.multipart.upload_via_session") as mock_session_upload:
            uploader.upload_outputs(response, upload_urls, file_output_fields)

        mock_session_upload.assert_not_called()


class TestDefaultUploaderSingleton:
    """Tests for get_default_uploader singleton."""

    def test_get_default_uploader_returns_singleton(self) -> None:
        """Test that get_default_uploader returns the same instance."""
        uploader1 = get_default_uploader()
        uploader2 = get_default_uploader()
        assert uploader1 is uploader2

    def test_default_uploader_is_s3_presigned_uploader(self) -> None:
        """Test that default uploader is S3PresignedUploader instance."""
        uploader = get_default_uploader()
        assert isinstance(uploader, S3PresignedUploader)

    def test_default_uploader_implements_protocol(self) -> None:
        """Test that default uploader implements OutputUploader protocol."""
        uploader = get_default_uploader()
        assert isinstance(uploader, OutputUploader)
