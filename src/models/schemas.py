"""Pydantic models for API request/response schemas."""

import re
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from ..services.repository_curation import KNOWN_WORKFLOW_STATUS
from ..services.repository_service import is_valid_node_id


def validate_node_id(value: Any) -> Any:
    """
    Reject anything that is present but is not an edu-sharing node id.

    Shared by every request model carrying one — the value reaches a repository
    URL that is called with the service account's credentials, so the shape has
    to be checked at the boundary rather than at each call site.

    A blank string means 'nothing entered' and becomes None. Whether the field is
    required at all depends on `input_source`, and each branch of the endpoint
    checks its own with a message that says so — this validator cannot know, and
    answering a text-input request with 'Ungültige node_id' names a field that
    request does not use.
    """
    if isinstance(value, str) and not value.strip():
        return None
    if value is None or is_valid_node_id(value):
        return value
    raise ValueError(
        "Ungültige node_id — erwartet wird eine Node-UUID, "
        "z.B. '3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9'."
    )


class InputSource(str, Enum):
    """Input source for metadata generation."""

    TEXT = "text"  # Direct text input (default)
    URL = "url"  # Fetch text via text extraction API
    NODE_ID = "node_id"  # Fetch from repository by NodeID
    NODE_URL = (
        "node_url"  # Use NodeID + URL (prefers stored data, falls back to crawler)
    )


class ExtractionMethod(str, Enum):
    """Text extraction method for URL input."""

    SIMPLE = "simple"
    BROWSER = "browser"


class OutputFormat(str, Enum):
    """Output format for text extraction."""

    MARKDOWN = "markdown"
    TXT = "txt"
    HTML = "html"


def sanitize_text(text: str) -> str:
    """
    Sanitize text input by normalizing control characters.
    - Preserves newlines (\n), tabs (\t), and carriage returns (\r)
    - Removes other control characters (0x00-0x1F except \t, \n, \r)
    - Normalizes various whitespace characters to regular spaces
    """
    if not text:
        return text

    # Remove NULL bytes and other problematic control characters
    # Keep: \t (0x09), \n (0x0A), \r (0x0D)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    # Normalize various Unicode whitespace to regular spaces
    text = re.sub(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000]", " ", text)

    # Normalize Windows line endings to Unix
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive whitespace (more than 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class LocalizedString(BaseModel):
    """Localized string with de/en support."""

    de: Optional[str] = None
    en: Optional[str] = None


class GenerateRequest(BaseModel):
    """Request model for metadata generation."""

    # Input source selection
    input_source: InputSource = Field(
        default=InputSource.TEXT,
        description="Input source: 'text' (direct input), 'url' (fetch via crawler), 'node_id' (fetch from repository), 'node_url' (repository + crawler fallback)",
    )

    # Text input (required for input_source='text')
    text: Optional[str] = Field(
        default=None,
        description="Input text to extract metadata from. Required when input_source='text'.",
    )

    # URL input (required for input_source='url' or 'node_url')
    source_url: Optional[str] = Field(
        default=None,
        description="URL to fetch text from via text extraction API. Required when input_source='url' or 'node_url'.",
    )
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.BROWSER,
        description="Text extraction method: 'simple' (fast, basic HTML parsing) or 'browser' (full browser rendering, slower but more complete)",
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Output format for text extraction: 'markdown' (default), 'txt' (plain text), 'html' (raw HTML)",
    )

    # NodeID input (required for input_source='node_id' or 'node_url')
    node_id: Optional[str] = Field(
        default=None,
        description="Repository NodeID to fetch metadata and text from. Required when input_source='node_id' or 'node_url'. Must be a node UUID.",
    )
    _check_node_id = field_validator("node_id")(validate_node_id)
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )

    # Common options
    existing_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Existing metadata JSON to use as base (will be updated/enriched). For node_id/node_url sources, fetched metadata is merged.",
    )
    context: str = Field(
        default="default",
        description="Schema context to use (e.g., 'default', 'mds_oeh')",
    )
    version: str = Field(
        default="latest",
        description="Schema version to use ('latest' for newest version, or specific like '1.8.1')",
    )
    schema_file: str = Field(
        default="auto",
        description="Schema file to use ('auto' for automatic detection, specific filename like 'event.json', or a vocab URI like 'http://w3id.org/openeduhub/vocabs/contentTypes/event')",
    )
    language: str = Field(
        default="de", description="Primary language for extraction (de/en)"
    )
    max_workers: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of parallel LLM workers (1-20)",
    )
    include_core: bool = Field(
        default=True,
        description="Include core fields (title, description, keywords, etc.) in extraction",
    )
    enable_geocoding: bool = Field(
        default=True,
        description="Enable geocoding to convert location addresses to coordinates (uses Photon API)",
    )

    # Normalization option
    normalize: bool = Field(
        default=True,
        description="Apply normalization to extracted values (dates, booleans, vocabularies, etc.)",
    )

    # Field regeneration options
    regenerate_fields: Optional[list[str]] = Field(
        default=None,
        description="List of field IDs to regenerate (re-extract from text). Other fields use existing_metadata.",
    )
    regenerate_empty: bool = Field(
        default=False,
        description="Re-extract fields that are empty/null in existing_metadata",
    )

    # LLM options (override defaults from .env)
    llm_provider: Optional[str] = Field(
        default=None,
        description="LLM provider to use. Options: 'openai' (native OpenAI API), 'b-api-openai' (OpenAI via B-API, default), 'b-api-academiccloud' (DeepSeek via B-API). If not set, uses METADATA_AGENT_LLM_PROVIDER from environment.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="LLM model to use. Without it the provider's configured default applies: 'deepseek-v4-flash' (b-api-academiccloud), 'gpt-5.6-luna' (b-api-openai), 'gpt-4o-mini' (openai).",
    )

    # Screenshot options (async preview generation during extraction)
    preview_url: Optional[str] = Field(
        default=None,
        description="URL to capture as preview screenshot (runs async parallel to KI extraction). If not set, auto-detected from source_url or ccm:wwwurl.",
    )
    screenshot_method: Optional[str] = Field(
        default=None,
        description="Screenshot method: 'pageshot' (external API, default) or 'playwright' (internal, privacy-safe). If not set, no screenshot is captured.",
    )

    @field_validator("text", mode="before")
    @classmethod
    def sanitize_text_input(cls, v: Any) -> str:
        """Sanitize text input before validation."""
        if isinstance(v, str):
            return sanitize_text(v)
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Workshop 'KI in der Bildung' am 15. März 2025 in Berlin. Lernen Sie die Grundlagen der künstlichen Intelligenz kennen.",
                    "existing_metadata": {"cclom:title": "Mein Workshop"},
                    "context": "default",
                    "version": "latest",
                    "schema_file": "auto",
                    "language": "de",
                    "include_core": True,
                    "max_workers": 10,
                    "llm_provider": "b-api-academiccloud",
                    "llm_model": "deepseek-v4-flash",
                    "screenshot_method": "pageshot",
                    "preview_url": "",
                }
            ]
        }
    }


