"""
What actually leaves the API on /upload.

The quality fields are invisible in the web component but must still travel the
whole way: /generate puts them in the JSON, the widget carries them through
untouched, and the upload writes them to the node because they carry
repo_field=true. Every step in between is a place where they could quietly get
dropped — the filter in _normalize_for_repo, the repo-field lookup that depends
on the content type, the 'virtual:'/'schema:' prefix skip.

This test drives the real upload against a recording HTTP client, so it fails if
any of those start swallowing the values.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src import main
from src.services import repository_service as repo_module
from src.services.repository_curation import DEFAULT_WORKFLOW_STATUS
from src.services.repository_service import RepositoryService

NODE_ID = "5ab4b434-4832-45ca-b4b4-34483265ca5d"
COLLECTION_ID = "3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"

VOCAB = "http://w3id.org/openeduhub/vocabs"

# A /generate response as the widget hands it on: visible fields plus the hidden
# quality assessment, flat, with the schema markers on top.
GENERATED_METADATA = {
    "contextName": "default",
    "schemaVersion": "2.0.0",
    "metadataset": "learning_material.json",
    "language": "de",
    "cclom:title": "Bruchrechnung Klasse 6",
    "cclom:general_description": "Arbeitsblatt zur Bruchrechnung mit Lösungen für die Klassenstufe 6.",
    "ccm:wwwurl": "https://example.org/bruchrechnung",
    "ccm:oeh_quality_relevancy_for_education": "1",
    "ccm:oeh_quality_criminal_law": f"{VOCAB}/quality/no_auto_findings",
    "ccm:oeh_quality_protection_of_minors": f"{VOCAB}/quality/no_auto_findings",
    "ccm:oeh_quality_copyright_law": f"{VOCAB}/quality/no_auto_findings",
    "ccm:oeh_quality_personal_law": f"{VOCAB}/quality/no_auto_findings",
    "ccm:oeh_quality_correctness": "4",
    "ccm:oeh_quality_currentness": "3",
    "ccm:oeh_quality_data_privacy": f"{VOCAB}/quality_data_privacy/5",
    "ccm:oeh_quality_neutralness": f"{VOCAB}/quality_neutrality/4",
    "ccm:oeh_quality_didactics": f"{VOCAB}/quality_didactics/4",
    "ccm:oeh_quality_medial": f"{VOCAB}/quality_media/3",
    "ccm:oeh_quality_transparentness": f"{VOCAB}/quality_transparency/5",
    "ccm:oeh_buffet_criteria": ["content_valid", "speech_valid", "usable_for_buffet"],
    # internal — must never reach the repository
    "_origins": {"cclom:title": "ai"},
    "_source_text": "Rohtext der Seite",
}

QUALITY_FIELDS = [
    key for key in GENERATED_METADATA if "quality" in key or "buffet" in key
]


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class _RecordingAsyncClient:
    """Stands in for httpx.AsyncClient and records every call."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _record(self, method, url, json_body):
        type(self).calls.append({"method": method, "url": url, "json": json_body})

    async def post(self, url, headers=None, json=None, files=None):
        self._record("POST", url, json)
        if "/children?" in url:
            return _Response(200, {"node": {"ref": {"id": NODE_ID}}})
        return _Response(200, {})

    async def put(self, url, headers=None, json=None):
        self._record("PUT", url, json)
        return _Response(200, {})

    async def get(self, url, headers=None):
        self._record("GET", url, None)
        return _Response(200, {"node": {"properties": {}, "aspects": []}})

    async def delete(self, url, headers=None):
        self._record("DELETE", url, None)
        return _Response(200, {})


@pytest.fixture
def recorded(monkeypatch):
    _RecordingAsyncClient.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _RecordingAsyncClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)
    return _RecordingAsyncClient.calls


def _written_metadata(calls):
    """The body of the main metadata write."""
    for call in calls:
        if call["method"] == "POST" and "METADATA_UPDATE" in call["url"]:
            return call["json"]
    raise AssertionError("no metadata write went out")


async def _upload(**kwargs):
    service = RepositoryService("user", "password")
    return await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_the_hidden_quality_fields_reach_the_repository(recorded):
    result = await _upload()

    assert result["success"] is True
    written = _written_metadata(recorded)

    for field_id in QUALITY_FIELDS:
        assert field_id in written, f"{field_id} wurde nicht ins Repository geschrieben"


