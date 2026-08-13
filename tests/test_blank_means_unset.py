"""
A field left blank means 'not given' — everywhere, not just where it 422s.

`test_empty_optional_fields` established that a blank value must not be a
validation error. It stops there, and that turned out to be half the rule: a
blank value that passes validation and is then *used* as a value is worse than
the 422, because nothing says so.

The case that showed it: both documented examples carry `"comment": ""` /
`"workflow_comment": ""` — that is what a form-shaped example looks like. The
comment reaches `run_workflow_steps`, which reads

    comment if comment is not None else "Upload via Metadata Agent API"

An empty string is not None. So every node uploaded with the documented example
got a blank entry in its workflow history instead of the documented default,
with a 200 and no hint that anything had been skipped.

The fix belongs in the request model, where the codebase already puts this rule
(`validate_node_id`, `sanitize_screenshot_method`): the boundary decides what
'left empty' means, and the service layer's `is not None` keeps its meaning for
a caller who genuinely sends one.
"""

import inspect
import typing

import pytest
from pydantic import BaseModel

import src.models.schemas as schemas
from src.models.schemas import UploadRequest, WorkflowRequest
from src.services.repository_curation import run_workflow_steps

STATUS = "140_ELEMENT_LEGALLY_APPROVED"
DEFAULT_COMMENT = "Upload via Metadata Agent API"


# ------------------------------------------------------------- the two models


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_upload_comment_counts_as_not_given(blank):
    request = UploadRequest(metadata={"cclom:title": "x"}, workflow_comment=blank)

    assert request.workflow_comment is None


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_workflow_comment_counts_as_not_given(blank):
    request = WorkflowRequest(steps=[STATUS], comment=blank)

    assert request.comment is None


def test_a_real_comment_survives_untouched():
    """Including its spacing — only an entirely blank value is 'not given'."""
    request = WorkflowRequest(steps=[STATUS], comment="  Redaktionell geprüft  ")

    assert request.comment == "  Redaktionell geprüft  "


# ------------------------------------------------------- through to the payload


class _RecordingClient:
    """Captures what would go to edu-sharing. No network, no repository."""

    def __init__(self):
        self.payloads = []

    async def put(self, url, headers=None, json=None):
        self.payloads.append(json)
        return _Response()

    async def get(self, url, headers=None):
        return _Response()


class _Response:
    status_code = 200

    def json(self):
        return {}


async def _comment_sent(comment):
    client = _RecordingClient()
    await run_workflow_steps(
        client, "Basic x", "https://repo.example", "n1", [STATUS], comment
    )
    return client.payloads[0]["comment"]


async def test_a_missing_comment_is_replaced_by_the_documented_default():
    assert await _comment_sent(None) == DEFAULT_COMMENT


async def test_the_documented_example_does_not_write_a_blank_comment():
    """
    End to end for the actual bug: the example's `comment: ""` goes through the
    model and must arrive as the default, not as an empty history entry.
    """
    request = WorkflowRequest(steps=[STATUS], comment="")

    assert await _comment_sent(request.comment) == DEFAULT_COMMENT


async def test_a_written_comment_still_reaches_the_history():
    assert await _comment_sent("Redaktionell geprüft") == "Redaktionell geprüft"


# ------------------------------------------------ every model, every blank form


def _optional_strings(model):
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if typing.get_origin(annotation) is not typing.Union:
            continue
        if set(typing.get_args(annotation)) == {str, type(None)}:
            yield name


# What each model needs before it will build at all.
REQUEST_MODELS = [
    (schemas.GenerateRequest, {}),
    (schemas.DetectContentTypeRequest, {}),
    (
        schemas.ExtractFieldRequest,
        {"schema_file": "core.json", "field_id": "cclom:title"},
    ),
    (schemas.ValidateRequest, {"metadata": {}}),
    (schemas.ExportMarkdownRequest, {"metadata": {}}),
    (schemas.UploadRequest, {"metadata": {"cclom:title": "x"}}),
    (schemas.CreateNodeRequest, {"metadata": {"cclom:title": "x"}}),
    (schemas.VerifyRequest, {}),
    (schemas.WorkflowRequest, {"steps": [STATUS]}),
    (schemas.ScreenshotRequest, {"url": "https://example.com"}),
]


@pytest.mark.parametrize(
    "model, required", REQUEST_MODELS, ids=[m.__name__ for m, _ in REQUEST_MODELS]
)
def test_every_optional_string_left_blank_ends_up_unset(model, required):
    """
    Not merely 'does not raise' — the value must be None afterwards, because
    that is what every downstream `if x is not None` is written against.
    """
    blanks = {name: "" for name in _optional_strings(model) if name not in required}
    if not blanks:
        pytest.skip(f"{model.__name__} hat keine optionalen Textfelder")

    request = model(**required, **blanks)

    still_set = {name: getattr(request, name) for name in blanks}
    assert all(value is None for value in still_set.values()), (
        f"leer übergeben, aber gesetzt geblieben: "
        f"{ {k: v for k, v in still_set.items() if v is not None} }"
    )


# --------------------------------------------------------------- empty lists
#
# There is no single rule here, and pretending otherwise would have cost a
# feature: for a list, 'empty' and 'not given' are not always the same thing.
# Each of the four is a separate decision, so each gets its own test.


def test_an_empty_collection_list_means_no_collection():
    """
    Nothing distinguishes 'reference this in no collections' from 'do not add
    it to any' — so the empty list is simply the absent one.
    """
    request = UploadRequest(metadata={"cclom:title": "x"}, collection_id=[])

    assert request.collection_id is None


def test_an_empty_regenerate_list_means_regenerate_nothing():
    """
    `if regenerate_fields or regenerate_empty` at the call site already reads
    `[]` as absent, so the model leaves it alone rather than adding a validator
    that changes nothing.
    """
    request = schemas.GenerateRequest(regenerate_fields=[])

    assert not request.regenerate_fields


@pytest.mark.parametrize(
    "model, required, field",
    [
        (WorkflowRequest, {"steps": [STATUS]}, "receiver"),
        (UploadRequest, {"metadata": {"cclom:title": "x"}}, "workflow_receiver"),
    ],
)
def test_an_empty_receiver_list_keeps_meaning_notify_nobody(model, required, field):
    """
    The one place where empty is a *choice*: `None` hands 200_tocheck to the
    Uploadmanager group, `[]` deliberately notifies no one. Folding them
    together would take away a caller's only way to say the second — so this
    field is left out of the blank-is-unset rule on purpose.
    """
    request = model(**required, **{field: []})

    assert getattr(request, field) == []


async def test_an_empty_receiver_reaches_the_payload_as_empty():
    client = _RecordingClient()

    await run_workflow_steps(
        client, "Basic x", "https://repo.example", "n1", [STATUS], None, []
    )

    assert client.payloads[0]["receiver"] == []


def test_an_empty_step_list_is_rejected_rather_than_guessed():
    """
    Here empty and absent differ the other way round: leaving `workflow_steps`
    out runs the default and hands the node to the editorial queue, which is
    the opposite of 'run no step'. The ambiguity is answered with an error
    naming the parameter that does say it.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="start_workflow=false"):
        UploadRequest(metadata={"cclom:title": "x"}, workflow_steps=[])


def test_the_model_list_covers_every_request_model():
    """A new request model must not slip past this sweep unnoticed."""
    declared = {
        name
        for name, obj in vars(schemas).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and name.endswith("Request")
    }

    assert declared == {model.__name__ for model, _ in REQUEST_MODELS}
