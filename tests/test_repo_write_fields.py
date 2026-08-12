"""
The fields a working editorial upload writes, and the two gates that used to
drop them.

A hand-written cURL from the WLO side creates the node with every property
inline and no filtering at all. This agent instead creates a minimal node and
writes a filtered property set afterwards, so a field only reaches the
repository if two conditions hold: the schema marks it `repo_field`, and it
survives `normalize_for_repo`. Three fields failed the first gate,
`schema:datePublished` failed both, and the three AI provenance flags were not
in any schema to begin with.

These tests pin the contract of both gates and the schema data behind them.
"""

import json
from pathlib import Path

import pytest

from src.services.llm_service import LLMService
from src.services.repository_values import normalize_for_repo
from src.utils.schema_loader import get_repo_fields, get_schema_fields

CONTEXTS = ["default", "mds_oeh"]
VERSION = "2.0.0"

# The AI provenance flags are stored as the strings 'true'/'false', which is what
# the repository receives from the editorial tooling today. A JSON boolean would
# serialize as `false`, not `"false"`.
AI_LICENSE_FIELDS = [
    "ccm:commonlicense_ai_allow_usage",
    "ccm:commonlicense_ai_generated",
    "ccm:commonlicense_ai_manually_modified",
]

# field id -> the schema file that declares it, per context. The two contexts
# organise these differently: default keeps ccm:oeh_lrt in core.json only,
# mds_oeh repeats it in the content type.
DECLARED_IN = {
    "default": {
        "ccm:oeh_lrt": "core.json",
        "oeh:required_tools": "learning_material.json",
        "schema:datePublished": "learning_material.json",
    },
    "mds_oeh": {
        "ccm:oeh_lrt": "core.json",
        "oeh:required_tools": "learning_material.json",
        "schema:datePublished": "learning_material.json",
    },
}


def _fields(context, schema_file):
    return {f["id"]: f for f in get_schema_fields(context, VERSION, schema_file)}


# ------------------------------------------------------- the two filter gates


def test_a_virtual_field_is_dropped_even_when_marked_as_a_repo_field():
    """
    'virtual:' names a value edu-sharing computes, never one it stores. There is
    no schema flag that could make writing one correct, so the filter stays
    unconditional.
    """
    result = normalize_for_repo(
        {"virtual:collection_id_primary": "abc"}, {"virtual:collection_id_primary"}
    )

    assert result == {}


def test_a_schema_field_the_schema_marks_writable_reaches_the_repository():
    """
    'schema:' is a real namespace in the repository — the editorial upload writes
    schema:datePublished directly. Whether it is written is the schema's call,
    not the prefix's.
    """
    result = normalize_for_repo(
        {"schema:datePublished": "2024-03-15"}, {"schema:datePublished"}
    )

    assert result == {"schema:datePublished": ["2024-03-15"]}


@pytest.mark.parametrize("key", ["schema:location", "schema:geo", "schema:name"])
def test_a_schema_field_the_schema_does_not_mark_stays_out(key):
    """
    These are inputs for transformations (schema:location → cm:latitude). None of
    them is a repo field in any schema, so the repo_field gate keeps them out on
    its own — the prefix filter was never what protected them.
    """
    result = normalize_for_repo({key: "wert"}, {"schema:datePublished"})

    assert result == {}


def test_no_transformation_input_is_accidentally_marked_writable():
    """
    Guards the assumption the test above rests on: dropping 'schema:' from the
    prefix filter is only safe while the transformation inputs carry
    repo_field=false. A future schema edit that flips one would write a raw JSON
    blob into the node, and this is what catches it.
    """
    transformation_inputs = {"schema:location", "schema:geo"}

    for context in CONTEXTS:
        for schema_file in Path(f"src/schemata/{context}/v{VERSION}").glob("*.json"):
            for field in json.loads(schema_file.read_text(encoding="utf-8")).get(
                "fields", []
            ):
                if field["id"] in transformation_inputs:
                    assert field["system"]["repo_field"] is False, (
                        f"{field['id']} in {schema_file} would now be written raw"
                    )


