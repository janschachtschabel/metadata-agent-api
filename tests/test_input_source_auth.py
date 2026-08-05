"""
Node reads must authenticate with the configured service account.

Without an Authorization header the repository answers 403 for every node that
is not readable anonymously — which includes every freshly uploaded inbox node.
"""

import base64
from types import SimpleNamespace

import httpx
import pytest

from src.services.input_source_service import InputSourceService
from src.services.repository_service import RepositoryService, build_auth_header

REPO_URL = "https://repo.example/edu-sharing/rest"
NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"


def _service(username: str = "", password: str = "") -> InputSourceService:
    """InputSourceService with stubbed settings (no .env, no network)."""
    service = InputSourceService()
    service.settings = SimpleNamespace(
        repository_url=REPO_URL,
        wlo_guest_username=username,
        wlo_guest_password=password,
    )
    return service


def _record_into(captured: list, payload: dict) -> httpx.AsyncClient:
    """Client that records every request and answers with `payload`."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_node_metadata_sends_basic_auth():
    captured: list[httpx.Request] = []
    service = _service("upload-user", "secret")
    service.http_client = _record_into(captured, {"node": {"properties": {}}})

    await service.fetch_node_metadata(NODE_ID)

    expected = "Basic " + base64.b64encode(b"upload-user:secret").decode()
    assert captured[0].headers.get("Authorization") == expected


@pytest.mark.asyncio
async def test_fetch_node_text_content_sends_basic_auth():
    captured: list[httpx.Request] = []
    service = _service("upload-user", "secret")
    service.http_client = _record_into(captured, {"text": "content"})

    await service.fetch_node_text_content(NODE_ID)

    expected = "Basic " + base64.b64encode(b"upload-user:secret").decode()
    assert captured[0].headers.get("Authorization") == expected


@pytest.mark.asyncio
async def test_no_auth_header_when_credentials_are_unset():
    """Public nodes must stay reachable on installations without credentials."""
    captured: list[httpx.Request] = []
    service = _service()  # no credentials configured
    service.http_client = _record_into(captured, {"node": {"properties": {}}})

    await service.fetch_node_metadata(NODE_ID)

    assert "Authorization" not in captured[0].headers


def test_build_auth_header_matches_repository_service():
    """The write path must keep producing exactly the header it produced before."""
    expected = "Basic " + base64.b64encode(b"upload-user:secret").decode()

    assert build_auth_header("upload-user", "secret") == expected
    assert RepositoryService("upload-user", "secret")._auth_header == expected


def test_build_auth_header_returns_none_without_credentials():
    assert build_auth_header("", "") is None
    assert build_auth_header("user", "") is None
    assert build_auth_header("", "secret") is None
