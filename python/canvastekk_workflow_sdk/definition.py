"""
Node Definition Models

These models define what a node is and how it should behave.
Every compliant node must provide a WorkflowNodeManifest.
"""

from __future__ import annotations

import enum
import json
import re
import warnings
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, computed_field, field_validator, model_serializer, model_validator

from canvastekk_workflow_sdk._version import __version__ as _sdk_version_stamp
from canvastekk_workflow_sdk.exceptions import NodeValidationError


def _stamped_sdk_version() -> str:
    """DA-3359 stamp factory — the installed SDK version (version leaf module)."""
    return _sdk_version_stamp


# DA-2627: DeprecationWarning is hidden by default outside __main__; surface the
# legacy-construction warning to node authors explicitly (scoped to this module).
warnings.filterwarnings("default", category=DeprecationWarning, module=r"canvastekk_workflow_sdk\.definition")

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.registry import InvokeType

_SLUG_PATTERN = re.compile(r"^[a-z]([a-z0-9-]*[a-z0-9])?$")
_SEMVER_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")

_LEGACY_DEPRECATION_MSG = (
    "NodeDefinition legacy construction (name=<slug>, title=<display>) is deprecated; "
    "use slug=<id> and name=<display>. The legacy mapping keeps working but will be removed "
    "in a future major version."
)

# fmt: off
ColorPreset = Literal[
    # Standard (500→600)
    "purple", "red", "gray", "cyan", "emerald", "orange", "amber",
    "sky", "violet", "teal", "indigo", "slate", "blue", "green",
    "pink", "yellow", "rose", "lime", "fuchsia",
    # Light variants (400→500)
    "emerald-light", "indigo-light", "slate-light",
    # Dark variants (600→700)
    "red-dark", "sky-dark", "teal-dark", "emerald-dark",
]
"""Color preset for the node header gradient.

Pick a preset name and the frontend maps it to the correct Tailwind gradient.
Use the standard variant (e.g. ``"emerald"``) unless you need to distinguish
nodes within the same category, in which case use ``-light`` or ``-dark``.
"""
# fmt: on


class WorkflowNodeStyles(BaseModel):
    """Presentation metadata consumed by the frontend."""

    icon: str | None = Field(
        default=None,
        description="Lucide icon name in PascalCase (e.g. 'Brain', 'GitBranch'). "
        "Any icon from the full Lucide set (1500+) is supported via dynamic imports. "
        "See https://lucide.dev/icons for the full list. "
        "Unknown names fall back to 'Box'.",
    )
    color: ColorPreset | None = Field(
        default=None,
        description="Color preset for the node header gradient. "
        "See ColorPreset type for all options (e.g. 'emerald', 'indigo-light').",
    )


class RetryConfig(BaseModel):
    """Retry configuration for node execution."""

    max_attempts: int = Field(
        default=1,
        ge=1,
        description="Total attempts (1 = no retry, 3 = 1 initial + 2 retries)",
    )
    initial_delay_ms: int = Field(
        default=1000,
        ge=0,
        description="Delay before first retry in milliseconds",
    )
    backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Multiplier for exponential backoff",
    )
    max_delay_ms: int = Field(
        default=30000,
        ge=0,
        description="Maximum delay between retries in milliseconds",
    )


class WorkflowNodeRole(str, enum.Enum):  # noqa: UP042
    """Node role in the workflow system.

    Values:
        START: Workflow entry point.
        END: Workflow exit point.
        ERROR_GATE: Error handling node.
        OPERATION: Regular processing node.
    """

    START = "start"
    END = "end"
    ERROR_GATE = "error_gate"
    OPERATION = "operation"


