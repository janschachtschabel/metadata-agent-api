"""
Comparing sent metadata against what the repository stored.

Backs the SOLL/IST report of `/upload/verify`. The comparison is deliberately
looser than equality: edu-sharing returns every value as an array, is
case-insensitive in practice, and converts dates to epoch milliseconds — a
strict comparison would report those as mismatches.

No HTTP, no state — the read lives in `repository_service`.
"""

import json
from functools import lru_cache
from typing import Any

from ..utils.schema_loader import get_repo_fields, get_schema_fields

# ccm:commonlicense_key resolves like any vocabulary field, but edu-sharing never
# gives it a DISPLAYNAME — not even when the value is right. What it does produce
# is virtual:licenseurl, and only for a value it recognises as a licence.
_LICENSE_KEY = "ccm:commonlicense_key"
_LICENSE_SIGNAL = "virtual:licenseurl"

# Fields the write path renames on the way out (see repository_values). The
# verdict has to look at the property that is actually on the node — under its
# schema name it would find nothing and report nothing, which is the silence
# this check exists to break.
WRITTEN_AS = {"oeh:new_lrt": "ccm:oeh_lrt"}

# Fields the MDS has no value space for. They are stored correctly and read back
# correctly; there is simply no label to resolve to, so they turn up unresolved
# on every node. Flagged as known so a report of real findings does not drown in
# them — measured on live nodes, see WLO-REPO-FELDER.md.
#
#   ccm:oeh_quality_correctness      the 0-5 scale is not in the MDS value space
#   ccm:commonlicense_ai_*           no widget in mds_oeh (208 checked)
NO_VALUE_SPACE = {
    "ccm:oeh_quality_correctness",
    "ccm:commonlicense_ai_allow_usage",
    "ccm:commonlicense_ai_generated",
    "ccm:commonlicense_ai_manually_modified",
}


@lru_cache(maxsize=64)
def vocabulary_fields(context: str, version: str, schema_file: str | None) -> frozenset:
    """
    Repository properties whose values are expected to resolve to a label.

    Named as they appear on the node, not as the schema calls them.
    """
    fields: set[str] = set()
    for name in {"core.json", schema_file} - {None}:
        try:
            for field in get_schema_fields(context, version, name):
                vocabulary = field.get("system", {}).get("vocabulary") or {}
                if vocabulary.get("concepts"):
                    field_id = field["id"]
                    fields.add(WRITTEN_AS.get(field_id, field_id))
        except Exception:
            continue
    return frozenset(fields)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    items = value if isinstance(value, list) else [value]
    return not any(str(item).strip() for item in items)


def check_resolution(
    field_id: str,
    properties: dict,
    context: str,
    version: str,
    schema_file: str | None = None,
) -> str | None:
    """
    Whether the repository reads a stored value as a value, or just as text.

    Returns 'resolved', 'unresolved', or None when there is nothing to judge —
    free text has no label to resolve to, and a field that is not on the node is
    the diff's business, not this one's.

    The whole point is the case where the value equals what was sent and is still
    dead: an unknown vocabulary entry is answered with an empty DISPLAYNAME, not
    with an error.
    """
    field_id = WRITTEN_AS.get(field_id, field_id)

    if _is_empty(properties.get(field_id)):
        return None

    if field_id == _LICENSE_KEY:
        return (
            "unresolved" if _is_empty(properties.get(_LICENSE_SIGNAL)) else "resolved"
        )

    if field_id not in vocabulary_fields(context, version, schema_file):
        return None

    return (
        "unresolved"
        if _is_empty(properties.get(f"{field_id}_DISPLAYNAME"))
        else "resolved"
    )


def unresolved_values(
    properties: dict,
    context: str,
    version: str,
    schema_file: str | None = None,
) -> list[dict]:
    """
    Every value on a node that the repository does not resolve.

    Needs no expected metadata — 'which of this node's values are dead' is a
    question worth asking about a node nobody here uploaded.
    """
    findings = []
    candidates = set(vocabulary_fields(context, version, schema_file)) | {_LICENSE_KEY}

    for field_id in sorted(candidates):
        verdict = check_resolution(field_id, properties, context, version, schema_file)
        if verdict == "unresolved":
            known = field_id in NO_VALUE_SPACE
            findings.append(
                {
                    "field_id": field_id,
                    "value": properties.get(field_id),
                    "known": known,
                    "reason": (
                        "kein Wertebereich im MDS — der Wert ist korrekt "
                        "gespeichert, es gibt nur kein Label dazu"
                        if known
                        else "kein virtual:licenseurl — das Repository liest den "
                        "Wert nicht als Lizenz"
                        if field_id == _LICENSE_KEY
                        else "leeres _DISPLAYNAME — der Wert steht in keinem Vokabular"
                    ),
                }
            )
    # Real findings first: the known ones are on every node and would otherwise
    # be what a reader sees.
    findings.sort(key=lambda f: (f["known"], f["field_id"]))
    return findings