class ProcessingInfo(BaseModel):
    """Processing statistics and debug info."""

    success: bool
    fields_extracted: int = Field(description="Number of fields with values")
    fields_total: int = Field(description="Total number of fields in schema")
    processing_time_ms: int = Field(description="Processing time in milliseconds")
    llm_provider: str = Field(description="LLM provider used")
    llm_model: str = Field(description="LLM model used")
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )
    warnings: list[str] = Field(default_factory=list, description="Any warnings")


class GenerateResponse(BaseModel):
    """
    Response model for metadata generation.

    The response contains header info, then flat metadata fields directly,
    followed by processing info at the end.
    """

    # Meta information (header)
    contextName: str = Field(description="Schema context name")
    schemaVersion: str = Field(description="Schema version used")
    metadataset: str = Field(description="Schema file that was used")
    metadataset_uri: Optional[str] = Field(
        default=None,
        description="Vocab URI for the metadataset (e.g., 'http://w3id.org/openeduhub/vocabs/contentTypes/event')",
    )
    language: str = Field(description="Language used for extraction")
    exportedAt: str = Field(description="ISO timestamp of generation")

    # Flat metadata - stored internally but expanded in serialization
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Generated metadata as flat key-value pairs. Fields appear at top level in response.",
    )

    # Processing info (separate)
    processing: ProcessingInfo = Field(
        description="Processing statistics and debug info"
    )

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Custom serialization to flatten metadata into response."""
        # Get base dict with header and processing
        result = {
            "contextName": self.contextName,
            "schemaVersion": self.schemaVersion,
            "metadataset": self.metadataset,
            "metadataset_uri": self.metadataset_uri,
            "language": self.language,
            "exportedAt": self.exportedAt,
        }

        # Add flattened metadata fields directly
        for key, value in self.metadata.items():
            if value is not None:
                result[key] = value

        # Add processing info at the end
        result["processing"] = self.processing.model_dump() if self.processing else {}

        return result


class ValidateRequest(BaseModel):
    """
    Request model for metadata validation.

    All parameters default to 'auto' and are automatically detected from the metadata:
    - contextName → context
    - schemaVersion → version
    - metadataset → schema_file

    You can override any parameter by providing an explicit value.
    """

    # The metadata to validate - can be full export or just fields
    metadata: dict[str, Any] = Field(
        ..., description="Metadata JSON to validate (full export or nested)"
    )

    # Parameters with auto-detection (set to 'auto' to read from metadata)
    context: str = Field(
        default="auto",
        description="Schema context ('auto' = read from contextName in metadata)",
    )
    version: str = Field(
        default="auto",
        description="Schema version ('auto' = read from schemaVersion in metadata)",
    )
    schema_file: str = Field(
        default="auto",
        description="Schema file ('auto' = read from metadataset in metadata)",
    )

    def get_effective_params(self) -> tuple[str, str, str, dict[str, Any]]:
        """
        Extract effective context, version, schema_file and clean metadata.
        Returns: (context, version, schema_file, clean_metadata)
        """
        metadata = self.metadata.copy()

        # Extract values from metadata
        meta_context = metadata.pop("contextName", None)
        meta_version = metadata.pop("schemaVersion", None)
        meta_schema = metadata.pop("metadataset", None)

        # Remove other meta fields
        metadata.pop("language", None)
        metadata.pop("exportedAt", None)
        metadata.pop("processing", None)

        # Also check old nested _schema format
        if "_schema" in metadata:
            schema_info = metadata.pop("_schema")
            meta_context = meta_context or schema_info.get("context")
            meta_version = meta_version or schema_info.get("version")
            meta_schema = meta_schema or schema_info.get("file")

        # Use explicit value if not 'auto', otherwise use detected value, otherwise fallback
        context = meta_context if self.context == "auto" else self.context
        version = meta_version if self.version == "auto" else self.version
        schema_file = meta_schema if self.schema_file == "auto" else self.schema_file

        # Final fallbacks if still None
        context = context or "default"
        version = version or "latest"
        schema_file = schema_file or "auto"

        return context, version, schema_file, metadata


class ValidationError(BaseModel):
    """Single validation error."""

    field_id: str
    message: str
    severity: str = Field(description="error, warning, or info")


class ValidateResponse(BaseModel):
    """Response model for metadata validation."""

    valid: bool
    schema_used: str
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationError] = Field(default_factory=list)
    coverage: float = Field(description="Percentage of required fields filled")


class ExportMarkdownRequest(BaseModel):
    """
    Request model for markdown export.

    Like ValidateRequest, all parameters default to 'auto' for auto-detection.
    Simply pass the complete output from /generate directly as `metadata`.
    """

    metadata: dict[str, Any] = Field(
        ..., description="Complete output from /generate endpoint - paste directly"
    )
    context: str = Field(
        default="auto", description="Schema context ('auto' = read from metadata)"
    )
    version: str = Field(
        default="auto", description="Schema version ('auto' = read from metadata)"
    )
    schema_file: str = Field(
        default="auto", description="Schema file ('auto' = read from metadata)"
    )
    language: str = Field(
        default="auto",
        description="Output language ('auto' = read from metadata, fallback: de)",
    )
    include_empty: bool = Field(default=False, description="Include empty fields")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metadata": {
                        "contextName": "default",
                        "schemaVersion": "1.8.1",
                        "metadataset": "event.json",
                        "language": "de",
                        "cclom:title": "Workshop KI in der Bildung",
                        "cclom:general_description": "Ein Workshop über KI...",
                        "schema:actor": [{"name": "Max Mustermann"}],
                        "schema:location": [
                            {"name": "Berlin", "address": {"addressLocality": "Berlin"}}
                        ],
                    }
                }
            ]
        }
    }

    def get_effective_params(self) -> tuple[str, str, str, str, dict[str, Any]]:
        """
        Extract effective parameters and clean metadata.
        Returns: (context, version, schema_file, language, clean_metadata)
        """
        metadata = self.metadata.copy()

        # Extract values from metadata
        meta_context = metadata.pop("contextName", None)
        meta_version = metadata.pop("schemaVersion", None)
        meta_schema = metadata.pop("metadataset", None)
        meta_language = metadata.pop("language", None)

        # Remove other meta fields
        metadata.pop("exportedAt", None)
        metadata.pop("processing", None)

        # Also check old nested _schema format
        if "_schema" in metadata:
            schema_info = metadata.pop("_schema")
            meta_context = meta_context or schema_info.get("context")
            meta_version = meta_version or schema_info.get("version")
            meta_schema = meta_schema or schema_info.get("file")

        # Use explicit value if not 'auto', otherwise use detected value
        context = meta_context if self.context == "auto" else self.context
        version = meta_version if self.version == "auto" else self.version
        schema_file = meta_schema if self.schema_file == "auto" else self.schema_file
        language = meta_language if self.language == "auto" else self.language

        # Final fallbacks
        context = context or "default"
        version = version or "latest"
        schema_file = schema_file or "auto"
        language = language or "de"

        return context, version, schema_file, language, metadata


class ExportMarkdownResponse(BaseModel):
    """Response model for markdown export."""

    markdown: str
    schema_used: str


class SchemaInfo(BaseModel):
    """Information about a schema."""

    file: str
    profile_id: str
    label: LocalizedString
    groups: list[str]
    field_count: int


class ContextInfo(BaseModel):
    """Information about a context."""

    name: str
    display_name: str
    versions: list[str]
    default_version: str


class SchemataInfoResponse(BaseModel):
    """Response with available schemata information."""

    contexts: list[ContextInfo]
    default_context: str


class ScreenshotMethod(str, Enum):
    """Screenshot capture method."""

    PAGESHOT = "pageshot"  # External PageShot API (fast, free, no key)
    PLAYWRIGHT = "playwright"  # Internal Playwright (privacy-safe, requires install)


class ScreenshotRequest(BaseModel):
    """Request model for standalone screenshot capture."""

    url: str = Field(description="Webpage URL to capture")
    method: ScreenshotMethod = Field(
        default=ScreenshotMethod.PAGESHOT,
        description="Capture method: 'pageshot' (external API, default) or 'playwright' (internal, privacy-safe)",
    )
    width: int = Field(
        default=800, ge=320, le=3840, description="Viewport width (320-3840)"
    )
    height: int = Field(
        default=500, ge=200, le=2160, description="Viewport height (200-2160)"
    )
    format: str = Field(
        default="png", description="Image format: 'png', 'jpeg', 'webp'"
    )
    full_page: bool = Field(default=False, description="Capture entire scrollable page")
    delay: int = Field(
        default=2000, ge=0, le=10000, description="Wait before capture in ms (0-10000)"
    )
    # Optional: upload directly to a node
    node_id: Optional[str] = Field(
        default=None,
        description="If provided, upload screenshot as preview to this edu-sharing node. Must be a node UUID.",
    )
    _check_node_id = field_validator("node_id")(validate_node_id)
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://klexikon.zum.de/wiki/Erde",
                    "method": "pageshot",
                    "width": 800,
                    "height": 500,
                    "format": "png",
                }
            ]
        }
    }


class ScreenshotResponse(BaseModel):
    """Response from screenshot capture."""

    success: bool
    method: str = Field(description="Method used: 'pageshot' or 'playwright'")
    url: str = Field(description="Captured URL")
    format: str = Field(description="Image format")
    mimetype: str = Field(description="MIME type (e.g. image/png)")
    width: int = Field(description="Viewport width")
    height: int = Field(description="Viewport height")
    size_bytes: int = Field(description="Image size in bytes")
    capture_time_ms: int = Field(description="Capture duration in ms")
    image_base64: Optional[str] = Field(
        default=None, description="Base64-encoded image (only in JSON response mode)"
    )
    # Preview upload result (if node_id was provided)
    preview_uploaded: Optional[bool] = Field(
        default=None, description="Whether preview was uploaded to node"
    )
    node_id: Optional[str] = Field(
        default=None, description="Node ID if preview was uploaded"
    )
    error: Optional[str] = None


class UploadRequest(BaseModel):
    """
    Request model for uploading metadata to WLO repository.

    Accepts the JSON output from /generate endpoint.
    """

    metadata: dict[str, Any] = Field(
        ...,
        description="Metadata dict from /generate endpoint (with contextName, schemaVersion, etc.)",
    )
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )
    check_duplicates: bool = Field(
        default=True, description="Check for duplicates by ccm:wwwurl before uploading"
    )
    start_workflow: bool = Field(
        default=True, description="Start review workflow after upload"
    )
    return_full_node: bool = Field(
        default=False,
        description="Read the node back after writing and return it as 'node_full' (complete edu-sharing node, same shape as GET /node/v1/nodes/-home-/{id}/metadata). Costs one extra repository call.",
    )
    source: Optional[str] = Field(
        default=None,
        description="Bezugsquelle / Publisher-Name. Wenn angegeben, wird ccm:oeh_publisher_combined mit diesem Wert überschrieben.",
    )
    # Collection options
    # Always a list, never a bare string: the other list parameters of this
    # endpoint (workflow_steps, workflow_receiver) take a list and nothing else,
    # and a field that silently accepts both makes the request format depend on
    # which parameter you happen to be filling in.
    collection_id: Optional[list[str]] = Field(
        default=None,
        description=(
            "Sammlung(en), in der/denen der hochgeladene Inhalt referenziert wird. "
            "Immer eine Liste — auch bei einer einzelnen Sammlung. Die Einträge "
            "sind IDs oder Sammlungs-URLs "
            "(z.B. '.../components/collections?id=<uuid>'). Sammlungen aus den "
            "Metadaten (virtual:collection_id_primary, ccm:collection_id) werden "
            "zusätzlich berücksichtigt."
        ),
    )

    # Two-step upload: create the node first (POST /node), fill it in later.
    # Without it every /upload creates its own node.
    node_id: Optional[str] = Field(
        default=None,
        description=(
            "Bestehender Node, in den geschrieben werden soll — z.B. die ID aus "
            "POST /node. Ohne Angabe wird ein neuer Node angelegt. Bei "
            "angegebener ID entfällt die Dublettenprüfung (der Node trägt die "
            "URL bereits) und der Node wird bei einem Fehler **nicht** verworfen."
        ),
    )
    _check_upload_node_id = field_validator("node_id")(validate_node_id)

    @field_validator("collection_id", mode="before")
    @classmethod
    def normalize_collection_id(cls, v: Any) -> Any:
        """Drop empty entries; a list that holds nothing usable counts as absent."""
        if not isinstance(v, list):
            # Anything else — including a bare ID — is left for the type check
            # to reject, so the caller gets told what shape was expected.
            return v
        cleaned = [str(x).strip() for x in v if x is not None and str(x).strip()]
        return cleaned or None

    # Workflow options
    workflow_steps: Optional[list[str]] = Field(
        default=None,
        description=(
            "Workflow-Status, die nach dem Upload der Reihe nach gesetzt werden. "
            "Standard: nur '200_tocheck' (Übergabe zur Prüfung durch Menschen). "
            "Beispiel für 'Qualität bestätigt': "
            "['200_tocheck', '140_ELEMENT_LEGALLY_APPROVED']. "
            f"Erlaubt: {', '.join(sorted(KNOWN_WORKFLOW_STATUS))}. "
            "Wirkt nur bei start_workflow=true."
        ),
    )
    workflow_comment: Optional[str] = Field(
        default=None,
        description="Kommentar, der bei jedem Workflow-Schritt protokolliert wird. Standard: 'Upload via Metadata Agent API'.",
    )
    workflow_receiver: Optional[list[str]] = Field(
        default=None,
        description=(
            "Authority-Namen, die bei jedem Workflow-Schritt benachrichtigt werden "
            "(z.B. ['GROUP_ORG_WLO-Uploadmanager']). Standard: die Uploadmanager-"
            "Gruppe für '200_tocheck', leer für alle anderen Status."
        ),
    )

    @field_validator("workflow_steps")
    @classmethod
    def validate_workflow_steps(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Reject unknown states — a typo must not end up in the repository."""
        if v is None:
            return None
        if not v:
            # Reads as "run no steps", but omitting it means "run the default",
            # which hands the node to the editorial queue — the opposite of what
            # was asked. start_workflow=false says it without the ambiguity.
            raise ValueError(
                "workflow_steps darf nicht leer sein. Für einen Upload ohne "
                "Workflow-Schritt start_workflow=false setzen."
            )
        unknown = [s for s in v if s not in KNOWN_WORKFLOW_STATUS]
        if unknown:
            raise ValueError(
                f"Unbekannte Workflow-Status: {', '.join(unknown)}. "
                f"Erlaubt: {', '.join(sorted(KNOWN_WORKFLOW_STATUS))}"
            )
        return v

    # Screenshot / Preview options
    preview_url: Optional[str] = Field(
        default=None,
        description="URL for preview screenshot. If provided, a screenshot is captured async and uploaded as node preview.",
    )
    screenshot_method: ScreenshotMethod = Field(
        default=ScreenshotMethod.PAGESHOT,
        description="Screenshot method: 'pageshot' (default) or 'playwright' (privacy-safe)",
    )

    @field_validator("screenshot_method", mode="before")
    @classmethod
    def sanitize_screenshot_method(cls, v: Any) -> str:
        """Convert empty string to default 'pageshot'."""
        if not v or (isinstance(v, str) and not v.strip()):
            return "pageshot"
        return v

    # Extended Data options
    write_extended_data: bool = Field(
        default=True,
        description="Write extended fields (ccm:oeh_extendedType, ccm:oeh_extendedData, ccm:oeh_extendedText) to node. Default: true.",
    )
    extended_text: Optional[str] = Field(
        default=None,
        description="Raw source text before extraction (user input, extracted page content, etc.). Written to ccm:oeh_extendedText.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metadata": {
                        "contextName": "default",
                        "schemaVersion": "1.8.1",
                        "metadataset": "event.json",
                        "cclom:title": "Example Event",
                        "cclom:general_description": "Description...",
                        "ccm:wwwurl": "https://example.com/event",
                    },
                    "check_duplicates": True,
                    "start_workflow": True,
                    "return_full_node": False,
                    "source": "Klexikon",
                    "preview_url": "https://example.com/event",
                    "screenshot_method": "pageshot",
                    "write_extended_data": True,
                    "extended_text": "Raw text content...",
                }
            ]
        }
    }


