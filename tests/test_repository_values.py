"""
Shaping metadata for the repository API: filtering, flattening, authors,
coordinates.

These are the pure steps between "what the AI produced" and "what edu-sharing
receives". They were reachable only through a full upload before, which left
most of their branches unexercised — these tests pin the behaviour so it can be
moved and changed safely. Licences have their own file.
"""

import pytest

from src.services.repository_values import (
    extract_geo_coordinates,
    flatten_value,
    normalize_for_repo,
    transform_author_to_vcard,
)

REPO_FIELDS = {"cclom:title", "ccm:wwwurl", "cm:author", "ccm:custom_license"}


# ------------------------------------------------------------------ filtering


def test_only_repo_fields_are_written():
    result = normalize_for_repo(
        {"cclom:title": "Titel", "ccm:unbekannt": "wert"}, REPO_FIELDS
    )

    assert result == {"cclom:title": ["Titel"]}


@pytest.mark.parametrize(
    "key", ["virtual:collection_id_primary", "schema:location", "schema:name"]
)
def test_internal_prefixes_never_reach_the_repository(key):
    """They are inputs for transformations, not properties of their own."""
    result = normalize_for_repo({key: "wert"}, REPO_FIELDS | {key})

    assert result == {}


def test_without_a_repo_field_set_nothing_is_written():
    """Refusing to guess beats writing blindly when the schema failed to load."""
    assert normalize_for_repo({"cclom:title": "Titel"}, set()) == {}
    assert normalize_for_repo({"cclom:title": "Titel"}, None) == {}


@pytest.mark.parametrize("empty", [None, "", []])
def test_empty_values_are_skipped(empty):
    assert normalize_for_repo({"cclom:title": empty}, REPO_FIELDS) == {}


def test_every_value_becomes_an_array():
    result = normalize_for_repo(
        {"cclom:title": "Titel", "cm:author": ["A", "B"]}, REPO_FIELDS
    )

    assert result == {"cclom:title": ["Titel"], "cm:author": ["A", "B"]}


def test_empty_entries_inside_a_list_are_dropped():
    result = normalize_for_repo({"cm:author": ["A", None, ""]}, REPO_FIELDS)

    assert result == {"cm:author": ["A"]}


# ------------------------------------------------------------------ flattening


@pytest.mark.parametrize("value", ["text", 42, 3.5, True])
def test_simple_values_pass_through(value):
    assert flatten_value(value) == value


@pytest.mark.parametrize(
    "item, expected",
    [
        ({"uri": "u", "name": "n", "label": "l"}, "u"),
        ({"name": "n", "label": "l"}, "n"),
        ({"label": "l", "value": "v"}, "l"),
        ({"@value": "a", "value": "v"}, "a"),
        ({"value": "v"}, "v"),
    ],
)
def test_objects_are_reduced_by_a_fixed_priority(item, expected):
    assert flatten_value(item) == expected


def test_an_object_without_a_known_key_is_serialised():
    assert flatten_value({"street": "Hauptstr. 1"}) == '{"street": "Hauptstr. 1"}'


def test_none_stays_none():
    assert flatten_value(None) is None


# --------------------------------------------------------------------- authors


def test_a_name_becomes_a_vcard_and_replaces_the_plain_field():
    """
    The shape follows what edu-sharing writes itself, read back from a live
    staging node: VERSION right after BEGIN, and N with its five positional
    components — 'BEGIN:VCARD\r\nVERSION:3.0\nFN:Dirk Unkauf\nN:Unkauf;Dirk;;;\n…'
    """
    normalized = {"cm:author": ["Philipp Lang"]}

    transform_author_to_vcard(normalized)

    assert "cm:author" not in normalized
    assert normalized["ccm:lifecyclecontributer_author"] == [
        "BEGIN:VCARD\nVERSION:3.0\nFN:Philipp Lang\nN:Lang;Philipp;;;\nEND:VCARD"
    ]


