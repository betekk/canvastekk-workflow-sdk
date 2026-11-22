"""CheckNodeBase: every check node runs measure → verdict → write (#283, D91).

A check node writes one method, :meth:`CheckNodeBase.measure`. The SDK owns
the rest and a subclass cannot replace it:

1. **measure** (the node): geometry, selection, filters → :class:`Reading`\\ s.
2. **verdict** (the SDK): :func:`rules_from_inputs` + :func:`judge` — rounding,
   operators, tolerance, bounds, alternative readings, per-subject counts,
   roll-up.
3. **write** (the SDK): the result file (layout 1.1.0, ``model_check.check``
   1.0.0) plus the inline outputs ``verdict``, ``verdict_counts`` and
   ``requirement_verdicts`` (D91b).

``result_body_format = "legacy"`` keeps the verdict step but hands writing
to :meth:`write_legacy_result`, so a node can switch its calculation before
it switches its file format (D91a).

Example::

    class BeamLengthNode(CheckNodeBase):
        manifest = WorkflowNodeManifest(..., checks={"beam_length": {"label": "Beam length", "unit": "mm"}})

        def measure(self, inputs, context):
            return [Reading.value("beam_length", subject_id=b.gid, actual=b.length_mm) for b in beams(inputs)]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Literal

from canvastekk_workflow_sdk.check_verdict import (
    CHECK_RESULT_SCHEMA,
    CHECK_RESULT_SCHEMA_VERSION,
    CheckVerdictError,
    JudgedResult,
    Reading,
    VerdictPolicy,
    judge,
    marked_input_values,
    marked_inputs,
    rules_from_inputs,
)
from canvastekk_workflow_sdk.node_execution_context import NodeExecutionContext
from canvastekk_workflow_sdk.result_file import (
    RESULT_FILE_DEFAULT_NAME,
    RESULT_FILE_VERSION_1_1_0,
    write_result_file,
)
from canvastekk_workflow_sdk.workflow_node_base import WorkflowNodeBase

PROGRESS_STEPS: tuple[tuple[float, str], ...] = ((0.05, "Measuring"), (0.85, "Judging"), (0.95, "Writing result"))
"""Progress pings the fixed steps send (fraction, message)."""


class CheckNodeBase(WorkflowNodeBase, ABC):
    """Base class for check nodes. Implement :meth:`measure` only."""

    _is_check_node: ClassVar[bool] = True

    result_body_format: ClassVar[Literal["1.0.0", "legacy"]] = "1.0.0"
    """``"1.0.0"``: the SDK writes layout 1.1.0 with the ``model_check.check`` 1.0.0 body.
    ``"legacy"``: the SDK judges, then :meth:`write_legacy_result` writes the file."""

    result_file_name: ClassVar[str] = RESULT_FILE_DEFAULT_NAME

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuse an ``execute`` override and a manifest without ``checks``."""
        if "execute" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must not override execute(): CheckNodeBase owns measure → verdict → write. "
                "Implement measure() only."
            )
        super().__init_subclass__(**kwargs)
        if ABC in cls.__bases__:
            return
        manifest = cls.manifest
        if not getattr(manifest, "checks", None):
            raise TypeError(f"{cls.__name__}.manifest must declare a non-empty 'checks' map")
        if cls.result_body_format not in ("1.0.0", "legacy"):
            raise TypeError(f"{cls.__name__}.result_body_format must be '1.0.0' or 'legacy'")

    @abstractmethod
    def measure(self, inputs: dict[str, Any], context: NodeExecutionContext) -> Sequence[Reading]:
        """Measure the model and return one :class:`Reading` per judged row.

        Args:
            inputs: The validated inputs (file inputs already downloaded).
            context: The execution context.

        Returns:
            Readings; observations and scope rows may ride along.
        """
        ...

    def body_extra(
        self,
        judged: JudgedResult,
        inputs: dict[str, Any],
        context: NodeExecutionContext,
    ) -> dict[str, Any] | None:
        """Return the check's viewer evidence, written as the body's top-level ``extra`` (#285).

        Readers show it as the check's evidence (the frontend reads it as the
        0.x ``result``, with ``measurements`` and ``instances`` inside it). It
        never decides a verdict. ``None`` (the default) writes no ``extra``.

        Args:
            judged: The SDK's verdicts.
            inputs: The validated inputs.
            context: The execution context.

        Returns:
            A JSON object, or ``None``.
        """
        return None

    def verdict_policy(self) -> VerdictPolicy | None:
        """Return the app's reading rules (e.g. allowed NOT_EVALUABLE codes); none by default."""
        return None

    def write_legacy_result(
        self,
        judged: JudgedResult,
        inputs: dict[str, Any],
        context: NodeExecutionContext,
    ) -> dict[str, Any]:
        """Write the result file in the node's previous format (``result_body_format = "legacy"``).

        Args:
            judged: The SDK's verdicts.
            inputs: The validated inputs.
            context: The execution context.

        Returns:
            Node outputs including ``result_file``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} sets result_body_format='legacy' but does not implement write_legacy_result()"
        )

    def judge_readings(self, inputs: dict[str, Any], readings: Sequence[Reading]) -> JudgedResult:
        """Run the SDK verdict step on readings (exposed for golden-parity tests)."""
        manifest = self.manifest
        return judge(
            rules_from_inputs(manifest.input_schema, inputs),
            readings,
            manifest.checks or {},
            policy=self.verdict_policy(),
        )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        """Run measure → verdict → write. Fixed; subclasses implement :meth:`measure`."""
        (measure_at, measure_msg), (judge_at, judge_msg), (write_at, write_msg) = PROGRESS_STEPS
        context.report_progress(measure_at, measure_msg)
        readings = list(self.measure(inputs, context))
        if not all(isinstance(r, Reading) for r in readings):
            raise CheckVerdictError(f"{type(self).__name__}.measure() must return Reading objects")
        context.report_progress(judge_at, judge_msg)
        judged = self.judge_readings(inputs, readings)
        context.report_progress(write_at, write_msg)
        if self.result_body_format == "legacy":
            outputs = dict(self.write_legacy_result(judged, inputs, context))
        else:
            outputs = write_result_file(
                context,
                result_schema=CHECK_RESULT_SCHEMA,
                result_schema_version=CHECK_RESULT_SCHEMA_VERSION,
                body=judged.body(extra=self.body_extra(judged, inputs, context)),
                summary=judged.summary(),
                filename=self.result_file_name,
                result_file_version=RESULT_FILE_VERSION_1_1_0,
                inputs=marked_input_values(self.manifest.input_schema, inputs),
                verdict=judged.verdict,
            )
        for key, value in judged.inline_outputs().items():
            outputs.setdefault(key, value)
        return outputs


def check_node_conformance_errors(node_cls: type) -> list[str]:
    """Return verdict-standard problems with a node class (empty = conforms).

    Rule: a node whose manifest marks an input with ``x-verdict`` must be a
    :class:`CheckNodeBase` subclass, and a check node must declare ``checks``.

    Args:
        node_cls: A node class.

    Returns:
        Human-readable problems.
    """
    manifest = getattr(node_cls, "manifest", None)
    if manifest is None:
        return [f"{getattr(node_cls, '__name__', node_cls)!s} has no manifest"]
    problems: list[str] = []
    is_check = isinstance(node_cls, type) and issubclass(node_cls, CheckNodeBase)
    if marked_inputs(manifest.input_schema) and not is_check:
        problems.append(f"{node_cls.__name__} marks inputs with x-verdict but does not subclass CheckNodeBase")
    if is_check and not getattr(manifest, "checks", None):
        problems.append(f"{node_cls.__name__} is a CheckNodeBase without a 'checks' map")
    return problems


__all__ = ["PROGRESS_STEPS", "CheckNodeBase", "check_node_conformance_errors"]