class UploadedNodeInfo(BaseModel):
    """Information about uploaded or existing node."""

    nodeId: str
    title: Optional[str] = None
    description: Optional[str] = None
    wwwurl: Optional[str] = None
    repositoryUrl: Optional[str] = None


class FieldUploadError(BaseModel):
    """Error info for a single field that failed during upload."""

    field_id: str
    error: str
    status_code: Optional[int] = None


class CollectionResult(BaseModel):
    """Result of referencing the node in a single collection."""

    collectionId: str
    success: bool
    error: Optional[str] = None


class WorkflowStepResult(BaseModel):
    """Result of a single workflow state transition."""

    status: str
    success: bool
    error: Optional[str] = None


class CreateNodeRequest(BaseModel):
    """
    Request for creating a node without writing metadata to it.

    The first half of an upload on its own: a caller who needs a node id before
    the metadata exists gets one here and hands it back to /upload later.
    """

    metadata: dict[str, Any] = Field(
        ...,
        description=(
            "Mindestens 'cclom:title'. Übernommen werden außerdem "
            "'cclom:general_description', 'cclom:general_keyword', 'ccm:wwwurl' "
            "und 'cclom:general_language' — genau die Felder, die der Upload "
            "beim Anlegen setzt. Alles andere wird ignoriert und gehört in den "
            "zweiten Schritt."
        ),
    )
    check_duplicates: bool = Field(
        default=False,
        description=(
            "Vor dem Anlegen nach 'ccm:wwwurl' suchen. Standardmäßig aus, weil "
            "die URL zu diesem Zeitpunkt oft noch nicht feststeht."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metadata": {
                        "cclom:title": "Bruchrechnung Klasse 6",
                        "ccm:wwwurl": "https://example.org/bruchrechnung",
                    },
                    "check_duplicates": False,
                }
            ]
        }
    }