def test_the_surname_comes_first_in_the_structured_name():
    """
    edu-sharing splits N positionally into VCARD_SURNAME and VCARD_GIVENNAME —
    swapping them renames the author.
    """
    normalized = {"cm:author": ["Philipp Lang"]}

    transform_author_to_vcard(normalized)

    n_line = normalized["ccm:lifecyclecontributer_author"][0].splitlines()[3]
    family, given, *rest = n_line[len("N:") :].split(";")
    assert (family, given) == ("Lang", "Philipp")
    assert rest == ["", "", ""]


def test_a_single_word_name_is_not_split():
    """Organisations have no given name to separate."""
    normalized = {"cm:author": ["Klexikon"]}

    transform_author_to_vcard(normalized)

    assert normalized["ccm:lifecyclecontributer_author"] == [
        "BEGIN:VCARD\nVERSION:3.0\nFN:Klexikon\nN:Klexikon;;;;\nEND:VCARD"
    ]


def test_blank_authors_are_skipped():
    normalized = {"cm:author": ["  ", ""]}

    transform_author_to_vcard(normalized)

    assert normalized == {}


def test_a_line_break_in_a_name_cannot_inject_vcard_properties():
    """
    Author names come out of the LLM extraction of an arbitrary web page, and a
    VCARD is a line-based format — an unescaped newline lets that page write
    properties of its own into the node metadata.
    """
    normalized = {"cm:author": ["Eva\nEMAIL:fremd@example.org"]}

    transform_author_to_vcard(normalized)

    lines = normalized["ccm:lifecyclecontributer_author"][0].splitlines()

    # A VCARD has exactly these five lines; the name must not add a sixth.
    assert len(lines) == 5
    assert lines[0] == "BEGIN:VCARD"
    assert lines[-1] == "END:VCARD"
    assert not any(line.startswith("EMAIL:") for line in lines)


def test_a_semicolon_is_escaped_where_it_would_split_the_name():
    """
    In N the ';' is the component separator: unescaped, 'Meier; Hans' shifts the
    given name into the surname slot.
    """
    normalized = {"cm:author": ["Meier; Hans"]}

    transform_author_to_vcard(normalized)

    n_line = normalized["ccm:lifecyclecontributer_author"][0].splitlines()[3]
    assert n_line == "N:Hans;Meier\\;;;;"


def test_the_display_name_is_not_escaped():
    """
    FN is a single text value — an escape there protects nothing, and shows up
    as a literal backslash in the editorial desk if the reader does not undo it.
    Verified against live nodes: edu-sharing hands FN straight to
    ccm:lifecyclecontributer_authorFN.
    """
    normalized = {"cm:author": ["Meier, Hans"]}

    transform_author_to_vcard(normalized)

    fn_line = normalized["ccm:lifecyclecontributer_author"][0].splitlines()[2]
    assert fn_line == "FN:Meier, Hans"


def test_without_an_author_nothing_changes():
    normalized = {"cclom:title": ["Titel"]}

    transform_author_to_vcard(normalized)

    assert normalized == {"cclom:title": ["Titel"]}


# ----------------------------------------------------------------- coordinates


def test_coordinates_come_from_the_first_location_that_has_them():
    normalized = {}
    original = {
        "schema:location": [
            {"name": "ohne Geo"},
            {"geo": {"latitude": 52.52, "longitude": 13.405}},
        ]
    }

    extract_geo_coordinates(normalized, original)

    assert normalized == {"cm:latitude": ["52.52"], "cm:longitude": ["13.405"]}


def test_a_single_location_object_works_like_a_list_of_one():
    normalized = {}

    extract_geo_coordinates(
        normalized, {"schema:location": {"geo": {"latitude": 1, "longitude": 2}}}
    )

    assert normalized == {"cm:latitude": ["1"], "cm:longitude": ["2"]}


def test_the_top_level_geo_field_is_the_fallback():
    normalized = {}

    extract_geo_coordinates(normalized, {"schema:geo": {"latitude": 1, "longitude": 2}})

    assert normalized == {"cm:latitude": ["1"], "cm:longitude": ["2"]}


def test_half_a_coordinate_pair_is_not_written():
    normalized = {}

    extract_geo_coordinates(normalized, {"schema:geo": {"latitude": 52.52}})

    assert normalized == {}
