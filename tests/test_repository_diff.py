"""
Comparing what was sent against what the repository stored.

This is what `/upload/verify` reports on. It was the least exercised code in the
service — reachable only through a live repository read — so these tests pin the
comparison rules before anything moves.

The rules are looser than equality on purpose: edu-sharing returns every value
as an array, lower-cases nothing, and converts dates to epoch milliseconds.
A comparison that ignored that would report mismatches for values that are in
fact identical.
"""

import pytest

from src.services import repository_diff as diff_module
from src.services.repository_diff import (
    compute_diff,
    dates_match,
    normalize_compare,
    properties_to_flat,
    to_epoch_ms,
    values_match,
)


# --------------------------------------------------- repository → flat metadata


def test_a_single_element_array_becomes_the_value():
    assert properties_to_flat({"cclom:title": ["Titel"]}) == {"cclom:title": "Titel"}


def test_a_multi_element_array_stays_a_list():
    assert properties_to_flat({"cclom:general_keyword": ["a", "b"]}) == {
        "cclom:general_keyword": ["a", "b"]
    }


def test_empty_arrays_disappear():
    assert properties_to_flat({"cclom:title": []}) == {}


@pytest.mark.parametrize(
    "key",
    [
        "sys:node-uuid",
        "virtual:primaryparent_nodeid",
        "ccm:taxonid_DISPLAYNAME",
        "ccm:lifecyclecontributer_authorVCARD_GIVENNAME",
        "cm:created",
        "cm:name",
    ],
)
def test_system_and_derived_properties_are_dropped(key):
    """They are repository bookkeeping, not metadata anyone sent."""
    assert properties_to_flat({key: ["x"]}) == {}


@pytest.mark.parametrize("key", ["cm:author", "cm:latitude", "cm:longitude"])
def test_the_three_useful_cm_properties_survive(key):
    assert properties_to_flat({key: ["x"]}) == {key: "x"}


# ------------------------------------------------------------- value comparison


@pytest.mark.parametrize(
    "expected, actual",
    [
        ("Titel", ["Titel"]),  # repository wraps everything in arrays
        ("Titel", "  titel  "),  # case and padding are irrelevant
        (["b", "a"], ["a", "b"]),  # order of a multi-value field is not meaningful
        ({"uri": "http://x/1"}, "http://x/1"),  # objects compare by their URI
        ({"label": "Mathe"}, "mathe"),
    ],
)
def test_values_that_only_differ_in_representation_match(expected, actual):
    assert values_match(expected, actual) is True


@pytest.mark.parametrize(
    "expected, actual",
    [("Titel", "Anderer Titel"), (["a", "b"], ["a"]), ("1", "2")],
)
def test_genuinely_different_values_do_not_match(expected, actual):
    assert values_match(expected, actual) is False


def test_an_iso_date_matches_the_epoch_millis_the_repository_returns():
    assert values_match("2026-03-15T10:00:00Z", "1773568800000") is True


def test_a_date_an_hour_apart_does_not_match():
    assert values_match("2026-03-15T10:00:00Z", "1773572400000") is False


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1773568800000", 1773568800000),  # already millis
        ("1773568800", 1773568800000),  # seconds get scaled
        ("2026-03-15T10:00:00Z", 1773568800000),
        ("2026-03-15T10:00:00", 1773568800000),
        ("2026-03-15T10:00", 1773568800000),
        ("kein Datum", None),
        ("42", None),  # too small to be a timestamp
    ],
)
def test_epoch_conversion(value, expected):
    assert to_epoch_ms(value) == expected


def test_two_non_dates_never_match_as_dates():
    assert dates_match("Titel", "Titel") is False


def test_normalise_unwraps_single_element_lists_recursively():
    assert normalize_compare([["  Titel "]]) == "titel"


# --------------------------------------------------------------- the whole diff


BASE = {"contextName": "default", "schemaVersion": "2.0.0", "metadataset": "core.json"}


def _statuses(diff):
    return {entry["field_id"]: entry["status"] for entry in diff}


def test_a_field_written_as_sent_counts_as_match():
    diff, summary = compute_diff(
        {**BASE, "cclom:title": "Titel"},
        {"cclom:title": "Titel"},
        "default",
        "2.0.0",
    )

    assert _statuses(diff)["cclom:title"] == "match"
    assert summary["match"] == 1


