"""
Reading a licence out of what a page says about itself.

The rules are asymmetric on purpose: a value that maps onto the vocabulary
replaces ccm:custom_license, anything else has to survive it. A licence this
code cannot read is not the same as no licence, and both directions of guessing
publish a claim about someone else's rights.
"""

import pytest

from src.services.repository_licenses import (
    VALID_LICENSE_KEYS,
    transform_license,
)


def test_a_cc_uri_becomes_key_and_version():
    normalized = {"ccm:custom_license": ["…/CC_BY_SA_40"]}

    transform_license(normalized, {"ccm:custom_license": "https://x/CC_BY_SA_40"})

    assert normalized["ccm:commonlicense_key"] == ["CC_BY_SA"]
    assert normalized["ccm:commonlicense_cc_version"] == ["4.0"]
    assert "ccm:custom_license" not in normalized


def test_the_other_licence_becomes_custom():
    normalized = {}

    transform_license(normalized, {"ccm:custom_license": "https://x/OTHER"})

    assert normalized["ccm:commonlicense_key"] == ["CUSTOM"]


def test_plain_licence_text_is_kept_and_marked_custom():
    """No slash means it is free text, not a vocabulary URI."""
    normalized = {"ccm:custom_license": ["Nur für den Schulgebrauch"]}

    transform_license(normalized, {"ccm:custom_license": "Nur für den Schulgebrauch"})

    assert normalized["ccm:custom_license"] == ["Nur für den Schulgebrauch"]
    assert normalized["ccm:commonlicense_key"] == ["CUSTOM"]


def test_a_link_that_is_no_vocabulary_key_stays_as_custom_text():
    """
    The schema defines ccm:custom_license as free text and its prompt asks for
    URLs ('https://example.com/nutzungsbedingungen'). A slash therefore cannot
    mean 'this is a vocabulary URI' — reading it that way used to delete the
    licence and leave the upload with no licence at all.
    """
    link = "https://example.com/nutzungsbedingungen"
    normalized = {"ccm:custom_license": [link]}

    transform_license(normalized, {"ccm:custom_license": link})

    assert normalized["ccm:custom_license"] == [link]
    assert normalized["ccm:commonlicense_key"] == ["CUSTOM"]


@pytest.mark.parametrize(
    "value",
    [
        "Nur für Bildungszwecke / nicht kommerziell",
        "https://example.com/rechte/lizenz.html",
        "https://creativecommons.org/licenses/by-xx/4.0/",
    ],
)
def test_a_licence_is_never_silently_discarded(value):
    """Whatever cannot be mapped must survive for the editors to see."""
    normalized = {"ccm:custom_license": [value]}

    transform_license(normalized, {"ccm:custom_license": value})

    assert normalized["ccm:custom_license"] == [value]
    assert normalized["ccm:commonlicense_key"] == ["CUSTOM"]


@pytest.mark.parametrize(
    "url, key, cc_version",
    [
        ("https://creativecommons.org/licenses/by/4.0/", "CC_BY", "4.0"),
        ("https://creativecommons.org/licenses/by-sa/4.0/", "CC_BY_SA", "4.0"),
        ("http://creativecommons.org/licenses/by-nd/2.0", "CC_BY_ND", "2.0"),
        ("https://creativecommons.org/licenses/by-nc/2.5/", "CC_BY_NC", "2.5"),
        # Ported licences carry a jurisdiction after the version
        (
            "https://creativecommons.org/licenses/by-nc-sa/3.0/de/",
            "CC_BY_NC_SA",
            "3.0",
        ),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC_0", "1.0"),
    ],
)
def test_a_creative_commons_link_becomes_a_proper_licence_key(url, key, cc_version):
    """
    The version comes out of the URL, not from a default — the schema prompt
    points at '/licenses/by/4.0/' as the place to read it, and 2.0/2.5/3.0
    licences are common on older material.
    """
    normalized = {"ccm:custom_license": [url]}

    transform_license(normalized, {"ccm:custom_license": url})

    assert normalized["ccm:commonlicense_key"] == [key]
    assert normalized["ccm:commonlicense_cc_version"] == [cc_version]
    assert "ccm:custom_license" not in normalized


def test_the_public_domain_mark_has_no_cc_version():
    """PDM is not a CC licence — ccm:commonlicense_cc_version does not apply."""
    url = "https://creativecommons.org/publicdomain/mark/1.0/"
    normalized = {"ccm:custom_license": [url]}

    transform_license(normalized, {"ccm:custom_license": url})

    assert normalized["ccm:commonlicense_key"] == ["PDM"]
    assert "ccm:commonlicense_cc_version" not in normalized


def test_text_around_a_licence_link_is_kept_alongside_the_key():
    """
    A sentence can carry more than the licence ('© Uni X, Teile unter CC BY').
    Dropping it because a link was recognised would lose the rest.
    """
    value = "© Universität München, Abbildungen CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/"
    normalized = {"ccm:custom_license": [value]}

    transform_license(normalized, {"ccm:custom_license": value})

    assert normalized["ccm:commonlicense_key"] == ["CC_BY_SA"]
    assert normalized["ccm:custom_license"] == [value]


def test_an_unknown_licence_key_is_dropped_with_its_version():
    normalized = {
        "ccm:commonlicense_key": ["ERFUNDEN"],
        "ccm:commonlicense_cc_version": ["4.0"],
    }

    transform_license(normalized, {})

    assert "ccm:commonlicense_key" not in normalized
    assert "ccm:commonlicense_cc_version" not in normalized


def test_a_cc_key_without_a_version_gets_the_default():
    normalized = {"ccm:commonlicense_key": ["CC_BY"]}

    transform_license(normalized, {})

    assert normalized["ccm:commonlicense_cc_version"] == ["4.0"]


def test_a_non_cc_key_gets_no_version():
    normalized = {"ccm:commonlicense_key": ["COPYRIGHT_FREE"]}

    transform_license(normalized, {})

    assert "ccm:commonlicense_cc_version" not in normalized
    assert "COPYRIGHT_FREE" in VALID_LICENSE_KEYS
