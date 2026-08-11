"""
The WLO quality assessment fields live in core.json and must stay in sync with
the mds_oeh metadata set of the repository.

Two properties matter and are easy to break by accident:

1. The vocabularies must be the ones the repository actually accepts. They were
   read from the live metadata set (/rest/mds/v1/metadatasets/-home-/mds_oeh on
   both staging and prod) — a value the MDS does not know is written but never
   resolves to a label, which shows up as an empty field in the editorial desk.
2. The fields must be AI-filled, written to the repository, and invisible in the
   web component canvas. The widget hides exactly the fields with
   ask_user=false, so that flag is the whole hiding mechanism.
"""

import re
from pathlib import Path

import pytest

from src.services.llm_service import LLMService
from src.utils.schema_loader import get_repo_fields, get_schema_fields, load_manifest

CONTEXTS = ["default", "mds_oeh"]
VERSION = "2.0.0"

VOCAB = "http://w3id.org/openeduhub/vocabs"

# Machine verdict of the five knock-out criteria. The human variants exist in
# the MDS too, but an AI must never claim a human check was performed.
KO_VALUES = {
    f"{VOCAB}/quality/no_auto_findings",
    f"{VOCAB}/quality/auto_findings",
}

NUMERIC_SCALE = {str(i) for i in range(6)}

# field id -> the set of values the field may carry
EXPECTED_VALUES = {
    "ccm:oeh_quality_relevancy_for_education": {"0", "1"},
    "ccm:oeh_quality_criminal_law": KO_VALUES,
    "ccm:oeh_quality_protection_of_minors": KO_VALUES,
    "ccm:oeh_quality_copyright_law": KO_VALUES,
    "ccm:oeh_quality_personal_law": KO_VALUES,
    "ccm:oeh_quality_data_privacy": {
        f"{VOCAB}/quality_data_privacy/{i}" for i in range(6)
    },
    "ccm:oeh_quality_neutralness": {
        f"{VOCAB}/quality_neutrality/{i}" for i in range(6)
    },
    "ccm:oeh_quality_didactics": {f"{VOCAB}/quality_didactics/{i}" for i in range(6)},
    "ccm:oeh_quality_medial": {f"{VOCAB}/quality_media/{i}" for i in range(6)},
    "ccm:oeh_quality_transparentness": {
        f"{VOCAB}/quality_transparency/{i}" for i in range(6)
    },
    # No URI value space exists for these two in the MDS — the repository stores
    # the plain numbers, which is also what every curated node carries today.
    "ccm:oeh_quality_correctness": NUMERIC_SCALE,
    "ccm:oeh_quality_currentness": NUMERIC_SCALE,
    "ccm:oeh_buffet_criteria": {
        "content_valid",
        "speech_valid",
        "medial_relevant",
        "didactics_valid",
        "accessible",
        "usable_for_buffet",
    },
}

QUALITY_FIELD_IDS = sorted(EXPECTED_VALUES)


def _core_fields(context):
    return {f["id"]: f for f in get_schema_fields(context, VERSION, "core.json")}


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_field_exists_in_core(context, field_id):
    assert field_id in _core_fields(context)


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_field_is_hidden_but_ai_filled_and_written(context, field_id):
    system = _core_fields(context)[field_id]["system"]

    assert system["ask_user"] is False, "must not appear in the web component canvas"
    assert system["ai_fillable"] is True, "the AI assesses these fields"
    assert system["repo_field"] is True, "must be written to the WLO repository"


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_vocabulary_matches_the_repository_metadata_set(context, field_id):
    vocabulary = _core_fields(context)[field_id]["system"]["vocabulary"]

    assert vocabulary["type"] == "closed"
    actual = {
        concept.get("uri") or concept.get("value") for concept in vocabulary["concepts"]
    }
    assert actual == EXPECTED_VALUES[field_id]


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_every_concept_is_labelled_in_both_languages(context, field_id):
    """The label reaches the LLM prompt — an empty one silently degrades it."""
    vocabulary = _core_fields(context)[field_id]["system"]["vocabulary"]

    for concept in vocabulary["concepts"]:
        assert concept["label"]["de"].strip()
        assert concept["label"]["en"].strip()


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_field_has_a_prompt_in_both_languages(context, field_id):
    prompt = _core_fields(context)[field_id]["prompt"]

    assert prompt["de"].strip()
    assert prompt["en"].strip()


