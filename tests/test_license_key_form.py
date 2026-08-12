"""
The spelling of ccm:commonlicense_key decides whether the licence exists.

There are two ways a licence reaches the node, and they used to disagree:

* a creativecommons.org deed URL in `ccm:custom_license` — mapped by
  `repository_licenses` to `CC_BY_SA`, correct;
* the extraction filling `ccm:commonlicense_key` directly from the field's own
  closed vocabulary — which listed `CC BY-SA`, with a space and a hyphen.

Measured against staging on 2026-08-12 by writing each form to a node and
reading it back. All seven of the spaced forms are stored verbatim and leave
`virtual:licenseurl` **null** — the repository does not recognise them as a
licence. All seven underscore forms resolve to their deed URL:

    CC BY-SA  → gespeichert, virtual:licenseurl = null
    CC_BY_SA  → https://creativecommons.org/licenses/by-sa/4.0/deed.de

`ccm:commonlicense_key_DISPLAYNAME` is null either way, so nothing about the
node's own fields gives the failure away — `virtual:licenseurl` is the only
place it shows.
"""

import json
from pathlib import Path

import pytest

from src.services.repository_licenses import (
    VALID_LICENSE_KEYS,
    map_creative_commons_url,
)
from src.utils.schema_loader import get_schema_fields

SCHEMATA = Path(__file__).resolve().parents[1] / "src/schemata"
CONTEXTS = ["default", "mds_oeh"]
VERSION = "2.0.0"

# The form the repository resolves, per licence. Left column is what the
# vocabulary used to offer.
RESOLVES = {
    "CC0": "CC_0",
    "CC BY": "CC_BY",
    "CC BY-SA": "CC_BY_SA",
    "CC BY-ND": "CC_BY_ND",
    "CC BY-NC": "CC_BY_NC",
    "CC BY-NC-SA": "CC_BY_NC_SA",
    "CC BY-NC-ND": "CC_BY_NC_ND",
}

RETIRED = sorted(RESOLVES)
EXPECTED = sorted(RESOLVES.values())


def _files_with_the_field():
    for path in sorted(SCHEMATA.glob(f"*/v{VERSION}/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for field in data.get("fields", []):
            if field["id"] == "ccm:commonlicense_key":
                yield path, field


FILES = list(_files_with_the_field())


@pytest.mark.parametrize("path, field", FILES, ids=[str(p.name) for p, _ in FILES])
def test_the_vocabulary_offers_the_form_the_repository_resolves(path, field):
    values = sorted(c["value"] for c in field["system"]["vocabulary"]["concepts"])

    assert values == EXPECTED, f"{path}"


@pytest.mark.parametrize("path, field", FILES, ids=[str(p.name) for p, _ in FILES])
def test_no_retired_spelling_is_offered_anywhere(path, field):
    """A value the repository stores but never resolves is a licence that is gone."""
    values = {c["value"] for c in field["system"]["vocabulary"]["concepts"]}

    assert not values & set(RETIRED), f"{path}: {sorted(values & set(RETIRED))}"


@pytest.mark.parametrize("path, field", FILES, ids=[str(p.name) for p, _ in FILES])
def test_the_prompt_names_the_same_values_as_the_vocabulary(path, field):
    """
    The vocabulary reaches the model through the prompt. Listing one spelling in
    the prose and another in the concepts invites exactly the value that fails.
    """
    values = {c["value"] for c in field["system"]["vocabulary"]["concepts"]}
    prompt = field["prompt"]["de"]

    for retired in RETIRED:
        assert retired not in prompt, f"{path}: '{retired}' steht noch im Prompt"
    for value in values:
        assert value in prompt, f"{path}: '{value}' fehlt im Prompt"


@pytest.mark.parametrize("context", CONTEXTS)
def test_the_active_content_types_are_covered(context):
    """learning_material and didactic_planning_tools are the ones in use."""
    for schema_file in ("learning_material.json", "didactic_planning_tools.json"):
        fields = {f["id"]: f for f in get_schema_fields(context, VERSION, schema_file)}
        values = {
            c["value"]
            for c in fields["ccm:commonlicense_key"]["system"]["vocabulary"]["concepts"]
        }
        assert values == set(EXPECTED)


# ---------------------------------------------------- agreement with the code


@pytest.mark.parametrize("value", EXPECTED)
def test_every_offered_value_passes_the_license_validation(value):
    """
    `transform_license` drops a key it does not know, so a vocabulary the code
    rejects would silently clear the field it just filled.
    """
    assert value in VALID_LICENSE_KEYS


@pytest.mark.parametrize(
    "deed, key",
    [
        ("https://creativecommons.org/licenses/by-sa/4.0/", "CC_BY_SA"),
        ("https://creativecommons.org/licenses/by-nc-nd/4.0/", "CC_BY_NC_ND"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC_0"),
    ],
)
def test_both_paths_to_a_license_now_produce_the_same_key(deed, key):
    """
    The deed-URL path was always correct; the vocabulary was the one out of step.
    Whichever way the licence arrives, the node must end up with one spelling.
    """
    assert map_creative_commons_url(deed)["ccm:commonlicense_key"] == [key]
    assert key in EXPECTED


# --------------------------------------------------------- the safety net


@pytest.mark.parametrize("spoken, stored", sorted(RESOLVES.items()))
def test_the_familiar_spelling_still_maps_to_the_stored_one(spoken, stored):
    """
    'CC BY-SA' is how the licence is written everywhere outside this repository,
    and it is what a model returns by default. The concept **labels** were left
    in that form on purpose: the vocabulary match falls through to them and hands
    back the concept's value. So the familiar spelling arrives and the resolving
    one is written — the prompt does not have to win that argument.
    """
    from src.services.llm_service import LLMService
    from src.utils.schema_loader import get_schema_fields

    service = LLMService.__new__(LLMService)
    field = {
        f["id"]: f
        for f in get_schema_fields("default", VERSION, "learning_material.json")
    }["ccm:commonlicense_key"]

    assert service._normalize_value(spoken, field) == stored
    assert service._normalize_value(spoken.lower(), field) == stored


def test_a_licence_it_cannot_place_is_dropped_rather_than_guessed():
    """Writing a wrong licence is worse than writing none — see CHANGELOG 1 and 2."""
    from src.services.llm_service import LLMService
    from src.utils.schema_loader import get_schema_fields

    service = LLMService.__new__(LLMService)
    field = {
        f["id"]: f
        for f in get_schema_fields("default", VERSION, "learning_material.json")
    }["ccm:commonlicense_key"]

    for value in ("Namensnennung", "irgendwas", "GPL", ""):
        assert service._normalize_value(value, field) is None