class CreateNodeResponse(BaseModel):
    """Response from node creation."""

    success: bool
    duplicate: Optional[bool] = None
    node: Optional[UploadedNodeInfo] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    """Response from repository upload."""

    success: bool
    duplicate: Optional[bool] = None
    node: Optional[UploadedNodeInfo] = None
    node_full: Optional[dict[str, Any]] = Field(
        default=None,
        description="Complete edu-sharing node as returned by the repository (same shape as the 'node' object of GET /node/v1/nodes/-home-/{id}/metadata). Only present when 'return_full_node' was requested and the read succeeded.",
    )
    error: Optional[str] = None
    step: Optional[str] = None
    fields_written: Optional[int] = None
    fields_skipped: Optional[int] = None
    node_created: Optional[bool] = Field(
        default=None,
        description=(
            "true, wenn dieser Aufruf den Node angelegt hat; false, wenn er über "
            "'node_id' übergeben wurde. Beide Fälle antworten mit 200 und "
            "derselben nodeId — sonst unterscheidet sie nichts."
        ),
    )
    schema_used: Optional[str] = Field(
        default=None,
        description=(
            "Typschema, gegen das geschrieben wurde (aus 'metadataset'). "
            "null bedeutet: nur core.json galt — wurde kein metadataset "
            "mitgeschickt, fallen typspezifische Felder weg."
        ),
    )
    repo_fields_available: Optional[int] = Field(
        default=None,
        description=(
            "Anzahl der Felder, die dieses Schema überhaupt ins Repository "
            "schreiben darf. Deutlich weniger als erwartet heißt: falsches "
            "oder fehlendes 'metadataset'."
        ),
    )
    field_errors: Optional[list[FieldUploadError]] = None
    preview: Optional[dict[str, Any]] = Field(
        default=None,
        description="Preview screenshot status: {success, method, capture_time_ms, size_bytes} or {success: false, error}",
    )
    collections: Optional[list[CollectionResult]] = Field(
        default=None,
        description="Ergebnis pro Sammlung, in der der Node referenziert wurde. Nur vorhanden, wenn Sammlungen angegeben waren.",
    )
    workflow: Optional[list[WorkflowStepResult]] = Field(
        default=None,
        description="Ergebnis pro Workflow-Schritt, in der ausgeführten Reihenfolge. Nur vorhanden, wenn start_workflow=true war.",
    )
    discarded_node: Optional[str] = Field(
        default=None,
        description="ID des unvollständigen Nodes, der nach einem Abbruch zurückgenommen wurde (Papierkorb, wiederherstellbar). Nur nach einem fehlgeschlagenen Upload gesetzt.",
    )


