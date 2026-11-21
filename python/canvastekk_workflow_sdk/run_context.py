"""
Workflow Run Context

Versioned run identity the workflow engine (CWE) sends with every
``/execute`` call once betekk/canvastekk-workflow-engine#1443 is live.
The result-file writer prefers ``run_context.workflow_run_id`` over the
bare wire ``run_id`` (which equals the workflow run id anyway once
CWE#1440 is deployed).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunContext(BaseModel):
    """Versioned run identity for the executing node (#281, epic #4320).

    Built by CWE at run creation and stamped with ``started_at`` by the
    executor; carried on every node call. Additive keys bump
    ``run_context_version``'s minor — consumers must ignore unknown keys
    (this model does, via the request's ``extra="ignore"``).
    """

    run_context_version: str = Field(
        description="Semver of the run_context object shape (v1: '1.0.0').",
    )
    workflow_run_id: str = Field(
        description=(
            "The workflow run id — one id per run, also the Temporal "
            "workflow id since CWE #1440."
        ),
    )
    workflow_definition_id: str | None = Field(
        default=None,
        description="Definition id the run executes.",
    )
    workflow_definition_slug: str | None = Field(
        default=None,
        description="Registered definition slug (e.g. model-checker).",
    )
    workflow_definition_version: str | None = Field(
        default=None,
        description="Semver of the definition.",
    )
    account_id: int | None = Field(
        default=None,
        ge=1,
        le=2**63 - 1,
        description="Account the run is attributed to.",
    )
    started_at: str | None = Field(
        default=None,
        description=(
            "ISO 8601 instant the executor started the run "
            "(``workflow.now()``) — not the create time."
        ),
    )
