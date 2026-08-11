"""
Turning what a page says about its licence into what edu-sharing stores.

Three shapes arrive here: a creativecommons.org deed link, a URI from the
openeduhub licence vocabulary, and free text. Only the first two map onto
`ccm:commonlicense_key`; everything else has to survive as `ccm:custom_license`,
because a licence this code cannot read is not the same as no licence. Guessing
in either direction publishes a claim about someone else's rights.

No HTTP, no state — the calls live in `repository_service`.
"""

import logging
import re

logger = logging.getLogger(__name__)


# Valid edu-sharing license keys (used for validation)
VALID_LICENSE_KEYS = {
    "NONE",
    "CC_0",
    "CC0",
    "CC_BY",
    "CC BY",
    "CC_BY_SA",
    "CC BY-SA",
    "CC_BY_ND",
    "CC BY-ND",
    "CC_BY_NC",
    "CC BY-NC",
    "CC_BY_NC_SA",
    "CC BY-NC-SA",
    "CC_BY_NC_ND",
    "CC BY-NC-ND",
    "PDM",
    "CUSTOM",
    "SCHULFUNK",
    "UNTERRICHTS_UND_LEHRMEDIEN",
    "COPYRIGHT_FREE",
    "COPYRIGHT_LICENSE",
}


# creativecommons.org licence deeds: /licenses/<code>/<version>[/<jurisdiction>].
# Ported licences (2.0–3.0) append a country, which must not end up in the
# version. Matched anywhere in the value, because the link often sits inside a
# sentence.
_CC_LICENSE_URL = re.compile(
    r"creativecommons\.org/licenses/([a-z-]+)/(\d+(?:\.\d+)?)", re.IGNORECASE
)
_CC_PUBLIC_DOMAIN_URL = re.compile(
    r"creativecommons\.org/publicdomain/(zero|mark)/(\d+(?:\.\d+)?)", re.IGNORECASE
)

# The two public-domain deeds do not follow the CC_<code> naming.
_CC_PUBLIC_DOMAIN_KEYS = {"zero": "CC_0", "mark": "PDM"}


def map_creative_commons_url(value: str) -> dict | None:
    """
    Map a creativecommons.org deed URL to licence key and version.

    Returns None when nothing matches, or when the code is not one of the seven
    licences edu-sharing knows — an unrecognised deed must stay readable text
    rather than become a wrong key.
    """
    match = _CC_LICENSE_URL.search(value)
    if match:
        code, version = match.group(1), match.group(2)
        key = "CC_" + code.upper().replace("-", "_")
    else:
        match = _CC_PUBLIC_DOMAIN_URL.search(value)
        if not match:
            return None
        key = _CC_PUBLIC_DOMAIN_KEYS[match.group(1).lower()]
        version = match.group(2)

    if key not in VALID_LICENSE_KEYS:
        return None

    mapped = {"ccm:commonlicense_key": [key]}
    # ccm:commonlicense_cc_version is a CC field; the public domain mark is not
    # a CC licence and carries no version there.
    if key.startswith("CC"):
        mapped["ccm:commonlicense_cc_version"] = [version]
    return mapped


def map_license_vocabulary_uri(value: str) -> dict | None:
    """
    Map a licence vocabulary URI to key (+ CC version), or None if it is not one.

    Returning None is what keeps an unmappable value alive: `ccm:custom_license`
    is a free-text field whose prompt explicitly asks for links to own licence
    terms, so 'contains a slash' does not make a value a vocabulary URI.
    """
    license_key = value.split("/")[-1]

    if license_key.endswith("_40") and license_key[:-3] in VALID_LICENSE_KEYS:
        return {
            "ccm:commonlicense_key": [license_key[:-3]],
            "ccm:commonlicense_cc_version": ["4.0"],
        }
    if license_key == "OTHER":
        return {"ccm:commonlicense_key": ["CUSTOM"]}
    if license_key in VALID_LICENSE_KEYS:
        return {"ccm:commonlicense_key": [license_key]}
    return None


def transform_license(normalized: dict, original: dict):
    """Transform license URLs to key + version format.

    A ccm:custom_license that maps onto the licence vocabulary becomes
    ccm:commonlicense_key (+ version) and is removed, because it would then be
    stored twice. Everything else — free text and links we cannot map — is kept
    and marked CUSTOM so the editors see what the source actually said.
    Validates ccm:commonlicense_key against known edu-sharing keys.
    """
    license_val = original.get("ccm:custom_license")

    if license_val:
        if isinstance(license_val, list):
            license_val = license_val[0] if license_val else None
        if isinstance(license_val, dict):
            license_val = license_val.get("uri") or license_val.get("label")

        if license_val and isinstance(license_val, str):
            mapped = None
            if "/" in license_val:
                mapped = map_creative_commons_url(
                    license_val
                ) or map_license_vocabulary_uri(license_val)

            if mapped:
                normalized.update(mapped)
                # Drop the source value only when it was nothing but the link.
                # A sentence around it ('© Uni X, Abbildungen CC BY') carries
                # more than the key can express.
                value_is_only_the_link = len(license_val.split()) == 1
                if value_is_only_the_link:
                    normalized.pop("ccm:custom_license", None)
            elif "ccm:commonlicense_key" not in normalized:
                normalized["ccm:commonlicense_key"] = ["CUSTOM"]

    # Validate ccm:commonlicense_key against known keys
    if "ccm:commonlicense_key" in normalized:
        key_list = normalized["ccm:commonlicense_key"]
        if isinstance(key_list, list) and key_list:
            key = str(key_list[0]).strip()
            if key not in VALID_LICENSE_KEYS:
                logger.warning(f"Invalid license key removed: {key[:80]}")
                del normalized["ccm:commonlicense_key"]
                normalized.pop("ccm:commonlicense_cc_version", None)

    # Default CC version only for CC-type licenses
    if (
        "ccm:commonlicense_key" in normalized
        and "ccm:commonlicense_cc_version" not in normalized
    ):
        key = (
            normalized["ccm:commonlicense_key"][0]
            if normalized["ccm:commonlicense_key"]
            else ""
        )
        if str(key).startswith("CC"):
            normalized["ccm:commonlicense_cc_version"] = ["4.0"]
