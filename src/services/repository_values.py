"""
Shaping metadata for the edu-sharing repository API.

Everything here is a pure step between what the extraction produced and what the
repository receives: which fields may be written at all, how a value is reduced
to something the API accepts, and the transformations edu-sharing expects for
authors and coordinates. Licences have their own reasons to change and live in
`repository_licenses`.

No HTTP, no state — the calls live in `repository_service`.
"""

import json
from typing import Any


def normalize_for_repo(metadata: dict, repo_field_ids: set[str] | None = None) -> dict:
    """
    Filter and normalize metadata for repository API.

    Only includes fields that:
    - Have repo_field=true in schema (if repo_field_ids provided)
    - Don't start with 'virtual:' (computed by edu-sharing, never stored)
    - Have non-empty values
    """
    normalized = {}

    # If no repo fields could be loaded from schemas, refuse to write blindly
    if not repo_field_ids:
        print("⚠️ No repo_field_ids loaded from schemas — skipping metadata write")
        return normalized

    for key, value in metadata.items():
        # 'virtual:' names something edu-sharing computes on read, so no schema
        # flag could make writing one correct. 'schema:' is deliberately not
        # filtered here: it is a real namespace in the repository — the editorial
        # upload writes schema:datePublished directly — and whether such a field
        # is written is the schema's call via repo_field below. The transformation
        # inputs (schema:location, schema:geo) carry repo_field=false and are kept
        # out by that gate.
        if key.startswith("virtual:"):
            continue

        # Only include fields with repo_field=true in schema
        if key not in repo_field_ids:
            continue

        # Skip empty values
        if value is None or value == "" or value == []:
            continue

        # Normalize to arrays and flatten complex objects
        if isinstance(value, list):
            flattened = []
            for item in value:
                if item is None or item == "":
                    continue
                flattened_item = flatten_value(item)
                if flattened_item is not None:
                    flattened.append(flattened_item)
            if flattened:
                normalized[key] = flattened
        elif isinstance(value, dict):
            flattened = flatten_value(value)
            if flattened is not None:
                normalized[key] = [flattened]
        else:
            normalized[key] = [value]

    return normalized


def flatten_value(item: Any) -> Any:
    """Flatten a complex object to a simple value for repository API."""
    if item is None:
        return None

    # Already a simple type
    if isinstance(item, (str, int, float, bool)):
        return item

    # Dictionary - extract the most relevant value
    if isinstance(item, dict):
        # Priority order for value extraction
        if "uri" in item:
            return item["uri"]
        if "name" in item:
            return item["name"]
        if "label" in item:
            return item["label"]
        if "@value" in item:
            return item["@value"]
        if "value" in item:
            return item["value"]
        # For complex objects like address, serialize to JSON
        return json.dumps(item, ensure_ascii=False)

    return str(item)


def escape_vcard_component(value: str) -> str:
    """
    Escape one component of the structured N field (RFC 6350 §3.4).

    Only N needs this: its parts are separated by ';', so a raw semicolon in a
    name shifts the given name into the surname slot. FN is a single text value
    and is deliberately left alone — an escape protects nothing there and would
    show up as a literal backslash wherever the reader does not undo it.
    """
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def transform_author_to_vcard(normalized: dict):
    """
    Transform cm:author plain names to VCARD format for ccm:lifecyclecontributer_author.

    The WLO repo stores authors as VCARD strings in ccm:lifecyclecontributer_author,
    not as plain strings in cm:author. edu-sharing parses them back into
    ccm:lifecyclecontributer_authorFN and the VCARD_* subfields, splitting N
    positionally — so the field order and the five N components are what makes
    surname and given name land where the editorial desk expects them.

    The shape mirrors what edu-sharing writes itself, read back from a live node:
    'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Dirk Unkauf\nN:Unkauf;Dirk;;;\n…END:VCARD'

    Example: "Philipp Lang" → "BEGIN:VCARD\nVERSION:3.0\nFN:Philipp Lang\nN:Lang;Philipp;;;\nEND:VCARD"
    """
    authors = normalized.pop("cm:author", None)
    if not authors:
        return

    vcards = []
    for author in authors:
        # Collapsing whitespace is what removes the line breaks a VCARD would
        # otherwise read as the start of another property.
        author = " ".join(str(author).split())
        if not author:
            continue

        parts = author.rsplit(" ", 1)
        if len(parts) == 2:
            given, family = (escape_vcard_component(part) for part in parts)
        else:
            # Single name or organization — nothing to separate
            given, family = "", escape_vcard_component(author)

        # N is positional: family;given;additional;prefixes;suffixes
        vcards.append(
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{author}\nN:{family};{given};;;\nEND:VCARD"
        )

    if vcards:
        normalized["ccm:lifecyclecontributer_author"] = vcards
        print(
            f"👤 Author VCARD: {len(vcards)} entries → ccm:lifecyclecontributer_author"
        )


def transform_lrt(normalized: dict, original: dict | None = None):
    """
    Accept the old name for the learning resource type and file it under the new.

    Since schema 2.0.0 the field is called `ccm:oeh_lrt` — the name the
    repository itself uses — and needs no translation. The released schemas
    1.8.0 and 1.8.1 still call it `oeh:new_lrt`, and so does every `/generate`
    answer stored before the rename.

    `original` is read because the repo_field filter runs first and drops
    `oeh:new_lrt`: it is not a field of the current schema. Without this the
    value would disappear without a word, which is the one thing worse than an
    error.

    An existing `ccm:oeh_lrt` wins — whoever set the repository property said
    what they meant.
    """
    legacy = normalized.pop("oeh:new_lrt", None)
    if legacy is None and original is not None:
        legacy = original.get("oeh:new_lrt")
        if legacy is not None and not isinstance(legacy, list):
            legacy = [legacy]

    if not legacy or normalized.get("ccm:oeh_lrt"):
        return

    normalized["ccm:oeh_lrt"] = legacy
    print(f"🏷️ LRT: {len(legacy)} entries from oeh:new_lrt → ccm:oeh_lrt")


def extract_geo_coordinates(normalized: dict, original: dict):
    """
    Extract geo coordinates and map to cm:latitude / cm:longitude.

    Sources (in priority order):
    1. schema:location[].geo.latitude/longitude  (event, course, education_*, organization)
    2. schema:geo.latitude/longitude              (organization top-level fallback)
    """
    # Source 1: schema:location[].geo
    locations = original.get("schema:location")
    if locations:
        if not isinstance(locations, list):
            locations = [locations]

        for loc in locations:
            if not isinstance(loc, dict):
                continue
            geo = loc.get("geo")
            if not isinstance(geo, dict):
                continue

            lat = geo.get("latitude")
            lon = geo.get("longitude")

            if lat is not None and lon is not None:
                normalized["cm:latitude"] = [str(lat)]
                normalized["cm:longitude"] = [str(lon)]
                print(f"📍 Geo (location): {lat}, {lon} → cm:latitude, cm:longitude")
                return

    # Source 2: schema:geo (organization.json top-level)
    geo = original.get("schema:geo")
    if isinstance(geo, dict):
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        if lat is not None and lon is not None:
            normalized["cm:latitude"] = [str(lat)]
            normalized["cm:longitude"] = [str(lon)]
            print(f"📍 Geo (top-level): {lat}, {lon} → cm:latitude, cm:longitude")
            return