class DeprecationInfo(BaseModel):
    """Advisory deprecation metadata for a node manifest.

    This is a *migration* signal, orthogonal to ``node_status`` (which is the
    operational routing lever — ``active | inactive | dead``). A deprecated node
    stays ``active`` until it is retired; ``deprecation`` only tells
    workflow-definition authors to move off the node. Mirrors RFC 9745
    (Deprecation) / RFC 8594 (Sunset) semantics at the data-model level.
    """

    deprecated_at: date | None = Field(
        default=None,
        description="Date deprecation took effect (RFC 9745 Deprecation). "
        "None = deprecated but the start date is unknown/not recorded.",
    )
    sunset_date: date | None = Field(
        default=None,
        description="Planned removal date (RFC 8594 Sunset). None = deprecated but no firm removal date yet.",
    )
    replacement_slug: str | None = Field(
        default=None,
        description="Slug of the node that replaces this one, if any. "
        "The engine resolves the slug to the node registry record.",
    )
    migration_url: str | None = Field(
        default=None,
        description="URL to migration documentation (RFC 9745 §3 "
        'Link rel="deprecation" / RFC 8594 §6 Link rel="sunset").',
    )
    notice: str = Field(
        description="Human-readable deprecation notice shown to workflow-definition authors.",
    )

    @model_validator(mode="after")
    def _validate_sunset_after_deprecation(self) -> DeprecationInfo:
        """Require ``sunset_date`` to fall on/after ``deprecated_at`` (DA-2305).

        Raises:
            ValueError: When both dates are set and the sunset precedes the
                deprecation start.
        """
        if self.sunset_date is not None and self.deprecated_at is not None and self.sunset_date < self.deprecated_at:
            raise ValueError(
                f"DeprecationInfo sunset_date {self.sunset_date} is before deprecated_at {self.deprecated_at}"
            )
        return self


