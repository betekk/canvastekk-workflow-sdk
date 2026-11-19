"""Tests for the LocalFileServer test utility."""

import httpx
import pytest

from canvastekk_workflow_sdk import (
    LocalFileServer,
    NodeExecutionContext,
    NodeExecutionRequest,
    WorkflowNodeBase,
    WorkflowNodeManifest,
    serve_files,
)


class _FileReaderNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        name="file-reader-test",
        version="1.0.0",
        title="File Reader Test",
        description="Downloads and reads a file",
        input_schema={
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "format": "file",
                    "x-accept": [".txt", ".csv"],
                    "x-maxSizeBytes": 1048576,
                },
            },
            "required": ["input_file"],
        },
        output_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
        },
    )

    def execute(self, inputs: dict, context: NodeExecutionContext) -> dict:
        from pathlib import Path

        content = Path(inputs["input_file"]).read_text()
        return {"content": content}


class TestLocalFileServer:
    def test_serves_file_over_http(self, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world")

        with LocalFileServer(tmp_path) as server:
            url = server.url_for("hello.txt")
            assert url.startswith("http://")

            resp = httpx.get(url)
            assert resp.status_code == 200
            assert resp.text == "hello world"

    def test_auto_picks_free_port(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        with LocalFileServer(tmp_path) as s1, LocalFileServer(tmp_path) as s2:
            assert s1.base_url != s2.base_url

    def test_url_for_combines_base_and_filename(self, tmp_path):
        with LocalFileServer(tmp_path) as server:
            url = server.url_for("scan.las")
            assert url.endswith("/scan.las")

    def test_base_url_raises_when_not_running(self, tmp_path):
        server = LocalFileServer(tmp_path)
        with pytest.raises(RuntimeError, match="not running"):
            _ = server.base_url

    def test_stop_is_idempotent(self, tmp_path):
        server = LocalFileServer(tmp_path)
        server.start()
        server.stop()
        server.stop()

    def test_context_manager_starts_and_stops(self, tmp_path):
        server = LocalFileServer(tmp_path)
        with server:
            assert server.base_url.startswith("http://")
        with pytest.raises(RuntimeError):
            _ = server.base_url

    def test_serves_multiple_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.csv").write_text("bbb")

        with LocalFileServer(tmp_path) as server:
            assert httpx.get(server.url_for("a.txt")).text == "aaa"
            assert httpx.get(server.url_for("b.csv")).text == "bbb"

    def test_404_for_missing_file(self, tmp_path):
        with LocalFileServer(tmp_path) as server:
            resp = httpx.get(server.url_for("nonexistent.txt"))
            assert resp.status_code == 404


class TestServeFilesContextManager:
    def test_serve_files_yields_running_server(self, tmp_path):
        (tmp_path / "data.txt").write_text("content")

        with serve_files(tmp_path) as server:
            resp = httpx.get(server.url_for("data.txt"))
            assert resp.text == "content"


class TestFullDownloadPipeline:
    def test_sdk_downloads_from_local_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        (tmp_path / "input.txt").write_text("downloaded content")

        with LocalFileServer(tmp_path) as server:
            url = server.url_for("input.txt")

            node = _FileReaderNode()
            request = NodeExecutionRequest(
                run_id="test-run",
                node_id="fr-1",
                inputs={"input_file": url},
            )
            response = node.run(request)

            assert response.status == "pass"
            assert response.outputs["content"] == "downloaded content"

    def test_sdk_validates_downloaded_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        (tmp_path / "data.csv").write_text("col1,col2\n1,2")

        with LocalFileServer(tmp_path) as server:
            url = server.url_for("data.csv")

            node = _FileReaderNode()
            request = NodeExecutionRequest(
                run_id="test-run",
                node_id="fr-1",
                inputs={"input_file": url},
            )
            response = node.run(request)

            assert response.status == "pass"

    def test_rejects_wrong_extension(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        (tmp_path / "evil.exe").write_bytes(b"\x00\x01\x02")

        with LocalFileServer(tmp_path) as server:
            url = server.url_for("evil.exe")

            node = _FileReaderNode()
            request = NodeExecutionRequest(
                run_id="test-run",
                node_id="fr-1",
                inputs={"input_file": url},
            )
            response = node.run(request)

            assert response.status == "fail"
            assert "not allowed" in (response.error or "")

    def test_serves_binary_file_byte_for_byte(self, tmp_path):
        binary_data = bytes(range(256))
        (tmp_path / "binary.bin").write_bytes(binary_data)

        with LocalFileServer(tmp_path) as server:
            resp = httpx.get(server.url_for("binary.bin"))
            assert resp.status_code == 200
            assert resp.content == binary_data

    def test_rejects_path_traversal(self, tmp_path):
        subdir = tmp_path / "safe"
        subdir.mkdir()
        (subdir / "file.txt").write_text("safe content")

        with LocalFileServer(subdir) as server:
            resp = httpx.get(server.url_for("../../etc/passwd"))
            assert resp.status_code in (403, 404)
