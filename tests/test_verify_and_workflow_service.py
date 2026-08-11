"""
The two endpoints that act on a node after it was uploaded.

`verify_node` backs POST /upload/verify/{node_id}, `set_workflow` backs
POST /workflow/{node_id}. Both were reachable only against a live repository and
had no test at all — 0% of either method was executed by the suite. What they
promise is written down in the README, and that is what these tests pin, not
whatever the implementation happens to do.
"""

import json

import httpx
import pytest

from src.services import repository_service as repo_module
from src.services.repository_service import RepositoryService

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class _RoutedClient:
    """
    Answers by URL fragment, and records every call.

    Configured per test through the class attributes, because the service
    constructs its own AsyncClient and hands us no seam to inject one.
    """

    calls: list = []
    node_properties: dict = {}
    node_status: int = 200
    workflow_put_status: int = 200
    workflow_history: object = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _record(self, method, url, headers, json_body=None):
        type(self).calls.append(
            {
                "method": method,
                "url": url,
                "auth": (headers or {}).get("Authorization"),
                "json": json_body,
            }
        )

    async def get(self, url, headers=None):
        self._record("GET", url, headers)
        if "/workflow" in url:
            return _Response(200, type(self).workflow_history or [])
        return _Response(
            type(self).node_status,
            {"node": {"properties": type(self).node_properties, "aspects": []}},
        )

    async def put(self, url, headers=None, json=None):
        self._record("PUT", url, headers, json)
        return _Response(type(self).workflow_put_status, {})


@pytest.fixture
def routed(monkeypatch):
    _RoutedClient.calls = []
    _RoutedClient.node_properties = {}
    _RoutedClient.node_status = 200
    _RoutedClient.workflow_put_status = 200
    _RoutedClient.workflow_history = None
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _RoutedClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)
    return _RoutedClient


def _service():
    return RepositoryService("upload-user", "secret")


# ----------------------------------------------------------------- verify_node


@pytest.mark.asyncio
async def test_repository_properties_are_returned_flat(routed):
    """edu-sharing answers with arrays; the report shows plain values."""
    routed.node_properties = {"cclom:title": ["Workshop KI"]}

    result = await _service().verify_node(NODE_ID)

    assert result["success"] is True
    assert result["node_id"] == NODE_ID
    assert result["actual_metadata"] == {"cclom:title": "Workshop KI"}


@pytest.mark.asyncio
async def test_without_expected_metadata_no_diff_is_reported(routed):
    """README: 'Ohne Body werden nur die aktuellen Metadaten gelesen (kein Diff)'."""
    routed.node_properties = {"cclom:title": ["Workshop KI"]}

    result = await _service().verify_node(NODE_ID)

    assert "diff" not in result
    assert "summary" not in result


@pytest.mark.asyncio
async def test_expected_metadata_produces_a_diff_and_a_summary(routed):
    routed.node_properties = {"cclom:title": ["Workshop KI"]}

    result = await _service().verify_node(
        NODE_ID,
        expected_metadata={
            "contextName": "default",
            "schemaVersion": "2.0.0",
            "metadataset": "core.json",
            "cclom:title": "Workshop KI",
        },
        context="default",
        version="2.0.0",
    )

    assert result["summary"]["match"] == 1
    assert {"field_id": "cclom:title", "status": "match"}.items() <= result["diff"][
        0
    ].items()


@pytest.mark.asyncio
async def test_the_read_carries_the_service_account(routed):
    """Inbox nodes are not readable anonymously — without auth this is a 403."""
    await _service().verify_node(NODE_ID)

    assert routed.calls[0]["auth"] is not None
    assert routed.calls[0]["auth"].startswith("Basic ")


@pytest.mark.asyncio
async def test_a_failed_read_is_reported_as_an_error_not_as_an_empty_result(routed):
    """An empty actual_metadata would read as 'the repository lost everything'."""
    routed.node_status = 404

    result = await _service().verify_node(NODE_ID)

    assert result["success"] is False
    assert "404" in result["error"]
    assert "actual_metadata" not in result


