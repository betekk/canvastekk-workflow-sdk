"""Multipart session uploads — DA-2886.

Covers the AC paths: session handshake (request model), both degradation
directions, deprecation-warning semantics, and the multipart machinery
ported from canvastekk-workflow-nodes (happy / failure / resume).
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import httpx
import pytest

from canvastekk_workflow_sdk import LegacyPresignedUploadWarning, UploadSession
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
    def test_string_target_takes_legacy_put_path(self, tmp_path, monkeypatch):
        f = tmp_path / "out.bin"
        f.write_bytes(b"data")
        calls: list[str] = []

        def fake_put(url: str, **kwargs: Any) -> httpx.Response:
            calls.append(url)
            return httpx.Response(200, request=httpx.Request("PUT", url))

        monkeypatch.setattr(httpx, "put", fake_put)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LegacyPresignedUploadWarning)
            S3PresignedUploader().upload_file(str(f), "https://presigned")
        assert calls == ["https://presigned"]

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


class TestDeprecationWarning:
    def test_warning_fires_and_is_filterable(self, tmp_path, monkeypatch):
        f = tmp_path / "out.bin"
        f.write_bytes(b"data")
        monkeypatch.setattr(httpx, "put", lambda url, **k: httpx.Response(200, request=httpx.Request("PUT", url)))
        uploader = S3PresignedUploader()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            uploader.upload_file(str(f), "https://presigned")
            uploader.upload_file(str(f), "https://presigned-2")

        legacy = [w for w in caught if issubclass(w.category, LegacyPresignedUploadWarning)]
        assert legacy, "deprecation warning must fire on the string path"
        assert issubclass(LegacyPresignedUploadWarning, DeprecationWarning)
        assert "v1.0" in str(legacy[0].message)

        with warnings.catch_warnings(record=True) as silenced:
            warnings.filterwarnings("ignore", category=LegacyPresignedUploadWarning)
            uploader.upload_file(str(f), "https://presigned-3")
        assert not [w for w in silenced if issubclass(w.category, LegacyPresignedUploadWarning)]

    def test_warning_deduped_per_call_site(self, tmp_path, monkeypatch):
        """Under the DEFAULT filter the registry dedups by location:
        two calls at one site → one warning; a second site → fires."""
        f = tmp_path / "out.bin"
        f.write_bytes(b"data")
        monkeypatch.setattr(
            httpx,
            "put",
            lambda url, **k: httpx.Response(200, request=httpx.Request("PUT", url)),
        )
        uploader = S3PresignedUploader()

        def same_site() -> None:
            uploader.upload_file(str(f), "https://p1")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("default")
            same_site()
            same_site()
        assert len(caught) == 1

        def second_site() -> None:
            uploader.upload_file(str(f), "https://p2")

        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter("default")
            second_site()
            second_site()
        assert len(caught2) == 1

    def test_session_path_emits_no_warning(self, tmp_path, monkeypatch):
        f = tmp_path / "out.bin"
        f.write_bytes(b"y" * 8)
        monkeypatch.setattr(
            "canvastekk_workflow_sdk.multipart.upload_via_session",
            lambda session, path, **k: None,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            S3PresignedUploader().upload_file(str(f), _session())
        assert not [w for w in caught if "deprecated" in str(w.message).lower()]

    def test_operator_log_fires_once_per_process(self, tmp_path, monkeypatch, caplog):
        import canvastekk_workflow_sdk.uploads as up

        f = tmp_path / "out.bin"
        f.write_bytes(b"data")
        monkeypatch.setattr(httpx, "put", lambda url, **k: httpx.Response(200, request=httpx.Request("PUT", url)))
        monkeypatch.setattr(up, "_operator_warning_emitted", False)
        uploader = S3PresignedUploader()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LegacyPresignedUploadWarning)
            with caplog.at_level(logging.WARNING, logger="canvastekk_workflow_sdk.uploads"):
                uploader.upload_file(str(f), "https://p1")
                uploader.upload_file(str(f), "https://p2")
        matches = [r for r in caplog.records if "Legacy single-PUT" in r.message]
        assert len(matches) == 1


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
