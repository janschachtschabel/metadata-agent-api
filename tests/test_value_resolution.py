"""
Whether a written value is a value, or just text sitting in a field.

Three bugs this session had the same shape: something was sent, the repository
answered `200`, and the value never arrived as a value.

* `oeh:new_lrt` — not in the content model, silently discarded
* `CC BY-SA` — stored verbatim, but the repository does not read it as a licence
* a fabricated `new_lrt` UUID — stored, resolving to nothing

None of them showed up in the status code, in `fields_written`, or in the
SOLL/IST diff: the field was there and its value equalled what was sent. What
gives them away is whether the repository can turn the value into a label.

Measured on a live node (2026-08-12): of the 19 vocabulary fields set there, 18
carry a `<field>_DISPLAYNAME` and one — `ccm:commonlicense_key` — never does; its
signal is `virtual:licenseurl`. `ccm:oeh_quality_correctness` carried a value and
an **empty** DISPLAYNAME, which is the documented case of a number outside the
MDS value space. That is the rule this file pins:

    vocabulary field  → <field>_DISPLAYNAME must be non-empty
    commonlicense_key → virtual:licenseurl must be present
    everything else   → nothing to resolve, no verdict
"""

import pytest

from src.services.repository_diff import check_resolution, compute_diff

CONTEXT, VERSION = "default", "2.0.0"

BASE = {"metadataset": "learning_material.json"}

LRT = "http://w3id.org/openeduhub/vocabs/new_lrt/36e68792-6159-481d-a97b-2c00901f4f78"


# ------------------------------------------------------------- the rule alone


def test_a_vocabulary_value_with_a_label_resolves():
    properties = {
        "ccm:oeh_lrt": [LRT],
        "ccm:oeh_lrt_DISPLAYNAME": ["Arbeitsblatt"],
    }

    assert check_resolution("ccm:oeh_lrt", properties, CONTEXT, VERSION) == "resolved"


@pytest.mark.parametrize("displayname", [[""], [], ["   "], None])
def test_a_vocabulary_value_without_a_label_does_not(displayname):
    """
    The exact shape of the three bugs: the value is there, nothing reads it.
    edu-sharing answers an unknown value with an empty DISPLAYNAME rather than
    an error.
    """
    properties = {"ccm:oeh_lrt": [LRT]}
    if displayname is not None:
        properties["ccm:oeh_lrt_DISPLAYNAME"] = displayname

    assert check_resolution("ccm:oeh_lrt", properties, CONTEXT, VERSION) == "unresolved"


@pytest.mark.parametrize(
    "key, licenseurl, expected",
    [
        ("CC_BY_SA", ["https://creativecommons.org/licenses/by-sa/4.0/"], "resolved"),
        ("CC BY-SA", None, "unresolved"),
        ("CC BY-SA", [], "unresolved"),
    ],
)
def test_the_licence_is_judged_by_its_url_not_by_a_label(key, licenseurl, expected):
    """
    ccm:commonlicense_key never gets a DISPLAYNAME — not even when it resolves.
    Judging it by the general rule would report every licence as unresolved.
    """
    properties = {"ccm:commonlicense_key": [key]}
    if licenseurl is not None:
        properties["virtual:licenseurl"] = licenseurl

    verdict = check_resolution("ccm:commonlicense_key", properties, CONTEXT, VERSION)

    assert verdict == expected


@pytest.mark.parametrize(
    "field_id", ["cclom:title", "cclom:general_description", "ccm:wwwurl"]
)
def test_free_text_has_nothing_to_resolve(field_id):
    """No verdict rather than a passing one — the difference matters in a report."""
    properties = {field_id: ["irgendwas"]}

    assert check_resolution(field_id, properties, CONTEXT, VERSION) is None


def test_a_field_that_is_not_on_the_node_gets_no_verdict():
    assert check_resolution("ccm:oeh_lrt", {}, CONTEXT, VERSION) is None


# ------------------------------------------------------- inside the diff


def _entry(diff, field_id):
    return next(e for e in diff if e["field_id"] == field_id)


def test_the_diff_reports_a_value_that_matches_but_does_not_resolve():
    """
    The case that made this necessary: sent and stored are equal, so the field
    reads 'match' — and the value is still dead.
    """
    expected = {**BASE, "ccm:oeh_lrt": LRT}
    properties = {"ccm:oeh_lrt": [LRT], "ccm:oeh_lrt_DISPLAYNAME": [""]}

    diff, summary = compute_diff(
        expected, {"ccm:oeh_lrt": LRT}, CONTEXT, VERSION, properties=properties
    )

    entry = _entry(diff, "ccm:oeh_lrt")
    assert entry["status"] == "match"
    assert entry["resolution"] == "unresolved"
    assert summary["unresolved"] == 1