class WorkflowRequest(BaseModel):
    """Request for advancing an existing node through the review workflow."""

    steps: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Workflow-Status, die der Reihe nach gesetzt werden. Jeder Schritt "
            "erzeugt einen eigenen Eintrag in der Workflow-Historie des Nodes — "
            "so bleibt nachvollziehbar, wer welchen Status gesetzt hat. "
            f"Erlaubt: {', '.join(sorted(KNOWN_WORKFLOW_STATUS))}."
        ),
    )
    comment: Optional[str] = Field(
        default=None,
        description="Kommentar, der bei jedem Schritt protokolliert wird. Standard: 'Upload via Metadata Agent API'.",
    )
    receiver: Optional[list[str]] = Field(
        default=None,
        description=(
            "Authority-Namen, die benachrichtigt werden (z.B. ['GROUP_ORG_WLO-Uploadmanager']). "
            "Standard: die Uploadmanager-Gruppe für '200_tocheck', leer für alle anderen Status."
        ),
    )

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, v: Any) -> Any:
        """Accept a single status string as well as a list."""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: list[str]) -> list[str]:
        """Reject unknown states — a typo must not end up in the repository."""
        unknown = [s for s in v if s not in KNOWN_WORKFLOW_STATUS]
        if unknown:
            raise ValueError(
                f"Unbekannte Workflow-Status: {', '.join(unknown)}. "
                f"Erlaubt: {', '.join(sorted(KNOWN_WORKFLOW_STATUS))}"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "steps": ["140_ELEMENT_LEGALLY_APPROVED"],
                    "comment": "",
                }
            ]
        }
    }


