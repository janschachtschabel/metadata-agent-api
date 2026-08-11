"""
Comparing sent metadata against what the repository stored.

Backs the SOLL/IST report of `/upload/verify`. The comparison is deliberately
looser than equality: edu-sharing returns every value as an array, is
case-insensitive in practice, and converts dates to epoch milliseconds — a
strict comparison would report those as mismatches.

No HTTP, no state — the read lives in `repository_service`.
"""

import json
from typing import Any

from ..utils.schema_loader import get_repo_fields


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
) -> tuple[list[dict], dict]:
    """
    Compute field-level SOLL/IST diff.

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
    }

    # Check all expected fields
    seen_keys = set()
    for field_id, expected_val in clean_expected.items():
        seen_keys.add(field_id)

        # Skip empty expected values
        if expected_val is None or expected_val == "" or expected_val == []:
            continue

        # Fields that were never eligible for repo write
        if field_id.startswith("virtual:") or field_id.startswith("schema:"):
            # These are internal fields that get transformed (e.g. schema:location → cm:latitude)
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
                }
            )
            summary["missing_in_repo"] += 1
        elif values_match(expected_val, actual_val):
            diff.append(
                {
                    "field_id": field_id,
                    "status": "match",
                    "expected": expected_val,
                    "actual": actual_val,
                }
            )
            summary["match"] += 1
        else:
            diff.append(
                {
                    "field_id": field_id,
                    "status": "mismatch",
                    "expected": expected_val,
                    "actual": actual_val,
                }
            )
            summary["mismatch"] += 1

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