class WorkflowNodeManifest(BaseModel):
    """
    Standard definition that every node must provide.

    This is the SDK's registry-level node type definition. In the engine's
    terminology, it maps to a ``WorkflowNode`` (the registered node type in
    the node registry), **not** a ``WorkflowDefinitionNode`` (which represents
    a node instance within a specific workflow definition).

    Returned by the /manifest endpoint and used by:
    - Registry to store node metadata (via ``register_node()``)
    - Frontend to render properties panel from input_schema
    - Orchestrator to validate inputs before execution

    Versioning:
        The ``version`` field is a semantic version string (e.g., ``"1.2.0"``)
        that is validated against the semver pattern (X.Y.Z) at definition time.
        The engine uses this version directly for registry storage and enforces
        immutability: re-registering with the same version and changed data
        is rejected — node authors must bump the version for schema changes.
    """

    # Identity
    slug: str = Field(description="Slug for routing and identity (e.g., 'segmentation')")
    version: str = Field(
        description="Semantic version string (e.g., '1.2.0'). Must follow X.Y.Z format. "
        "The engine uses this version directly. Re-registering with the same version "
        "and changed data is rejected — bump the version for any schema changes."
    )
    name: str = Field(description="Human-readable display name (e.g., 'Point Cloud Segmentation')")
    description: str = Field(description="What this node does")

    # Schema (JSON Schema - language agnostic)
    input_schema: dict[str, Any] = Field(
        description="JSON Schema for expected inputs",
    )
    output_schema: dict[str, Any] = Field(
        description="JSON Schema for expected outputs",
    )

    # Cost
    token_cost: float = Field(
        default=0.0,
        ge=0.0,
        description="Cost per execution (0.0 for free nodes)",
    )

    # Retry defaults
    default_retry: RetryConfig = Field(
        default_factory=RetryConfig,
        description="Default retry policy for this node type",
    )

    # Metadata
    category: str = Field(
        default="utility",
        description="Category (e.g., 'transform', 'inference', 'utility', 'control-flow')",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Maximum execution time in seconds",
    )
    role: WorkflowNodeRole = Field(
        default=WorkflowNodeRole.OPERATION,
        description="Node role in the workflow system",
    )

    # Styles (optional — frontend presentation)
    styles: WorkflowNodeStyles | None = Field(
        default=None,
        description="Icon and color for the workflow builder UI",
    )

    # Deprecation (optional — advisory migration signal; NOT node_status)
    deprecation: DeprecationInfo | None = Field(
        default=None,
        description="If set, this node is deprecated. Surfaced to workflow-definition "
        "authors as a migration signal; orthogonal to node_status (a deprecated node "
        "stays active until retired).",
    )

    # SDK compatibility range (optional — exported via registry constraints; DA-1955)
    minimum_sdk_version: str | None = Field(
        default=None,
        description="Minimum canvastekk-workflow-sdk version this node requires "
        "(X.Y.Z). Exported in the register payload constraints so the engine can "
        "flag incompatible hosts (drift report engine_compatible). DA-3359: "
        "legacy — superseded by the stamped `sdk_version`; dual-written in "
        "register payloads for one release and dropped in 0.38.",
    )
    maximum_sdk_version: str | None = Field(
        default=None,
        description="Maximum canvastekk-workflow-sdk version this node supports "
        "(X.Y.Z, inclusive). Exported in the register payload constraints.",
    )

    # DA-3359: SDK provenance is STAMPED, not declared. The stamp is computed
    # from the installed SDK version at instantiation; it is not a constructor
    # field (kwargs rejected) and the property is read-only (assignment
    # rejected) — manual overrides are impossible by construction.
    _sdk_version: str = PrivateAttr(default_factory=lambda: _stamped_sdk_version())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sdk_version(self) -> str:
        """Stamped SDK provenance (DA-3359): auto-filled from the installed
        SDK version, read-only. Exported in register payload constraints
        (with a legacy ``minimum_sdk_version`` dual-write for one release);
        the engine's admission gate dual-reads either key."""
        return self._sdk_version

    # Documentation links (optional — DA-1937 preview surface)
    docs_url: str | None = Field(
        default=None,
        description="HTTP(S) URL to this node's documentation.",
    )
    changelog_url: str | None = Field(
        default=None,
        description="HTTP(S) URL to this node's changelog.",
    )

    @model_serializer(mode="wrap")
    def _drop_optional_when_none(self, handler: Callable[[WorkflowNodeManifest], dict[str, Any]]) -> dict[str, Any]:
        """Serialize the manifest, omitting optional keys when they are None.

        Covers ``deprecation`` plus the DA-1955 optional fields
        (``minimum_sdk_version``/``maximum_sdk_version``/``docs_url``/
        ``changelog_url``). Nodes that do not set them serialize
        byte-identically to the pre-DA-1955 shape, which protects the
        ``/manifest`` endpoint and contract/stability consumers that compare
        serialized output. Covers every instance-serialization path
        (``to_dict`` / ``model_dump``); does not affect ``model_json_schema``.
        """
        data = handler(self)
        for optional_key in (
            "deprecation",
            "minimum_sdk_version",
            "maximum_sdk_version",
            "docs_url",
            "changelog_url",
        ):
            if data.get(optional_key) is None:
                data.pop(optional_key, None)
        return data

    @computed_field  # type: ignore[misc]
    @property
    def id(self) -> str:
        """Return the node identifier in the format 'slug-vversion'."""
        return f"{self.slug}-v{self.version}"

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_vocabulary(cls, data: Any) -> Any:
        """Resolve the legacy ``name``/``title`` construction vocabulary (DA-2627).

        The manifest's identity field is ``slug`` and its display field is ``name``.
        Because ``name`` changed meaning, compatibility is resolved here — at
        construction, deterministically — never on the wire:

        - ``slug`` absent AND both ``name`` and ``title`` present (legacy call):
          ``slug = name``, display ``name = title``, with a DeprecationWarning.
        - ``name`` only (no ``slug``, no ``title``): error — ambiguous in both
          vocabularies; the message disambiguates.
        - ``slug`` present AND ``title`` present: ``title`` is ignored with a
          warning (display comes from ``name``).
        - A ``slug ?? name`` fallback is deliberately NOT implemented: it would
          silently map a lowercase display name into identity.

        Raises:
            ValueError: On the ambiguous name-only construction.
        """
        if not isinstance(data, dict):
            return data

        has_slug = "slug" in data
        has_name = "name" in data
        has_title = "title" in data

        if not has_slug and has_name and has_title:
            warnings.warn(
                _LEGACY_DEPRECATION_MSG,
                DeprecationWarning,
                stacklevel=2,
            )
            data = dict(data)
            data["slug"] = data.pop("name")
            data["name"] = data.pop("title")
        elif not has_slug and has_name and not has_title:
            raise ValueError(
                f"Node manifest received name={data['name']!r} without slug or title — ambiguous. "
                "Identity goes in slug=; display goes in name=. "
                "(Legacy name=<slug>+title=<display> construction still works.)"
            )
        elif has_slug and has_title:
            warnings.warn(
                "NodeDefinition received both slug= and title=; title is ignored (display name comes from name=).",
                DeprecationWarning,
                stacklevel=2,
            )
            data = dict(data)
            data.pop("title", None)

        return data

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_PATTERN.fullmatch(v):
            raise ValueError(
                f"Node slug must be a lowercase slug (alphanumeric and hyphens only, no leading/trailing hyphens). Got: '{v}'"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(v):
            raise ValueError(f"Node version must be semantic version (X.Y.Z). Got: '{v}'")
        return v

    @field_validator("minimum_sdk_version", "maximum_sdk_version")
    @classmethod
    def _validate_sdk_versions(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _SEMVER_PATTERN.fullmatch(v):
            raise ValueError(f"SDK version bounds must be semantic version (X.Y.Z). Got: '{v}'")
        return v

    @field_validator("docs_url", "changelog_url")
    @classmethod
    def _validate_http_urls(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"URL must use http(s) scheme. Got: '{v}'")
        return v

    @property
    def file_input_fields(self) -> list[str]:
        """Return list of input field names that accept file uploads.

        A field is considered a file input if it has `format: "file"` in the input_schema properties.
        """
        properties = self.input_schema.get("properties", {})
        return [name for name, schema in properties.items() if schema.get("format") == "file"]

    @property
    def has_file_inputs(self) -> bool:
        """Return True if any input field accepts file uploads."""
        return len(self.file_input_fields) > 0

    @property
    def file_output_fields(self) -> list[str]:
        """Return list of output field names that produce files.

        A field is considered a file output if it has `format: "file"` in the output_schema properties.
        """
        properties = self.output_schema.get("properties", {})
        return [name for name, schema in properties.items() if schema.get("format") == "file"]

    def validate_file_input(self, field_name: str, file_path: Path) -> None:
        """Validate a downloaded file against x-* extensions on the schema.

        Call this after downloading a file input to validate constraints.

        Args:
            field_name: Name of the input field in input_schema.
            file_path: Path to the downloaded file.

        Raises:
            NodeValidationError: If the file fails validation.
        """
        properties = self.input_schema.get("properties", {})
        schema = properties.get(field_name, {})

        x_accept = schema.get("x-accept")
        if x_accept and file_path.suffix:
            # DA-3429: an empty suffix means the artifact carries no declarable
            # extension (e.g. DA-3339 emission keys named by field, or
            # Content-Disposition filenames without one). Skipping the check
            # here restores the pre-0.35 tolerance — the handler's own content
            # handling (e.g. ensure_las conversion) stays responsible for
            # correctness. Files with a real extension are still validated.
            if file_path.suffix.lower() not in [ext.lower() for ext in x_accept]:
                raise NodeValidationError(
                    f"File extension '{file_path.suffix}' is not allowed for field '{field_name}'. "
                    f"Allowed extensions: {x_accept}"
                )

        x_max_size = schema.get("x-maxSizeBytes")
        if x_max_size is not None:
            file_size = file_path.stat().st_size
            if file_size > x_max_size:
                raise NodeValidationError(
                    f"File size ({file_size} bytes) exceeds maximum size ({x_max_size} bytes) for field '{field_name}'"
                )

    @model_validator(mode="after")
    def _validate_file_field_formats(self) -> WorkflowNodeManifest:
        """Validate that file fields use format: "file" and type: "string"."""
        schemas_to_check = [
            ("input_schema", self.input_schema),
            ("output_schema", self.output_schema),
        ]

        for schema_name, schema in schemas_to_check:
            properties = schema.get("properties", {})
            for name, prop_schema in properties.items():
                field_format = prop_schema.get("format")
                field_type = prop_schema.get("type")

                if field_format == "binary":
                    raise ValueError(
                        f"Field '{name}' uses format 'binary' which is no longer supported. "
                        f"Use format 'file' instead. (See DA-894 migration guide.)"
                    )

                if field_format == "file" and field_type != "string":
                    raise ValueError(
                        f"Field '{name}' has format 'file' but type is '{field_type}'. "
                        f"File fields must have type 'string'."
                    )

        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


def export_definition(
    definition: WorkflowNodeManifest,
    output_path: str | Path,
    *,
    invoke_type: InvokeType = "http",
    invoke_url: str | None = None,
    node_status: str = "active",
    tags: list[str] | None = None,
    styles: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> Path:
    """
    Export a WorkflowNodeManifest as a full node-manifest JSON file.

    DA-1955: the output is the FULL manifest shape (includes ``node_role``,
    ``retry``, ``node_status``) consumed by the node's ``/manifest``
    endpoint and the engine's SDKNodeDefinition model. It is NOT a valid
    body for ``POST /api/workflows/nodes/`` (that request schema is
    ``extra="forbid"`` without those fields) — use ``register_node()`` for the
    HTTP registration path, which emits the aligned payload. ``deprecation``
    is the one overlap: it is an accepted engine register field (DA-2305) and
    is emitted by ``build_registry_payload`` itself, so it needs no re-adding
    here.

    Maps SDK WorkflowNodeManifest fields to the registry schema and writes the result
    as a clean JSON file.

    Field mapping:
        WorkflowNodeManifest.name (display) -> label
        WorkflowNodeManifest.slug -> registry identity (via build_registry_payload)
        WorkflowNodeManifest.default_retry -> retry
        WorkflowNodeManifest.id (computed, slug-derived) -> intentionally omitted; registry derives its own identifier
        WorkflowNodeManifest.version -> included as the node's semantic version; same version + changed data is rejected by the engine

    Args:
        definition: The SDK WorkflowNodeManifest to export.
        output_path: File path to write the JSON output.
        invoke_type: Invocation type (http, lambda, sagemaker, in-process).
        invoke_url: URL/ARN for invoking the node. None for in-process nodes.
        node_status: Registry status (active, inactive, dead).
        tags: Searchable tags for the registry.
        styles: Presentation metadata (icon, color). Overrides definition.styles if provided.
        constraints: Resource/compatibility constraints (placeholder).

    Returns:
        The resolved Path where the file was written.
    """
    from canvastekk_workflow_sdk.registry import build_registry_payload

    output_path = Path(output_path)

    registry_dict = build_registry_payload(
        definition,
        invoke_type=invoke_type,
        invoke_url=invoke_url,
        tags=tags,
        constraints=constraints,
        node_status=node_status,
    )

    # DA-1955: full manifest shape. The exported file targets the node's
    # /manifest endpoint format (SDKNodeDefinition, extra-tolerant), not the
    # engine's extra="forbid" registration request — re-add registry-only keys.
    registry_dict["node_role"] = definition.role.value
    registry_dict["retry"] = definition.default_retry.model_dump(mode="json")
    registry_dict["node_status"] = node_status

    if styles is not None:
        registry_dict["styles"] = styles

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(registry_dict, indent=2) + "\n")
    return output_path