@pytest.mark.asyncio
async def test_the_assessed_values_are_written_unchanged(recorded):
    await _upload()
    written = _written_metadata(recorded)

    # edu-sharing takes every property as an array
    assert written["ccm:oeh_quality_criminal_law"] == [
        f"{VOCAB}/quality/no_auto_findings"
    ]
    assert written["ccm:oeh_quality_data_privacy"] == [
        f"{VOCAB}/quality_data_privacy/5"
    ]
    assert written["ccm:oeh_quality_correctness"] == ["4"]
    assert written["ccm:oeh_quality_relevancy_for_education"] == ["1"]
    assert written["ccm:oeh_buffet_criteria"] == [
        "content_valid",
        "speech_valid",
        "usable_for_buffet",
    ]


@pytest.mark.asyncio
async def test_internal_keys_stay_out_of_the_repository(recorded):
    await _upload()
    written = _written_metadata(recorded)

    for key in (
        "_origins",
        "_source_text",
        "contextName",
        "schemaVersion",
        "metadataset",
    ):
        assert key not in written


@pytest.mark.asyncio
async def test_a_collection_id_references_the_content_in_that_collection(recorded):
    result = await _upload(collection_ids=[COLLECTION_ID])

    references = [
        call
        for call in recorded
        if call["method"] == "PUT" and "/collections/" in call["url"]
    ]
    assert len(references) == 1
    assert references[0]["url"].endswith(
        f"/collections/-home-/{COLLECTION_ID}/references/{NODE_ID}"
    )
    assert result["collections"] == [{"collectionId": COLLECTION_ID, "success": True}]


@pytest.mark.asyncio
async def test_an_upload_without_a_licence_makes_no_licence_claim(recorded):
    """
    GENERATED_METADATA carries no licence — the extraction prompt returns null
    when it finds none. Filling that in as COPYRIGHT_FREE turns 'we do not know'
    into 'this material is free of copyright' and publishes that claim to a
    public repository. Leaving the field empty is what hands the decision to the
    editorial workflow the upload already enters.
    """
    await _upload()

    written = _written_metadata(recorded)
    assert "ccm:commonlicense_key" not in written


@pytest.mark.asyncio
async def test_without_a_collection_id_nothing_is_referenced(recorded):
    result = await _upload()

    assert not [call for call in recorded if "/collections/" in call["url"]]
    assert "collections" not in result


@pytest.mark.asyncio
async def test_the_upload_still_stops_at_the_human_review_state(recorded):
    """Default behaviour is unchanged: hand over for checking, nothing further."""
    await _upload()

    workflow = [call for call in recorded if call["url"].endswith("/workflow")]
    assert [call["json"]["status"] for call in workflow] == [DEFAULT_WORKFLOW_STATUS]


