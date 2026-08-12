"""
The three shapes a caller can post to /upload must mean the same thing.

`/generate` answers with the schema markers *next to* `metadata`, while
everything downstream looks for them *inside* it: main reads contextName and
schemaVersion off the metadata dict, and RepositoryService reads metadataset
from it to decide which schema's repo_fields apply. Posting the /generate
response verbatim — which the README calls the simple way to use this endpoint —
therefore used to fall back to core.json alone: for an event that silently drops
ccm:oeh_event_begin, ccm:oeh_event_end, ccm:price and ccm:competence, with
success: true and no warning.
"""

import pytest
from fastapi.testclient import TestClient

from src import main

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"

FIELDS = {
    "cclom:title": "Fortbildung KI",
    "ccm:wwwurl": "https://example.org/fortbildung",
    "ccm:oeh_event_begin": "2026-03-15T09:00",
}

ENVELOPE = {
    "contextName": "default",
    "schemaVersion": "2.0.0",
    "metadataset": "event.json",
    "metadataset_uri": "http://w3id.org/openeduhub/vocabs/contentTypes/event",
    "language": "de",
    "exportedAt": "2026-03-01T10:00:00.000Z",
}

BODIES = {
    # Envelope and fields side by side at the top level
    "flat": {**ENVELOPE, **FIELDS},
    # The /generate response, posted verbatim
    "generate_response": {**ENVELOPE, "metadata": FIELDS},
    # What the web component sends: the whole response under `metadata`
    "web_component": {"metadata": {**ENVELOPE, "metadata": FIELDS}},
}


class _StubRepositoryService:
    _auth_header = "Basic stub"

    def __init__(self):
        self.upload_calls = []
        self.result = {"success": True, "node": {"nodeId": NODE_ID}}

    async def upload_metadata(self, **kwargs):
        self.upload_calls.append(kwargs)
        return self.result


class _StubScreenshotService:
    """The ccm:wwwurl would otherwise trigger a real request to PageShot."""

    async def capture(self, url, method):
        return {"success": False, "error": "stubbed"}


@pytest.fixture
def client(monkeypatch):
    stub = _StubRepositoryService()
    monkeypatch.setattr(main, "get_repository_service", lambda: stub)
    monkeypatch.setattr(main, "get_screenshot_service", _StubScreenshotService)
    with TestClient(main.app) as test_client:
        test_client.stub = stub
        yield test_client


def _upload(client, body):
    assert client.post("/upload", json=body).status_code == 200
    return client.stub.upload_calls[0]


@pytest.mark.parametrize("shape", sorted(BODIES))
def test_every_body_shape_names_the_same_schema(client, shape):
    """Which schema applies decides which fields may be written at all."""
    call = _upload(client, BODIES[shape])

    assert call["context"] == "default"
    assert call["version"] == "2.0.0"


@pytest.mark.parametrize("shape", sorted(BODIES))
def test_every_body_shape_carries_the_content_type(client, shape):
    """
    RepositoryService reads metadataset off the metadata to load the type
    schema. Without it only core.json applies — 22 repo fields instead of 29.
    """
    metadata = _upload(client, BODIES[shape])["metadata"]
    inner = (
        metadata.get("metadata")
        if isinstance(metadata.get("metadata"), dict)
        else metadata
    )

    assert "event.json" in (metadata.get("metadataset"), inner.get("metadataset"))


@pytest.mark.parametrize("shape", sorted(BODIES))
def test_the_fields_survive_every_shape(client, shape):
    metadata = _upload(client, BODIES[shape])["metadata"]
    inner = (
        metadata.get("metadata")
        if isinstance(metadata.get("metadata"), dict)
        else metadata
    )

    assert inner["cclom:title"] == "Fortbildung KI"
    assert inner["ccm:oeh_event_begin"] == "2026-03-15T09:00"