# ------------------------------------------------- fields blocked by the flag


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", sorted(DECLARED_IN["default"]))
def test_the_field_is_marked_for_writing(context, field_id):
    schema_file = DECLARED_IN[context][field_id]
    system = _fields(context, schema_file)[field_id]["system"]

    assert system["repo_field"] is True


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", sorted(DECLARED_IN["default"]))
def test_a_learning_material_upload_may_write_the_field(context, field_id):
    """The content type the editorial cURL uploads — end to end through the loader."""
    repo_fields = get_repo_fields(context, VERSION, "learning_material.json")

    assert field_id in repo_fields


@pytest.mark.parametrize("context", CONTEXTS)
def test_the_extracted_and_the_derived_type_share_one_property(context):
    """
    `ccm:oeh_lrt` is the property, for both: what the extraction found and — only
    when it found nothing — the coarse type derived from the content type. They
    were two names for a while, which cost a rename on the write path and a
    second one in the diff.
    """
    repo_fields = get_repo_fields(context, VERSION, "learning_material.json")

    assert "ccm:oeh_lrt" in repo_fields
    assert "oeh:new_lrt" not in repo_fields


# ---------------------------------------------------- the AI provenance flags


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_the_ai_flag_exists_in_core(context, field_id):
    """In core.json, not in a content type: any resource can be AI-generated."""
    assert field_id in _fields(context, "core.json")


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_the_ai_flag_is_ai_filled_editable_and_written(context, field_id):
    system = _fields(context, "core.json")[field_id]["system"]

    assert system["repo_field"] is True
    assert system["ai_fillable"] is True
    assert system["ask_user"] is True, "a licence statement stays correctable"
    assert system["multiple"] is False


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_the_ai_flag_offers_exactly_true_and_false(context, field_id):
    """
    Stored as strings. A closed vocabulary is what keeps the LLM from answering
    'ja' or 'unbekannt', which the repository would store verbatim.
    """
    system = _fields(context, "core.json")[field_id]["system"]

    assert system["datatype"] == "string"
    vocabulary = system["vocabulary"]
    assert vocabulary["type"] == "closed"
    assert {c["value"] for c in vocabulary["concepts"]} == {"true", "false"}


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_the_ai_flag_is_labelled_and_prompted_in_both_languages(context, field_id):
    field = _fields(context, "core.json")[field_id]

    for part in ("label", "description", "prompt"):
        assert field[part]["de"].strip()
        assert field[part]["en"].strip()
    for concept in field["system"]["vocabulary"]["concepts"]:
        assert concept["label"]["de"].strip()
        assert concept["label"]["en"].strip()


@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_a_json_boolean_from_the_llm_counts_as_the_vocabulary_value(field_id):
    """
    A model asked for 'true' or 'false' returns a JSON boolean about as often as
    the string. str(True) is 'True', which does not match the concept value
    'true' — dropping it would lose the assessment silently, the same way the
    numeric quality scales used to lose theirs.
    """
    service = LLMService.__new__(LLMService)
    field = _fields("default", "core.json")[field_id]

    assert service._normalize_value(True, field) == "true"
    assert service._normalize_value(False, field) == "false"


@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_anything_but_true_or_false_is_refused(field_id):
    """The repository would store 'unbekannt' verbatim and never resolve it."""
    service = LLMService.__new__(LLMService)
    field = _fields("default", "core.json")[field_id]

    for value in ("unbekannt", "vielleicht", 5):
        assert service._normalize_value(value, field) is None


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", AI_LICENSE_FIELDS)
def test_the_ai_flag_reaches_the_repository_as_a_string(context, field_id):
    """
    The proven wire format is ["true"] / ["false"]. A Python bool would be
    serialized as a JSON boolean, which is a different value on the wire.
    """
    for value in ("true", "false"):
        result = normalize_for_repo({field_id: value}, {field_id})

        assert result == {field_id: [value]}
