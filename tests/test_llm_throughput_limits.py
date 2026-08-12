"""
Staying inside what the LLM gateway allows.

The b-api was measured on 2026-08-12: it permits exactly **two** requests in
flight and about **two per second**, and the budget hangs on the API key at the
gateway — not on the model — so both b-api providers draw from the same one. A
third parallel request is refused with 429 immediately, and the response carries
no `retry-after`, so there is nothing to read the wait off. Overload makes it
worse rather than slower: at 3 req/s the effective throughput drops *below* what
2 req/s delivers.

That makes the limit a client-side obligation. Two properties have to hold, and
neither is visible in a single request:

1. Concurrency is bounded **across service instances**. `get_llm_service()`
   builds a fresh `LLMService` whenever a request overrides provider or model,
   so a per-instance semaphore would let two simultaneous API calls send four.
2. Request starts are **spaced**. A burst of two per second is fine; five
   without a pause empties the token bucket.
"""

import asyncio

import pytest

from src.config import Settings, get_settings
from src.services.llm_service import (
    LLMService,
    RateLimiter,
    reset_provider_gates,
)

# Kept before any monkeypatching so a stub for the rate limiter's sleep cannot
# also take away the probe's only way to yield to the event loop.
real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def _fresh_gates():
    """The gates are process-wide on purpose; tests must not inherit each other's."""
    reset_provider_gates()
    get_settings.cache_clear()
    yield
    reset_provider_gates()
    get_settings.cache_clear()


# ------------------------------------------------------------- rate limiting


class _RecordingSleep:
    """Records what was slept for without advancing the clock."""

    def __init__(self):
        self.delays = []

    async def __call__(self, delay):
        self.delays.append(delay)


@pytest.mark.asyncio
async def test_the_rate_limiter_spaces_consecutive_starts(monkeypatch):
    """Four calls at two per second are handed slots 0.5s apart."""
    sleeper = _RecordingSleep()
    monkeypatch.setattr(asyncio, "sleep", sleeper)
    limiter = RateLimiter(2.0)

    delays = [await limiter.acquire() for _ in range(4)]

    assert delays[0] == pytest.approx(0.0, abs=0.05)
    assert delays[1] == pytest.approx(0.5, abs=0.05)
    assert delays[2] == pytest.approx(1.0, abs=0.05)
    assert delays[3] == pytest.approx(1.5, abs=0.05)


@pytest.mark.asyncio
async def test_a_rate_of_zero_means_no_waiting(monkeypatch):
    """Native OpenAI grants far higher limits — the cap must be switchable off."""
    sleeper = _RecordingSleep()
    monkeypatch.setattr(asyncio, "sleep", sleeper)
    limiter = RateLimiter(0)

    delays = [await limiter.acquire() for _ in range(5)]

    assert delays == [0.0] * 5
    assert sleeper.delays == []


@pytest.mark.asyncio
async def test_the_limiter_does_not_hold_back_a_caller_that_arrives_late(monkeypatch):
    """A slot in the past is not a debt — an idle client starts immediately."""
    sleeper = _RecordingSleep()
    monkeypatch.setattr(asyncio, "sleep", sleeper)
    limiter = RateLimiter(2.0)

    await limiter.acquire()
    limiter._next_slot = asyncio.get_running_loop().time() - 60

    assert await limiter.acquire() == pytest.approx(0.0, abs=0.05)


# --------------------------------------------------------------- concurrency


class _ConcurrencyProbe:
    """Stands in for the HTTP client and records how many calls overlap."""

    def __init__(self):
        self.active = 0
        self.peak = 0
        self.calls = 0

    async def post(self, url, headers=None, json=None):
        self.active += 1
        self.calls += 1
        try:
            # Yielding is what lets the other tasks in — without it every call
            # would run to completion before the next started and the peak would
            # read 1 no matter what the limit is.
            for _ in range(3):
                await real_sleep(0)
            self.peak = max(self.peak, self.active)
            raise AssertionError("stop after counting")
        finally:
            self.active -= 1


def _service(probe, **overrides):
    service = LLMService(llm_provider="b-api-openai")
    service.http_client = probe
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


async def _fire(service, count):
    async def one():
        with pytest.raises(AssertionError):
            await service._call_llm([{"role": "user", "content": "x"}])

    await asyncio.gather(*(one() for _ in range(count)))


@pytest.mark.asyncio
async def test_no_more_requests_are_in_flight_than_the_gateway_allows(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _RecordingSleep())
    probe = _ConcurrencyProbe()

    await _fire(_service(probe), 8)

    assert probe.calls == 8
    assert probe.peak <= 2


@pytest.mark.asyncio
async def test_two_service_instances_share_one_budget(monkeypatch):
    """
    The limit sits on the API key at the gateway. A per-instance semaphore would
    let two concurrent API requests — each with its own service, which is what a
    model override produces — send four in parallel.
    """
    monkeypatch.setattr(asyncio, "sleep", _RecordingSleep())
    probe = _ConcurrencyProbe()
    first, second = _service(probe), _service(probe)

    await asyncio.gather(_fire(first, 4), _fire(second, 4))

    assert probe.calls == 8
    assert probe.peak <= 2


