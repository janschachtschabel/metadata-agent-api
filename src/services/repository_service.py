"""Repository service for uploading metadata to WLO edu-sharing repository."""

import base64
import json
import logging
import re
from typing import Any, Optional

import httpx

from ..utils.schema_loader import get_repo_fields, get_content_type_uri
from .repository_curation import (
    DEFAULT_WORKFLOW_STATUS,
    extract_collection_ids,
    fetch_workflow_history,
    run_workflow_steps,
    set_collections,
)
from .repository_diff import compute_diff, properties_to_flat
from .repository_licenses import transform_license
from .repository_values import (
    extract_geo_coordinates,
    normalize_for_repo,
    transform_author_to_vcard,
    transform_lrt,
)

logger = logging.getLogger(__name__)


# edu-sharing node ids are Alfresco UUIDs.
_NODE_ID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Rolling back a half-finished upload runs *after* that upload has already spent
# its budget — typically after its own 45s timeout, inside a serverless
# invocation capped at 60s (vercel.json: maxDuration). A generous timeout here
# gets killed exactly in the slow-repository case the rollback exists for, and
# the orphaned node survives anyway. It is a single DELETE; keep it short.
DISCARD_TIMEOUT_SECONDS = 5.0


def is_valid_node_id(value: Any) -> bool:
    """
    Check whether a value is a usable edu-sharing node id.

    Every node id the API accepts ends up interpolated into a repository URL
    that is called with the service account's credentials. A value containing
    '/' would steer that authenticated request at a different endpoint, so
    callers must reject anything that is not the plain UUID shape.
    """
    return isinstance(value, str) and _NODE_ID_PATTERN.fullmatch(value) is not None


def build_auth_header(username: str, password: str) -> Optional[str]:
    """
    Build a Basic Auth header for the WLO service account.

    Returns None when either credential is missing, so callers can fall back to
    anonymous access instead of sending a header for empty credentials.
    """
    if not username or not password:
        return None
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {encoded}"


def _get_repository_config() -> dict:
    """Build repository config from settings (single configured URL)."""
    from ..config import get_settings

    settings = get_settings()

    # Derive upload base URL from settings (strip '/rest' suffix if present,
    # because the upload endpoints append '/rest/...' themselves)
    base = settings.repository_url.rstrip("/")
    if base.endswith("/rest"):
        base = base[: -len("/rest")]

    return {
        "base_url": base,
        "inbox_id": settings.wlo_inbox_id,
    }


# Mapping: ccm:oeh_extendedType URI → oeh:new_lrt URI
# Sets the learning resource type (LRT) based on the detected content type.
EXTENDED_TYPE_TO_NEW_LRT = {
    "http://w3id.org/openeduhub/vocabs/contentTypes/event": "http://w3id.org/openeduhub/vocabs/new_lrt/955590ae-5f06-4513-98e9-91dfa8d5a05e",
    "http://w3id.org/openeduhub/vocabs/contentTypes/source": "http://w3id.org/openeduhub/vocabs/new_lrt/3869b453-d3c1-4b34-8f25-9127e9d68766",
    "http://w3id.org/openeduhub/vocabs/contentTypes/education_offer": "http://w3id.org/openeduhub/vocabs/new_lrt/03ab835b-c39c-48d1-b5af-7611de2f6464",
    "http://w3id.org/openeduhub/vocabs/contentTypes/tool_service": "http://w3id.org/openeduhub/vocabs/new_lrt/cefccf75-cba3-427d-9a0f-35b4fedcbba1",
    "http://w3id.org/openeduhub/vocabs/contentTypes/didactic_concepts": "http://w3id.org/openeduhub/vocabs/new_lrt/0a79a1d0-583b-47ce-86a7-517ab352d796",
    "http://w3id.org/openeduhub/vocabs/contentTypes/learning_material": "http://w3id.org/openeduhub/vocabs/new_lrt/1846d876-d8fd-476a-b540-b8ffd713fedb",
}


