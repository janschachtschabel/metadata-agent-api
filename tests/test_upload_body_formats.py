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
