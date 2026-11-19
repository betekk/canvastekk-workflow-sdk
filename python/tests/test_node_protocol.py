"""Node protocol 2 (engine#1300): negotiated SUCCEEDED / FAILED outcomes."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import NodeExecutionContext
from canvastekk_workflow_sdk.exceptions import NodeValidationError
from canvastekk_workflow_sdk.node_call_protocol import (
    NODE_CALL_PROTOCOL_HEADER,
    NODE_CALL_PROTOCOL_VERSION,
    node_call_outcome_for_protocol,
    read_node_call_outcome,
    requested_node_call_protocol,
)
from canvastekk_workflow_sdk.node_io_data_contracts import WorkflowNodeCallOutcome, parse_workflow_node_call_outcome
from canvastekk_workflow_sdk.workflow.node_executor import HttpNodeExecutor
from canvastekk_workflow_sdk.workflow_node_app import create_workflow_node_app
from tests.test_app import EchoNode, FailingNode

_BODY = {"run_id": "r", "node_id": "n", "inputs": {"message": "hi"}}


@pytest.mark.parametrize(
    ("header", "protocol"),
    [(None, 1), ("1", 1), ("2", 2), (" 2 ", 2), ("3", NODE_CALL_PROTOCOL_VERSION), ("0", 1), ("two", 1), ("", 1)],
)
def test_requested_protocol(header: str | None, protocol: int) -> None:
    assert requested_node_call_protocol(header) == protocol


def test_outcomes_translate_only_under_protocol_2() -> None:
    assert [node_call_outcome_for_protocol(s, 2) for s in ("pass", "fail", "pending")] == ["SUCCEEDED", "FAILED", "ACCEPTED"]
    assert [node_call_outcome_for_protocol(s, 1) for s in ("pass", "fail", "pending")] == ["pass", "fail", "pending"]


@pytest.mark.parametrize(
    ("wire", "legacy"),
    [("pass", "pass"), ("SUCCEEDED", "pass"), ("succeeded", "pass"), ("FAILED", "fail"), ("ACCEPTED", "pending")],
)
def test_read_outcome_accepts_both_protocols(wire: str, legacy: str) -> None:
    assert read_node_call_outcome(wire) == legacy


def test_read_outcome_unknown() -> None:
    assert read_node_call_outcome("skipped") is None
    assert read_node_call_outcome(None) is None


def test_execute_answers_protocol_2_words_only_when_asked() -> None:
    client = TestClient(create_workflow_node_app(EchoNode()))

    old = client.post("/execute", json=_BODY)
    new = client.post("/execute", json=_BODY, headers={NODE_CALL_PROTOCOL_HEADER: "2"})

    assert old.json()["status"] == "pass"
    assert new.json()["status"] == "SUCCEEDED"
    assert new.json()["outputs"] == old.json()["outputs"] == {"message": "hi"}


def test_a_failing_node_answers_failed_under_protocol_2() -> None:
    client = TestClient(create_workflow_node_app(FailingNode()))

    assert client.post("/execute", json=_BODY).json()["status"] == "fail"
    assert client.post("/execute", json=_BODY, headers={NODE_CALL_PROTOCOL_HEADER: "2"}).json()["status"] == "FAILED"


def test_strict_parser_reads_exact_protocol_2_results() -> None:
    assert parse_workflow_node_call_outcome("SUCCEEDED") is WorkflowNodeCallOutcome.PASS
    assert parse_workflow_node_call_outcome("FAILED") is WorkflowNodeCallOutcome.FAIL
    for bad in ("ACCEPTED", "succeeded", "Failed"):
        with pytest.raises(NodeValidationError):
            parse_workflow_node_call_outcome(bad)


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "succeeds"), [("SUCCEEDED", True), ("pass", True), ("FAILED", False)])
async def test_http_executor_sends_the_header_and_reads_both(status: str, succeeds: bool) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"execution_id": "e", "status": status, "outputs": {"x": 1}, "error": "boom"})

    executor = HttpNodeExecutor(retries=0).register_url("echo", "http://node.example")
    executor._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    context = NodeExecutionContext(run_id="r", node_id="n")

    if succeeds:
        assert await executor.execute("echo", {}, context) == {"x": 1}
    else:
        with pytest.raises(RuntimeError, match="boom"):
            await executor.execute("echo", {}, context)
    assert seen[0].headers[NODE_CALL_PROTOCOL_HEADER] == "2"
    assert json.loads(seen[0].content)["run_id"] == "r"