class RepositoryService:
    """
    Service for uploading metadata to WLO edu-sharing repository.

    Workflow:
    1. Check for duplicates (by ccm:wwwurl)
    2. Create node with minimal data
    3. Set full metadata
    4. Add to collections (optional)
    5. Run the review workflow steps
    """

    def __init__(self, username: str, password: str):
        """
        Initialize repository service with credentials.

        Args:
            username: WLO guest upload username
            password: WLO guest upload password
        """
        self.username = username
        self.password = password
        self._auth_header = self._create_auth_header()

    def _create_auth_header(self) -> str:
        """Create Basic Auth header (credentials are guaranteed by the factory)."""
        return build_auth_header(self.username, self.password) or ""

    async def upload_metadata(
        self,
        metadata: dict[str, Any],
        repository: str = "staging",
        check_duplicates: bool = True,
        start_workflow: bool = True,
        context: str = "default",
        version: str = "latest",
        write_extended_data: bool = True,
        extended_text: Optional[str] = None,
        return_full_node: bool = False,
        collection_ids: Optional[list[str]] = None,
        workflow_steps: Optional[list[str]] = None,
        workflow_comment: Optional[str] = None,
        workflow_receiver: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Upload metadata to WLO repository.

        Args:
            metadata: Metadata dict from /generate endpoint
            repository: Ignored (kept for backward compatibility)
            check_duplicates: Check for duplicates by ccm:wwwurl
            start_workflow: Run the review workflow after upload
            write_extended_data: Write ccm:oeh_extendedType/Data/Text fields
            extended_text: Raw source text before extraction
            return_full_node: Read the node back and include it as 'node_full'
            collection_ids: Collection IDs (or collection URLs) the new node is
                referenced in, additionally to any collection found in metadata
            workflow_steps: Workflow states to run in order. Defaults to the
                single handover state DEFAULT_WORKFLOW_STATUS.
            workflow_comment: Comment written with every workflow step
            workflow_receiver: Authority names notified by every workflow step

        Returns:
            Upload result with nodeId, success status, etc.
        """
        config = _get_repository_config()

        base_url = config["base_url"]
        inbox_id = config["inbox_id"]

        # Extract metadata fields (remove processing info, etc.)
        clean_metadata = self._extract_metadata_fields(metadata)

        # Determine which schema was used from metadataset field
        schema_file = metadata.get("metadataset") or None

        # Load repo-eligible fields from schemas
        repo_field_ids = get_repo_fields(context, version, schema_file)
        print(f"📋 Repo fields from schema: {len(repo_field_ids)} fields")
        if schema_file:
            print(f"   Schemas: core.json + {schema_file}")

        # Remembered so a failure after this point can undo the half-finished node
        created_node_id: Optional[str] = None

        try:
            # Longer timeout for sequential edu-sharing calls (especially on Vercel)
            timeout = httpx.Timeout(45.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                # 1. Check for duplicates
                if check_duplicates:
                    url = clean_metadata.get("ccm:wwwurl")
                    if url:
                        duplicate = await self._check_duplicate(client, base_url, url)
                        if duplicate.get("exists"):
                            node_id = duplicate.get("nodeId")
                            dup_result = {
                                "success": False,
                                "duplicate": True,
                                "node": {
                                    "nodeId": node_id,
                                    "title": duplicate.get("title"),
                                    "description": duplicate.get("description"),
                                    "wwwurl": url,
                                    "repositoryUrl": f"{base_url}/components/render/{node_id}",
                                },
                                "error": f'URL existiert bereits: "{duplicate.get("title")}"',
                            }
                            if return_full_node and node_id:
                                dup_result["node_full"] = await self._fetch_full_node(
                                    client, base_url, node_id
                                )
                            return dup_result

                # 2. Create node with minimal data
                node_result = await self._create_node(
                    client, base_url, inbox_id, clean_metadata
                )
                if not node_result.get("success"):
                    return node_result

                node_id = node_result["nodeId"]
                created_node_id = node_id
                print(f"✅ Created node: {node_id}")

                # 2b. Add required aspects for special fields
                await self._ensure_aspects(client, base_url, node_id, clean_metadata)

                # 3. Set full metadata (only repo_field=true fields from schemas)
                metadata_result = await self._set_metadata(
                    client, base_url, node_id, clean_metadata, repo_field_ids
                )

                # 4. Reference the node in collections (from metadata and/or request)
                all_collection_ids = extract_collection_ids(
                    clean_metadata, collection_ids
                )
                collection_result = None
                if all_collection_ids:
                    collection_result = await set_collections(
                        client,
                        self._auth_header,
                        base_url,
                        node_id,
                        all_collection_ids,
                    )

                # 5. Write extended data fields (bypasses repo_field filter)
                if write_extended_data:
                    await self._write_extended_fields(
                        client,
                        base_url,
                        node_id,
                        metadata,
                        context,
                        version,
                        extended_text,
                    )

                # 6. Run the review workflow steps
                workflow_result = None
                if start_workflow:
                    workflow_result = await run_workflow_steps(
                        client,
                        self._auth_header,
                        base_url,
                        node_id,
                        workflow_steps or [DEFAULT_WORKFLOW_STATUS],
                        workflow_comment,
                        workflow_receiver,
                    )

                # Extract key metadata for response (with fallbacks for organization schema)
                title = clean_metadata.get("cclom:title") or clean_metadata.get(
                    "schema:name"
                )
                if isinstance(title, list):
                    title = title[0] if title else None
                description = clean_metadata.get(
                    "cclom:general_description"
                ) or clean_metadata.get("schema:description")
                if isinstance(description, list):
                    description = description[0] if description else None
                wwwurl = clean_metadata.get("ccm:wwwurl") or clean_metadata.get(
                    "schema:url"
                )
                if isinstance(wwwurl, list):
                    wwwurl = wwwurl[0] if wwwurl else None

                result = {
                    "success": True,
                    # Which schema decided what may be written. Without it a
                    # caller cannot tell a complete upload from one that quietly
                    # fell back to core.json and dropped the type-specific
                    # fields — both answer 200.
                    "schema_used": schema_file,
                    "repo_fields_available": len(repo_field_ids),
                    "node": {
                        "nodeId": node_id,
                        "title": title,
                        "description": description[:200] + "..."
                        if description and len(description) > 200
                        else description,
                        "wwwurl": wwwurl,
                        "repositoryUrl": f"{base_url}/components/render/{node_id}",
                    },
                    "fields_written": metadata_result.get("fields_written", 0),
                    "fields_skipped": metadata_result.get("fields_skipped", 0),
                }

                if collection_result is not None:
                    result["collections"] = collection_result["results"]
                if workflow_result is not None:
                    result["workflow"] = workflow_result["steps"]

                # Add field errors if any
                field_errors = metadata_result.get("field_errors", [])
                if field_errors:
                    result["field_errors"] = field_errors
                    result["error"] = (
                        f"{len(field_errors)} Feld(er) konnten nicht geschrieben werden"
                    )

                # If ALL fields failed, mark as unsuccessful
                if metadata_result.get(
                    "fields_written", 0
                ) == 0 and not metadata_result.get("success", True):
                    result["success"] = False
                    result["step"] = "setMetadata"

                # 7. Read the finished node back for callers that cannot fetch it
                # themselves (e.g. guest clients without repository access)
                if return_full_node:
                    result["node_full"] = await self._fetch_full_node(
                        client, base_url, node_id
                    )

                return result

        except httpx.TimeoutException as e:
            print(f"❌ Repository upload timed out: {e}")
            return await self._failed(
                base_url,
                created_node_id,
                f"Timeout bei der Verbindung zum Repository: {e}",
            )
        except httpx.ConnectError as e:
            print(f"❌ Repository connection failed: {e}")
            return await self._failed(
                base_url,
                created_node_id,
                f"Verbindung zum Repository fehlgeschlagen: {e}",
            )
        except Exception as e:
            print(f"❌ Repository upload failed: {type(e).__name__}: {e}")
            return await self._failed(
                base_url, created_node_id, f"{type(e).__name__}: {e}"
            )

    async def _failed(
        self, base_url: str, created_node_id: Optional[str], error: str
    ) -> dict[str, Any]:
        """
        Build the error response and undo a half-finished upload.

        The upload is create-then-populate. When the second half never runs, the
        node stays in the inbox carrying only its title — invisible to the
        caller, who sees success=false and retries, leaving one more behind
        every time. Discarding it keeps a failed upload from becoming litter.
        """
        result: dict[str, Any] = {"success": False, "error": error}
        if not created_node_id:
            return result

        if await self._discard_node(base_url, created_node_id):
            result["discarded_node"] = created_node_id
            result["error"] = f"{error} (unvollständiger Node wurde verworfen)"
        else:
            result["node"] = {"nodeId": created_node_id}
            result["error"] = (
                f"{error} — der unvollständige Node {created_node_id} konnte nicht "
                "verworfen werden und liegt weiterhin im Eingangsordner"
            )
        return result

    async def _discard_node(self, base_url: str, node_id: str) -> bool:
        """
        Move a node to the recycle bin. Never raises.

        Called while handling another error, so its own failure must not replace
        the original one — it is reported alongside instead.
        """
        url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}?recycle=true"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(DISCARD_TIMEOUT_SECONDS)
            ) as client:
                response = await client.delete(
                    url,
                    headers={
                        "Authorization": self._auth_header,
                        "Accept": "application/json",
                    },
                )
            if response.status_code in (200, 204):
                print(f"🧹 Discarded incomplete node {node_id}")
                return True
            print(f"⚠️ Could not discard {node_id}: HTTP {response.status_code}")
            return False
        except Exception as e:
            print(f"⚠️ Could not discard {node_id}: {type(e).__name__}: {e}")
            return False

    def _extract_metadata_fields(self, metadata: dict) -> dict:
        """Extract only metadata fields, removing processing/system info.

        Handles two formats:
        - Flat (from /generate API): fields at root level alongside system keys
        - Nested (from web component export): fields inside a 'metadata' sub-dict
        """
        # If there's a nested 'metadata' dict, unwrap it (web component export format)
        if "metadata" in metadata and isinstance(metadata.get("metadata"), dict):
            return {
                k: v for k, v in metadata["metadata"].items() if not k.startswith("_")
            }

        # Flat format: strip system and meta keys
        excluded_keys = {
            "contextName",
            "schemaVersion",
            "metadataset",
            "metadataset_uri",
            "language",
            "exportedAt",
            "processing",
            "preview_image_url",
        }
        return {
            k: v
            for k, v in metadata.items()
            if k not in excluded_keys and not k.startswith("_")
        }

    async def _check_duplicate(
        self, client: httpx.AsyncClient, base_url: str, url: str
    ) -> dict:
        """Check if URL already exists in repository."""
        try:
            search_url = f"{base_url}/rest/search/v1/queries/-home-/mds_oeh/ngsearch"

            response = await client.post(
                search_url,
                headers={
                    "Authorization": self._auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                # Only 'criteria' — SearchParameters rejects unknown fields with
                # 400 (a 'facettes' key used to be sent here), which silently
                # turned every duplicate check into "no duplicate found".
                json={"criteria": [{"property": "ccm:wwwurl", "values": [url]}]},
            )

            if response.status_code != 200:
                print(f"⚠️ Duplicate check failed: {response.status_code}")
                return {"exists": False, "warning": "Duplicate check failed"}

            data = response.json()

            if data.get("nodes") and len(data["nodes"]) > 0:
                node = data["nodes"][0]
                props = node.get("properties", {})
                return {
                    "exists": True,
                    "nodeId": node["ref"]["id"],
                    "title": node.get("title") or props.get("cclom:title", [""])[0],
                    "description": props.get("cclom:general_description", [""])[0]
                    if props.get("cclom:general_description")
                    else None,
                }

            return {"exists": False}

        except Exception as e:
            print(f"⚠️ Duplicate check error: {e}")
            return {"exists": False, "warning": str(e)}

    async def _create_node(
        self, client: httpx.AsyncClient, base_url: str, inbox_id: str, metadata: dict
    ) -> dict:
        """Create node with minimal essential fields."""
        create_url = f"{base_url}/rest/node/v1/nodes/-home-/{inbox_id}/children?type=ccm:io&renameIfExists=true&versionComment=MAIN_FILE_UPLOAD"

        # Essential fields for node creation, with fallbacks for different schemas
        # (e.g. organization uses schema:name instead of cclom:title)
        essential_fields_with_fallbacks = [
            ("cclom:title", ["schema:name"]),
            ("cclom:general_description", ["schema:description"]),
            ("cclom:general_keyword", []),
            ("ccm:wwwurl", ["schema:url"]),
            ("cclom:general_language", []),
        ]

        clean_metadata = {"ccm:linktype": ["USER_GENERATED"]}
        for field, fallbacks in essential_fields_with_fallbacks:
            value = metadata.get(field)
            # Try fallbacks if primary field is empty
            if value is None or value == "" or value == []:
                for fb in fallbacks:
                    value = metadata.get(fb)
                    if value is not None and value != "" and value != []:
                        break
            if value is not None and value != "" and value != []:
                # Normalize to array
                if isinstance(value, list):
                    clean_metadata[field] = value
                else:
                    clean_metadata[field] = [value]

        print(f"📡 Creating node at: {create_url[:80]}...")
        response = await client.post(
            create_url,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=clean_metadata,
        )

        if response.status_code not in (200, 201):
            error_text = response.text[:500]
            print(f"❌ Create node failed: {response.status_code} - {error_text}")
            return {
                "success": False,
                "error": f"Create node failed: {response.status_code} - {error_text}",
            }

        data = response.json()
        return {"success": True, "nodeId": data["node"]["ref"]["id"]}

    async def _fetch_full_node(
        self, client: httpx.AsyncClient, base_url: str, node_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Read the complete node from the repository.

        Returns the raw edu-sharing node object (same shape as the 'node' entry of
        GET /node/v1/nodes/-home-/{id}/metadata), or None if the read fails.

        Never raises: the upload itself already succeeded at this point, so a
        failed read-back must not turn a successful upload into an error.
        """
        url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/metadata?propertyFilter=-all-"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
            )
            if response.status_code != 200:
                print(
                    f"⚠️ Read-back of node {node_id} failed: HTTP {response.status_code}"
                )
                return None
            return response.json().get("node")
        except Exception as e:
            print(f"⚠️ Read-back of node {node_id} failed: {type(e).__name__}: {e}")
            return None

    async def _set_metadata(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        node_id: str,
        metadata: dict,
        repo_field_ids: set[str] | None = None,
    ) -> dict:
        """
        Set full metadata on node using dynamically loaded repo fields from schemas.

        Strategy:
        1. Filter metadata to only include fields with repo_field=true in schemas
        2. Try bulk update with all fields
        3. If bulk fails, retry field-by-field to identify problematic fields
        4. Report per-field errors
        """
        metadata_url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/metadata?versionComment=METADATA_UPDATE&obeyMds=false"

        # Normalize metadata values for repository API
        normalized = normalize_for_repo(metadata, repo_field_ids)

        # Handle license transformation
        transform_license(normalized, metadata)

        # No default license on purpose: the extraction returns null when it
        # finds none, and filling that in would turn "we do not know" into a
        # claim that the material is free of copyright — published to a public
        # repository. An empty field is what hands the decision to the editorial
        # workflow this upload already enters.
        if "ccm:commonlicense_key" not in normalized:
            print("📜 No license detected — left empty for editorial review")

        # Extract geo coordinates from schema:location → cm:latitude / cm:longitude
        extract_geo_coordinates(normalized, metadata)

        # Transform cm:author → ccm:lifecyclecontributer_author (VCARD format)
        transform_author_to_vcard(normalized)

        # Transform oeh:new_lrt → ccm:oeh_lrt (the property the repository keeps)
        transform_lrt(normalized)

        if not normalized:
            return {
                "success": True,
                "fields_written": 0,
                "fields_skipped": 0,
                "field_errors": [],
            }

        fields_to_write = set(normalized.keys())
        print(f"📝 Writing {len(fields_to_write)} fields to node {node_id}")

        # --- Strategy 1: Bulk update (all fields at once) ---
        response = await client.post(
            metadata_url,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=normalized,
        )

        if response.status_code in (200, 201):
            print(f"✅ Bulk metadata update succeeded: {len(normalized)} fields")
            return {
                "success": True,
                "fields_written": len(normalized),
                "fields_skipped": 0,
                "field_errors": [],
            }

        # --- Strategy 2: Bulk failed → field-by-field fallback ---
        bulk_error = response.text[:500]
        print(f"⚠️ Bulk metadata update failed ({response.status_code}): {bulk_error}")
        print("🔄 Retrying field-by-field to identify problematic fields...")

        fields_written = 0
        fields_skipped = 0
        field_errors = []

        for field_id, field_value in normalized.items():
            try:
                single_response = await client.post(
                    metadata_url,
                    headers={
                        "Authorization": self._auth_header,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={field_id: field_value},
                )

                if single_response.status_code in (200, 201):
                    fields_written += 1
                else:
                    fields_skipped += 1
                    error_text = single_response.text[:200]
                    field_errors.append(
                        {
                            "field_id": field_id,
                            "error": f"HTTP {single_response.status_code}: {error_text}",
                            "status_code": single_response.status_code,
                        }
                    )
                    print(f"   ❌ {field_id}: {single_response.status_code}")
            except Exception as e:
                fields_skipped += 1
                field_errors.append(
                    {"field_id": field_id, "error": str(e), "status_code": None}
                )
                print(f"   ❌ {field_id}: {e}")

        print(
            f"📊 Field-by-field result: {fields_written} written, {fields_skipped} failed"
        )

        return {
            "success": fields_written > 0,
            "fields_written": fields_written,
            "fields_skipped": fields_skipped,
            "field_errors": field_errors,
        }

    async def _write_extended_fields(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        node_id: str,
        metadata: dict[str, Any],
        context: str,
        version: str,
        extended_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Write the 3 extended metadata fields to a node (bypasses repo_field filter).

        Fields:
        - ccm:oeh_extendedType: URI of the content type from core.json vocabulary
        - ccm:oeh_extendedData: Full metadata JSON after generation/extraction
        - ccm:oeh_extendedText: Raw source text before extraction
        """
        metadata_url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/metadata?versionComment=EXTENDED_DATA&obeyMds=false"

        extended_fields: dict[str, list[str]] = {}

        # 1. ccm:oeh_extendedType — resolve URI from metadataset (schema_file)
        type_uri = None
        schema_file = metadata.get("metadataset")
        if schema_file:
            type_uri = get_content_type_uri(schema_file, context, version)
            if type_uri:
                extended_fields["ccm:oeh_extendedType"] = [type_uri]
                print(f"📎 extendedType: {type_uri} (from {schema_file})")
            else:
                print(f"⚠️ extendedType: No URI found for schema_file={schema_file}")

        # 1b. ccm:oeh_lrt — derived from the content type, but only as a fallback.
        # This write happens after the metadata write, so setting it here
        # unconditionally would replace whatever the extraction found. The
        # derivation knows six coarse types ('Material'); the extraction picks
        # from 220 ('Arbeitsblatt', 'Simulation'). The precise value wins.
        extracted_lrt = metadata.get("oeh:new_lrt") or metadata.get("ccm:oeh_lrt")
        if extracted_lrt:
            print(f"📎 lrt: kept from extraction, not overwritten ({extracted_lrt})")
        elif type_uri and type_uri in EXTENDED_TYPE_TO_NEW_LRT:
            lrt_uri = EXTENDED_TYPE_TO_NEW_LRT[type_uri]
            extended_fields["ccm:oeh_lrt"] = [lrt_uri]
            print(f"📎 lrt: {lrt_uri} (from extendedType {type_uri.split('/')[-1]})")

        # 2. ccm:oeh_extendedData — full metadata as JSON string
        # Remove internal processing keys, keep only actual metadata fields
        # Handle nested format (web component export) vs flat format (API response)
        if "metadata" in metadata and isinstance(metadata.get("metadata"), dict):
            data_dict = {
                k: v for k, v in metadata["metadata"].items() if not k.startswith("_")
            }
        else:
            excluded_keys = {
                "contextName",
                "schemaVersion",
                "metadataset",
                "metadataset_uri",
                "language",
                "exportedAt",
                "processing",
                "_origins",
                "_source_text",
                "preview_image_url",
            }
            data_dict = {k: v for k, v in metadata.items() if k not in excluded_keys}
        if data_dict:
            extended_fields["ccm:oeh_extendedData"] = [
                json.dumps(data_dict, ensure_ascii=False)
            ]
            print(
                f"📎 extendedData: {len(json.dumps(data_dict, ensure_ascii=False))} chars"
            )

        # 3. ccm:oeh_extendedText — raw source text
        if extended_text:
            extended_fields["ccm:oeh_extendedText"] = [extended_text]
            print(f"📎 extendedText: {len(extended_text)} chars")

        if not extended_fields:
            print("⚠️ No extended fields to write")
            return {"success": True, "fields_written": 0}

        # Write all extended fields in one request
        try:
            response = await client.post(
                metadata_url,
                headers={
                    "Authorization": self._auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=extended_fields,
            )

            if response.status_code in (200, 201):
                print(f"✅ Extended fields written: {list(extended_fields.keys())}")
                return {"success": True, "fields_written": len(extended_fields)}
            else:
                error_text = response.text[:300]
                print(
                    f"⚠️ Extended fields bulk write failed ({response.status_code}): {error_text}"
                )

                # Fallback: write field-by-field
                written = 0
                for field_id, field_value in extended_fields.items():
                    try:
                        single_resp = await client.post(
                            metadata_url,
                            headers={
                                "Authorization": self._auth_header,
                                "Content-Type": "application/json",
                                "Accept": "application/json",
                            },
                            json={field_id: field_value},
                        )
                        if single_resp.status_code in (200, 201):
                            written += 1
                            print(f"   ✅ {field_id}")
                        else:
                            print(f"   ❌ {field_id}: {single_resp.status_code}")
                    except Exception as e:
                        print(f"   ❌ {field_id}: {e}")

                return {"success": written > 0, "fields_written": written}

        except Exception as e:
            print(f"❌ Extended fields write failed: {e}")
            return {"success": False, "fields_written": 0, "error": str(e)}

    async def _ensure_aspects(
        self, client: httpx.AsyncClient, base_url: str, node_id: str, metadata: dict
    ):
        """
        Add required aspects to node based on metadata content.

        Aspects are Alfresco extension packages that enable specific property groups.
        Without the correct aspect, the repo silently drops writes to those properties.
        """
        extra_aspects = []

        # cm:geographic → needed for cm:latitude, cm:longitude
        has_geo = False
        locations = metadata.get("schema:location")
        if locations:
            if isinstance(locations, list):
                for loc in locations:
                    if isinstance(loc, dict) and isinstance(loc.get("geo"), dict):
                        has_geo = True
                        break
            elif isinstance(locations, dict) and isinstance(locations.get("geo"), dict):
                has_geo = True
        # Also check schema:geo (organization.json top-level)
        if not has_geo and isinstance(metadata.get("schema:geo"), dict):
            geo = metadata["schema:geo"]
            if geo.get("latitude") is not None and geo.get("longitude") is not None:
                has_geo = True
        if has_geo:
            extra_aspects.append("cm:geographic")

        # cm:author → needed for ccm:lifecyclecontributer_author
        if metadata.get("cm:author"):
            extra_aspects.append("cm:author")

        if not extra_aspects:
            return

        # Read current aspects, merge, PUT back
        try:
            aspects_url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/aspects"
            r = await client.get(
                f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/metadata?propertyFilter=-all-",
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
            )
            current_aspects = []
            if r.status_code == 200:
                current_aspects = r.json().get("node", {}).get("aspects", [])

            new_aspects = [a for a in extra_aspects if a not in current_aspects]
            if new_aspects:
                full_list = current_aspects + new_aspects
                r = await client.put(
                    aspects_url,
                    headers={
                        "Authorization": self._auth_header,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=full_list,
                )
                if r.status_code == 200:
                    print(f"🔧 Aspects added: {new_aspects}")
                else:
                    print(f"⚠️ Failed to add aspects {new_aspects}: {r.status_code}")
        except Exception as e:
            print(f"⚠️ Aspect update error: {e}")

    async def verify_node(
        self,
        node_id: str,
        repository: str = "staging",
        expected_metadata: dict[str, Any] | None = None,
        context: str = "default",
        version: str = "latest",
    ) -> dict[str, Any]:
        """
        Read metadata from repository and optionally compare against expected values.

        Args:
            node_id: The node ID to verify
            repository: 'staging' or 'prod'
            expected_metadata: If provided, compute field-level diff
            context: Schema context for repo_field filtering
            version: Schema version for repo_field filtering

        Returns:
            Dict with actual_metadata, optional diff and summary
        """
        config = _get_repository_config()

        base_url = config["base_url"]

        try:
            timeout = httpx.Timeout(30.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Fetch node metadata
                url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/metadata?propertyFilter=-all-"
                response = await client.get(
                    url,
                    headers={
                        "Authorization": self._auth_header,
                        "Accept": "application/json",
                    },
                )

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Failed to fetch node: HTTP {response.status_code} — {response.text[:300]}",
                    }

                data = response.json()
                properties = data.get("node", {}).get("properties", {})

                # Convert to flat metadata (same logic as input_source_service)
                actual = properties_to_flat(properties)

                result = {
                    "success": True,
                    "node_id": node_id,
                    "actual_metadata": actual,
                }

                # If expected metadata provided, compute diff
                if expected_metadata:
                    diff, summary = compute_diff(
                        expected_metadata, actual, context, version
                    )
                    result["diff"] = diff
                    result["summary"] = summary

                return result

        except httpx.TimeoutException as e:
            return {"success": False, "error": f"Timeout: {e}"}
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    async def set_workflow(
        self,
        node_id: str,
        steps: list[str],
        comment: Optional[str] = None,
        receiver: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Advance an existing node through the review workflow.

        Used after the upload has already handed the node over for human
        checking, to walk the remaining editorial states step by step.

        Returns the per-step result plus the node's resulting workflow state and
        its full history (which records who set which state).
        """
        config = _get_repository_config()
        base_url = config["base_url"]

        try:
            timeout = httpx.Timeout(45.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                run = await run_workflow_steps(
                    client,
                    self._auth_header,
                    base_url,
                    node_id,
                    steps,
                    comment,
                    receiver,
                )

                result: dict[str, Any] = {
                    "success": run["success"],
                    "nodeId": node_id,
                    "steps": run["steps"],
                    "repositoryUrl": f"{base_url}/components/render/{node_id}",
                }

                # Read back so callers see the state that actually stuck
                node = await self._fetch_full_node(client, base_url, node_id)
                if node:
                    wf_status = (node.get("properties") or {}).get("ccm:wf_status")
                    if isinstance(wf_status, list):
                        wf_status = wf_status[0] if wf_status else None
                    result["current_status"] = wf_status

                history = await fetch_workflow_history(
                    client, self._auth_header, base_url, node_id
                )
                if history is not None:
                    result["history"] = history

                if not run["success"]:
                    failed = [s["status"] for s in run["steps"] if not s["success"]]
                    result["error"] = (
                        f"Workflow-Schritt(e) fehlgeschlagen: {', '.join(failed)}"
                    )

                return result

        except httpx.TimeoutException as e:
            return {
                "success": False,
                "nodeId": node_id,
                "error": f"Timeout bei der Verbindung zum Repository: {e}",
            }
        except httpx.ConnectError as e:
            return {
                "success": False,
                "nodeId": node_id,
                "error": f"Verbindung zum Repository fehlgeschlagen: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "nodeId": node_id,
                "error": f"{type(e).__name__}: {e}",
            }


# Singleton instance
_repository_service: Optional[RepositoryService] = None


def get_repository_service() -> Optional[RepositoryService]:
    """Get repository service singleton (requires credentials in environment)."""
    global _repository_service

    if _repository_service is None:
        from ..config import get_settings

        settings = get_settings()

        username = settings.wlo_guest_username
        password = settings.wlo_guest_password

        if username and password:
            _repository_service = RepositoryService(username, password)
        else:
            return None

    return _repository_service