def test_the_endpoint_passes_the_applied_schema_on(client):
    """
    The service reports which schema it wrote against; the endpoint must not
    swallow it. What the numbers mean is pinned in test_upload_pipeline.
    """
    client.stub.result = {
        "success": True,
        "node": {"nodeId": NODE_ID},
        "schema_used": "event.json",
        "repo_fields_available": 29,
    }

    body = client.post("/upload", json=BODIES["generate_response"]).json()

    assert body["schema_used"] == "event.json"
    assert body["repo_fields_available"] == 29


# The other two endpoints that take the same body read the markers the same way.


@pytest.mark.parametrize("shape", sorted(BODIES))
def test_validate_checks_against_the_named_schema(client, shape):
    """
    Validating against a schema nobody asked for reports on the wrong content
    type — and answers 200 while doing it.
    """
    response = client.post("/validate", json=BODIES[shape])

    assert response.status_code == 200
    assert response.json()["schema_used"] == "event.json"


@pytest.mark.parametrize("shape", sorted(BODIES))
def test_markdown_export_uses_the_named_schema(client, shape):
    response = client.post("/export/markdown", json=BODIES[shape])

    assert response.status_code == 200
    assert response.json()["schema_used"] == "event.json"


# ------------------------------------------------- options in the flat shape
#
# The flat shape arrives as one bag of keys, so the upload options have to be
# lifted out of it by name before the rest becomes the metadata dict. That list
# is hand-maintained: a name missing from it is not rejected, it is filed away
# as a metadata field and silently does nothing. `node_id` was missing exactly
# that way — the two-step upload created a second node instead of filling the
# one it was given.

OPTION_VALUES = {
    "node_id": "1c0e6a44-9d7b-4f2e-8e6a-449d7b4f2e11",
    "check_duplicates": False,
    "start_workflow": False,
    "write_extended_data": False,
    "return_full_node": True,
    "source": "Landesinstitut",
    "extended_text": "Rohtext",
    "collection_id": ["3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"],
    "workflow_steps": ["200_tocheck"],
    "workflow_comment": "Kommentar",
    "workflow_receiver": ["GROUP_Redaktion"],
}


@pytest.mark.parametrize("option", sorted(OPTION_VALUES))
def test_an_option_in_the_flat_shape_is_read_as_an_option(client, option):
    call = _upload(client, {**BODIES["flat"], option: OPTION_VALUES[option]})

    assert option not in call["metadata"], (
        f"'{option}' landete in den Metadaten statt als Option gelesen zu werden"
    )


# 'source' is not handed to the service — it is applied to the metadata before
# the call, overwriting ccm:oeh_publisher_combined.
PASSED_THROUGH = sorted(set(OPTION_VALUES) - {"source"})


@pytest.mark.parametrize("option", PASSED_THROUGH)
def test_an_option_in_the_flat_shape_reaches_the_service(client, option):
    """Not being swallowed is half of it — the value has to arrive as well."""
    call = _upload(client, {**BODIES["flat"], option: OPTION_VALUES[option]})
    expected = OPTION_VALUES[option]
    # The service names this one differently than the request does.
    key = {"collection_id": "collection_ids"}.get(option, option)

    assert call[key] == expected


def test_the_source_option_overwrites_the_publisher(client):
    call = _upload(client, {**BODIES["flat"], "source": "Landesinstitut"})

    assert call["metadata"]["ccm:oeh_publisher_combined"] == "Landesinstitut"


def test_the_option_list_covers_every_field_of_the_request_model():
    """
    A new field on UploadRequest that nobody adds to the flat-shape extraction
    is invisible in the recommended body format. This is the check that says so
    at build time instead of in production.
    """
    from src.models.schemas import UploadRequest

    fields = set(UploadRequest.model_fields) - {"metadata", "repository"}
    # preview_url and screenshot_method drive the screenshot, which is stubbed
    # here; they are covered by the screenshot tests.
    fields -= {"preview_url", "screenshot_method"}

    assert fields <= set(OPTION_VALUES), (
        f"nicht auf die flache Form geprüft: {sorted(fields - set(OPTION_VALUES))}"
    )