@pytest.mark.asyncio
async def test_a_content_type_without_its_own_repo_fields_still_writes_the_core_ones(
    recorded,
):
    """
    The repo-field set is core.json plus the content type's schema. person.json
    contributes none — the quality assessment must survive that.
    """
    service = RepositoryService("user", "password")
    metadata = {**GENERATED_METADATA, "metadataset": "person.json"}

    await service.upload_metadata(
        metadata=metadata,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    written = _written_metadata(recorded)
    for field_id in QUALITY_FIELDS:
        assert field_id in written


@pytest.mark.asyncio
async def test_unknown_fields_are_not_written(recorded):
    """The repo_field flag is the gate — anything else stays out."""
    service = RepositoryService("user", "password")
    metadata = {
        **GENERATED_METADATA,
        "ccm:erfundenes_feld": "wert",
        "virtual:collection_id_primary": COLLECTION_ID,
    }

    await service.upload_metadata(
        metadata=metadata,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    written = _written_metadata(recorded)
    assert "ccm:erfundenes_feld" not in written
    assert "virtual:collection_id_primary" not in written
    # but the collection from the metadata is still honoured
    assert [
        call
        for call in recorded
        if f"/collections/-home-/{COLLECTION_ID}/" in call["url"]
    ]


@pytest.mark.asyncio
async def test_the_duplicate_check_sends_only_what_the_search_api_accepts(recorded):
    """
    SearchParameters rejects unknown fields with 400. A stray 'facettes' key did
    that on every upload, and because the check fails soft, every duplicate went
    through as new content.
    """
    service = RepositoryService("user", "password")
    await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=True,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    searches = [call for call in recorded if "ngsearch" in call["url"]]
    assert len(searches) == 1, "the duplicate check did not run"
    assert set(searches[0]["json"]) == {"criteria"}
    assert searches[0]["json"]["criteria"] == [
        {"property": "ccm:wwwurl", "values": [GENERATED_METADATA["ccm:wwwurl"]]}
    ]


class _DyingAfterCreateClient(_RecordingAsyncClient):
    """Creates the node, then the connection dies — the case that bit us live."""

    async def post(self, url, headers=None, json=None, files=None):
        if "METADATA_UPDATE" in url:
            self._record("POST", url, json)
            raise httpx.TimeoutException("read timeout")
        return await super().post(url, headers=headers, json=json, files=files)


@pytest.mark.asyncio
async def test_a_failure_after_creation_does_not_leave_a_half_written_node(monkeypatch):
    """
    The upload is create-then-populate. If the second half never runs, the node
    sits in the inbox with a title and nothing else — invisible to the caller,
    who only sees success=false and retries, producing another one. Roll it back.
    """
    _DyingAfterCreateClient.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _DyingAfterCreateClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)

    service = RepositoryService("user", "password")
    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    assert result["success"] is False
    deletes = [c for c in _DyingAfterCreateClient.calls if c["method"] == "DELETE"]
    assert len(deletes) == 1, "the created node must be discarded"
    assert f"/nodes/-home-/{NODE_ID}" in deletes[0]["url"]
    assert "recycle=true" in deletes[0]["url"], "must be recoverable, not permanent"
    assert result.get("discarded_node") == NODE_ID


@pytest.mark.asyncio
async def test_a_successful_upload_discards_nothing(recorded):
    result = await _upload()

    assert result["success"] is True
    assert not [c for c in recorded if c["method"] == "DELETE"]
    assert "discarded_node" not in result


class _DiscardRefusedClient(_DyingAfterCreateClient):
    """Creation succeeds, the upload dies, and the cleanup is refused too."""

    async def delete(self, url, headers=None):
        self._record("DELETE", url, None)
        return _Response(403, {})


@pytest.mark.asyncio
async def test_a_node_that_cannot_be_discarded_is_handed_back_for_cleanup(monkeypatch):
    """
    The rollback can itself fail — no permission, repository gone. Then the node
    really is still there, and the only way anyone learns about it is this
    response. Silence here recreates exactly the litter the rollback prevents.
    """
    _DiscardRefusedClient.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _DiscardRefusedClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)

    service = RepositoryService("user", "password")
    result = await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    assert result["success"] is False
    assert "discarded_node" not in result, "nothing was discarded"
    assert result["node"]["nodeId"] == NODE_ID, "the caller needs the id to clean up"
    assert NODE_ID in result["error"]


@pytest.mark.asyncio
async def test_a_failure_before_creation_has_nothing_to_discard(monkeypatch):
    class _DyingAtCreate(_RecordingAsyncClient):
        async def post(self, url, headers=None, json=None, files=None):
            self._record("POST", url, json)
            raise httpx.ConnectError("no route to host")

    _DyingAtCreate.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _DyingAtCreate)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)

    service = RepositoryService("user", "password")
    result = await service.upload_metadata(
        metadata=GENERATED_METADATA, check_duplicates=False, write_extended_data=False
    )

    assert result["success"] is False
    assert not [c for c in _DyingAtCreate.calls if c["method"] == "DELETE"]


def test_httpx_is_still_the_client_the_service_uses():
    """Guards the monkeypatch target above from silently going stale."""
    assert repo_module.httpx is httpx


# ------------------------------------------------- what the endpoint hands back


@pytest.mark.parametrize(
    "service_result, expected",
    [
        ({"success": False, "error": "kaputt", "discarded_node": NODE_ID}, NODE_ID),
        ({"success": True, "node": {"nodeId": NODE_ID}}, None),
    ],
)
def test_the_endpoint_passes_a_discarded_node_on(monkeypatch, service_result, expected):
    """
    The rollback only helps if the caller hears about it: the node is in the
    recycle bin, and this id is what restores it. The response is assembled
    field by field, so a field missing from the model is dropped without a
    trace — service-level tests cannot see that.
    """

    class _StubService:
        _auth_header = "Basic stub"

        async def upload_metadata(self, **kwargs):
            return service_result

    monkeypatch.setattr(main, "get_repository_service", lambda: _StubService())

    with TestClient(main.app) as client:
        body = client.post("/upload", json={"cclom:title": "Titel"}).json()

    assert body["discarded_node"] == expected


# ------------------------------------------------------------ extended fields
#
# write_extended_data defaults to true in the API, but every test above passes
# false — which left _write_extended_fields and _ensure_aspects at 0% coverage
# while being the default path in production.


async def _upload_with_extended(**kwargs):
    service = RepositoryService("user", "password")
    return await service.upload_metadata(
        metadata=GENERATED_METADATA,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=True,
        **kwargs,
    )


