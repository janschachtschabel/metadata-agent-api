"""
Where the upload writes to is decided by exactly one setting.

METADATA_AGENT_REPOSITORY_URL is configured as the '/rest' API URL because the
read paths use it that way, while the upload endpoints append '/rest/...'
themselves — so the config has to strip the suffix again. Getting that wrong
points a production deployment at staging without any error, which is why it
took several attempts to settle (see the 'Fix für Repo URLs' / 'Fix für Env URL'
commits). These tests pin the conversion.
"""

from types import SimpleNamespace

import pytest

from src import config as config_module
from src.config import Settings
from src.services.repository_service import _get_repository_config

INBOX_ID = "21144164-30c0-4c01-ae16-264452197063"


@pytest.fixture
def configured(monkeypatch):
    """Point the repository config at a given URL, bypassing .env and cache."""

    def _configure(repository_url: str):
        monkeypatch.setattr(
            config_module,
            "get_settings",
            lambda: SimpleNamespace(
                repository_url=repository_url, wlo_inbox_id=INBOX_ID
            ),
        )
        return _get_repository_config()

    return _configure


@pytest.mark.parametrize(
    "repository_url",
    [
        "https://repo.example/edu-sharing/rest",
        "https://repo.example/edu-sharing/rest/",
        "https://repo.example/edu-sharing",
        "https://repo.example/edu-sharing/",
    ],
)
def test_the_upload_base_url_drops_the_rest_suffix(configured, repository_url):
    """The upload endpoints append '/rest/...' — a second one would 404."""
    assert configured(repository_url)["base_url"] == "https://repo.example/edu-sharing"


def test_the_configured_url_is_what_the_upload_uses(configured):
    """No second source of truth: switching the setting switches the target."""
    prod = "https://redaktion.openeduhub.net/edu-sharing/rest"

    assert (
        configured(prod)["base_url"] == "https://redaktion.openeduhub.net/edu-sharing"
    )
    assert (
        configured("https://repository.staging.openeduhub.net/edu-sharing/rest")[
            "base_url"
        ]
        == "https://repository.staging.openeduhub.net/edu-sharing"
    )


def test_the_inbox_id_comes_from_the_settings(configured):
    assert configured("https://repo.example/edu-sharing/rest")["inbox_id"] == INBOX_ID


def test_no_settings_field_promises_a_repository_override_it_cannot_deliver():
    """
    A 'WLO_REPOSITORY_BASE_URL' field sat here for a long time, documented in
    DEPLOYMENT.md and INSTALL.md as overriding the repository — and was read by
    nobody. Setting it in production silently kept pointing at staging. If an
    override is wanted again, it has to be read by _get_repository_config().
    """
    repository_settings = {
        name
        for name in Settings.model_fields
        if "repositor" in name and name != "repository_url"
    }

    assert not repository_settings, (
        f"{repository_settings} look like repository settings but "
        "_get_repository_config() only reads repository_url"
    )
