"""
Compare the quality vocabularies in core.json against the live WLO metadata set.

The values in core.json are a copy of the mds_oeh value spaces. If WLO changes a
value space, nothing breaks loudly: the API writes with obeyMds=false, so
edu-sharing accepts any string. The value simply stops resolving to a label and
the field shows up empty in the editorial desk. This script makes that drift
visible.

Usage:
    python scripts/check_quality_vocabularies.py
    python scripts/check_quality_vocabularies.py --env prod
    python scripts/check_quality_vocabularies.py --env staging prod

Exit code 1 if a value is missing from the live value space, ignoring the two
deviations documented in WLO-REPO-FELDER.md.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.schema_loader import get_schema_fields  # noqa: E402

MDS_PATH = "/edu-sharing/rest/mds/v1/metadatasets/-home-/mds_oeh"
REPOSITORIES = {
    "staging": "https://repository.staging.openeduhub.net",
    "prod": "https://redaktion.openeduhub.net",
}

# Deviations we accept on purpose — see WLO-REPO-FELDER.md for the reasoning.
# field id -> values that are knowingly not in the MDS value space
ACCEPTED_DEVIATIONS = {
    # The R scale requested by WLO editorial; the MDS currently carries the
    # knock-out value space for this field instead.
    "ccm:oeh_quality_correctness": {"0", "1", "2", "3", "4", "5"},
    # Not in the value space but present on curated nodes in production.
    "ccm:oeh_buffet_criteria": {"usable_for_buffet"},
}


def load_live_widgets(base_url: str) -> dict:
    with urllib.request.urlopen(base_url + MDS_PATH, timeout=120) as response:
        mds = json.loads(response.read().decode("utf-8"))
    return {w["id"]: w for w in mds.get("widgets", []) if w.get("id")}


def local_quality_fields() -> dict:
    return {
        field["id"]: field
        for field in get_schema_fields("default", "2.0.0", "core.json")
        if field.get("group") == "quality"
    }


def check(env: str, base_url: str) -> int:
    print(f"=== {env} ({base_url}) ===")
    live = load_live_widgets(base_url)
    problems = 0

    for field_id, field in local_quality_fields().items():
        mine = [
            concept.get("uri") or concept.get("value")
            for concept in field["system"]["vocabulary"]["concepts"]
        ]
        widget = live.get(field_id)
        if widget is None:
            print(f"  FEHLT  {field_id} - im MDS nicht vorhanden")
            problems += 1
            continue

        theirs = {value["id"] for value in (widget.get("values") or [])}
        accepted = ACCEPTED_DEVIATIONS.get(field_id, set())
        unexpected = [v for v in mine if v not in theirs and v not in accepted]
        known = [v for v in mine if v not in theirs and v in accepted]

        expects_multiple = widget.get("type") == "checkboxVertical"
        if expects_multiple != field["system"]["multiple"]:
            print(
                f"  TYP    {field_id} - MDS ist '{widget.get('type')}', "
                f"Schema hat multiple={field['system']['multiple']}"
            )
            problems += 1

        if unexpected:
            print(f"  ABW.   {field_id} - nicht im MDS-Valuespace:")
            for value in unexpected:
                print(f"           {value}")
            problems += 1
        elif known:
            print(f"  OK*    {field_id} - {len(known)} dokumentierte Abweichung(en)")
        else:
            print(f"  OK     {field_id} - {len(mine)} Werte")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        nargs="+",
        choices=sorted(REPOSITORIES),
        default=["staging", "prod"],
    )
    args = parser.parse_args()

    problems = 0
    for env in args.env:
        problems += check(env, REPOSITORIES[env])
        print()

    if problems:
        print(f"{problems} Abweichung(en) - core.json und MDS laufen auseinander.")
        return 1
    print("Alle Vokabulare stimmen mit dem Live-Metadatensatz ueberein.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