@pytest.mark.asyncio
async def test_both_b_api_providers_draw_from_the_same_budget(monkeypatch):
    """One key, one budget — the provider path behind it does not matter."""
    monkeypatch.setattr(asyncio, "sleep", _RecordingSleep())
    probe = _ConcurrencyProbe()
    openai_side = _service(probe)
    academic = LLMService(llm_provider="b-api-academiccloud")
    academic.http_client = probe

    await asyncio.gather(_fire(openai_side, 4), _fire(academic, 4))

    assert probe.peak <= 2


@pytest.mark.asyncio
async def test_a_higher_configured_limit_is_honoured(monkeypatch):
    """The measured value is a default, not a hard-coded truth."""
    monkeypatch.setenv("METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS", "5")
    monkeypatch.setattr(asyncio, "sleep", _RecordingSleep())
    probe = _ConcurrencyProbe()

    service = LLMService(llm_provider="b-api-openai")
    service.http_client = probe
    await _fire(service, 8)

    assert probe.peak <= 5
    assert probe.peak > 2


# ------------------------------------------------------- configured defaults


def _config(provider, **env):
    return Settings(**env).get_llm_config(provider_override=provider)


@pytest.mark.parametrize("provider", ["b-api-openai", "b-api-academiccloud"])
def test_the_b_api_defaults_match_what_the_gateway_permits(provider):
    config = _config(provider)

    assert config["max_concurrent_requests"] == 2
    assert config["requests_per_second"] == 2.0
    assert config["limit_group"] == "b-api"


def test_native_openai_is_not_capped_by_the_b_api_measurement():
    """Its limits are per account and far higher; its 429 says how long to wait."""
    config = _config("openai")

    assert config["requests_per_second"] == 0.0
    assert config["max_concurrent_requests"] > 2
    assert config["limit_group"] == "openai"


@pytest.mark.parametrize("provider", ["b-api-openai", "b-api-academiccloud", "openai"])
def test_both_limits_can_be_set_for_every_provider(provider):
    config = _config(
        provider,
        llm_max_concurrent_requests=3,
        llm_max_requests_per_second=1.5,
    )

    assert config["max_concurrent_requests"] == 3
    assert config["requests_per_second"] == 1.5


@pytest.mark.parametrize("provider", ["b-api-openai", "b-api-academiccloud", "openai"])
def test_a_rate_of_zero_switches_the_cap_off_rather_than_using_the_default(provider):
    config = _config(provider, llm_max_requests_per_second=0)

    assert config["requests_per_second"] == 0.0


# --------------------------------------------------- model and base url parity


@pytest.mark.parametrize(
    "provider, setting, model",
    [
        ("b-api-openai", "b_api_openai_model", "gpt-5.6-sol"),
        ("b-api-academiccloud", "b_api_academiccloud_model", "openai-gpt-oss-120b"),
        ("openai", "openai_model", "gpt-4o"),
    ],
)
def test_every_provider_takes_its_model_from_configuration(provider, setting, model):
    config = Settings(**{setting: model}).get_llm_config(provider_override=provider)

    assert config["model"] == model


@pytest.mark.parametrize("provider", ["b-api-openai", "b-api-academiccloud", "openai"])
def test_a_request_may_override_the_model_for_every_provider(provider):
    config = Settings().get_llm_config(
        provider_override=provider, model_override="ein-anderes-modell"
    )

    assert config["model"] == "ein-anderes-modell"


def test_the_academiccloud_default_is_a_model_the_gateway_serves():
    """
    'deepseek-r1' answered 404 Model Not Found — a default that cannot work is
    worse than none, because nothing about the failure names the setting.
    """
    assert Settings().b_api_academiccloud_model == "deepseek-v4-flash"


def test_the_default_provider_and_its_model_belong_together():
    """
    deepseek-v4-flash is an AcademicCloud model. Leaving the provider on
    b-api-openai while naming it the default model would 404 on the first call.
    """
    settings = Settings()

    assert settings.llm_provider == "b-api-academiccloud"
    assert settings.get_llm_config()["model"] == "deepseek-v4-flash"


@pytest.mark.parametrize(
    "provider, base",
    [
        ("openai", "https://my-gateway.example/v1"),
        ("b-api-openai", "https://b.example/api/v1/llm/openai"),
        ("b-api-academiccloud", "https://b.example/api/v1/llm/academiccloud"),
    ],
)
def test_every_provider_takes_its_base_url_from_configuration(provider, base):
    setting = {
        "openai": "openai_api_base",
        "b-api-openai": "b_api_openai_base",
        "b-api-academiccloud": "b_api_academiccloud_base",
    }[provider]

    config = Settings(**{setting: base}).get_llm_config(provider_override=provider)

    assert config["api_base"] == base


def test_a_trailing_slash_on_the_openai_base_url_does_not_double_up():
    """The call path appends '/chat/completions'."""
    config = Settings(openai_api_base="https://my-gateway.example/v1/").get_llm_config(
        provider_override="openai"
    )

    assert config["api_base"] == "https://my-gateway.example/v1"


# ----------------------------------------------------------------- temperature


def test_native_openai_follows_the_shared_temperature_by_default():
    """
    Setting METADATA_AGENT_LLM_TEMPERATURE and having exactly one of three
    providers ignore it is a trap, not a feature.
    """
    config = _config("openai", llm_temperature=0.9)

    assert config["temperature"] == 0.9


def test_the_openai_temperature_still_overrides_the_shared_one():
    """Kept working for existing .env files that set it."""
    config = _config("openai", llm_temperature=0.9, openai_temperature=0.1)

    assert config["temperature"] == 0.1
