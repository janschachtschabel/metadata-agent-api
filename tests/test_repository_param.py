"""
`repository` is accepted but ignored — the target comes from
METADATA_AGENT_REPOSITORY_URL. These tests pin that it is handled uniformly:
accepted everywhere, rejected nowhere, and flagged deprecated in the schema.

Backwards compatibility here means: every request that works today keeps
working. The change only widens what is accepted.
"""

import pytest
from fastapi.testclient import TestClient

from src import main
from src.models.schemas import (
    DetectContentTypeRequest,
    ExtractFieldRequest,
    GenerateRequest,
    ScreenshotRequest,
    UploadRequest,
    VerifyRequest,
)

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"

MODELS_WITH_MINIMAL_PAYLOAD = [
    (GenerateRequest, {"text": "x"}),
    (DetectContentTypeRequest, {"text": "x"}),
    (
        ExtractFieldRequest,
        {"text": "x", "field_id": "cclom:title", "schema_file": "core.json"},
    ),
    (UploadRequest, {"metadata": {"cclom:title": "x"}}),
    (VerifyRequest, {}),
    (ScreenshotRequest, {"url": "https://example.org"}),
]


@pytest.mark.parametrize("model, payload", MODELS_WITH_MINIMAL_PAYLOAD)
def test_established_values_keep_working(model, payload):
    for value in ("staging", "prod", "production"):
        assert model(**payload, repository=value).repository == value


@pytest.mark.parametrize("model, payload", MODELS_WITH_MINIMAL_PAYLOAD)
def test_unknown_values_are_accepted_since_the_field_is_ignored(model, payload):
    assert model(**payload, repository="irgendwas").repository == "irgendwas"


@pytest.mark.parametrize("model, payload", MODELS_WITH_MINIMAL_PAYLOAD)
def test_omitting_the_field_keeps_the_documented_default(model, payload):
    assert model(**payload).repository == "staging"


def test_schema_marks_the_field_deprecated():
    """Clients should be able to see from the schema that it does nothing."""
    schema = main.app.openapi()["components"]["schemas"]
    for name in ("GenerateRequest", "UploadRequest", "VerifyRequest"):
        field = schema[name]["properties"]["repository"]
        assert field.get("deprecated") is True, f"{name}.repository not deprecated"


class _StubRepositoryService:
    async def verify_node(
        self, node_id, repository, expected_metadata, context, version
    ):
        return {"success": True, "node_id": node_id, "actual_metadata": {}}


def test_verify_endpoint_no_longer_rejects_unknown_repository(monkeypatch):
    monkeypatch.setattr(
        main, "get_repository_service", lambda: _StubRepositoryService()
    )

    with TestClient(main.app) as client:
        response = client.post(
            f"/upload/verify/{NODE_ID}", json={"repository": "irgendwas"}
        )

    assert response.status_code == 200
