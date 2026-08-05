"""
/widget/info must describe the widget that is actually shipped.

The endpoint used to advertise attributes and events that did not exist in the
bundle, which sent integrators down dead ends. These tests read the shipped
bundle and fail when the endpoint drifts away from it again.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import main

BUNDLE = Path(__file__).resolve().parents[1] / "src/static/widget/dist/main.js"


@pytest.fixture(scope="module")
def bundle_source() -> str:
    if not BUNDLE.exists():
        pytest.skip(f"widget bundle not built: {BUNDLE}")
    return BUNDLE.read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def info() -> dict:
    with TestClient(main.app) as client:
        response = client.get("/widget/info")
    assert response.status_code == 200
    return response.json()


def test_every_advertised_event_exists_in_the_bundle(info, bundle_source):
    for event in info["events"]:
        assert event in bundle_source, (
            f"/widget/info advertises event '{event}' which the bundle does not emit"
        )


def test_every_advertised_layout_exists_in_the_bundle(info, bundle_source):
    for layout in info["layouts"]:
        assert f'"layout-{layout}"' in bundle_source, (
            f"/widget/info advertises layout '{layout}' which the bundle does not define"
        )


def test_every_advertised_attribute_exists_in_the_bundle(info, bundle_source):
    """Attributes are kebab-case; Angular Elements derives them from camelCase inputs."""
    for attribute in info["attributes"]:
        parts = attribute.split("-")
        camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
        assert f"{camel}:" in bundle_source, (
            f"/widget/info advertises attribute '{attribute}' "
            f"(input '{camel}') which the bundle does not accept"
        )


def test_response_keeps_its_documented_top_level_shape(info):
    for key in ("name", "dist_base_url", "scripts", "variants", "events", "examples"):
        assert key in info
