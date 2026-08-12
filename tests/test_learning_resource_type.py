"""
The learning resource type, and the property that actually holds it.

Measured against the live repository on 2026-08-12: `oeh:new_lrt` does not exist
in the content model — a write is answered `200` and silently discarded, and no
node out of 100 carries it. The property the repository keeps is **`ccm:oeh_lrt`**;
124 values across those 100 nodes, all of them URIs from the `new_lrt` vocabulary
(`new_lrt_aggregated` appears nowhere), all resolving to a label.

So the extracted type has to land in `ccm:oeh_lrt` — which is also where the
upload writes a *derived* type, mapped coarsely from the detected content type
(learning_material → "Material"). Both cannot win: the extraction knows
"Arbeitsblatt" where the derivation only knows "Material", and the extended-data
write happens **after** the metadata write, so without care the coarse value
overwrites the precise one.
"""

import json
from pathlib import Path

import httpx
import pytest

from src.services.repository_values import normalize_for_repo, transform_lrt
from src.utils.schema_loader import get_schema_fields

CONTEXTS = ["default", "mds_oeh"]
VERSION = "2.0.0"

VOCAB = "http://w3id.org/openeduhub/vocabs/new_lrt"
ARBEITSBLATT = f"{VOCAB}/8e83b3f9-cd5b-4bef-99c9-6bcdd6b1f3d8"
MATERIAL = f"{VOCAB}/1846d876-d8fd-476a-b540-b8ffd713fedb"


def _lrt_field(context):
    fields = {f["id"]: f for f in get_schema_fields(context, VERSION, "core.json")}
    return fields["oeh:new_lrt"]


# ------------------------------------------------------ the write target


def test_the_extracted_type_is_written_to_the_property_the_repository_keeps():
    normalized = normalize_for_repo({"oeh:new_lrt": [ARBEITSBLATT]}, {"oeh:new_lrt"})

    transform_lrt(normalized)

    assert normalized == {"ccm:oeh_lrt": [ARBEITSBLATT]}


def test_the_source_key_does_not_survive_the_transformation():
    """Writing both would send one value into a property that discards it."""
    normalized = {"oeh:new_lrt": [ARBEITSBLATT]}

    transform_lrt(normalized)

    assert "oeh:new_lrt" not in normalized


def test_nothing_is_invented_when_no_type_was_extracted():
    normalized = {"cclom:title": ["Titel"]}

    transform_lrt(normalized)

    assert normalized == {"cclom:title": ["Titel"]}


@pytest.mark.parametrize("empty", [[], None, ""])
def test_an_empty_type_does_not_produce_an_empty_property(empty):
    normalized = {"oeh:new_lrt": empty}

    transform_lrt(normalized)

    assert "ccm:oeh_lrt" not in normalized


def test_an_existing_repository_value_is_not_overwritten():
    """Whoever set ccm:oeh_lrt directly meant it."""
    normalized = {"oeh:new_lrt": [ARBEITSBLATT], "ccm:oeh_lrt": [MATERIAL]}

    transform_lrt(normalized)

    assert normalized["ccm:oeh_lrt"] == [MATERIAL]
    assert "oeh:new_lrt" not in normalized


# ------------------------------------------------------------ the vocabulary


@pytest.mark.parametrize("context", CONTEXTS)
def test_the_vocabulary_is_the_full_new_lrt_tree(context):
    """
    87 of 220 concepts were listed, so 133 real types could not be produced —
    'Quelle', 'Portal', 'Datenbank', 'Lexikon oder Enzyklopädie' among them. The
    vocabulary is closed, so a concept that is missing here is a value the
    extraction can never return.
    """
    concepts = _lrt_field(context)["system"]["vocabulary"]["concepts"]

    assert len(concepts) == 220


@pytest.mark.parametrize("context", CONTEXTS)
def test_every_concept_is_a_new_lrt_uri(context):
    """
    Not new_lrt_aggregated: the repository stores new_lrt URIs exclusively —
    124 values across 100 read nodes, none from the aggregated vocabulary.
    """
    concepts = _lrt_field(context)["system"]["vocabulary"]["concepts"]

    for concept in concepts:
        assert concept["uri"].startswith(f"{VOCAB}/"), concept["uri"]
        assert concept["label"]["de"].strip()


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize(
    "label", ["Quelle", "Portal", "Datenbank", "Arbeitsblatt", "Material", "Webseite"]
)
def test_the_types_the_repository_actually_uses_are_offered(context, label):
    concepts = _lrt_field(context)["system"]["vocabulary"]["concepts"]

    assert label in {c["label"]["de"] for c in concepts}


def test_both_contexts_carry_the_same_vocabulary():
    def by_uri(context):
        return {
            c["uri"]: c["label"]["de"]
            for c in _lrt_field(context)["system"]["vocabulary"]["concepts"]
        }

    assert by_uri("default") == by_uri("mds_oeh")


@pytest.mark.slow
def test_the_vocabulary_still_matches_the_published_one():
    """
    The single test that talks to the network. It is what makes the number above
    mean something — 220 is only correct as long as the published vocabulary says
    so. Skipped when offline rather than failing, because a broken build on a
    train is worse than a stale count.
    """

    def flatten(concepts, out):
        for concept in concepts:
            out[concept["id"]] = (concept.get("prefLabel") or {}).get("de", "")
            if concept.get("narrower"):
                flatten(concept["narrower"], out)

    try:
        response = httpx.get(
            "https://vocabs.openeduhub.de/w3id.org/openeduhub/vocabs/new_lrt/index.json",
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"Vokabular nicht erreichbar: {exc}")

    published = {}
    flatten(response.json()["hasTopConcept"], published)
    ours = {
        c["uri"]: c["label"]["de"]
        for c in _lrt_field("default")["system"]["vocabulary"]["concepts"]
    }

    assert ours == published


def test_the_snapshot_used_by_the_schema_is_kept_in_the_repository():
    """The offline tests above compare against this; it is how they stay checkable."""
    snapshot = Path(__file__).resolve().parents[1] / "src/schemata/vocabs/new_lrt.json"

    assert snapshot.exists()
    concepts = json.loads(snapshot.read_text(encoding="utf-8"))
    assert len(concepts) == 220
