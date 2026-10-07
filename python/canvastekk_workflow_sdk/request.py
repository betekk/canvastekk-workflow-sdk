"""
Node Execution Request Model

This is the payload sent to a node's /execute endpoint.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from canvastekk_workflow_sdk.uploads import UploadSession


class NodeExecutionRequest(BaseModel):
    """
    Request payload for node execution.

    Sent by the orchestrator to a node's POST /execute endpoint.
    ``run_id``/``node_id`` are constrained to a slug charset and may not
    contain ``..`` (defense against path construction attacks — the ids
    flow into ``/tmp/{run_id}/{node_id}`` output paths).
    """

    _SLUG_RE = r"^[A-Za-z0-9._-]+$"

    run_id: str = Field(
        pattern=_SLUG_RE,
        description="Workflow run identifier (slug: letters, digits, dot, underscore, hyphen)",
    )
    node_id: str = Field(
        pattern=_SLUG_RE,
        description="Node instance ID in workflow (slug: letters, digits, dot, underscore, hyphen)",
    )
    execution_id: str | None = Field(
        default=None,
        pattern=_SLUG_RE,
        description=(
            "Dispatcher-minted execution id (e.g. 'ecs-<uuid>'). When provided, "
            "progress pings carry it so the engine's forgery guard matches the "
            "id it parked at dispatch time (#3498); when absent the node invents "
            "a uuid4 (inline behavior, echoed back via the response)."
        ),
    )

    @model_validator(mode="after")
    def _reject_dot_segments(self) -> NodeExecutionRequest:
        """Reject `..` substrings and dot-only values.

        The slug charset alone still permits `..` and `.` segments; these
        flow into ``/tmp/{run_id}/{node_id}`` path construction and would
        escape the run sandbox (DA-1711 3.1). ``execution_id`` joins the
        check for cross-leg parity with the TS ``slugField`` refinement
        (#3498 review) — it does not touch paths, but one wire field must
        not validate differently per SDK leg.
        """
        for field_name in ("run_id", "node_id", "execution_id"):
            value = getattr(self, field_name, None)
            if value is None:
                continue
            if ".." in value or value.strip(".") != value or not value.strip("."):
                raise ValueError(f"{field_name} must not contain dot segments (got {value!r})")
        return self

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Input values (may include signed URLs for file access)",
    )
    account_id: int | None = Field(
        default=None,
        ge=1,
        le=2**63 - 1,
        description=(
            "Active account ID asserted by the orchestrator (DA-2242). "
            "Engine-controlled: /execute sets this exclusively from the "
            "X-Account-Id header — body-supplied values are stripped. "
            "None for local runs."
        ),
    )
    callback_url: str | None = Field(
        default=None,
        description="For async execution - URL to POST result to when complete",
    )
    output_upload_url: dict[str, str | UploadSession] | None = Field(
        default=None,
        description=(
            "Mapping of output field name to a multipart upload-session "
            "descriptor (the only upload target since SDK 0.36.0, "
            "DA-3340). A legacy presigned-PUT string is still admitted at "
            "this parse — solely so the upload seam can fail loudly with "
            "NodeIOError instead of an opaque 422"
        ),
    )

    model_config = ConfigDict(
        # Tolerate unknown body keys both directions (old engine ↔ new SDK).
        extra="ignore",
        json_schema_extra={
            "examples": [
                {
                    "run_id": "run-abc123",
                    "node_id": "echo-1",
                    "inputs": {"message": "Hello, World!"},
                    "account_id": 42,
                    "callback_url": None,
                    "output_upload_url": None,
                }
            ]
        },
    )
