"""
ENV-PARAMETER.md is the operator-facing contract of this service.

A setting that exists in code but not in the document is invisible to whoever
deploys it — and one that is documented but no longer read is worse, because
setting it looks like it works. Neither is caught by anything else, so it is
checked here against the model itself rather than against a hand-kept list.
"""

import re
from pathlib import Path

from src.config import Settings

DOCUMENT = Path(__file__).resolve().parents[1] / "ENV-PARAMETER.md"

# Secrets keep their bare name; everything else takes the prefix.
PREFIX = "METADATA_AGENT_"


def _configured_variables() -> set[str]:
    names = set()
    for name, field in Settings.model_fields.items():
        names.add(field.alias or f"{PREFIX}{name.upper()}")
    return names


def _documented_variables() -> set[str]:
    text = DOCUMENT.read_text(encoding="utf-8")
    return set(
        re.findall(
            r"\b(?:METADATA_AGENT_[A-Z0-9_]+|B_API_KEY|OPENAI_API_KEY|WLO_GUEST_[A-Z]+)\b",
            text,
        )
    )


def test_every_setting_is_documented():
    missing = sorted(_configured_variables() - _documented_variables())

    assert not missing, f"fehlt in ENV-PARAMETER.md: {missing}"


def test_no_documented_variable_has_gone_away():
    """A documented setting the code stopped reading is a silent no-op."""
    stale = sorted(_documented_variables() - _configured_variables())

    assert not stale, f"in ENV-PARAMETER.md, aber nicht mehr in Settings: {stale}"


def test_the_env_template_only_names_variables_that_exist():
    template = (DOCUMENT.parent / ".env.template").read_text(encoding="utf-8")
    named = set(
        re.findall(
            r"^#?\s*(METADATA_AGENT_[A-Z0-9_]+|B_API_KEY|OPENAI_API_KEY|WLO_GUEST_[A-Z]+)=",
            template,
            re.MULTILINE,
        )
    )

    stale = sorted(named - _configured_variables())

    assert not stale, f"in .env.template, aber nicht in Settings: {stale}"