class WorkflowResponse(BaseModel):
    """Response after running workflow steps on a node."""

    success: bool
    nodeId: str
    steps: Optional[list[WorkflowStepResult]] = Field(
        default=None,
        description="Ergebnis pro Schritt, in der ausgeführten Reihenfolge",
    )
    current_status: Optional[str] = Field(
        default=None,
        description="ccm:wf_status des Nodes nach den Schritten (zurückgelesen aus dem Repository)",
    )
    history: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Workflow-Historie des Nodes — enthält pro Eintrag u.a. Status, Kommentar, Zeitpunkt und den ausführenden Nutzer.",
    )
    repositoryUrl: Optional[str] = None
    error: Optional[str] = None


class FieldDiff(BaseModel):
    """Diff info for a single metadata field."""

    field_id: str
    status: (
        str  # "match", "mismatch", "missing_in_repo", "extra_in_repo", "not_written"
    )
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    resolution: Optional[str] = Field(
        default=None,
        description=(
            "`resolved`, `unresolved` oder null. Unabhängig von `status`: ein "
            "Feld kann exakt den gesendeten Wert tragen (`match`) und trotzdem "
            "auf nichts auflösen. null heißt: nichts aufzulösen (Freitext) oder "
            "nicht geprüft."
        ),
    )


