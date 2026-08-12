"""Application configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from functools import lru_cache
from typing import Any, Optional


# What the gateway behind a provider tolerates, as measured rather than promised.
#
# b-api (2026-08-12, staging): exactly two requests in flight, about two per
# second. The budget hangs on the API key at the gateway — not on the model — so
# both b-api providers draw from the same one, which is why they share a limit
# group. A third parallel request is refused with 429 at once and the response
# carries no `retry-after`, so a client cannot read the wait off; it has to stay
# under the limit instead. Pushing harder is counter-productive: at 3 req/s the
# effective throughput falls below what 2 req/s delivers.
#
# Native OpenAI grants far higher per-account limits and its 429 does say how
# long to wait, so no client-side rate cap is imposed by default.
PROVIDER_LIMITS: dict[str, dict[str, Any]] = {
    "b-api": {"max_concurrent_requests": 2, "requests_per_second": 2.0},
    "openai": {"max_concurrent_requests": 10, "requests_per_second": 0.0},
}

# provider name -> which budget it draws from
LIMIT_GROUPS = {
    "b-api-openai": "b-api",
    "b-api-academiccloud": "b-api",
    "openai": "openai",
}


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # API Settings
    app_name: str = "Metadata Agent API"
    app_version: str = "2.0.0"
    debug: bool = False

    # LLM Provider Selection
    # Options: 'openai', 'b-api-openai', 'b-api-academiccloud'
    llm_provider: str = "b-api-academiccloud"

    # OpenAI Configuration (native OpenAI API)
    #
    # openai_api_base points at any OpenAI-compatible endpoint, not only
    # api.openai.com — an Azure deployment, a self-hosted vLLM or a gateway all
    # work, as long as they serve /chat/completions and take a Bearer token.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # Unset means: follow llm_temperature, the same setting the b-api providers
    # read. Having exactly one of three providers ignore the shared temperature
    # is a trap; this keeps the separate knob for anyone who already sets it.
    openai_temperature: Optional[float] = None

    # B-API Configuration (shared key for both b-api providers)
    b_api_key: str = Field(default="", alias="B_API_KEY")

    # B-API Base URL (Staging/Prod — endpoint paths are derived automatically)
    # Staging: https://b-api.staging.openeduhub.net
    # Prod:    https://b-api.prod.openeduhub.net
    b_api_base_url: str = "https://b-api.staging.openeduhub.net"

    # B-API OpenAI (OpenAI-compatible endpoint via B-API)
    # Derived from b_api_base_url if left empty
    b_api_openai_base: str = ""
    b_api_openai_model: str = "gpt-5.6-luna"

    # B-API AcademicCloud (AcademicCloud endpoint via B-API)
    # Derived from b_api_base_url if left empty.
    #
    # 'deepseek-v4-flash' beat 'openai-gpt-oss-120b' on both axes over four runs
    # of the same extraction (2026-08-12): 46s against 68s, and 37 of 50 fields
    # against 30 — including the one expected field the other missed. Both got
    # the exactly checkable values right.
    #
    # An earlier default 'deepseek-r1' answered 404 Model Not Found. A default
    # that cannot work is worse than none, because nothing in the failure names
    # the setting.
    b_api_academiccloud_base: str = ""
    b_api_academiccloud_model: str = "deepseek-v4-flash"

    # General LLM Settings
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2000

    # Only sent to reasoning models (GPT-5 family, o-series); older models
    # reject both. Empty means: do not send the parameter at all.
    #
    # Measured against gpt-5.6-luna on 2026-08-11, five runs per level on event
    # texts. 'none' is roughly 40% faster (6.9-8.9s vs 9.6-15.3s) and costs half
    # the output tokens — but dropped ccm:oeh_event_begin in 2 of 5 runs and
    # once destabilised the content-type detection, while 'low' hit 8/9 expected
    # fields every time. A missing event date is not worth three seconds.
    # 'minimal' is rejected by the API; valid: none, low, medium, high.
    llm_verbosity: str = "low"
    llm_reasoning_effort: str = "low"
    llm_max_retries: int = 3
    llm_retry_delay: float = 1.0

    # How hard the gateway may be pushed. Unset means: use the measured default
    # for the provider (see PROVIDER_LIMITS). Both are enforced across the whole
    # process, not per request — the gateway counts them that way too.
    #   llm_max_concurrent_requests: requests allowed in flight at once
    #   llm_max_requests_per_second: 0 switches the rate cap off entirely
    llm_max_concurrent_requests: Optional[int] = None
    llm_max_requests_per_second: Optional[float] = None

    # Worker Settings
    # Fan-out width of the parallel field extraction. It is capped by
    # llm_max_concurrent_requests — asking for more workers than the gateway
    # allows in flight only queues them up.
    default_max_workers: int = 10
    request_timeout: int = 60

    # Default Schema Settings
    default_context: str = "default"
    default_version: str = "1.8.1"

    # Normalization Settings
    normalization_enabled: bool = True
    normalization_temperature: float = 0.1

    # Repository URL (for NodeID input source and upload)
    # Staging: https://repository.staging.openeduhub.net/edu-sharing/rest
    # Prod:    https://redaktion.openeduhub.net/edu-sharing/rest
    repository_url: str = "https://repository.staging.openeduhub.net/edu-sharing/rest"

    # Text Extraction API Settings (for URL input source)
    # Staging: https://text-extraction.staging.openeduhub.net
    # Prod:    https://text-extraction.prod.openeduhub.net
    text_extraction_api_url: str = "https://text-extraction.staging.openeduhub.net"
    text_extraction_default_method: str = "simple"  # 'simple' or 'browser'

    # WLO Repository Upload Credentials (for /upload endpoint)
    wlo_guest_username: str = Field(default="", alias="WLO_GUEST_USERNAME")
    wlo_guest_password: str = Field(default="", alias="WLO_GUEST_PASSWORD")

    # WLO Repository Inbox ID (where new upload nodes are created)
    wlo_inbox_id: str = "21144164-30c0-4c01-ae16-264452197063"

    # Screenshot Settings
    screenshot_method: str = (
        "pageshot"  # 'pageshot' (external) or 'playwright' (internal)
    )
    screenshot_width: int = 800
    screenshot_height: int = 500
    screenshot_format: str = "png"
    screenshot_block_ads: bool = True
    screenshot_full_page: bool = False
    screenshot_delay: int = 2000  # ms to wait before capture
    pageshot_api_url: str = "https://pageshot.site/v1/screenshot"

    # CORS Settings
    cors_origins: str = "*"  # Comma-separated origins, or '*' for all

    @field_validator(
        "openai_temperature",
        "llm_max_concurrent_requests",
        "llm_max_requests_per_second",
        mode="before",
    )
    @classmethod
    def empty_means_unset(cls, v: Any) -> Any:
        """
        An empty environment variable means 'not configured', not '0'.

        `METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=` in a .env file would
        otherwise fail validation and take the whole process down at import.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def normalize_and_derive(self) -> "Settings":
        """Strip trailing slashes from URLs and derive B-API endpoints."""
        # Strip trailing slashes from all URL settings
        self.b_api_base_url = self.b_api_base_url.rstrip("/")
        self.text_extraction_api_url = self.text_extraction_api_url.rstrip("/")
        self.repository_url = self.repository_url.rstrip("/")
        self.openai_api_base = self.openai_api_base.rstrip("/")
        self.pageshot_api_url = self.pageshot_api_url.rstrip("/")

        # Derive B-API endpoint paths from base URL
        if not self.b_api_openai_base:
            self.b_api_openai_base = f"{self.b_api_base_url}/api/v1/llm/openai"
        if not self.b_api_academiccloud_base:
            self.b_api_academiccloud_base = (
                f"{self.b_api_base_url}/api/v1/llm/academiccloud"
            )
        return self

    model_config = {
        "env_prefix": "METADATA_AGENT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,  # Allow both alias and field name
        "extra": "ignore",
    }

    def get_llm_config(
        self,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> dict:
        """
        Get LLM configuration based on selected provider.

        Args:
            provider_override: Override the default provider from .env
            model_override: Override the default model for the provider
        """
        provider = provider_override or self.llm_provider

        if provider == "b-api-openai":
            config = {
                "provider": "b-api-openai",
                "api_key": self.b_api_key,
                "api_base": self.b_api_openai_base,
                "model": model_override or self.b_api_openai_model,
                "temperature": self.llm_temperature,
                "requires_custom_header": True,  # X-API-KEY instead of Bearer
            }
        elif provider == "b-api-academiccloud":
            config = {
                "provider": "b-api-academiccloud",
                "api_key": self.b_api_key,
                "api_base": self.b_api_academiccloud_base,
                "model": model_override or self.b_api_academiccloud_model,
                "temperature": self.llm_temperature,
                "requires_custom_header": True,
            }
        else:  # openai (default)
            config = {
                "provider": "openai",
                "api_key": self.openai_api_key,
                "api_base": self.openai_api_base,
                "model": model_override or self.openai_model,
                "temperature": (
                    self.llm_temperature
                    if self.openai_temperature is None
                    else self.openai_temperature
                ),
                "requires_custom_header": False,
            }

        config.update(self.get_throughput_limits(config["provider"]))
        return config

    def get_throughput_limits(self, provider: str) -> dict:
        """
        How many requests this provider's gateway may be given, and how fast.

        The configured values win over the measured defaults; a rate of 0 means
        no cap and is deliberately distinguished from 'unset'.
        """
        group = LIMIT_GROUPS.get(provider, "openai")
        defaults = PROVIDER_LIMITS[group]

        concurrent = self.llm_max_concurrent_requests
        per_second = self.llm_max_requests_per_second

        return {
            "limit_group": group,
            "max_concurrent_requests": max(
                1,
                defaults["max_concurrent_requests"]
                if concurrent is None
                else concurrent,
            ),
            "requests_per_second": float(
                defaults["requests_per_second"] if per_second is None else per_second
            ),
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
