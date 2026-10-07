"""Tests for NodeExecutionRequest validation."""


class TestSlugValidation:
    """run_id/node_id slug constraints (DA-1711 3.1) — ids flow into
    /tmp/{run_id}/{node_id} paths, so traversal payloads must be rejected
    at the validation layer."""

    def test_dotdot_run_id_rejected(self) -> None:
        import pytest

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        with pytest.raises(Exception):
            NodeExecutionRequest(run_id="../../etc", node_id="n1", inputs={})

    def test_dotdot_node_id_rejected(self) -> None:
        import pytest

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        with pytest.raises(Exception):
            NodeExecutionRequest(run_id="r1", node_id="..", inputs={})

    def test_absolute_ish_id_rejected(self) -> None:
        import pytest

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        with pytest.raises(Exception):
            NodeExecutionRequest(run_id="/abs/path", node_id="n1", inputs={})

    def test_valid_slug_accepted(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(run_id="run-abc.123_x", node_id="node.1-y", inputs={})
        assert req.run_id == "run-abc.123_x"


class TestAccountIdField:
    """DA-2242: optional, bounded account_id transport field."""

    def test_defaults_to_none(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        assert req.account_id is None

    def test_accepts_int(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, account_id=42)
        assert req.account_id == 42

    def test_rejects_zero_negative_and_int64_overflow(self) -> None:
        import pytest
        from pydantic import ValidationError

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        for bad in (0, -1, 2**63):
            with pytest.raises(ValidationError):
                NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, account_id=bad)

    def test_unknown_body_keys_still_ignored(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, future_field="x")
        assert req.account_id is None


class TestExecutionIdField:
    """#3498: optional dispatcher-minted execution id — pings must carry the
    id the engine parked, else the forgery guard 403s every ping."""

    def test_defaults_to_none(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})
        assert req.execution_id is None

    def test_accepts_ecs_uuid(self) -> None:
        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        req = NodeExecutionRequest(
            run_id="r1", node_id="n1", inputs={},
            execution_id="ecs-0f2c6a1e-0000-4000-8000-000000000000",
        )
        assert req.execution_id.startswith("ecs-")

    def test_rejects_non_slug_charset(self) -> None:
        import pytest
        from pydantic import ValidationError

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        with pytest.raises(ValidationError):
            NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, execution_id="has space")

    def test_rejects_dot_segments_like_ts_slugfield(self) -> None:
        """#3498 review: python and TS legs must validate execution_id
        identically — TS slugField refines dot segments; python mirrors."""
        import pytest
        from pydantic import ValidationError

        from canvastekk_workflow_sdk.request import NodeExecutionRequest

        with pytest.raises(ValidationError):
            NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, execution_id="a..b")
