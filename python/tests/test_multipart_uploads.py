"""Multipart session uploads — DA-2886.

Covers the AC paths: session handshake (request model), both target
shapes at the parse boundary, the legacy-target fail-loud contract
(DA-3340), and the multipart machinery ported from
canvastekk-workflow-nodes (happy / failure / resume).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from canvastekk_workflow_sdk import UploadSession
from canvastekk_workflow_sdk.exceptions import NodeIOError
from canvastekk_workflow_sdk.multipart import upload_via_session
from canvastekk_workflow_sdk.request import NodeExecutionRequest
from canvastekk_workflow_sdk.uploads import S3PresignedUploader


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


class TestSessionHandshake:
    def test_mixed_targets_validate(self):
        sess = _session()
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            node_inputs={},
            output_upload_url={"legacy": "https://presigned", "modern": sess.model_dump()},
        )
        assert req.output_upload_url["legacy"] == "https://presigned"
        assert isinstance(req.output_upload_url["modern"], UploadSession)

    def test_plain_string_only_still_validates(self):
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            node_inputs={},
            output_upload_url={"out": "https://presigned"},
        )
        assert req.output_upload_url == {"out": "https://presigned"}

    def test_malformed_session_dict_rejects(self):
        with pytest.raises(Exception):
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                node_inputs={},
                # Missing every session field — not a valid target shape.
                output_upload_url={"out": {"kind": "multipart-upload-session"}},
            )


class TestDegradation:
    def test_string_target_raises_node_io_error(self, tmp_path, monkeypatch):
        """Legacy string target → NodeIOError; the multipart client is never
        invoked (fail-loud, no silent fallback — DA-3340)."""
        f = tmp_path / "out.bin"
        f.write_bytes(b"data")

        def _fail(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("multipart client must not run for a legacy target")

        monkeypatch.setattr("canvastekk_workflow_sdk.multipart.upload_via_session", _fail)
        with pytest.raises(NodeIOError) as excinfo:
            S3PresignedUploader().upload_file(str(f), "https://presigned")
        assert str(excinfo.value) == "engine sent deprecated presigned target — upgrade the engine"

    def test_session_target_takes_multipart_path(self, tmp_path, monkeypatch):
        """New SDK + new engine: initiate → part PUTs → complete."""
        f = tmp_path / "out.bin"
        f.write_bytes(b"x" * 10)
        sess = _session()
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "s3":
                seen["part-put"] = request
                return httpx.Response(200, headers={"ETag": '"e"'})
            seen[request.url.path] = request
            if request.url.path.endswith("/initiate"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-1",
                        "part_size": 4,
                        "part_urls": [
                            "https://s3/part1",
                            "https://s3/part2",
                            "https://s3/part3",
                        ],
                    },
                )
            if request.url.path.endswith("/complete"):
                return httpx.Response(200)
            raise AssertionError(f"unexpected control call: {request.url}")

        real_client = httpx.Client

        def _client_factory(**kwargs: Any) -> httpx.Client:
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx, "Client", _client_factory)
        upload_via_session(sess, str(f))
        assert any(p.endswith("/initiate") for p in seen)
        assert any(p.endswith("/complete") for p in seen)
        assert seen["part-put"]


class TestMachinery:
    def _wire(self, monkeypatch, handler):
        real_client = httpx.Client

        def _client_factory(**kwargs: Any) -> httpx.Client:
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx, "Client", _client_factory)

    def test_happy_path_no_unsigned_headers_and_sorted_complete(self, tmp_path, monkeypatch):
        f = tmp_path / "big.bin"
        payload = bytes(range(256)) * 2  # 512 bytes → 2 parts of 256
        f.write_bytes(payload)
        part_puts: list[tuple[str, dict[str, str]]] = []
        complete_bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/initiate"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-h",
                        "part_size": 256,
                        "part_urls": ["https://s3/p1", "https://s3/p2"],
                    },
                )
            if request.url.host == "s3":
                body = request.read()
                part_puts.append((str(request.url), dict(request.headers)))
                assert request.headers["Content-Length"] == str(len(body))
                # The engine presigns part URLs with SignedHeaders=host — any
                # header outside that set (e.g. Content-MD5) makes S3 reject
                # the PUT with AccessDenied (DA-3341).
                assert "Content-MD5" not in request.headers
                return httpx.Response(200, headers={"ETag": f'"etag-{len(body)}"'})
            if path.endswith("/complete"):
                import json as _json

                complete_bodies.append(_json.loads(request.read()))
                return httpx.Response(200)
            raise AssertionError(f"unexpected call: {request.url}")

        self._wire(monkeypatch, handler)
        upload_via_session(_session(), str(f), max_parallel_parts=1)

        assert len(part_puts) == 2
        assert [b["part_number"] for b in complete_bodies[0]["parts"]] == [1, 2]
        assert complete_bodies[0]["upload_id"] == "uid-h"

    def test_part_failure_after_retries_aborts_and_reraises(self, tmp_path, monkeypatch):
        f = tmp_path / "big.bin"
        f.write_bytes(b"z" * 8)
        aborted: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/initiate"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-f",
                        "part_size": 4,
                        "part_urls": ["https://s3/ok", "https://s3/bad"],
                    },
                )
            if str(request.url) == "https://s3/ok":
                return httpx.Response(200, headers={"ETag": '"e1"'})
            if str(request.url) == "https://s3/bad":
                return httpx.Response(500, text="boom")
            if path.endswith("/status"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-f",
                        "uploaded_parts": [{"part_number": 1, "etag": "e1"}],
                    },
                )
            if path.endswith("/abort"):
                aborted.append("called")
                return httpx.Response(200)
            if path.endswith("/complete"):
                raise AssertionError("complete must not be reached")
            raise AssertionError(f"unexpected call: {request.url}")

        self._wire(monkeypatch, handler)
        with pytest.raises(Exception):
            upload_via_session(
                _session(),
                str(f),
                max_parallel_parts=1,
                retry_attempts=1,
                resume_attempts=1,
            )
        assert aborted == ["called"]

    def test_resume_adopt_server_truth_then_complete(self, tmp_path, monkeypatch):
        f = tmp_path / "big.bin"
        f.write_bytes(b"q" * 8)
        complete_bodies: list[dict] = []
        bad_part_attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/initiate"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-r",
                        "part_size": 4,
                        "part_urls": ["https://s3/r1", "https://s3/r2"],
                    },
                )
            if str(request.url) == "https://s3/r1":
                # Part 1 fails once post-retry, but the server already
                # stored it — status reports it confirmed.
                bad_part_attempts["n"] += 1
                if bad_part_attempts["n"] <= 1:
                    return httpx.Response(500, text="transient")
                raise AssertionError("part 1 re-uploaded despite server truth")
            if str(request.url) == "https://s3/r2":
                return httpx.Response(200, headers={"ETag": '"e2"'})
            if path.endswith("/status"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-r",
                        "uploaded_parts": [{"part_number": 1, "etag": "server-e1"}],
                    },
                )
            if path.endswith("/complete"):
                import json as _json

                complete_bodies.append(_json.loads(request.read()))
                return httpx.Response(200)
            raise AssertionError(f"unexpected call: {request.url}")

        self._wire(monkeypatch, handler)
        upload_via_session(
            _session(),
            str(f),
            max_parallel_parts=1,
            retry_attempts=1,
            resume_attempts=1,
        )
        parts = complete_bodies[0]["parts"]
        # Server-truth etag for part 1, local etag for part 2.
        assert parts == [
            {"part_number": 1, "etag": "server-e1"},
            {"part_number": 2, "etag": "e2"},
        ]

    def test_status_upload_id_mismatch_aborts_and_reraises_original(self, tmp_path, monkeypatch):
        f = tmp_path / "big.bin"
        f.write_bytes(b"m" * 8)
        aborted: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/initiate"):
                return httpx.Response(
                    200,
                    json={
                        "upload_id": "uid-real",
                        "part_size": 4,
                        "part_urls": ["https://s3/m1", "https://s3/m2"],
                    },
                )
            if request.url.host == "s3":
                return httpx.Response(500, text="part boom")
            if path.endswith("/status"):
                # Mismatched upload_id — resume impossible.
                return httpx.Response(200, json={"upload_id": "uid-OTHER", "uploaded_parts": []})
            if path.endswith("/abort"):
                aborted.append("called")
                return httpx.Response(200)
            raise AssertionError(f"unexpected call: {request.url}")

        self._wire(monkeypatch, handler)
        with pytest.raises(NodeIOError) as exc_info:
            upload_via_session(
                _session(),
                str(f),
                max_parallel_parts=1,
                retry_attempts=1,
                resume_attempts=1,
            )
        # The ORIGINAL part failure is re-raised, not the mismatch error.
        assert "S3 PUT failed for part 1" in str(exc_info.value)
        assert "upload_id mismatch" not in str(exc_info.value)
        assert aborted == ["called"]