def test_a_value_that_resolves_is_marked_as_such():
    expected = {**BASE, "ccm:oeh_lrt": LRT}
    properties = {"ccm:oeh_lrt": [LRT], "ccm:oeh_lrt_DISPLAYNAME": ["Arbeitsblatt"]}

    diff, summary = compute_diff(
        expected, {"ccm:oeh_lrt": LRT}, CONTEXT, VERSION, properties=properties
    )

    assert _entry(diff, "ccm:oeh_lrt")["resolution"] == "resolved"
    assert summary["unresolved"] == 0


def test_without_the_raw_properties_no_verdict_is_invented():
    """
    The properties are optional so existing callers keep working. Reporting
    'resolved' because nothing was checked would be worse than reporting nothing.
    """
    expected = {**BASE, "ccm:oeh_lrt": LRT}

    diff, summary = compute_diff(expected, {"ccm:oeh_lrt": LRT}, CONTEXT, VERSION)

    assert _entry(diff, "ccm:oeh_lrt")["resolution"] is None
    assert summary["unresolved"] == 0


def test_the_licence_case_survives_the_whole_diff():
    expected = {**BASE, "ccm:commonlicense_key": "CC BY-SA"}
    properties = {"ccm:commonlicense_key": ["CC BY-SA"]}

    diff, summary = compute_diff(
        expected,
        {"ccm:commonlicense_key": "CC BY-SA"},
        CONTEXT,
        VERSION,
        properties=properties,
    )

    entry = _entry(diff, "ccm:commonlicense_key")
    assert entry["status"] == "match"
    assert entry["resolution"] == "unresolved"


def test_a_field_that_never_arrived_is_still_reported_as_missing():
    """The resolution check is an addition, not a replacement."""
    expected = {**BASE, "ccm:oeh_lrt": LRT}

    diff, summary = compute_diff(expected, {}, CONTEXT, VERSION, properties={})

    entry = _entry(diff, "ccm:oeh_lrt")
    assert entry["status"] == "missing_in_repo"
    assert entry["resolution"] is None


# ------------------------------------------------------- standing on its own


def test_a_node_can_be_checked_without_any_expected_metadata():
    """
    'Which of this node's values are dead?' needs no SOLL side — and that is the
    question someone asks about a node they did not upload themselves.
    """
    from src.services.repository_diff import unresolved_values

    properties = {
        "cclom:title": ["Ein Titel"],
        "ccm:oeh_lrt": [LRT],
        "ccm:oeh_lrt_DISPLAYNAME": [""],
        "ccm:educationalcontext": [
            "http://w3id.org/openeduhub/vocabs/educationalContext/schule"
        ],
        "ccm:educationalcontext_DISPLAYNAME": ["Schule"],
        "ccm:commonlicense_key": ["CC BY-SA"],
    }

    findings = unresolved_values(properties, CONTEXT, VERSION, "learning_material.json")

    assert {f["field_id"] for f in findings} == {"ccm:oeh_lrt", "ccm:commonlicense_key"}


def test_the_fields_the_mds_has_no_labels_for_are_marked_as_known():
    """
    ccm:oeh_quality_correctness and the three ccm:commonlicense_ai_* have no
    value space in the MDS. They are stored and read back correctly; there is
    simply no label. They turn up on **every** node, so a report that does not
    separate them trains its reader to skip it.
    """
    from src.services.repository_diff import unresolved_values

    properties = {
        "ccm:oeh_quality_correctness": ["4"],
        "ccm:commonlicense_ai_allow_usage": ["true"],
        "ccm:oeh_lrt": [LRT],
        "ccm:oeh_lrt_DISPLAYNAME": [""],
    }

    findings = unresolved_values(properties, CONTEXT, VERSION, "learning_material.json")
    by_field = {f["field_id"]: f["known"] for f in findings}

    assert by_field["ccm:oeh_lrt"] is False
    assert by_field["ccm:oeh_quality_correctness"] is True
    assert by_field["ccm:commonlicense_ai_allow_usage"] is True


def test_the_real_findings_are_listed_first():
    from src.services.repository_diff import unresolved_values

    properties = {
        "ccm:oeh_quality_correctness": ["4"],
        "ccm:oeh_lrt": [LRT],
        "ccm:oeh_lrt_DISPLAYNAME": [""],
    }

    findings = unresolved_values(properties, CONTEXT, VERSION, "learning_material.json")

    assert [f["known"] for f in findings] == sorted(f["known"] for f in findings)
    assert findings[0]["field_id"] == "ccm:oeh_lrt"


def test_a_healthy_node_reports_nothing():
    from src.services.repository_diff import unresolved_values

    properties = {
        "cclom:title": ["Ein Titel"],
        "ccm:oeh_lrt": [LRT],
        "ccm:oeh_lrt_DISPLAYNAME": ["Arbeitsblatt"],
        "ccm:commonlicense_key": ["CC_BY_SA"],
        "virtual:licenseurl": ["https://creativecommons.org/licenses/by-sa/4.0/"],
    }

    assert (
        unresolved_values(properties, CONTEXT, VERSION, "learning_material.json") == []
    )
