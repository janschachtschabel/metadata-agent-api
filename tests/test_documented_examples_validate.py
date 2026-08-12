"""
Every example the Swagger UI hands out must survive its own endpoint's validation.

This is the general form of a bug that showed up twice: the `/extract-field`
example carried `"node_id": ""` next to `"input_source": "text"` and was answered
`422 Ungültige node_id`, and the same example named a `field_id` that had been
renamed out of the schema. Both were found by a person clicking *Try it out* —
nothing in the build noticed, because an example is free text.

There are two places examples live and they are easy to confuse:

* `model_config["json_schema_extra"]["examples"]` on the request model — the
  single unnamed example Swagger preselects.
* `openapi_extra` on the route in `main.py` — the named ones in the dropdown
  ("1. Text-Eingabe"). These are the ones people actually pick, and the ones
  that had drifted.

Validation only: nothing here calls an LLM or touches the repository. A `422`
never depends on either.
"""

import inspect

import pytest
from pydantic import BaseModel, ValidationError

import src.models.schemas as schemas
from src.main import app
from src.models.schemas import (
    DetectContentTypeRequest,
    ExportMarkdownRequest,
    ExtractFieldRequest,
    GenerateRequest,
    UploadRequest,
    ValidateRequest,
    VerifyRequest,
    WorkflowRequest,
)

# Which model validates the body of which path. Endpoints taking a raw Request
# do not say so in the spec, so it cannot be derived — but a wrong entry here
# would make the test lie, which is what test_the_map_is_complete guards.
BODY_MODEL = {
    "/generate": GenerateRequest,
    "/detect-content-type": DetectContentTypeRequest,
    "/extract-field": ExtractFieldRequest,
    "/validate": ValidateRequest,
    "/export/markdown": ExportMarkdownRequest,
    "/upload": UploadRequest,
    "/upload/verify/{node_id}": VerifyRequest,
    "/workflow/{node_id}": WorkflowRequest,
}

METHODS = {"get", "put", "post", "delete", "patch"}


def _named_examples():
    """(path, example name, body) for every example in the OpenAPI surface."""
    spec = app.openapi()
    for path, operations in sorted(spec["paths"].items()):
        for method, operation in operations.items():
            if method not in METHODS:
                continue
            content = (operation.get("requestBody") or {}).get("content") or {}
            for media in content.values():
                for name, example in (media.get("examples") or {}).items():
                    body = example.get("value") if isinstance(example, dict) else None
                    if isinstance(body, dict):
                        yield path, name, body


NAMED = list(_named_examples())


def _model_examples():
    """(model name, index, body) for the example on each request model."""
    for name, obj in vars(schemas).items():
        if not (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name.endswith("Request")
        ):
            continue
        extra = (obj.model_config or {}).get("json_schema_extra") or {}
        for index, body in enumerate(extra.get("examples", [])):
            yield obj, f"{name}[{index}]", body


MODEL_EXAMPLES = list(_model_examples())


def _validate(model, body, label):
    try:
        model(**body)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in d['loc'])}: {d['msg']}"
            for d in error.errors()
        )
        pytest.fail(f"{label} wird von {model.__name__} abgelehnt — {problems}")


# /upload, /validate and /export/markdown take a raw Request and accept three
# body shapes: fields flat at the top level, under `metadata`, or the whole
# /generate answer under `metadata`. The flat one — the documented
# recommendation — is not what the model expects, so the endpoint wraps it
# first. Validating the raw example against the model would fail on exactly the
# shape people are told to send.
WRAPS_A_FLAT_BODY = {"/upload", "/validate", "/export/markdown"}

# Option names the flat-body path lifts out before wrapping the rest. Mirrors
# the list in main.py; tests/test_upload_body_formats.py checks that it stays
# in step with UploadRequest.
FLAT_BODY_OPTIONS = {
    "node_id",
    "repository",
    "check_duplicates",
    "start_workflow",
    "source",
    "preview_url",
    "screenshot_method",
    "write_extended_data",
    "extended_text",
    "return_full_node",
    "collection_id",
    "workflow_steps",
    "workflow_comment",
    "workflow_receiver",
}


def _as_the_endpoint_sees_it(path, body):
    if path not in WRAPS_A_FLAT_BODY:
        return body
    if isinstance(body.get("metadata"), dict):
        return body
    options = {k: v for k, v in body.items() if k in FLAT_BODY_OPTIONS}
    fields = {k: v for k, v in body.items() if k not in FLAT_BODY_OPTIONS}
    return {"metadata": fields, **options}


@pytest.mark.parametrize(
    "path, name, body", NAMED, ids=[f"{p}:{n}" for p, n, _ in NAMED]
)
def test_a_named_example_validates_against_its_endpoint(path, name, body):
    _validate(
        BODY_MODEL[path], _as_the_endpoint_sees_it(path, body), f"{path} → '{name}'"
    )


@pytest.mark.parametrize(
    "model, label, body", MODEL_EXAMPLES, ids=[label for _, label, _ in MODEL_EXAMPLES]
)
def test_a_model_example_validates_against_its_own_model(model, label, body):
    _validate(model, body, label)


def test_the_map_is_complete():
    """
    An endpoint with examples but no entry above would be silently unchecked —
    exactly the gap that let the /extract-field example drift.
    """
    documented = {path for path, _, _ in NAMED}

    assert documented <= set(BODY_MODEL), (
        f"kein Modell hinterlegt für: {sorted(documented - set(BODY_MODEL))}"
    )


def test_there_are_examples_to_check_at_all():
    """Guards against the whole file passing because it found nothing."""
    assert len(NAMED) >= 15
    assert len(MODEL_EXAMPLES) >= 8


# ------------------------------------------------- the shape that caused it


@pytest.mark.parametrize(
    "model, extra",
    [
        (GenerateRequest, {}),
        (DetectContentTypeRequest, {}),
        (ExtractFieldRequest, {"schema_file": "core.json", "field_id": "cclom:title"}),
        (UploadRequest, {"metadata": {"cclom:title": "x"}}),
    ],
)
def test_every_optional_string_field_tolerates_being_left_blank(model, extra):
    """
    A form-shaped example spells out every field and leaves the unused ones
    empty. That must not be a validation error on any of them — the earlier bug
    was one such field, and this is the check that it was the only one.
    """
    blanks = {
        name: ""
        for name, field in model.model_fields.items()
        if name not in extra and _is_optional_string(field)
    }

    _validate(model, {**extra, **blanks}, f"{model.__name__} mit leeren Feldern")


def _is_optional_string(field) -> bool:
    """
    Optional[str] and nothing else — not Optional[dict[str, Any]], whose repr
    also contains 'str'.
    """
    import typing

    annotation = field.annotation
    if typing.get_origin(annotation) is not typing.Union:
        return False
    args = set(typing.get_args(annotation))
    return args == {str, type(None)}
