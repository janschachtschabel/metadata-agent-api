"""
What the Swagger UI shows as the request body of POST /upload.

The endpoint takes a raw `Request` — it accepts the flat `/generate` answer as
well as the wrapped form, which no single Pydantic parameter can express. The
price was `openapi_extra={"schema": {"type": "object"}}`: an object with no
properties, so the *Schema* tab listed nothing. Every option — `collection_id`,
`node_id`, `workflow_steps`, `source` — existed on `UploadRequest` and was
invisible unless it happened to appear in one of the two examples. `node_id`
appeared in neither.

Seven of the ten body endpoints already `$ref` their model; `custom_openapi()`
injects the models for exactly that reason. A plain `$ref` to `UploadRequest`
would be wrong here in one respect — it marks `metadata` required, and the
documented body has its fields at the top level — so the schema is derived from
the model and relaxed on those two points, rather than written out by hand where
it would drift from the model on the next added option.
"""

import re

import pytest
from fastapi.testclient import TestClient

import src.main as main
from src.main import app
from src.models.schemas import UploadRequest

SPEC = app.openapi()
UPLOAD_BODY = SPEC["paths"]["/upload"]["post"]["requestBody"]["content"][
    "application/json"
]
UPLOAD_SCHEMA = UPLOAD_BODY["schema"]


# ------------------------------------------------------------- the schema tab


def test_the_request_body_lists_its_properties():
    """`{"type": "object"}` renders as an empty box — the state this replaces."""
    assert UPLOAD_SCHEMA.get("properties"), (
        "Das Schema von /upload nennt keine Properties — /docs zeigt keine Optionen."
    )


@pytest.mark.parametrize("option", ["collection_id", "node_id"])
def test_the_options_asked_for_are_in_the_schema(option):
    assert option in UPLOAD_SCHEMA["properties"]


def test_every_option_of_the_model_reaches_the_schema():
    """
    Derived, not transcribed: an option added to UploadRequest has to show up
    here without anyone remembering to copy it.
    """
    assert set(UPLOAD_SCHEMA["properties"]) == set(UploadRequest.model_fields)


@pytest.mark.parametrize("option", ["collection_id", "node_id", "workflow_steps"])
def test_an_option_carries_its_description(option):
    """A property list without descriptions is barely better than no list."""
    assert UPLOAD_SCHEMA["properties"][option].get("description", "").strip()


# ------------------------------------------------- what the body really allows


def test_nothing_is_declared_required():
    """
    `metadata` is required on the model but not in the documented body: the
    recommended shape puts the fields at the top level and the endpoint wraps
    them. Marking it required would describe a request that the examples
    themselves do not send.
    """
    assert not UPLOAD_SCHEMA.get("required")


def test_metadata_fields_are_allowed_alongside_the_options():
    """
    `cclom:title` and friends arrive as extra properties in the flat form.
    additionalProperties=false would declare the documented body invalid.
    """
    assert UPLOAD_SCHEMA.get("additionalProperties") is not False


def test_the_schema_does_not_carry_a_second_set_of_examples():
    """
    Pydantic puts model_config examples into the schema; the route already
    offers named ones. Both shown at once is two competing suggestions.
    """
    assert "examples" not in UPLOAD_SCHEMA


# ----------------------------------------------------------------- the examples


def _example(name):
    return UPLOAD_BODY["examples"][name]["value"]


def test_an_example_shows_how_to_write_into_an_existing_node():
    """
    The two-step upload (POST /node → POST /upload) is only discoverable if some
    example spells the field out.
    """
    carrying = [name for name in UPLOAD_BODY["examples"] if "node_id" in _example(name)]

    assert carrying, "kein /upload-Beispiel zeigt node_id"


def test_an_example_shows_a_collection():
    carrying = [
        name for name in UPLOAD_BODY["examples"] if "collection_id" in _example(name)
    ]

    assert carrying, "kein /upload-Beispiel zeigt collection_id"


@pytest.mark.parametrize("option", ["node_id", "collection_id"])
def test_the_first_example_offers_the_option_blank(option):
    """
    The example people copy is the first one. Showing the field empty is what
    makes it visible without pre-filling a value nobody asked for — and it only
    works if a blank value validates, which test_empty_optional_fields checks.
    """
    value = _example("direkt").get(option)

    assert value in ("", [], None), (
        f"{option} steht im ersten Beispiel als {value!r} statt leer"
    )


# --------------------------------------------------------- the document itself


