"""
A malformed body on /upload/verify must not silently degrade to "just read".

The endpoint's purpose is the SOLL/IST comparison. Swallowing a body error and
answering 200 without a diff tells the caller "everything checked out" when
nothing was ever compared.
"""

import pytest
from fastapi.testclient import TestClient

from src import main

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"


class _StubRepositoryService:
    """Stands in for the repository; records how verify_node was called."""

    def __init__(self):
        self.calls = []

    async def verify_node(
        self, node_id, repository, expected_metadata, context, version
    ):
        self.calls.append({"node_id": node_id, "expected_metadata": expected_metadata})
        return {
            "success": True,
            "node_id": node_id,
            "actual_metadata": {"cclom:title": "Titel"},
            "diff": [] if expected_metadata else None,
            "summary": {"match": 0} if expected_metadata else None,
        }


@pytest.fixture
def client(monkeypatch):
    stub = _StubRepositoryService()
    monkeypatch.setattr(main, "get_repository_service", lambda: stub)
    with TestClient(main.app) as test_client:
        test_client.stub = stub
        yield test_client


def test_body_with_broken_json_is_rejected(client):
    response = client.post(
        f"/upload/verify/{NODE_ID}",
        content='{"expected_metadata": {"cclom:title": "Titel"',  # truncated
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert client.stub.calls == [], "no comparison must be reported as done"


def test_body_violating_the_schema_is_rejected(client):
    response = client.post(
        f"/upload/verify/{NODE_ID}",
        json={"expected_metadata": "kein Objekt"},  # must be a dict
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert client.stub.calls == []


def test_empty_body_still_reads_the_node(client):
    """The documented read-only mode must keep working."""
    response = client.post(f"/upload/verify/{NODE_ID}")

    assert response.status_code == 200
    assert client.stub.calls[0]["expected_metadata"] is None


def test_valid_body_is_compared(client):
    expected = {"cclom:title": "Titel"}
    response = client.post(
        f"/upload/verify/{NODE_ID}", json={"expected_metadata": expected}
    )

    assert response.status_code == 200
    assert client.stub.calls[0]["expected_metadata"] == expected
