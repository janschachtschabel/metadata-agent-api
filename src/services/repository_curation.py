"""
What happens to a node after its metadata is written.

Two curation steps that follow the upload but change for their own reasons:
referencing the content in collections, and walking it through the WLO editorial
review workflow one state at a time.

The functions take an open HTTP client and the auth header rather than holding
state — `repository_service` owns the connection.
"""

from typing import Any, Optional
from urllib.parse import unquote

import httpx

# Review workflow status used when a node is handed over for human checking.
# This is the state the upload flow stops at unless further steps are requested.
DEFAULT_WORKFLOW_STATUS = "200_tocheck"

# Receiver group for DEFAULT_WORKFLOW_STATUS — the WLO upload management queue.
DEFAULT_WORKFLOW_RECEIVER = ["GROUP_ORG_WLO-Uploadmanager"]

# Workflow states of the WLO editorial process, read from the repository config
# (/rest/config/v1/values → workflow.workflows) plus the two states that occur in
# live data but are not listed there ('200_tocheck', '125_METADATA_QUALITY_FOR_BUFFET').
# Kept as a documented allow-list so a typo fails fast instead of writing an
# unknown state into the repository.
KNOWN_WORKFLOW_STATUS = {
    "100_unchecked",
    "110_METADATA_RECORD_REQUESTED",
    "120_METADATA_QUALITY_CONFIRMED",
    "125_METADATA_QUALITY_FOR_BUFFET",
    "130_ELEMENT_REJECTED",
    "140_ELEMENT_LEGALLY_APPROVED",
    "150_PUBLISH_IN_SEARCH",
    "160_REMOVE_FROM_SEARCH",
    "200_tocheck",
    "TASK_CREATE_TREE",
    "TASK_CHECK_COLLECTION_PROPOSAL",
    "TASK_CHECK_QUALITY",
}


def extract_id_from_url(value: Any) -> str:
    """
    Extract a collection node ID from a plain ID or a repository URL.

    Handles the shapes users actually paste from the WLO frontend:
    - '3039bdb2-…'                                    → as-is
    - '…/components/collections/3039bdb2-…'           → last path segment
    - '…/components/collections?id=3039bdb2-…&x=1'    → 'id' query parameter
    """
    if not isinstance(value, str):
        return str(value) if value else ""

    candidate = value.strip()
    if not candidate:
        return ""

    # Collection links carry the node in the 'id' query parameter
    if "?" in candidate:
        base, _, query = candidate.partition("?")
        for part in query.split("&"):
            key, _, val = part.partition("=")
            if key == "id" and val:
                return unquote(val).split("/")[-1]
        candidate = base

    candidate = candidate.split("#")[0].rstrip("/")
    return unquote(candidate).split("/")[-1]


def extract_collection_ids(
    metadata: dict, extra: Optional[list[str]] = None
) -> list[str]:
    """
    Collect the collection IDs a node should be referenced in.

    Sources, in this order: the explicitly requested IDs (upload parameter),
    the primary collection from metadata, additional collections from
    metadata. Duplicates are removed while keeping the first occurrence.
    """
    ids = []

    # Explicitly requested collections (upload parameter)
    for coll in extra or []:
        ids.append(extract_id_from_url(coll))

    # Primary collection
    primary = metadata.get("virtual:collection_id_primary")
    if primary:
        ids.append(extract_id_from_url(primary))

    # Additional collections
    additional = metadata.get("ccm:collection_id", [])
    if isinstance(additional, list):
        for coll in additional:
            ids.append(extract_id_from_url(coll))

    seen: set[str] = set()
    unique = []
    for coll_id in ids:
        if coll_id and coll_id not in seen:
            seen.add(coll_id)
            unique.append(coll_id)
    return unique


async def set_collections(
    client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    node_id: str,
    collection_ids: list[str],
) -> dict:
    """Reference the node in the given collections."""
    results = []

    for collection_id in collection_ids:
        try:
            url = f"{base_url}/rest/collection/v1/collections/-home-/{collection_id}/references/{node_id}"
            response = await client.put(
                url,
                headers={
                    "Authorization": auth_header,
                    "Accept": "application/json",
                },
            )
            success = response.status_code in (200, 201)
            entry: dict[str, Any] = {
                "collectionId": collection_id,
                "success": success,
            }
            if success:
                print(f"📚 Referenced in collection {collection_id}")
            else:
                entry["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                print(f"⚠️ Collection {collection_id} failed: {response.status_code}")
            results.append(entry)
        except Exception as e:
            print(f"⚠️ Collection {collection_id} failed: {type(e).__name__}: {e}")
            results.append(
                {"collectionId": collection_id, "success": False, "error": str(e)}
            )

    return {"results": results}


async def run_workflow_steps(
    client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    node_id: str,
    steps: list[str],
    comment: Optional[str] = None,
    receiver: Optional[list[str]] = None,
) -> dict:
    """
    Walk the editorial review workflow one state at a time.

    edu-sharing records every PUT as its own entry in the node's workflow
    history, together with the acting user. Running the states one by one is
    therefore what makes the protocol readable later ("who confirmed the
    quality?") — a single jump to the final state would lose the trail.
    """
    workflow_url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/workflow"
    results = []

    for status in steps:
        # The receiver group only makes sense for the handover state; the
        # later editorial states are recorded on the acting user (see the
        # 'receiver: []' of the editorial desk itself).
        step_receiver = receiver
        if step_receiver is None:
            step_receiver = (
                DEFAULT_WORKFLOW_RECEIVER if status == DEFAULT_WORKFLOW_STATUS else []
            )

        # Exactly the three fields WorkflowHistory accepts — anything else
        # (a 'logLevel' used to be sent here) makes edu-sharing answer 400
        # with UnrecognizedPropertyException and the state is never set.
        payload = {
            "receiver": [{"authorityName": name} for name in step_receiver],
            "comment": comment
            if comment is not None
            else "Upload via Metadata Agent API",
            "status": status,
        }

        try:
            response = await client.put(
                workflow_url,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            success = response.status_code in (200, 201)
            entry: dict[str, Any] = {"status": status, "success": success}
            if success:
                print(f"🔄 Workflow → {status}")
            else:
                entry["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                print(f"⚠️ Workflow → {status} failed: {response.status_code}")
            results.append(entry)
        except Exception as e:
            print(f"⚠️ Workflow → {status} failed: {type(e).__name__}: {e}")
            results.append({"status": status, "success": False, "error": str(e)})

    return {"success": all(r["success"] for r in results), "steps": results}


async def fetch_workflow_history(
    client: httpx.AsyncClient, auth_header: str, base_url: str, node_id: str
) -> Optional[list[dict[str, Any]]]:
    """
    Read the workflow protocol of a node.

    Never raises: the workflow steps themselves already ran at this point, so
    a failed read must not turn a successful transition into an error.
    """
    url = f"{base_url}/rest/node/v1/nodes/-home-/{node_id}/workflow"
    try:
        response = await client.get(
            url,
            headers={
                "Authorization": auth_header,
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            print(
                f"⚠️ Workflow history of {node_id} unavailable: HTTP {response.status_code}"
            )
            return None
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("history") or data.get("workflow")
    except Exception as e:
        print(f"⚠️ Workflow history of {node_id} failed: {type(e).__name__}: {e}")
        return None