# ---------------------------------------------------------------- set_workflow


@pytest.mark.asyncio
async def test_every_step_is_set_in_the_given_order(routed):
    steps = ["120_METADATA_QUALITY_CONFIRMED", "150_PUBLISH_IN_SEARCH"]

    result = await _service().set_workflow(NODE_ID, steps)

    written = [c["json"]["status"] for c in routed.calls if c["method"] == "PUT"]
    assert written == steps
    assert result["success"] is True
    assert [s["status"] for s in result["steps"]] == steps


@pytest.mark.asyncio
async def test_the_resulting_state_is_read_back_from_the_node(routed):
    """The caller must see the state that actually stuck, not the one we sent."""
    routed.node_properties = {"ccm:wf_status": ["150_PUBLISH_IN_SEARCH"]}

    result = await _service().set_workflow(NODE_ID, ["150_PUBLISH_IN_SEARCH"])

    assert result["current_status"] == "150_PUBLISH_IN_SEARCH"


@pytest.mark.asyncio
async def test_the_history_is_returned_when_the_repository_has_one(routed):
    routed.workflow_history = [{"status": "200_tocheck", "editor": "upload-user"}]

    result = await _service().set_workflow(NODE_ID, ["120_METADATA_QUALITY_CONFIRMED"])

    assert result["history"] == routed.workflow_history


@pytest.mark.asyncio
async def test_a_rejected_step_names_itself_in_the_error(routed):
    routed.workflow_put_status = 403

    result = await _service().set_workflow(NODE_ID, ["150_PUBLISH_IN_SEARCH"])

    assert result["success"] is False
    assert "150_PUBLISH_IN_SEARCH" in result["error"]


@pytest.mark.asyncio
async def test_the_response_links_to_the_node_in_the_repository(routed):
    result = await _service().set_workflow(NODE_ID, ["120_METADATA_QUALITY_CONFIRMED"])

    assert result["repositoryUrl"].endswith(f"/components/render/{NODE_ID}")


@pytest.mark.asyncio
async def test_an_unreachable_repository_is_an_error_not_an_exception(
    routed, monkeypatch
):
    """
    The connection itself fails, so nothing gets as far as a single request —
    only set_workflow's own handler can turn this into an answer. A failing PUT
    would not reach it: run_workflow_steps catches that per step.
    """

    async def _no_connection(self):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(_RoutedClient, "__aenter__", _no_connection)

    result = await _service().set_workflow(NODE_ID, ["150_PUBLISH_IN_SEARCH"])

    assert result["success"] is False
    assert result["nodeId"] == NODE_ID
    assert "Verbindung zum Repository fehlgeschlagen" in result["error"]


@pytest.mark.asyncio
async def test_a_timeout_while_advancing_the_workflow_is_reported(routed, monkeypatch):
    async def _too_slow(self):
        raise httpx.TimeoutException("took too long")

    monkeypatch.setattr(_RoutedClient, "__aenter__", _too_slow)

    result = await _service().set_workflow(NODE_ID, ["150_PUBLISH_IN_SEARCH"])

    assert result["success"] is False
    assert "Timeout" in result["error"]


@pytest.mark.asyncio
async def test_a_failing_verify_read_is_reported_as_an_error(routed, monkeypatch):
    """/upload/verify must answer even when the repository is unreachable."""

    async def _no_connection(self):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(_RoutedClient, "__aenter__", _no_connection)

    result = await _service().verify_node(NODE_ID)

    assert result["success"] is False
    assert "ConnectError" in result["error"]


@pytest.mark.asyncio
async def test_a_slow_verify_read_times_out_with_a_message(routed, monkeypatch):
    async def _too_slow(self):
        raise httpx.TimeoutException("took too long")

    monkeypatch.setattr(_RoutedClient, "__aenter__", _too_slow)

    result = await _service().verify_node(NODE_ID)

    assert result["success"] is False
    assert "Timeout" in result["error"]