class VerifyRequest(BaseModel):
    """Request for verifying uploaded metadata against repository."""

    expected_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Expected metadata (e.g. output from /generate). If provided, a SOLL/IST diff is computed.",
    )
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "expected_metadata": {
                        "cclom:title": "Example Event",
                        "cclom:general_description": "Description...",
                        "ccm:wwwurl": "https://example.com/event",
                        "ccm:taxonid": "http://w3id.org/openeduhub/vocabs/discipline/12002",
                    },
                }
            ]
        }
    }


class VerifyResponse(BaseModel):
    """Response from upload verification."""

    success: bool
    node_id: str
    actual_metadata: dict[str, Any] = Field(
        description="Flat metadata as read from the repository"
    )
    unresolved: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description=(
            "Werte, die im Feld stehen, die das Repository aber nicht als Wert "
            "liest — leeres `_DISPLAYNAME` bzw. fehlendes `virtual:licenseurl`. "
            "Ohne `expected_metadata` ermittelt: ein Feld kann exakt das "
            "enthalten, was gesendet wurde, und trotzdem auf nichts auflösen. "
            "Leere Liste = alles löst auf."
        ),
    )
    diff: Optional[list[FieldDiff]] = Field(
        default=None,
        description="Field-level diff (only when expected_metadata is provided)",
    )
    summary: Optional[dict[str, int]] = Field(
        default=None,
        description="Diff summary: match, mismatch, missing_in_repo, extra_in_repo, not_written counts",
    )
    error: Optional[str] = None


class DetectContentTypeRequest(BaseModel):
    """Request model for content type detection."""

    # Input source selection
    input_source: InputSource = Field(
        default=InputSource.TEXT,
        description="Input source: 'text' (direct input), 'url' (fetch via crawler), 'node_id' (fetch from repository), 'node_url' (repository + crawler fallback)",
    )

    # Text input (required for input_source='text')
    text: Optional[str] = Field(
        default=None,
        description="Input text to analyze. Required when input_source='text'.",
    )

    # URL input (required for input_source='url' or 'node_url')
    source_url: Optional[str] = Field(
        default=None,
        description="URL to fetch text from via text extraction API. Required when input_source='url' or 'node_url'.",
    )
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.BROWSER,
        description="Text extraction method: 'simple' (fast, basic HTML parsing) or 'browser' (full browser rendering, slower but more complete)",
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Output format for text extraction: 'markdown' (default), 'txt' (plain text), 'html' (raw HTML)",
    )

    # NodeID input (required for input_source='node_id' or 'node_url')
    node_id: Optional[str] = Field(
        default=None,
        description="Repository NodeID to fetch metadata and text from. Required when input_source='node_id' or 'node_url'. Must be a node UUID.",
    )
    _check_node_id = field_validator("node_id")(validate_node_id)
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )

    # Detection options
    context: str = Field(default="default", description="Schema context to use")
    version: str = Field(
        default="latest", description="Schema version to use ('latest' for newest)"
    )
    language: str = Field(default="de", description="Language for detection (de/en)")

    # LLM options (override defaults from .env)
    llm_provider: Optional[str] = Field(
        default=None,
        description="LLM provider to use. Options: 'openai' (native OpenAI API), 'b-api-openai' (OpenAI via B-API, default), 'b-api-academiccloud' (DeepSeek via B-API). If not set, uses METADATA_AGENT_LLM_PROVIDER from environment.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="LLM model to use. Without it the provider's configured default applies: 'deepseek-v4-flash' (b-api-academiccloud), 'gpt-5.6-luna' (b-api-openai), 'gpt-4o-mini' (openai).",
    )

    @field_validator("text", mode="before")
    @classmethod
    def sanitize_text_input(cls, v: Any) -> str:
        """Sanitize text input before validation."""
        if isinstance(v, str):
            return sanitize_text(v)
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input_source": "text",
                    "text": "Workshop 'KI in der Bildung' am 15. März 2025 in Berlin.",
                    "source_url": "",
                    "extraction_method": "browser",
                    "node_id": "",
                    "context": "default",
                    "version": "latest",
                    "language": "de",
                    "llm_provider": "b-api-academiccloud",
                    "llm_model": "deepseek-v4-flash",
                }
            ]
        }
    }


class ContentTypeInfo(BaseModel):
    """Information about a detected content type."""

    schema_file: str = Field(description="Schema file name (e.g., 'event.json')")
    uri: Optional[str] = Field(
        default=None,
        description="Vocab URI for this content type (e.g., 'http://w3id.org/openeduhub/vocabs/contentTypes/event')",
    )
    profile_id: Optional[str] = Field(
        default=None, description="Profile ID if available"
    )
    label: LocalizedString = Field(description="Localized label for the content type")
    confidence: Optional[str] = Field(
        default=None, description="Detection confidence (high/medium/low)"
    )


class DetectContentTypeResponse(BaseModel):
    """Response model for content type detection."""

    detected: ContentTypeInfo = Field(description="Detected content type")
    available: list[ContentTypeInfo] = Field(
        description="All available content types for this context/version"
    )
    context: str = Field(description="Schema context used")
    version: str = Field(description="Schema version used")
    processing_time_ms: int = Field(description="Processing time in milliseconds")