def properties_to_flat(properties: dict) -> dict:
    """Convert repository array-style properties to flat metadata."""
    flat = {}
    for key, value in properties.items():
        # Skip internal/system properties
        if key.startswith("sys:") or key.startswith("virtual:"):
            continue
        # Skip DISPLAYNAME variants
        if key.endswith("_DISPLAYNAME"):
            continue
        # Skip VCARD sub-fields (keep only the main VCARD field)
        if "VCARD_" in key:
            continue
        # Skip cm: system fields (keep only metadata-relevant ones)
        cm_keep = {"cm:author", "cm:latitude", "cm:longitude"}
        if key.startswith("cm:") and key not in cm_keep:
            continue

        if isinstance(value, list):
            if len(value) == 1:
                flat[key] = value[0]
            elif len(value) > 1:
                flat[key] = value
            # Skip empty lists
        elif value is not None:
            flat[key] = value

    return flat


def compute_diff(
    expected: dict,
    actual: dict,
    context: str,
    version: str,
    properties: dict | None = None,
) -> tuple[list[dict], dict]:
    """
    Compute field-level SOLL/IST diff.

    `properties` are the node's raw properties, before `properties_to_flat`
    stripped the `_DISPLAYNAME` and `virtual:` entries. Passing them adds a
    `resolution` verdict per field — a value can equal what was sent and still
    be dead, which every other column here reports as a clean match. Optional so
    existing callers keep working; without it the verdict is None rather than a
    guess.

    Returns:
        Tuple of (diff_list, summary_counts)
    """
    # Clean expected metadata (remove processing/header keys)
    excluded = {
        "contextName",
        "schemaVersion",
        "metadataset",
        "metadataset_uri",
        "language",
        "exportedAt",
        "processing",
        "_origins",
        "_source_text",
        "repository",
        "check_duplicates",
        "start_workflow",
        "preview_url",
        "preview:url",
        "preview_image_url",
    }
    clean_expected = {k: v for k, v in expected.items() if k not in excluded}

    # Load repo fields to know which fields were eligible for writing
    schema_file = expected.get("metadataset")
    repo_field_ids = get_repo_fields(context, version, schema_file)

    diff = []
    summary = {
        "match": 0,
        "mismatch": 0,
        "missing_in_repo": 0,
        "extra_in_repo": 0,
        "not_written": 0,
        # Counted separately: an unresolved value is also a match. Folding it
        # into 'mismatch' would hide that the value arrived exactly as sent.
        "unresolved": 0,
    }

    def resolution_of(field_id: str) -> str | None:
        if properties is None:
            return None
        return check_resolution(field_id, properties, context, version, schema_file)

    # Check all expected fields
    seen_keys = set()
    for field_id, expected_val in clean_expected.items():
        seen_keys.add(field_id)

        # Skip empty expected values
        if expected_val is None or expected_val == "" or expected_val == []:
            continue

        # Fields that were never eligible for repo write. Only 'virtual:' is
        # unconditional — it is computed by edu-sharing, never stored. A
        # 'schema:' field falls through to the repo_field check below, which is
        # what decides it on the write path too (see normalize_for_repo).
        if field_id.startswith("virtual:"):
            diff.append(
                {
                    "field_id": field_id,
                    "status": "not_written",
                    "expected": expected_val,
                    "actual": None,
                }
            )
            summary["not_written"] += 1
            continue

        # An empty set means the schemas could not be read — get_repo_fields()
        # swallows that. The write path then refuses to write anything at all,
        # so every field is absent by decision, not because the repository lost
        # it. Reporting 'missing_in_repo' here would blame the wrong side.
        if not repo_field_ids or field_id not in repo_field_ids:
            diff.append(
                {
                    "field_id": field_id,
                    "status": "not_written",
                    "expected": expected_val,
                    "actual": None,
                }
            )
            summary["not_written"] += 1
            continue

        actual_val = actual.get(field_id)

        # The write path renames some fields (oeh:new_lrt → ccm:oeh_lrt). Looking
        # only under the schema name would report a field as missing that is
        # sitting right there under its repository name — and then report the
        # repository name again as 'extra_in_repo', so the same value shows up
        # twice, once as a loss and once as a surprise.
        if field_id in WRITTEN_AS:
            written_as = WRITTEN_AS[field_id]
            seen_keys.add(written_as)
            if actual_val is None:
                actual_val = actual.get(written_as)

        if actual_val is None:
            # Special case: cm:author is transformed to ccm:lifecyclecontributer_author
            if field_id == "cm:author":
                author_fn = actual.get("ccm:lifecyclecontributer_authorFN")
                if author_fn:
                    diff.append(
                        {
                            "field_id": field_id,
                            "status": "match",
                            "expected": expected_val,
                            "actual": f"(transformed → ccm:lifecyclecontributer_authorFN: {author_fn})",
                        }
                    )
                    summary["match"] += 1
                    continue

            diff.append(
                {
                    "field_id": field_id,
                    "status": "missing_in_repo",
                    "expected": expected_val,
                    "actual": None,
                    "resolution": None,
                }
            )
            summary["missing_in_repo"] += 1
        elif values_match(expected_val, actual_val):
            resolution = resolution_of(field_id)
            diff.append(
                {
                    "field_id": field_id,
                    "status": "match",
                    "expected": expected_val,
                    "actual": actual_val,
                    "resolution": resolution,
                }
            )
            summary["match"] += 1
            if resolution == "unresolved":
                summary["unresolved"] += 1
        else:
            resolution = resolution_of(field_id)
            diff.append(
                {
                    "field_id": field_id,
                    "status": "mismatch",
                    "expected": expected_val,
                    "actual": actual_val,
                    "resolution": resolution,
                }
            )
            summary["mismatch"] += 1
            if resolution == "unresolved":
                summary["unresolved"] += 1

    # Check for extra fields in repo that weren't in expected
    for field_id, actual_val in actual.items():
        if field_id in seen_keys:
            continue
        if actual_val is None or actual_val == "" or actual_val == []:
            continue
        diff.append(
            {
                "field_id": field_id,
                "status": "extra_in_repo",
                "expected": None,
                "actual": actual_val,
            }
        )
        summary["extra_in_repo"] += 1

    # Sort: problems first, then matches
    status_order = {
        "missing_in_repo": 0,
        "mismatch": 1,
        "not_written": 2,
        "extra_in_repo": 3,
        "match": 4,
    }
    diff.sort(key=lambda d: status_order.get(d["status"], 5))

    return diff, summary


