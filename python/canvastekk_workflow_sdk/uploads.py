"""
Output Upload Handlers

Provides the OutputUploader protocol and concrete implementations
for uploading node output files to external storage (e.g., S3).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from canvastekk_workflow_sdk.exceptions import NodeIOError

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


#: An upload target. Session-only since SDK 0.36.0 (DA-3340): the legacy
#: presigned-PUT ``str`` member was removed; a string target reaching the
#: upload seam raises :class:`NodeIOError`.
UploadTarget = UploadSession


@runtime_checkable
class OutputUploader(Protocol):
    """Protocol for output upload handlers.

    Implement this protocol to provide custom upload behaviour
    (e.g., GCS, Azure Blob, local NFS). The SDK calls ``upload_outputs``
    after a successful execution when upload URLs are available.
    """

    def upload_file(self, file_path: str, target: UploadTarget) -> None:
        """Upload a single file to storage via an upload target.

        Since SDK 0.36.0 (DA-3340) the target is an :class:`UploadSession`
        descriptor only. A legacy presigned-PUT string reaching this seam
        raises :class:`NodeIOError` — fail-loud compliance, never a silent
        fallback; the fix is upgrading the engine, not node changes.

        Args:
            file_path: Local path to the file.
            target: Multipart upload-session descriptor.
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
                (multipart session descriptor; a legacy string target
                raises :class:`NodeIOError`).
            file_output_fields: List of output fields that produce files.
        """
        ...


class S3PresignedUploader:
    """Upload binary outputs via engine-provided upload sessions.

    Sessions are redeemed through the multipart client
    (``multipart.upload_via_session``). A failed upload raises
    :class:`NodeIOError` / :class:`NodeExecutionError`, which the router
    layer (``app.py``) converts into a ``fail``/``UPLOAD_FAILED``
    response — silently reporting success with local-only paths would
    strand downstream consumers (DA-1711 4.1).
    """

    def upload_file(self, file_path: str, target: UploadTarget) -> None:
        """Upload a single file to an engine-provided upload target.

        Session-only since SDK 0.36.0 (DA-3340): an
        :class:`UploadSession` descriptor takes the multipart client
        (lazy initiate → bounded parallel part PUTs → complete;
        per-part retry; resume-from-server-truth; abort-on-failure). A
        legacy presigned-PUT string raises :class:`NodeIOError` —
        fail-loud compliance, never a silent fallback; the engine must
        be upgraded (DA-3338), not the node. Terminal failures re-raise
        so the router layer (``app.py``) converts them into
        ``fail``/``UPLOAD_FAILED`` responses (DA-1711).

        Args:
            file_path: Local path to the file.
            target: Multipart upload-session descriptor.

        Raises:
            NodeIOError: A legacy presigned-PUT string target was
                received, or a part-PUT/local I/O failure survived
                retries/resume/abort.
            NodeExecutionError: Control-plane failure.
        """
        if isinstance(target, UploadSession):
            from canvastekk_workflow_sdk.multipart import upload_via_session

            upload_via_session(target, file_path)
            return

        raise NodeIOError("engine sent deprecated presigned target — upgrade the engine")

    def upload_outputs(
        self,
        response: NodeExecutionResponse,
        upload_urls: dict[str, UploadTarget],
        file_output_fields: list[str],
    ) -> None:
        """Upload binary output files via engine upload targets.

        A declared file-output field that HAS an upload target but whose
        value is not a string referencing an existing local file RAISES
        :class:`NodeIOError` — the engine stamps an ``s3://`` URI for every
        present output field on pass, so skipping the upload would report
        success while corrupting every downstream consumer (DA-2337). A
        legacy presigned-PUT string target raises :class:`NodeIOError`
        (DA-3340).

        Args:
            response: The node execution response containing output values.
            upload_urls: Mapping of output field name to upload target
                (multipart session descriptor).
            file_output_fields: Output field names that produce files.

        Raises:
            NodeIOError: If a present file-output field with an upload
                target holds a non-string value, a path that is not an
                existing local file, or the target itself is a legacy
                presigned-PUT string.
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