class ExtractFieldRequest(BaseModel):
    """Request model for single field extraction."""

    # Input source selection
    input_source: InputSource = Field(
        default=InputSource.TEXT,
        description="Input source: 'text' (direct input), 'url' (fetch via crawler), 'node_id' (fetch from repository), 'node_url' (repository + crawler fallback)",
    )

    # Text input (required for input_source='text')
    text: Optional[str] = Field(
        default=None,
        description="Input text to extract the field value from. Required when input_source='text'.",
    )

    # URL input (required for input_source='url' or 'node_url')
    source_url: Optional[str] = Field(
        default=None,
        description="URL to fetch text from via text extraction API. Required when input_source='url' or 'node_url'.",
    )
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.BROWSER,
        description="Text extraction method: 'simple' (fast, basic HTML parsing) or 'browser' (full browser rendering, slower but more complete)",
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Output format for text extraction: 'markdown' (default), 'txt' (plain text), 'html' (raw HTML)",
    )

    # NodeID input (required for input_source='node_id' or 'node_url')
    node_id: Optional[str] = Field(
        default=None,
        description="Repository NodeID to fetch metadata and text from. Required when input_source='node_id' or 'node_url'. Must be a node UUID.",
    )
    _check_node_id = field_validator("node_id")(validate_node_id)
    repository: str = Field(
        default="staging",
        deprecated=True,
        description="Deprecated — wird ignoriert. Die Repository-URL kommt aus METADATA_AGENT_REPOSITORY_URL. Wird aus Abwärtskompatibilität weiterhin akzeptiert.",
    )

    # Field-specific options
    context: str = Field(default="default", description="Schema context to use")
    version: str = Field(
        default="latest", description="Schema version to use ('latest' for newest)"
    )
    schema_file: str = Field(
        ...,
        description="Schema file containing the field (e.g., 'event.json', 'core.json') or a vocab URI (e.g., 'http://w3id.org/openeduhub/vocabs/contentTypes/event')",
    )
    field_id: str = Field(
        ...,
        description="Field ID to extract (e.g., 'ccm:oeh_event_begin', 'cclom:title')",
    )
    existing_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Existing metadata JSON with current field values (for context in update scenarios). For node_id/node_url sources, fetched metadata is merged.",
    )
    language: str = Field(default="de", description="Language for extraction (de/en)")
    normalize: bool = Field(
        default=True,
        description="Apply normalization to extracted value (dates, vocabularies, etc.)",
    )

    # LLM options (override defaults from .env)
    llm_provider: Optional[str] = Field(
        default=None,
        description="LLM provider to use. Options: 'openai' (native OpenAI API), 'b-api-openai' (OpenAI via B-API, default), 'b-api-academiccloud' (DeepSeek via B-API). If not set, uses METADATA_AGENT_LLM_PROVIDER from environment.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="LLM model to use. Without it the provider's configured default applies: 'deepseek-v4-flash' (b-api-academiccloud), 'gpt-5.6-luna' (b-api-openai), 'gpt-4o-mini' (openai).",
    )

    @field_validator("text", mode="before")
    @classmethod
    def sanitize_text_input(cls, v: Any) -> str:
        """Sanitize text input before validation."""
        if isinstance(v, str):
            return sanitize_text(v)
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "context": "default",
                    "version": "latest",
                    "schema_file": "event.json",
                    "field_id": "ccm:oeh_event_begin",
                    "text": "Workshop 'KI in der Bildung' am 15. März 2025 in Berlin.",
                    "language": "de",
                    "llm_model": "deepseek-v4-flash",
                    "llm_provider": "b-api-academiccloud",
                    "normalize": True,
                },
                {
                    "context": "default",
                    "version": "latest",
                    "schema_file": "event.json",
                    "field_id": "ccm:oeh_event_begin",
                    "text": "Der Workshop wurde auf den 20. März 2025 verschoben.",
                    "existing_metadata": {"ccm:oeh_event_begin": "2025-03-15T00:00"},
                    "language": "de",
                    "llm_model": "deepseek-v4-flash",
                    "llm_provider": "b-api-academiccloud",
                    "normalize": True,
                },
            ]
        }
    }


class ExtractFieldResponse(BaseModel):
    """Response model for single field extraction."""

    field_id: str = Field(description="Field ID that was extracted")
    field_label: Optional[str] = Field(
        default=None, description="Human-readable field label"
    )
    value: Any = Field(description="Extracted (and normalized) value")
    raw_value: Optional[Any] = Field(
        default=None, description="Value before normalization (if different)"
    )
    previous_value: Optional[Any] = Field(
        default=None, description="Previous value if provided"
    )
    changed: bool = Field(description="Whether the value changed from previous")
    normalized: bool = Field(description="Whether normalization was applied")
    context: str = Field(description="Schema context used")
    version: str = Field(description="Schema version used")
    schema_file: str = Field(description="Schema file used")
    processing: dict[str, Any] = Field(
        description="Processing info (provider, model, time)"
    )
