"""Multipart upload machinery for engine upload sessions (DA-2886).

Ported from canvastekk-workflow-nodes ``_shared/cds_multipart.py``
(925-test-pinned patterns DA-2881/2882/2884) with one adaptation: the
control plane is the ENGINE's session endpoints described by an
:class:`~canvastekk_workflow_sdk.uploads.UploadSession` descriptor,
not a CDS client. This module owns the byte-level concerns:

- ETag parsing (S3 returns quoted hex; some S3-compatible stores don't)
- Per-part chunking (seek + read within a single open file handle)
- Per-part retry with backoff (multipart is designed for per-part retry)
- Resume reconciliation (post-retry part failure queries server-side
  upload status and re-attempts only unconfirmed parts — DA-2881)
- Abort-on-failure contract (aborts only when resume is exhausted or
  impossible; NEVER on complete failure)

The orchestrator (:func:`upload_via_session`) opens ONE file handle and
ONE bare httpx client for the duration, pre-reads part chunks
sequentially on the orchestrator thread (``fh.seek()`` on a shared
handle races), and dispatches part PUTs to bounded worker threads in
batches (DA-2882).
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, BinaryIO

import httpx

from canvastekk_workflow_sdk.exceptions import NodeExecutionError, NodeIOError
from canvastekk_workflow_sdk.uploads import UploadSession

logger = logging.getLogger(__name__)

#: Per-S3-part-PUT timeout (read/write) — separate from the short
#: control-plane timeout. Generous: a 5 GB part on a slow link is legal.
_S3_PUT_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=10.0)
#: Control-plane (initiate/complete/abort/status) timeout.
_CONTROL_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

_DEFAULT_RETRY_ATTEMPTS = 3
_DEFAULT_RETRY_BACKOFFS: tuple[float, ...] = (1.0, 2.0)
_DEFAULT_RESUME_ATTEMPTS = 1
_DEFAULT_MAX_PARALLEL_PARTS = 4


def _parse_etag(raw: str | None) -> str:
    """Extract a clean ETag from an S3 part-PUT response header.

    S3 returns ETags double-quoted; some S3-compatible stores (MinIO, R2)
    return unquoted; weak ETags (``W/"abc"``) are accepted with the
    prefix stripped.

    Args:
        raw: Raw ETag header value (may be ``None``).

    Returns:
        Cleaned ETag string (no quotes, no weak prefix).

    Raises:
        NodeExecutionError: If ``raw`` is ``None`` or empty after cleaning.
    """
    if not raw:
        raise NodeExecutionError("S3 part PUT returned no ETag — cannot confirm multipart upload")
    cleaned = raw.strip()
    if cleaned.startswith("W/"):
        cleaned = cleaned[2:]
    if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
        cleaned = cleaned[1:-1]
    if not cleaned:
        raise NodeExecutionError("S3 part PUT returned empty ETag after cleaning")
    return cleaned


def _read_part_chunk(
    fh: BinaryIO,
    part_number: int,
    part_size: int,
    file_path: str,
) -> bytes:
    """Read one part's bytes from the open file handle (orchestrator only).

    MUST run on the single orchestrator thread — ``fh.seek()`` on a shared
    handle races under concurrency (DA-2882).

    Args:
        fh: Open binary file handle (caller owns lifecycle).
        part_number: 1-based part number.
        part_size: Bytes per part (server-determined).
        file_path: Filesystem path (for error messages only).

    Returns:
        The part's bytes (shorter than ``part_size`` only for the last part).

    Raises:
        NodeIOError: If the file shrank during read (0 bytes at offset).
    """
    offset = (part_number - 1) * part_size
    fh.seek(offset)
    chunk = fh.read(part_size)
    if not chunk:
        raise NodeIOError(
            f"file shrank during upload: part {part_number} read 0 bytes from {file_path} at offset {offset}",
            path=file_path,
        )
    return chunk


def _put_one_part(
    s3_client: httpx.Client,
    presigned_url: str,
    part_number: int,
    chunk: bytes,
    file_path: str,
    content_type: str,
    total_parts: int,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS,
    retry_backoffs: tuple[float, ...] = _DEFAULT_RETRY_BACKOFFS,
) -> dict[str, Any]:
    """PUT one pre-read part chunk to S3 with retry. Pure worker (DA-2882).

    Args:
        s3_client: Bare httpx client (no Authorization — presigned URLs).
        presigned_url: The part's presigned PUT URL.
        part_number: 1-based part number.
        chunk: The part's bytes, pre-read by the orchestrator.
        file_path: Filesystem path (for error messages only).
        content_type: MIME type for the part PUT.
        total_parts: Total part count (progress logging only).
        retry_attempts: Max attempts per part (including the first).
        retry_backoffs: Seconds between retries.

    Returns:
        ``{"part_number": ..., "etag": ...}``.

    Raises:
        NodeIOError: If all attempts fail (S3 error body surfaced).
        NodeExecutionError: If the response carries no usable ETag.
    """
    # No Content-MD5 on part PUTs (DA-2891 verdict superseded by DA-3341
    # evidence): the engine presigns part URLs with SignedHeaders=host only
    # and the MD5 is unknowable at mint time, so an unsigned Content-MD5
    # header makes S3 reject the PUT with AccessDenied "There were headers
    # present in the request which were not signed". Integrity rides TLS
    # in transit plus S3's MPU etag consistency; reintroduce per-part
    # checksums only via a mint-time per-part signing protocol change.

    last_exc: Exception | None = None
    for attempt in range(1, retry_attempts + 1):
        # S3 requires explicit Content-Length on presigned PUTs — it
        # rejects plain Transfer-Encoding: chunked.
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(chunk)),
        }
        try:
            res = s3_client.put(presigned_url, content=chunk, headers=headers)
            res.raise_for_status()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retry_attempts:
                backoff = retry_backoffs[attempt - 1] if attempt - 1 < len(retry_backoffs) else retry_backoffs[-1]
                logger.warning(
                    "S3 part %d/%d PUT attempt %d failed: %s — retrying in %.1fs",
                    part_number,
                    total_parts,
                    attempt,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
                continue
            # Surface the S3 error body (BadDigest/InvalidDigest XML names
            # the condition) so digest failures are diagnosable, not opaque.
            detail = ""
            if isinstance(exc, httpx.HTTPStatusError):
                body = exc.response.text[:200].strip()
                if body:
                    detail = f" — {body}"
            raise NodeIOError(
                f"S3 PUT failed for part {part_number}/{total_parts} after {retry_attempts} attempts: {exc}{detail}",
                path=file_path,
            ) from exc

        etag = _parse_etag(res.headers.get("ETag"))
        logger.info(
            "S3 part %d/%d uploaded (etag=%s, bytes=%d)",
            part_number,
            total_parts,
            etag,
            len(chunk),
        )
        return {"part_number": part_number, "etag": etag}

    # Defensive — unreachable (loop returns or raises above).
    raise NodeIOError(
        f"S3 part {part_number} upload exhausted retries without raising",
        path=file_path,
    ) from last_exc


def _reconcile_resume(
    status_url: str,
    upload_id: str,
    part_numbers: set[int],
    failure: Exception,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Reconcile in-flight progress against server-side upload status.

    Called after a post-retry part failure: the failed PUT may have landed
    (S3 stored it but the response was lost), and earlier parts are
    certainly stored. Queries ``status_url`` and splits the session's part
    numbers into server-confirmed (authoritative etags) and remaining.

    Args:
        status_url: Session status endpoint (GET).
        upload_id: The in-flight multipart upload ID.
        part_numbers: Our part-number bundle (status rows naming unknown
            parts are ignored, not trusted).
        failure: The original part failure; re-raised whenever
            reconciliation is impossible.

    Returns:
        ``(confirmed, remaining)`` — confirmed part descriptors (sorted by
        part number) and the part numbers still to upload.

    Raises:
        Exception: Re-raises ``failure`` if the status query fails, the
            server's ``upload_id`` does not match, or the response is
            malformed.
    """
    try:
        with httpx.Client(timeout=_CONTROL_TIMEOUT) as client:
            res = client.get(status_url)
            res.raise_for_status()
            status = res.json()
    except Exception as exc:
        logger.warning(
            "upload-status query failed during resume: %s — cannot resume, failing the upload",
            exc,
        )
        raise failure from exc
    if status.get("upload_id") != upload_id:
        logger.warning(
            "upload-status upload_id mismatch (expected %s, got %s) — cannot resume, failing the upload",
            upload_id,
            status.get("upload_id"),
        )
        raise failure
    confirmed_by_number: dict[int, dict[str, Any]] = {}
    for part in status.get("uploaded_parts", []):
        number = part.get("part_number")
        if number in part_numbers:
            confirmed_by_number[number] = part
    confirmed = sorted(confirmed_by_number.values(), key=lambda part: part["part_number"])
    remaining = sorted(part_numbers - confirmed_by_number.keys())
    return confirmed, remaining


