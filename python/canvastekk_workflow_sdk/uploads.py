"""
Output Upload Handlers

Provides the OutputUploader protocol and concrete implementations
for uploading node output files to external storage (e.g., S3).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import warnings
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from canvastekk_workflow_sdk.exceptions import NodeIOError

# Explicit generous timeout for output uploads: httpx's implicit default
# (5 s per operation) aborts legitimate multi-GB uploads on slower links.
_UPLOAD_TIMEOUT_SECONDS = 600.0

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.response import NodeExecutionResponse

logger = logging.getLogger(__name__)


class UploadSession(BaseModel):
    """Engine-provided multipart upload-session descriptor (DA-2886).

    When the engine (DA-2887) supports multipart output uploads it may
    send this descriptor as an upload target instead of a plain presigned
    URL string. The SDK redeems the session lazily: it POSTs the file
    size to ``initiate_url`` only when an upload actually starts, then
    PUTs parts in bounded parallel batches and finalizes via
    ``complete_url``. See ``multipart.py`` for the machinery.

    Wire contract (snake_case, matching the execute-request wire):
    ``initiate`` POST ``{"size", "content_type"}`` →
    ``{"upload_id", "part_size", "part_urls": [...]}``;
    ``complete`` POST ``{"upload_id", "parts": [{"part_number", "etag"}]}``;
    ``abort`` POST ``{"upload_id"}`` (best-effort);
    ``status`` GET → ``{"upload_id", "uploaded_parts": [...]}``.
    """

    kind: Literal["multipart-upload-session"] = Field(
        default="multipart-upload-session",
        description="Discriminator; always 'multipart-upload-session'.",
    )
    session_token: str = Field(description="Opaque, TTL-bound engine token.")
    initiate_url: str
    complete_url: str
    abort_url: str
    status_url: str
    expires_at: str | None = Field(default=None, description="ISO-8601 expiry (informational).")


#: An upload target: legacy presigned-URL string or session descriptor.
UploadTarget = str | UploadSession


class LegacyPresignedUploadWarning(DeprecationWarning):
    """The engine minted a single-PUT presigned URL (legacy path).

    Emitted per call site when ``upload_file`` receives a plain string
    target. The multipart-only standard (DA-2885) deprecates this path;
    it is removed in SDK v1.0. Silencing: standard ``warnings``
    filtering only — ``filterwarnings("ignore", category=
    LegacyPresignedUploadWarning)``.
    """


_operator_warning_lock = threading.Lock()
_operator_warning_emitted = False


def _warn_legacy_presigned_upload() -> None:
    """Deprecation optics for the legacy single-PUT path (DA-2886).

    Developers get a per-call-site deduplicated ``DeprecationWarning``
    (the default warnings registry dedups by location — standard
    filtering is the ONLY silencing mechanism, no env flag). Operators
    get one ``logger.warning`` per process.

    ``stacklevel=3`` blames the DIRECT caller of ``upload_file`` — in
    production that is the router seam (``upload_outputs``), because
    output uploads run in the router after ``execute()`` returns and
    node-package frames are not in that stack; for direct callers the
    blamed frame is their exact call site.
    """
    global _operator_warning_emitted
    warnings.warn(
        "Single-PUT presigned upload target is deprecated under the "
        "multipart-only standard (DA-2885). Upgrade the workflow engine "
        "to multipart upload sessions (DA-2887) — this SDK path is "
        "removed in v1.0.",
        LegacyPresignedUploadWarning,
        stacklevel=3,
    )
    with _operator_warning_lock:
        if not _operator_warning_emitted:
            _operator_warning_emitted = True
            logger.warning(
                "Legacy single-PUT output uploads in use — engine does not "
                "yet provide multipart upload sessions (DA-2887). SDK path "
                "removal target: v1.0."
            )


@runtime_checkable
class OutputUploader(Protocol):
    """Protocol for output upload handlers.

    Implement this protocol to provide custom upload behaviour
    (e.g., GCS, Azure Blob, local NFS). The SDK calls ``upload_outputs``
    after a successful execution when upload URLs are available.
    """

    def upload_file(self, file_path: str, target: UploadTarget) -> None:
        """Upload a single file to storage via an upload target.

        DA-2886 widening: the target is a presigned-URL string (legacy
        single-PUT, deprecated) or an upload-session descriptor
        (multipart). Custom implementations may keep accepting strings
        only — the widening is additive.

        Args:
            file_path: Local path to the file.
            target: Pre-signed upload URL or session descriptor.
        """
        ...

    def upload_outputs(
        self,
        response: NodeExecutionResponse,
        upload_urls: dict[str, UploadTarget],
        file_output_fields: list[str],
    ) -> None:
        """Upload multiple output files to storage.

        Implementations MUST raise (not skip) when a file-output field that
        is present in ``response.outputs`` and has an upload target holds a
        value that is not an existing local file — silently skipping would
        report success while the engine stamps a storage URI for the
        missing object, corrupting downstream consumers (DA-2337).

        Args:
            response: The node execution response.
            upload_urls: Mapping of field name to upload target
                (presigned URL string or multipart session descriptor).
            file_output_fields: List of output fields that produce files.
        """
        ...


class S3PresignedUploader:
    """Upload binary outputs to S3 via pre-signed PUT URLs.

    Uses httpx for HTTP requests. A failed upload raises
    :class:`httpx.HTTPStatusError`, which the router layer
    (``app.py``) converts into a ``fail``/``UPLOAD_FAILED`` response —
    silently reporting success with local-only paths would strand
    downstream consumers (DA-1711 4.1).
    """

    _MAX_ATTEMPTS = 3
    _INITIAL_BACKOFF_SECONDS = 0.5

    def upload_file(self, file_path: str, target: UploadTarget) -> None:
        """Upload a single file to an engine-provided upload target.

        Direct swap (DA-2886): a plain string target takes the legacy
        single-PUT path (with a deprecation warning — removed in SDK
        v1.0); an :class:`UploadSession` descriptor takes the multipart
        client (lazy initiate → bounded parallel part PUTs → complete;
        per-part retry; resume-from-server-truth; abort-on-failure).
        Node-developer code needs no changes — the router, not the
        developer, performs uploads.

        The legacy string path keeps its contract: ``Content-Length`` set
        explicitly (pins the fixed-length identity wire contract against
        transport drift, mirroring the TS SDK's DA-1811 fix), the file is
        streamed (never buffered) preserving the multi-GB contract,
        ``timeout`` is per-operation, transient failures (transport, 5xx)
        retry up to 3 attempts with exponential backoff (0.5s, 1s), 4xx
        never retries, and the file reopens per attempt. The session path
        re-raises terminal failures so the router layer (``app.py``) still
        converts them into ``fail``/``UPLOAD_FAILED`` responses (DA-1711).

        Args:
            file_path: Local path to the file.
            target: Presigned URL string (legacy) or upload-session
                descriptor (multipart).

        Raises:
            LegacyPresignedUploadWarning: Emitted (not raised) per call
                site on the string path.
            httpx.HTTPStatusError: Legacy path — upload failed after
                retries.
            NodeIOError: Session path — part-PUT or local I/O failure
                after retries/resume/abort.
            NodeExecutionError: Session path — control-plane failure.
        """
        if isinstance(target, UploadSession):
            from canvastekk_workflow_sdk.multipart import upload_via_session

            upload_via_session(target, file_path)
            return

        _warn_legacy_presigned_upload()
        presigned_url = target
        last_error: Exception | None = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                with open(file_path, "rb") as f:
                    resp = httpx.put(
                        presigned_url,
                        content=f,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(os.path.getsize(file_path)),
                        },
                        timeout=_UPLOAD_TIMEOUT_SECONDS,
                    )
                    resp.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                last_error = e
            except httpx.TransportError as e:
                last_error = e

            if attempt < self._MAX_ATTEMPTS:
                backoff = self._INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Upload attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt,
                    self._MAX_ATTEMPTS,
                    last_error,
                    backoff,
                )
                time.sleep(backoff)

        assert last_error is not None
        raise last_error

    def upload_outputs(
        self,
        response: NodeExecutionResponse,
        upload_urls: dict[str, UploadTarget],
        file_output_fields: list[str],
    ) -> None:
        """Upload binary output files via engine upload targets.

        A declared file-output field that HAS a pre-signed URL but whose
        value is not a string referencing an existing local file RAISES
        :class:`NodeIOError` — the engine stamps an ``s3://`` URI for every
        present output field on pass, so skipping the upload would report
        success while corrupting every downstream consumer (DA-2337).

        Args:
            response: The node execution response containing output values.
            upload_urls: Mapping of output field name to pre-signed PUT URL.
            file_output_fields: Output field names that produce files.

        Raises:
            NodeIOError: If a present file-output field with a pre-signed
                URL holds a non-string value or a path that is not an
                existing local file.
        """
        if not response.outputs:
            return

        for field_name in file_output_fields:
            if field_name not in upload_urls:
                continue

            if field_name not in response.outputs:
                # Omitted output: the engine stamps s3:// URIs only for
                # fields present in the response, so omission is legal.
                continue

            value = response.outputs[field_name]
            if not isinstance(value, str):
                logger.error("Output field '%s' value is not a string: %s", field_name, type(value).__name__)
                raise NodeIOError(f"Output field '{field_name}' value is not a string: {type(value).__name__}")

            if not os.path.isfile(value):
                logger.error("Output field '%s' value is not a local file: %s", field_name, value)
                raise NodeIOError(
                    f"Output field '{field_name}' value is not a local file: {value}",
                    path=value,
                )

            self.upload_file(value, upload_urls[field_name])
            logger.info("Uploaded output '%s' to S3 (%d bytes)", field_name, os.path.getsize(value))


_default_uploader = S3PresignedUploader()


def get_default_uploader() -> S3PresignedUploader:
    """Return the process-wide default :class:`S3PresignedUploader` instance."""
    return _default_uploader
