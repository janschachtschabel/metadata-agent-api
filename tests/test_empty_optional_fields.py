"""
An empty string is 'nothing entered', not 'a broken value'.

The Swagger UI shows one example per endpoint with every optional field spelled
out, empty ones included — `"node_id": ""` next to `"input_source": "text"`. That
is how a form-shaped example reads, and it is what people send. The node_id
validator answered it with `422 Ungültige node_id`, which names a field the
request does not use and a mistake nobody made.

Whether a field is actually required depends on `input_source`, and each branch
of the endpoint already checks its own with a message that says so
(`node_id required for input_source='node_id'`). The type validator has no
business guessing at that — it only has to reject a value that is *present and
malformed*.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from src.main import app
from src.models.schemas import (
    DetectContentTypeRequest,
    ExtractFieldRequest,
    GenerateRequest,
    ScreenshotRequest,
    UploadRequest,
)

NODE_ID = "3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"

# The example the Swagger UI offers for POST /extract-field, verbatim.
DOCS_EXAMPLE = {
    "input_source": "text",
    "text": "Workshop 'KI in der Bildung' am 15. März 2025 in Berlin.",
    "source_url": "",
    "extraction_method": "browser",
    "output_format": "markdown",
    "node_id": "",
    "context": "default",
    "version": "latest",
    "schema_file": "event.json",
    "field_id": "schema:startDate",
    "existing_metadata": {},
    "language": "de",
    "normalize": True,
    "llm_provider": "b-api-academiccloud",
    "llm_model": "deepseek-v4-flash",
}


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_node_id_counts_as_not_given(blank):
    request = ExtractFieldRequest(
        input_source="text",
        text="x",
        schema_file="event.json",
        field_id="a:b",
        node_id=blank,
    )

    assert request.node_id is None


CARRY_NODE_ID = [
    (GenerateRequest, {}),
    (DetectContentTypeRequest, {}),
    (ExtractFieldRequest, {"schema_file": "event.json", "field_id": "a:b"}),
    (ScreenshotRequest, {"url": "https://example.com"}),
    # Here it names the node to write into, not one to read from — but a blank
    # value has to mean the same thing: not given, so create one.
    (UploadRequest, {"metadata": {"cclom:title": "x"}}),
]


@pytest.mark.parametrize("model, extra", CARRY_NODE_ID)
def test_every_request_model_treats_a_blank_node_id_alike(model, extra):
    """
    One validator, so one behaviour — a caller should not have to remember which
    endpoint tolerates a blank field. VerifyRequest is absent on purpose: its
    node id comes from the URL path, not the body.
    """
    assert model(node_id="", **extra).node_id is None


def test_the_list_above_covers_every_model_that_carries_a_node_id():
    """A new request model with a node_id must not slip past this file."""
    import inspect

    import src.models.schemas as schemas

    with_node_id = {
        name
        for name, obj in vars(schemas).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and "node_id" in obj.model_fields
        and name.endswith("Request")
    }

    assert with_node_id == {model.__name__ for model, _ in CARRY_NODE_ID}


@pytest.mark.parametrize("bad", ["kein-uuid", "12345", "../../etc/passwd", "abc def"])
def test_a_node_id_that_is_present_but_malformed_is_still_rejected(bad):
    """
    The value reaches a repository URL called with the service account's
    credentials. Relaxing the empty case must not relax that.
    """
    with pytest.raises(ValidationError):
        ExtractFieldRequest(
            input_source="text",
            text="x",
            schema_file="event.json",
            field_id="a:b",
            node_id=bad,
        )


def test_a_real_node_id_still_passes():
    request = ExtractFieldRequest(
        input_source="node_id",
        schema_file="event.json",
        field_id="a:b",
        node_id=NODE_ID,
    )

    assert request.node_id == NODE_ID


def test_a_blank_node_id_becomes_none_rather_than_staying_empty_text():
    """
    Downstream the value is interpolated into a repository URL. An empty string
    would build a request against the parent path; None is what the
    `if not req.node_id` guards in the endpoint are written for.
    """
    request = ExtractFieldRequest(
        input_source="text",
        text="x",
        schema_file="event.json",
        field_id="a:b",
        node_id="  ",
    )

    assert request.node_id is None


# ------------------------------------------------------------- through the API


def test_the_documented_example_is_accepted():
    """If the example the UI hands out does not validate, nothing else matters."""
    with TestClient(app) as client:
        response = client.post("/extract-field", json=DOCS_EXAMPLE)

    assert response.status_code != 422, response.json()


@pytest.mark.parametrize(
    "source, missing, expected",
    [
        ("url", "source_url", "source_url required for input_source='url'"),
        ("node_id", "node_id", "node_id required for input_source='node_id'"),
        ("node_url", "node_id", "node_id required for input_source='node_url'"),
    ],
)
def test_a_blank_required_field_is_reported_against_the_input_source(
    source, missing, expected
):
    """
    The point of letting '' through the type check: the error that follows names
    the field *and* why it is needed, instead of claiming a malformed UUID.
    """
    body = {
        "input_source": source,
        "source_url": "",
        "node_id": "",
        "schema_file": "event.json",
        "field_id": "schema:startDate",
    }

    with TestClient(app) as client:
        response = client.post("/extract-field", json=body)

    assert response.status_code == 400
    assert response.json()["detail"] == expected
