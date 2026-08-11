"""
A caller-supplied node id must never shape a repository URL unchecked.

Every node id the API accepts is interpolated into a URL that is then called
with the service account's credentials. An id containing '/' therefore steers
that authenticated request at a different endpoint. The ids are Alfresco UUIDs,
so the shape is easy to require — and requiring it is the whole defence.

Six entry points carry one: four request bodies and two path parameters.
"""

import pytest
from fastapi.testclient import TestClient

from src import main
from src.models.schemas import (
    DetectContentTypeRequest,
    ExtractFieldRequest,
    GenerateRequest,
    ScreenshotRequest,
)
from src.services.repository_service import is_valid_node_id

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"

CRAFTED_IDS = [
    "a/../../../rest/admin/v1/applications",
    "../../etc",
    "nicht-eine-node-id",
    f"{NODE_ID} extra",
    f"{NODE_ID}/metadata",
    "",
]

MODELS_WITH_NODE_ID = [
    (GenerateRequest, {}),
    (DetectContentTypeRequest, {"text": "x"}),
    (
        ExtractFieldRequest,
        {"text": "x", "field_id": "cclom:title", "schema_file": "core.json"},
    ),
    (ScreenshotRequest, {"url": "https://example.org"}),
]


# ------------------------------------------------------------------ the rule


@pytest.mark.parametrize("value", [NODE_ID, NODE_ID.upper()])
def test_a_node_uuid_is_valid(value):
    assert is_valid_node_id(value) is True


@pytest.mark.parametrize("value", CRAFTED_IDS + [None, 42])
def test_anything_that_is_not_a_node_uuid_is_invalid(value):
    assert is_valid_node_id(value) is False


# --------------------------------------------------------------- the bodies


@pytest.mark.parametrize("model, payload", MODELS_WITH_NODE_ID)
@pytest.mark.parametrize("crafted", CRAFTED_IDS)
def test_request_bodies_reject_a_crafted_node_id(model, payload, crafted):
    with pytest.raises(ValueError):
        model(**payload, node_id=crafted)


@pytest.mark.parametrize("model, payload", MODELS_WITH_NODE_ID)
def test_request_bodies_accept_a_node_uuid(model, payload):
    assert model(**payload, node_id=NODE_ID).node_id == NODE_ID


@pytest.mark.parametrize("model, payload", MODELS_WITH_NODE_ID)
def test_omitting_the_node_id_keeps_working(model, payload):
    """Only the node_id input sources need one — the others must stay usable."""
    assert model(**payload).node_id is None


# ---------------------------------------------------------- the path params


class _StubRepositoryService:
    """Stands in for the repository; records whether it was reached at all."""

    _auth_header = "Basic stub"

    def __init__(self):
        self.calls = []

    async def verify_node(
        self, node_id, repository, expected_metadata, context, version
    ):
        self.calls.append(node_id)
        return {"success": True, "actual_metadata": {}, "diff": None, "summary": None}

    async def set_workflow(self, node_id, steps, comment=None, receiver=None):
        self.calls.append(node_id)
        return {"success": True, "nodeId": node_id, "steps": []}


@pytest.fixture
def client(monkeypatch):
    stub = _StubRepositoryService()
    monkeypatch.setattr(main, "get_repository_service", lambda: stub)
    with TestClient(main.app) as test_client:
        test_client.stub = stub
        yield test_client


@pytest.mark.parametrize(
    "path, body",
    [
        ("/upload/verify", {}),
        ("/workflow", {"steps": ["140_ELEMENT_LEGALLY_APPROVED"]}),
    ],
)
@pytest.mark.parametrize(
    "crafted",
    # '%2F' decodes to '/' inside a path parameter
    ["a%2F..%2F..%2Frest%2Fadmin", "..%2F..%2Fetc", "nicht-eine-node-id"],
)
def test_path_parameters_never_pass_a_crafted_node_id_on(client, path, body, crafted):
    response = client.post(f"{path}/{crafted}", json=body)

    assert 400 <= response.status_code < 500
    assert client.stub.calls == [], "nothing may reach the repository"


@pytest.mark.parametrize(
    "path, body",
    [
        ("/upload/verify", {}),
        ("/workflow", {"steps": ["140_ELEMENT_LEGALLY_APPROVED"]}),
    ],
)
def test_path_parameters_accept_a_node_uuid(client, path, body):
    """The guard must not reject what the endpoints document."""
    response = client.post(f"{path}/{NODE_ID}", json=body)

    assert response.status_code == 200
    assert client.stub.calls == [NODE_ID]