def test_a_field_the_repository_stored_differently_counts_as_mismatch():
    diff, summary = compute_diff(
        {**BASE, "cclom:title": "Titel"}, {"cclom:title": "Anderer"}, "default", "2.0.0"
    )

    assert _statuses(diff)["cclom:title"] == "mismatch"
    assert summary["mismatch"] == 1


def test_a_field_that_never_arrived_counts_as_missing():
    diff, summary = compute_diff(
        {**BASE, "cclom:title": "Titel"}, {}, "default", "2.0.0"
    )

    assert _statuses(diff)["cclom:title"] == "missing_in_repo"
    assert summary["missing_in_repo"] == 1


def test_a_field_without_repo_field_is_reported_as_not_written():
    """Not a defect — the schema never marked it for writing."""
    diff, summary = compute_diff(
        {**BASE, "ccm:oeh_extendedType": "x"}, {}, "default", "2.0.0"
    )

    assert _statuses(diff)["ccm:oeh_extendedType"] == "not_written"
    assert summary["not_written"] == 1


@pytest.mark.parametrize("field_id", ["virtual:collection_id_primary", "schema:name"])
def test_internal_prefixes_are_reported_as_not_written(field_id):
    diff, _ = compute_diff({**BASE, field_id: "x"}, {}, "default", "2.0.0")

    assert _statuses(diff)[field_id] == "not_written"


def test_something_only_the_repository_has_is_reported_as_extra():
    diff, summary = compute_diff(
        {**BASE}, {"ccm:wf_status": "200_tocheck"}, "default", "2.0.0"
    )

    assert _statuses(diff)["ccm:wf_status"] == "extra_in_repo"
    assert summary["extra_in_repo"] == 1


def test_the_author_transformation_is_not_reported_as_a_loss():
    """
    cm:author is written as a VCARD under a different property. It is only a
    repo field of the content types that declare it — with core.json alone the
    'not written' rule applies first.
    """
    diff, summary = compute_diff(
        {**BASE, "metadataset": "learning_material.json", "cm:author": "Philipp Lang"},
        {"ccm:lifecyclecontributer_authorFN": "Philipp Lang"},
        "default",
        "2.0.0",
    )

    assert _statuses(diff)["cm:author"] == "match"
    assert summary["match"] == 1


def test_header_keys_and_upload_options_are_not_compared():
    diff, _ = compute_diff(
        {**BASE, "language": "de", "check_duplicates": True, "_origins": {"a": "ai"}},
        {},
        "default",
        "2.0.0",
    )

    assert diff == []


def test_empty_expected_values_are_not_compared():
    diff, _ = compute_diff(
        {**BASE, "cclom:title": None, "ccm:wwwurl": "", "cclom:general_keyword": []},
        {},
        "default",
        "2.0.0",
    )

    assert diff == []


def test_problems_are_listed_before_matches():
    """The report is meant to be read top-down."""
    diff, _ = compute_diff(
        {**BASE, "cclom:title": "Titel", "ccm:wwwurl": "https://example.org"},
        {"cclom:title": "Titel"},
        "default",
        "2.0.0",
    )

    assert [entry["status"] for entry in diff] == ["missing_in_repo", "match"]


def test_an_unreadable_schema_reports_not_written_instead_of_blaming_the_repo(
    monkeypatch,
):
    """
    get_repo_fields() swallows a load failure and returns an empty set. The write
    path then refuses to write anything at all (normalize_for_repo), so the
    fields are absent from the repository *by decision*, not because it lost
    them. Reporting them as 'missing_in_repo' points at the wrong culprit in
    exactly the situation this report exists to diagnose.
    """
    monkeypatch.setattr(diff_module, "get_repo_fields", lambda *a, **k: set())

    diff, summary = compute_diff(
        {**BASE, "cclom:title": "Titel", "ccm:wwwurl": "https://example.org"},
        {},
        "default",
        "2.0.0",
    )

    assert summary["missing_in_repo"] == 0
    assert summary["not_written"] == 2
    assert set(_statuses(diff).values()) == {"not_written"}