@pytest.mark.parametrize("context", CONTEXTS)
def test_buffet_criteria_is_the_only_multi_valued_field(context):
    fields = _core_fields(context)

    for field_id in QUALITY_FIELD_IDS:
        system = fields[field_id]["system"]
        expected_multiple = field_id == "ccm:oeh_buffet_criteria"
        assert system["multiple"] is expected_multiple
        assert system["datatype"] == ("array" if expected_multiple else "string")


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("schema_file", ["learning_material.json", "event.json"])
def test_quality_fields_are_uploaded_for_every_content_type(context, schema_file):
    """They sit in core.json, so they apply to all content types."""
    repo_fields = get_repo_fields(context, VERSION, schema_file)

    assert set(QUALITY_FIELD_IDS) <= repo_fields


@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_the_extraction_prompt_offers_exactly_the_repository_values(field_id):
    """
    The LLM only ever sees the vocabulary through the prompt. If a value does not
    appear there it cannot be produced — and the prompt truncates at 20 concepts,
    which every one of these vocabularies stays below.
    """
    service = LLMService.__new__(LLMService)
    field = _core_fields("default")[field_id]

    prompt = service._build_extraction_prompt(field, "Beispieltext.", None, "de")

    for value in EXPECTED_VALUES[field_id]:
        assert value in prompt
    assert "weitere" not in prompt.split("Vokabular")[-1]


@pytest.mark.parametrize("field_id", QUALITY_FIELD_IDS)
def test_repository_values_survive_normalization_unchanged(field_id):
    service = LLMService.__new__(LLMService)
    field = _core_fields("default")[field_id]

    for value in EXPECTED_VALUES[field_id]:
        assert service._normalize_value(value, field) == value


MIGRATED_TO_URIS = sorted(
    field_id
    for field_id, values in EXPECTED_VALUES.items()
    if any(value.startswith("http") for value in values)
)


NUMERIC_FIELDS = sorted(
    field_id for field_id, values in EXPECTED_VALUES.items() if values <= NUMERIC_SCALE
)


@pytest.mark.parametrize("field_id", NUMERIC_FIELDS)
def test_a_number_from_the_llm_counts_as_the_scale_value(field_id):
    """
    The scales are stored as the strings '0'…'5', but an LLM asked for one of
    those returns a JSON number about as often as a string. Dropping that would
    lose the assessment silently.
    """
    service = LLMService.__new__(LLMService)
    field = _core_fields("default")[field_id]

    for value in EXPECTED_VALUES[field_id]:
        assert service._normalize_value(int(value), field) == value


@pytest.mark.parametrize("field_id", NUMERIC_FIELDS)
def test_a_number_outside_the_scale_is_still_refused(field_id):
    service = LLMService.__new__(LLMService)
    field = _core_fields("default")[field_id]

    assert service._normalize_value(9, field) is None


@pytest.mark.parametrize("field_id", MIGRATED_TO_URIS)
def test_the_legacy_numeric_scale_is_not_written_for_migrated_fields(field_id):
    """
    These fields moved to URI value spaces. The old numbers no longer resolve to
    a label in the repository — and for the knock-out criteria '0' now maps to
    the human 'findings' entry, the opposite of what it used to mean. Letting one
    through would write a wrong verdict, so it must be dropped instead.
    """
    service = LLMService.__new__(LLMService)
    field = _core_fields("default")[field_id]

    for legacy in ("0", "1", "5"):
        assert service._normalize_value(legacy, field) is None


def test_the_repo_field_list_document_stays_in_sync_with_the_schemas():
    """
    WLO-REPO-FELDER.md is the review list handed to the WLO side. A field added
    to a schema but missing from the document silently ends up in the repository
    without anyone having signed it off.
    """
    document = (Path(__file__).resolve().parents[1] / "WLO-REPO-FELDER.md").read_text(
        encoding="utf-8"
    )

    manifest = load_manifest("default")["versions"][VERSION]
    documented = set(re.findall(r"`([a-z]+:[A-Za-z_]+)`", document))

    for schema_file in manifest["schemas"]:
        for field in get_schema_fields("default", VERSION, schema_file):
            if field["system"].get("repo_field"):
                assert field["id"] in documented, (
                    f"{field['id']} ({schema_file}) fehlt in WLO-REPO-FELDER.md"
                )