def _refs(node):
    """Every $ref string anywhere in the spec."""
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"]
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def test_every_ref_in_the_document_resolves():
    """
    The derived schema keeps `#/components/schemas/ScreenshotMethod` and relies
    on custom_openapi() having put it there. A dangling $ref breaks the whole
    Swagger page, not just the one field.
    """
    known = set(SPEC.get("components", {}).get("schemas", {}))
    dangling = sorted(
        {
            ref
            for ref in _refs(SPEC)
            if ref.startswith("#/components/schemas/")
            and ref.rsplit("/", 1)[1] not in known
        }
    )

    assert not dangling


def test_the_openapi_document_can_be_built_twice():
    """
    custom_openapi() caches into app.openapi_schema. A schema derived at import
    time must not depend on that cache being cold.
    """
    assert app.openapi() == SPEC


# ------------------------------------------- the options list stays in one place


def test_the_flat_body_lifts_out_exactly_the_options_the_schema_names():
    """
    An option missing from the pop-list in main.py is filed away as a metadata
    field and silently does nothing — the bug that swallowed node_id. The schema
    and that list describe the same set, so they are checked against each other.
    """
    import inspect

    import src.main as main

    source = inspect.getsource(main.upload_to_repository)
    lifted = set(re.findall(r'data\.pop\("([^"]+)"', source))

    options = set(UploadRequest.model_fields) - {"metadata"}
    assert options <= lifted, f"nicht ausgehoben: {sorted(options - lifted)}"


def test_optional_list_options_accept_an_empty_list():
    """
    `[]` is what a form-shaped example leaves behind for a list option. It has
    to mean 'no collection', not a validation error.
    """
    request = UploadRequest(metadata={"cclom:title": "x"}, collection_id=[])

    assert request.collection_id is None


def test_a_list_option_still_refuses_a_bare_id():
    """
    Relaxing the empty case must not reopen the string/list ambiguity: the other
    list parameters take a list and nothing else.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UploadRequest(
            metadata={"cclom:title": "x"},
            collection_id="3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9",
        )


# ------------------------------------------------- the examples, actually sent
#
# Validating the example against the model checks the second half of the path.
# The flat body is unwrapped *before* Pydantic sees it, so an option the
# unwrapping mishandles — node_id was swallowed there once — never reaches the
# model to be rejected. These post the body the UI would post.

NODE_ID = "3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"


class _StubRepository:
    _auth_header = "Basic stub"

    def __init__(self):
        self.calls = []

    async def upload_metadata(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "node": {"nodeId": NODE_ID},
            "fields_written": 1,
            "fields_skipped": 0,
        }


class _StubScreenshots:
    """The examples carry a ccm:wwwurl, which would start a real capture."""

    async def capture(self, url, method):
        return {"success": False, "error": "stub"}


@pytest.fixture
def client(monkeypatch):
    stub = _StubRepository()
    monkeypatch.setattr(main, "get_repository_service", lambda: stub)
    monkeypatch.setattr(main, "get_screenshot_service", lambda: _StubScreenshots())
    with TestClient(app) as test_client:
        test_client.stub = stub
        yield test_client


@pytest.mark.parametrize("name", list(UPLOAD_BODY["examples"]))
def test_every_documented_example_is_accepted_by_the_endpoint(client, name):
    response = client.post("/upload", json=_example(name))

    assert response.status_code == 200, response.json()


def test_the_blank_options_of_the_first_example_arrive_as_not_given(client):
    """
    The question this whole change turns on: leaving `node_id` and
    `collection_id` empty has to mean 'create a node, no collection' — not an
    error, and not an empty value handed on to the repository.
    """
    client.post("/upload", json=_example("direkt"))

    call = client.stub.calls[0]
    assert call["node_id"] is None
    assert call["collection_ids"] is None


def test_a_filled_node_id_reaches_the_repository(client):
    """The other half: when it is filled in, it must not be dropped."""
    client.post("/upload", json=_example("in_bestehenden_node"))

    assert client.stub.calls[0]["node_id"] == NODE_ID


@pytest.mark.parametrize("name", list(UPLOAD_BODY["examples"]))
def test_no_option_is_written_into_the_node_as_metadata(client, name):
    """
    An option the unwrapping does not lift out is filed away as a metadata
    field, where it does nothing and silently pollutes the node.
    """
    client.post("/upload", json=_example(name))

    written = set(client.stub.calls[0]["metadata"])
    assert not written & set(UploadRequest.model_fields)