def _abort_session(abort_url: str, upload_id: str) -> None:
    """Best-effort abort — documented as never-raising.

    A failure here is logged, never propagated: the caller is already on
    an error path and the original exception must survive.
    """
    try:
        with httpx.Client(timeout=_CONTROL_TIMEOUT) as client:
            res = client.post(abort_url, json={"upload_id": upload_id})
            res.raise_for_status()
    except Exception:
        logger.exception(
            "abort_url call failed for upload_id=%s — original error preserved",
            upload_id,
        )


def upload_via_session(
    session: UploadSession,
    file_path: str,
    content_type: str = "application/octet-stream",
    *,
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS,
    retry_backoffs: tuple[float, ...] = _DEFAULT_RETRY_BACKOFFS,
    resume_attempts: int = _DEFAULT_RESUME_ATTEMPTS,
    max_parallel_parts: int = _DEFAULT_MAX_PARALLEL_PARTS,
) -> None:
    """Orchestrate a complete session-based multipart upload (DA-2886).

    Flow:

        1. Lazy initiate: POST ``initiate_url`` with the file size → the
           engine creates the S3 multipart upload and mints exactly
           ``ceil(size / part_size)`` presigned part URLs
        2. ONE file handle, ONE bare httpx S3 client, ONE bounded worker
           pool for the whole upload
        3. Per batch of ``max_parallel_parts``: pre-read chunks
           sequentially on the orchestrator thread, then PUT them in
           parallel (DA-2882)
        4. On a post-retry part failure: reconcile against server-side
           status and re-attempt only unconfirmed parts, up to
           ``resume_attempts`` rounds (DA-2881)
        5. POST ``complete_url`` with all etags sorted by part number
        6. On exhausted/impossible resume or local I/O failure: abort via
           ``abort_url`` (best-effort), re-raise the original error
        7. On complete failure: do NOT abort (parts are already valid in
           S3; complete is idempotent)

    Args:
        session: Engine-provided upload-session descriptor.
        file_path: Local filesystem path to the file.
        content_type: MIME type for the object and every part PUT.
        retry_attempts: Max attempts per part PUT.
        retry_backoffs: Seconds between part retries.
        resume_attempts: Extra resume rounds after a post-retry part
            failure (default 1).
        max_parallel_parts: Concurrent part PUTs per batch (default 4;
            the memory ceiling is ``max_parallel_parts × part_size``
            buffered bytes).

    Raises:
        NodeIOError: On part-PUT failure (after retries and resume) or
            local I/O failure — after the abort attempt.
        NodeExecutionError: On a malformed initiate bundle or part-count
            mismatch. Raw ``httpx.HTTPStatusError`` on control-plane
            non-2xx (the router converts any exception into
            ``fail``/``UPLOAD_FAILED``, DA-1711).
    """
    size = _file_size(file_path)
    bundle = _initiate(session, size, content_type)
    upload_id: str = bundle["upload_id"]
    part_size: int = bundle["part_size"]
    part_urls: list[str] = bundle["part_urls"]
    part_numbers = list(range(1, len(part_urls) + 1))
    total_parts = len(part_numbers)
    if total_parts == 0:
        raise NodeExecutionError(f"engine returned 0 part URLs for {file_path} ({size} bytes) — cannot upload")
    url_by_number = dict(zip(part_numbers, part_urls, strict=True))

    logger.info(
        "Starting multipart session upload file=%s size=%d parts=%d part_size=%d",
        file_path,
        size,
        total_parts,
        part_size,
    )

    etags: list[dict[str, Any]] = []
    remaining = list(part_numbers)
    resume_rounds_left = max(0, resume_attempts)
    batch_size = max(1, max_parallel_parts)
    try:
        with (
            httpx.Client(timeout=_S3_PUT_TIMEOUT) as s3_client,
            open(file_path, "rb") as fh,
            ThreadPoolExecutor(max_workers=batch_size) as pool,
        ):

            def _put(part_number: int, chunk: bytes) -> dict[str, Any]:
                return _put_one_part(
                    s3_client=s3_client,
                    presigned_url=url_by_number[part_number],
                    part_number=part_number,
                    chunk=chunk,
                    file_path=file_path,
                    content_type=content_type,
                    total_parts=total_parts,
                    retry_attempts=retry_attempts,
                    retry_backoffs=retry_backoffs,
                )

            while True:
                part_failure: Exception | None = None
                for start in range(0, len(remaining), batch_size):
                    batch = remaining[start : start + batch_size]
                    # Pre-read sequentially on the orchestrator thread —
                    # the only place fh is touched. A local read failure
                    # (file shrank) is NOT resumable; it propagates to the
                    # abort path below.
                    chunks = [_read_part_chunk(fh, n, part_size, file_path) for n in batch]
                    try:
                        # Executor.map preserves input order; the memory
                        # ceiling is batch_size × part_size buffered.
                        etags.extend(pool.map(_put, batch, chunks))
                    except (NodeIOError, NodeExecutionError) as exc:
                        # The failed part may still have landed in S3, and
                        # a mid-batch sibling's PUT may complete after this
                        # raise — attempt a resume round before giving up.
                        part_failure = exc
                        break
                if part_failure is None:
                    break
                if resume_rounds_left <= 0:
                    raise part_failure
                resume_rounds_left -= 1
                logger.warning(
                    "multipart session part failure (upload_id=%s) — "
                    "reconciling against server upload status (resume "
                    "rounds left: %d)",
                    upload_id,
                    resume_rounds_left,
                )
                confirmed, remaining = _reconcile_resume(
                    status_url=session.status_url,
                    upload_id=upload_id,
                    part_numbers=set(part_numbers),
                    failure=part_failure,
                )
                # Server truth supersedes local etag bookkeeping.
                etags = confirmed
                if not remaining:
                    break
    except Exception:
        # Resume exhausted/impossible, part-PUT failure, or local I/O
        # failure — abort to release orphaned S3 multipart state. Best
        # effort: _abort_session never raises, so the original exception
        # always propagates cleanly.
        logger.exception(
            "multipart session upload failed (upload_id=%s) — aborting",
            upload_id,
        )
        _abort_session(session.abort_url, upload_id)
        raise

    # Complete — NOT inside the try/except above. If complete fails, the
    # parts are already valid in S3; aborting would destroy them. Complete
    # is idempotent, so a retry of the whole flow can call it again.
    # S3 CompleteMultipartUpload requires parts ordered by part number;
    # after a resume round etags arrive from two sources.
    etags = sorted(
        ({part["part_number"]: part for part in etags}).values(),
        key=lambda part: part["part_number"],
    )
    logger.info(
        "All %d parts uploaded — completing multipart session upload (upload_id=%s)",
        total_parts,
        upload_id,
    )
    with httpx.Client(timeout=_CONTROL_TIMEOUT) as client:
        res = client.post(
            session.complete_url,
            json={"upload_id": upload_id, "parts": etags},
        )
        res.raise_for_status()


def _file_size(file_path: str) -> int:
    """Return the file's size, wrapping OS errors as :class:`NodeIOError`."""
    try:
        return os.path.getsize(file_path)
    except OSError as exc:
        raise NodeIOError(f"cannot stat upload source: {exc}", path=file_path) from exc


def _initiate(session: UploadSession, size: int, content_type: str) -> dict[str, Any]:
    """Redeem the session token lazily (POST initiate_url).

    Raises:
        NodeExecutionError: On non-2xx or a malformed response bundle.
    """
    with httpx.Client(timeout=_CONTROL_TIMEOUT) as client:
        res = client.post(
            session.initiate_url,
            json={"size": size, "content_type": content_type},
        )
        res.raise_for_status()
        try:
            bundle = res.json()
        except ValueError as exc:
            raise NodeExecutionError(f"initiate response is not JSON: {exc}") from exc
    missing = [k for k in ("upload_id", "part_size", "part_urls") if not bundle.get(k)]
    if missing:
        raise NodeExecutionError(f"initiate response missing fields: {', '.join(missing)}")
    return bundle