def values_match(expected: Any, actual: Any) -> bool:
    """Compare expected and actual values, handling type differences."""
    # Normalize both to comparable form
    exp_norm = normalize_compare(expected)
    act_norm = normalize_compare(actual)
    if exp_norm == act_norm:
        return True

    # Special case: ISO date string vs epoch millis (repo auto-converts)
    return dates_match(exp_norm, act_norm)


def dates_match(a: Any, b: Any) -> bool:
    """Check if two values represent the same datetime (ISO vs epoch millis)."""
    try:
        a_ts = to_epoch_ms(str(a))
        b_ts = to_epoch_ms(str(b))
        if a_ts is not None and b_ts is not None:
            # Allow 60s tolerance (repo may round)
            return abs(a_ts - b_ts) < 60_000
        return False
    except Exception:
        return False


def to_epoch_ms(value: str) -> int | None:
    """Try to interpret a string as epoch milliseconds."""
    from datetime import datetime, timezone

    # Already epoch millis?
    try:
        num = int(value)
        if num > 1_000_000_000_000:  # clearly epoch millis (> year 2001)
            return num
        if num > 1_000_000_000:  # epoch seconds
            return num * 1000
    except (ValueError, TypeError):
        pass

    # ISO date string?
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            continue

    return None


def normalize_compare(value: Any) -> Any:
    """Normalize a value for comparison."""
    if isinstance(value, list):
        if len(value) == 1:
            return normalize_compare(value[0])
        return sorted(str(v).strip().lower() for v in value)
    if isinstance(value, dict):
        # Extract URI or label for comparison
        if "uri" in value:
            return str(value["uri"]).strip().lower()
        if "label" in value:
            return str(value["label"]).strip().lower()
        return json.dumps(value, sort_keys=True, ensure_ascii=False).lower()
    return str(value).strip().lower()
