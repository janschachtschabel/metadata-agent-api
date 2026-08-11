"""
Upload-time collection references and the step-by-step review workflow.

The review workflow is walked one state at a time on purpose: edu-sharing
records every PUT as its own history entry with the acting user, which is what
makes "who confirmed the quality?" answerable later. These tests pin that one
request goes out per step, in order, and that an unknown state is refused before
it can reach the repository.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src import main
from src.models.schemas import UploadRequest, WorkflowRequest
from src.services.repository_curation import (
    DEFAULT_WORKFLOW_RECEIVER,
    DEFAULT_WORKFLOW_STATUS,
    extract_collection_ids,
    extract_id_from_url,
    run_workflow_steps,
)

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"
COLLECTION_ID = "3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"


# ---------------------------------------------------------------- collections


@pytest.mark.parametrize(
    "value",
    [
        COLLECTION_ID,
        f"  {COLLECTION_ID}  ",
        f"https://repository.staging.openeduhub.net/edu-sharing/components/collections?id={COLLECTION_ID}&mainnav=true",
        f"https://redaktion.openeduhub.net/edu-sharing/components/collections/{COLLECTION_ID}",
        f"https://redaktion.openeduhub.net/edu-sharing/components/collections/{COLLECTION_ID}/",
    ],
)
def test_collection_id_is_extracted_from_what_users_paste(value):
    assert extract_id_from_url(value) == COLLECTION_ID


def test_a_list_is_required():
    assert UploadRequest(
        metadata={}, collection_id=[COLLECTION_ID, "second"]
    ).collection_id == [COLLECTION_ID, "second"]


def test_a_bare_id_is_rejected():
    """
    One shape for one field. The other list parameters of this endpoint —
    workflow_steps, workflow_receiver — take a list and nothing else; accepting
    a bare string here as well would make the request format a matter of which
    parameter you happen to be filling in.
    """
    with pytest.raises(ValidationError):
        UploadRequest(metadata={}, collection_id=COLLECTION_ID)


@pytest.mark.parametrize("value", [None, [], ["", "  "]])
def test_empty_collection_id_stays_absent(value):
    """An empty list is unambiguous — omitting the field means the same thing."""
    assert UploadRequest(metadata={}, collection_id=value).collection_id is None


def test_the_schema_declares_an_array_and_nothing_else():
    """
    A generated client only ever sends what the schema declares. As long as the
    schema still offers 'string', clients will send one.
    """
    collection_id = UploadRequest.model_json_schema()["properties"]["collection_id"]
    types = {variant.get("type") for variant in collection_id.get("anyOf", [])}

    assert "array" in types
    assert "string" not in types


def test_requested_collections_come_first_and_duplicates_are_dropped():
    ids = extract_collection_ids(
        {
            "virtual:collection_id_primary": "primary",
            "ccm:collection_id": ["extra", "primary"],
        },
        [COLLECTION_ID, "primary"],
    )

    assert ids == [COLLECTION_ID, "primary", "extra"]


# ------------------------------------------------------------------ workflow


class _RecordingClient:
    """Captures the PUTs the workflow makes instead of talking to a repository."""

    class _Response:
        status_code = 200
        text = ""

    def __init__(self):
        self.puts = []

    async def put(self, url, headers=None, json=None):
        self.puts.append({"url": url, "json": json})
        return self._Response()


@pytest.mark.asyncio
async def test_every_step_is_a_separate_request_in_order():
    client = _RecordingClient()

    result = await run_workflow_steps(
        client,
        "Basic test",
        "https://repo.example/edu-sharing",
        NODE_ID,
        [DEFAULT_WORKFLOW_STATUS, "140_ELEMENT_LEGALLY_APPROVED"],
    )

    assert result["success"] is True
    assert [step["status"] for step in result["steps"]] == [
        DEFAULT_WORKFLOW_STATUS,
        "140_ELEMENT_LEGALLY_APPROVED",
    ]
    assert [put["json"]["status"] for put in client.puts] == [
        DEFAULT_WORKFLOW_STATUS,
        "140_ELEMENT_LEGALLY_APPROVED",
    ]
    assert all(
        put["url"].endswith(f"/nodes/-home-/{NODE_ID}/workflow") for put in client.puts
    )


@pytest.mark.asyncio
async def test_only_the_handover_step_notifies_the_upload_managers():
    """The editorial states are recorded on the acting user, not sent onward."""
    client = _RecordingClient()

    await run_workflow_steps(
        client,
        "Basic test",
        "https://repo.example/edu-sharing",
        NODE_ID,
        [DEFAULT_WORKFLOW_STATUS, "140_ELEMENT_LEGALLY_APPROVED"],
    )

    handover, approved = client.puts
    assert handover["json"]["receiver"] == [
        {"authorityName": name} for name in DEFAULT_WORKFLOW_RECEIVER
    ]
    assert approved["json"]["receiver"] == []


@pytest.mark.asyncio
async def test_the_payload_carries_nothing_edu_sharing_does_not_know():
    """
    WorkflowHistory rejects unknown fields with 400
    (UnrecognizedPropertyException) and the state is then never set. A stray
    'logLevel' did exactly that — silently, because nobody read the result.
    Keep the body to the three fields the endpoint accepts.
    """
    client = _RecordingClient()

    await run_workflow_steps(
        client,
        "Basic test",
        "https://repo.example/edu-sharing",
        NODE_ID,
        ["200_tocheck"],
    )

    assert set(client.puts[0]["json"]) == {"receiver", "comment", "status"}


@pytest.mark.asyncio
async def test_an_explicit_receiver_overrides_the_default():
    client = _RecordingClient()

    await run_workflow_steps(
        client,
        "Basic test",
        "https://repo.example/edu-sharing",
        NODE_ID,
        ["140_ELEMENT_LEGALLY_APPROVED"],
        comment="geprüft",
        receiver=["GROUP_ORG_WLO-Redaktion"],
    )

    assert client.puts[0]["json"]["receiver"] == [
        {"authorityName": "GROUP_ORG_WLO-Redaktion"}
    ]
    assert client.puts[0]["json"]["comment"] == "geprüft"


@pytest.mark.asyncio
async def test_a_failing_step_does_not_hide_the_remaining_ones():
    class _FailingClient(_RecordingClient):
        class _Response:
            status_code = 403
            text = "forbidden"

        async def put(self, url, headers=None, json=None):
            self.puts.append({"url": url, "json": json})
            return self._Response()

    client = _FailingClient()

    result = await run_workflow_steps(
        client,
        "Basic test",
        "https://repo.example/edu-sharing",
        NODE_ID,
        [DEFAULT_WORKFLOW_STATUS, "140_ELEMENT_LEGALLY_APPROVED"],
    )

    assert result["success"] is False
    assert len(result["steps"]) == 2
    assert all(step["success"] is False for step in result["steps"])
    assert "403" in result["steps"][0]["error"]


def test_workflow_request_accepts_a_single_status():
    assert WorkflowRequest(steps="140_ELEMENT_LEGALLY_APPROVED").steps == [
        "140_ELEMENT_LEGALLY_APPROVED"
    ]


@pytest.mark.parametrize(
    "steps",
    [["140_ELEMENT_LEGALY_APPROVED"], ["quatsch"], [DEFAULT_WORKFLOW_STATUS, "nope"]],
)
def test_unknown_status_is_refused(steps):
    with pytest.raises(ValueError):
        WorkflowRequest(steps=steps)

    with pytest.raises(ValueError):
        UploadRequest(metadata={}, workflow_steps=steps)


def test_an_empty_step_list_is_refused_instead_of_silently_defaulting():
    """
    An empty list reads as "run no steps", but falling back to the default would
    hand the node to the editorial queue — the opposite. 'start_workflow: false'
    says it unambiguously, so the ambiguous spelling is rejected.
    """
    with pytest.raises(ValueError):
        UploadRequest(metadata={}, workflow_steps=[])


# -------------------------------------------------------------- endpoint wiring


class _StubRepositoryService:
    """Stands in for the repository; records how it was called."""

    _auth_header = "Basic stub"

    def __init__(self):
        self.upload_calls = []
        self.workflow_calls = []

    async def upload_metadata(self, **kwargs):
        self.upload_calls.append(kwargs)
        return {
            "success": True,
            "node": {"nodeId": NODE_ID},
            "fields_written": 1,
            "fields_skipped": 0,
            "collections": [{"collectionId": COLLECTION_ID, "success": True}],
            "workflow": [{"status": DEFAULT_WORKFLOW_STATUS, "success": True}],
        }

    async def set_workflow(self, node_id, steps, comment=None, receiver=None):
        self.workflow_calls.append(
            {
                "node_id": node_id,
                "steps": steps,
                "comment": comment,
                "receiver": receiver,
            }
        )
        return {
            "success": True,
            "nodeId": node_id,
            "steps": [{"status": s, "success": True} for s in steps],
            "current_status": steps[-1],
            "history": [{"status": steps[-1], "editor": "gast"}],
            "repositoryUrl": f"https://repo.example/components/render/{node_id}",
        }


@pytest.fixture
def client(monkeypatch):
    stub = _StubRepositoryService()
    monkeypatch.setattr(main, "get_repository_service", lambda: stub)
    with TestClient(main.app) as test_client:
        test_client.stub = stub
        yield test_client


def test_upload_forwards_collection_and_workflow_options(client):
    response = client.post(
        "/upload",
        json={
            "cclom:title": "Titel",
            "collection_id": [COLLECTION_ID],
            "workflow_steps": [DEFAULT_WORKFLOW_STATUS, "140_ELEMENT_LEGALLY_APPROVED"],
            "workflow_comment": "",
            "workflow_receiver": [],
        },
    )

    assert response.status_code == 200
    call = client.stub.upload_calls[0]
    assert call["collection_ids"] == [COLLECTION_ID]
    assert call["workflow_steps"] == [
        DEFAULT_WORKFLOW_STATUS,
        "140_ELEMENT_LEGALLY_APPROVED",
    ]
    assert call["workflow_comment"] == ""
    assert call["workflow_receiver"] == []
    # the upload options must not leak into the metadata written to the node
    assert "collection_id" not in call["metadata"]
    assert "workflow_steps" not in call["metadata"]


def test_upload_reports_collection_and_workflow_results(client):
    response = client.post(
        "/upload", json={"cclom:title": "Titel", "collection_id": [COLLECTION_ID]}
    )

    body = response.json()
    assert body["collections"] == [
        {"collectionId": COLLECTION_ID, "success": True, "error": None}
    ]
    assert body["workflow"] == [
        {"status": DEFAULT_WORKFLOW_STATUS, "success": True, "error": None}
    ]


def test_the_endpoint_refuses_a_bare_collection_id(client):
    """422 at the boundary, not a coerced guess about what was meant."""
    response = client.post(
        "/upload", json={"cclom:title": "Titel", "collection_id": COLLECTION_ID}
    )

    assert response.status_code == 422
    assert "collection_id" in response.text


def test_upload_without_collections_keeps_the_previous_response_shape(client):
    client.post("/upload", json={"cclom:title": "Titel"})

    call = client.stub.upload_calls[0]
    assert call["collection_ids"] is None
    assert call["workflow_steps"] is None


def test_workflow_endpoint_runs_the_requested_steps(client):
    response = client.post(
        f"/workflow/{NODE_ID}",
        json={"steps": ["140_ELEMENT_LEGALLY_APPROVED"], "comment": ""},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["current_status"] == "140_ELEMENT_LEGALLY_APPROVED"
    assert body["history"] == [
        {"status": "140_ELEMENT_LEGALLY_APPROVED", "editor": "gast"}
    ]
    assert client.stub.workflow_calls[0]["steps"] == ["140_ELEMENT_LEGALLY_APPROVED"]


def test_workflow_endpoint_refuses_an_unknown_status(client):
    response = client.post(f"/workflow/{NODE_ID}", json={"steps": ["quatsch"]})

    assert response.status_code == 422
    assert client.stub.workflow_calls == [], "nothing may reach the repository"


def test_workflow_endpoint_refuses_a_broken_body(client):
    response = client.post(
        f"/workflow/{NODE_ID}",
        content='{"steps": ["140_ELEMENT_LEGALLY_APPROVED"',  # truncated
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert client.stub.workflow_calls == []


def test_workflow_endpoint_refuses_an_empty_body(client):
    response = client.post(f"/workflow/{NODE_ID}")

    assert response.status_code == 400
    assert client.stub.workflow_calls == []


def test_workflow_endpoint_accepts_a_regular_node_id(client):
    """The guard must not reject what the endpoint documents."""
    response = client.post(
        f"/workflow/{NODE_ID}", json={"steps": ["140_ELEMENT_LEGALLY_APPROVED"]}
    )

    assert response.status_code == 200
    assert client.stub.workflow_calls[0]["node_id"] == NODE_ID
