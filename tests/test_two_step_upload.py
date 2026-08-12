"""
Creating the node first, filling it in later.

Callers who want a node id before they have any metadata — to reference it, to
show it, to hand it to an editor — can now get one from `POST /node` and pass it
back to `/upload` later. Both halves already existed inside `upload_metadata`;
what is new is that the seam is reachable from outside.

Two things about the existing upload path make this less trivial than it looks,
and both are what most of this file is about:

1. **The rollback deletes.** `_failed()` discards the node when anything after
   creation goes wrong, so a half-written node does not become litter. That is
   right for a node this service created and wrong for one it was handed — the
   caller may have put content there, and it is not ours to bin.
2. **The duplicate check searches by `ccm:wwwurl`.** Run against a node that
   already carries that URL it finds the target itself and aborts the upload as
   a duplicate of itself.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src import main
from src.services import repository_service as repo_module
from src.services.repository_service import RepositoryService

from test_upload_pipeline import (
    GENERATED_METADATA,
    NODE_ID,
    _RecordingAsyncClient,
    _Response,
)

EXISTING_NODE = "1c0e6a44-9d7b-4f2e-8e6a-449d7b4f2e11"


@pytest.fixture
def recorded(monkeypatch):
    _RecordingAsyncClient.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _RecordingAsyncClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)
    return _RecordingAsyncClient.calls


def _creates(calls):
    return [c for c in calls if c["method"] == "POST" and "/children?" in c["url"]]


def _deletes(calls):
    return [c for c in calls if c["method"] == "DELETE"]


def _searches(calls):
    return [c for c in calls if "/search/" in c["url"]]


def _metadata_writes(calls):
    return [c for c in calls if "METADATA_UPDATE" in c["url"]]


# --------------------------------------------------------- step one: the node


@pytest.mark.asyncio
async def test_creating_a_node_returns_an_id_without_writing_metadata(recorded):
    service = RepositoryService("user", "password")

    result = await service.create_node({"cclom:title": "Nur ein Titel"})

    assert result["success"] is True
    assert result["node"]["nodeId"] == NODE_ID
    assert len(_creates(recorded)) == 1
    assert _metadata_writes(recorded) == []


@pytest.mark.asyncio
async def test_the_created_node_carries_the_fields_the_upload_would_have_set(recorded):
    """
    The same five the upload path puts on a new node, no more: anything else
    needs the schema filter, which is what the second step is for.
    """
    service = RepositoryService("user", "password")

    await service.create_node(
        {
            "cclom:title": "Bruchrechnung",
            "cclom:general_description": "Ein Arbeitsblatt.",
            "cclom:general_keyword": ["Bruch", "Mathematik"],
            "ccm:wwwurl": "https://example.org/b",
            "cclom:general_language": "de",
            "ccm:oeh_quality_correctness": "4",
        }
    )

    written = _creates(recorded)[0]["json"]

    assert written["cclom:title"] == ["Bruchrechnung"]
    assert written["ccm:wwwurl"] == ["https://example.org/b"]
    assert written["ccm:linktype"] == ["USER_GENERATED"]
    assert "ccm:oeh_quality_correctness" not in written


@pytest.mark.asyncio
async def test_a_node_can_be_created_from_a_title_alone(recorded):
    """
    The documented main use of this endpoint. Measured against staging on
    2026-08-12: the repository answers `500 missing name` unless it can work out
    a cm:name — which it derives from ccm:wwwurl and never from cclom:title. A
    title-only create therefore has to carry the name itself.
    """
    service = RepositoryService("user", "password")

    result = await service.create_node({"cclom:title": "Nur ein Titel"})

    assert result["success"] is True
    assert _creates(recorded)[0]["json"]["cm:name"] == ["Nur ein Titel"]


@pytest.mark.asyncio
async def test_the_repository_keeps_deriving_the_name_when_it_can(recorded):
    """
    With a URL present edu-sharing builds the name from it ('example.org_b'), and
    every node uploaded so far carries such a name. Setting one anyway would
    rename them all — a change nobody asked for, in a field the editorial desk
    sees.
    """
    service = RepositoryService("user", "password")

    await service.create_node(
        {"cclom:title": "Mit URL", "ccm:wwwurl": "https://example.org/b"}
    )

    assert "cm:name" not in _creates(recorded)[0]["json"]


@pytest.mark.parametrize(
    "title, expected",
    [
        ('Bruch/Rechnung: "Teil 1"', "Bruch_Rechnung_ _Teil 1_"),
        ("  Rand  ", "Rand"),
        ("a" * 300, "a" * 200),
        ("...", "Unbenannt"),
    ],
)
@pytest.mark.asyncio
async def test_the_derived_name_is_one_alfresco_accepts(recorded, title, expected):
    """
    Alfresco refuses * " \\ > < ? / : | in a name and trims dots and spaces at the
    edges. A title carrying one would trade the 'missing name' error for a
    different one.
    """
    service = RepositoryService("user", "password")

    await service.create_node({"cclom:title": title})

    assert _creates(recorded)[0]["json"]["cm:name"] == [expected]


@pytest.mark.asyncio
async def test_a_name_the_caller_supplied_is_left_alone(recorded):
    service = RepositoryService("user", "password")

    await service.create_node({"cclom:title": "Titel", "cm:name": "Eigener Name"})

    assert _creates(recorded)[0]["json"]["cm:name"] == ["Eigener Name"]


@pytest.mark.asyncio
async def test_creating_without_a_title_is_refused_before_anything_is_sent(recorded):
    """A node with no title is unfindable litter in the inbox."""
    service = RepositoryService("user", "password")

    result = await service.create_node({"ccm:wwwurl": "https://example.org/b"})

    assert result["success"] is False
    assert "cclom:title" in result["error"]
    assert _creates(recorded) == []


@pytest.mark.asyncio
async def test_the_duplicate_check_runs_when_a_url_is_given(recorded):
    service = RepositoryService("user", "password")

    await service.create_node(
        {"cclom:title": "x", "ccm:wwwurl": "https://example.org/b"},
        check_duplicates=True,
    )

    assert _searches(recorded)


# ------------------------------------------------- step two: filling it in


@pytest.mark.asyncio
async def test_an_upload_with_a_node_id_writes_to_it_instead_of_creating_one(recorded):
    service = RepositoryService("user", "password")

    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        node_id=EXISTING_NODE,
        context="default",
        version="2.0.0",
        write_extended_data=False,
        start_workflow=False,
    )

    assert result["success"] is True
    assert result["node"]["nodeId"] == EXISTING_NODE
    assert _creates(recorded) == [], "nothing may be created"
    assert EXISTING_NODE in _metadata_writes(recorded)[0]["url"]


@pytest.mark.asyncio
async def test_the_answer_says_whether_the_node_was_created_or_reused(recorded):
    """Without it a caller cannot tell a fresh node from one it handed over."""
    service = RepositoryService("user", "password")

    reused = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        node_id=EXISTING_NODE,
        context="default",
        version="2.0.0",
        write_extended_data=False,
        start_workflow=False,
    )
    fresh = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
        start_workflow=False,
    )

    assert reused["node_created"] is False
    assert fresh["node_created"] is True


@pytest.mark.asyncio
async def test_the_duplicate_check_is_skipped_for_a_given_node(recorded):
    """
    It searches by ccm:wwwurl. The node being filled in already carries that URL
    — from step one — so the check would find the target itself and abort the
    upload as its own duplicate.
    """
    service = RepositoryService("user", "password")

    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        node_id=EXISTING_NODE,
        check_duplicates=True,
        context="default",
        version="2.0.0",
        write_extended_data=False,
        start_workflow=False,
    )

    assert _searches(recorded) == []
    assert result["success"] is True
    assert result.get("duplicate") is not True


# ------------------------------------------------------------- the rollback


class _FailingAfterCreate(_RecordingAsyncClient):
    """Lets the node be created, then fails the metadata write."""

    async def post(self, url, headers=None, json=None, files=None):
        self._record("POST", url, json)
        if "/children?" in url:
            return _Response(200, {"node": {"ref": {"id": NODE_ID}}})
        if "METADATA_UPDATE" in url:
            raise RuntimeError("Repository weg")
        return _Response(200, {})


@pytest.fixture
def failing(monkeypatch):
    _FailingAfterCreate.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _FailingAfterCreate)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)
    return _FailingAfterCreate.calls


@pytest.mark.asyncio
async def test_a_node_this_service_created_is_discarded_when_the_upload_fails(failing):
    """The behaviour that must not change — a half-written node is litter."""
    service = RepositoryService("user", "password")

    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
    )

    assert result["success"] is False
    assert result["discarded_node"] == NODE_ID
    assert _deletes(failing)


@pytest.mark.asyncio
async def test_a_node_the_caller_handed_over_is_never_discarded(failing):
    """
    The whole point of the two-step flow is that the id outlives the first call.
    Binning it on a failed second call would destroy something this service did
    not create and may not own.
    """
    service = RepositoryService("user", "password")

    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        node_id=EXISTING_NODE,
        context="default",
        version="2.0.0",
    )

    assert result["success"] is False
    assert "discarded_node" not in result
    assert _deletes(failing) == [], "nothing of the caller's may be deleted"


# --------------------------------------------------------------- the endpoint


@pytest.fixture
def client(recorded):
    with TestClient(main.app) as test_client:
        yield test_client


def test_the_endpoint_creates_a_node_from_a_title(client, recorded):
    response = client.post("/node", json={"metadata": {"cclom:title": "Ein Titel"}})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["node"]["nodeId"] == NODE_ID
    assert body["node"]["repositoryUrl"].endswith(NODE_ID)


def test_the_endpoint_refuses_a_body_without_a_title(client, recorded):
    response = client.post("/node", json={"metadata": {"ccm:wwwurl": "https://e.org"}})

    assert response.status_code == 400
    assert "cclom:title" in response.json()["detail"]


@pytest.mark.parametrize("bad", ["kein-uuid", "../../etc", "abc def"])
def test_the_upload_refuses_a_malformed_node_id(client, recorded, bad):
    """Same guard as every other node id — it ends up in a repository URL."""
    response = client.post(
        "/upload", json={"metadata": {"cclom:title": "x"}, "node_id": bad}
    )

    assert response.status_code == 422


def test_a_blank_node_id_on_upload_means_create_one(client, recorded):
    """Consistent with every other optional node id in this API."""
    response = client.post(
        "/upload",
        json={
            "metadata": GENERATED_METADATA,
            "node_id": "",
            "check_duplicates": False,
            "start_workflow": False,
            "write_extended_data": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["node_created"] is True
    assert len(_creates(recorded)) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"metadata": GENERATED_METADATA, "node_id": EXISTING_NODE},
            id="node_id neben metadata",
        ),
        pytest.param(
            {**GENERATED_METADATA, "node_id": EXISTING_NODE},
            id="flach, wie /generate liefert",
        ),
    ],
)
def test_the_node_id_is_read_in_every_body_format(client, recorded, body):
    """
    The flat form is the documented recommendation — the /generate answer passed
    on unchanged. It reaches the endpoint as a bag of metadata keys, and the
    upload options are lifted out of it by name. A name missing from that list is
    not rejected; it is filed away as a metadata field and silently does nothing,
    so the upload would create a second node instead of filling the given one.
    """
    response = client.post(
        "/upload",
        json={**body, "start_workflow": False, "write_extended_data": False},
    )

    assert response.status_code == 200
    assert response.json()["node_created"] is False
    assert _creates(recorded) == []


def test_the_two_steps_fit_together(client, recorded):
    """
    The whole point, in one test: the id the first call returns is accepted by
    the second, and no second node appears.
    """
    created = client.post(
        "/node", json={"metadata": {"cclom:title": "Bruchrechnung"}}
    ).json()
    node_id = created["node"]["nodeId"]

    filled = client.post(
        "/upload",
        json={
            "metadata": GENERATED_METADATA,
            "node_id": node_id,
            "start_workflow": False,
            "write_extended_data": False,
        },
    ).json()

    assert filled["success"] is True
    assert filled["node"]["nodeId"] == node_id
    assert filled["node_created"] is False
    assert len(_creates(recorded)) == 1, "only the first step creates"


def test_the_openapi_surface_documents_both_halves(client):
    """
    /upload takes a raw Request, so its path entry carries a bare object schema —
    the models are only visible under components, which is where a client
    generator reads them from.
    """
    spec = json.loads(client.get("/openapi.json").text)
    schemas = spec["components"]["schemas"]

    assert "/node" in spec["paths"]
    assert "CreateNodeRequest" in schemas
    assert "node_id" in schemas["UploadRequest"]["properties"]
    assert "node_created" in schemas["UploadResponse"]["properties"]