def _extended_write(calls):
    """
    The body of the extended-fields write.

    It goes to the same /metadata endpoint as the main write, so it is told
    apart by its content, not by its URL.
    """
    for call in calls:
        body = call["json"]
        if isinstance(body, dict) and "ccm:oeh_extendedType" in body:
            return body
    raise AssertionError("no extended-fields write went out")


@pytest.mark.asyncio
async def test_the_extended_fields_are_written_when_asked_for(recorded):
    """README: content type, the full JSON and the raw text, plus the derived lrt."""
    await _upload_with_extended(extended_text="Rohtext der Seite")

    written = _extended_write(recorded)

    assert set(written) == {
        "ccm:oeh_extendedType",
        "ccm:oeh_lrt",
        "ccm:oeh_extendedData",
        "ccm:oeh_extendedText",
    }
    assert written["ccm:oeh_extendedText"] == ["Rohtext der Seite"]


@pytest.mark.asyncio
async def test_the_content_type_uri_follows_the_schema_that_was_used(recorded):
    """GENERATED_METADATA declares learning_material.json."""
    await _upload_with_extended()

    written = _extended_write(recorded)

    assert written["ccm:oeh_extendedType"] == [
        f"{VOCAB}/contentTypes/learning_material"
    ]
    assert written["ccm:oeh_lrt"][0].startswith(f"{VOCAB}/new_lrt/")


@pytest.mark.asyncio
async def test_the_extended_data_carries_the_metadata_without_internal_keys(recorded):
    """The stored JSON is what a later import reads back — internals must not leak."""
    await _upload_with_extended()

    stored = json.loads(_extended_write(recorded)["ccm:oeh_extendedData"][0])

    assert stored["cclom:title"] == "Bruchrechnung Klasse 6"
    assert "_source_text" not in stored
    assert "_origins" not in stored


@pytest.mark.asyncio
async def test_without_extended_text_that_field_is_not_written(recorded):
    """WLO-REPO-FELDER: ccm:oeh_extendedText only when extended_text is set."""
    await _upload_with_extended()

    assert "ccm:oeh_extendedText" not in _extended_write(recorded)


# --------------------------------------------------- aspects and error paths
#
# edu-sharing drops writes to cm:latitude and ccm:lifecyclecontributer_author
# unless the node carries the matching aspect — silently, with a 200. And when
# the bulk write is rejected, the service retries field by field to name the
# offender instead of failing the whole upload.

GEO_AND_AUTHOR = {
    **GENERATED_METADATA,
    "cm:author": "Philipp Lang",
    "schema:location": [{"geo": {"latitude": 52.52, "longitude": 13.405}}],
}


class _RejectingBulkClient(_RecordingAsyncClient):
    """Rejects the write that carries more than one field."""

    async def post(self, url, headers=None, json=None, files=None):
        self._record("POST", url, json)
        if "/children?" in url:
            return _Response(200, {"node": {"ref": {"id": NODE_ID}}})
        if "METADATA_UPDATE" in url and json and len(json) > 1:
            return _Response(400, {"error": "one of these is not allowed"})
        return _Response(200, {})


@pytest.mark.asyncio
async def test_geo_and_author_get_the_aspects_they_need(recorded):
    service = RepositoryService("user", "password")
    await service.upload_metadata(
        metadata=GEO_AND_AUTHOR,
        check_duplicates=False,
        context="default",
        version="2.0.0",
        write_extended_data=False,
    )

    aspect_writes = [
        c["json"] for c in recorded if c["method"] == "PUT" and "/aspects" in c["url"]
    ]
    assert len(aspect_writes) == 1
    assert set(aspect_writes[0]) >= {"cm:geographic", "cm:author"}


@pytest.mark.asyncio
async def test_no_aspect_call_without_geo_or_author(recorded):
    """A node that needs no extra aspect must not be touched for one."""
    await _upload()

    assert not [c for c in recorded if "/aspects" in c["url"]]


@pytest.mark.asyncio
async def test_a_rejected_bulk_write_names_the_fields_that_failed(monkeypatch):
    """
    One bad value must not cost the whole upload. The retry writes each field on
    its own so the response can say which one the repository refused.
    """
    _RejectingBulkClient.calls = []
    monkeypatch.setattr(repo_module.httpx, "AsyncClient", _RejectingBulkClient)
    monkeypatch.setattr(repo_module.httpx, "Timeout", lambda *a, **k: None)

    result = await _upload()

    assert result["success"] is True
    assert result["fields_written"] > 0
    singles = [
        c
        for c in _RejectingBulkClient.calls
        if c["method"] == "POST"
        and "METADATA_UPDATE" in c["url"]
        and c["json"]
        and len(c["json"]) == 1
    ]
    assert len(singles) == result["fields_written"]
