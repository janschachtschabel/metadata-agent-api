"""
What actually goes on the wire to the LLM.

The GPT-5 family renamed `max_tokens` to `max_completion_tokens` and accepts
only the default temperature. Measured against the B-API on 2026-08-11:

    max_tokens          → 400 "not supported with this model"
    temperature: 0.3    → 400 "Only the default (1) value is supported"
    verbosity / reasoning_effort accepted (both rejected by gpt-4.1-mini)

So the request body cannot be one shape for every model. Older models keep the
body they had — their behaviour must not change because a new default arrived.
"""

import pytest

from src.services.llm_service import LLMService, uses_reasoning_parameters


class _CapturingClient:
    """Captures the request body instead of sending it."""

    def __init__(self):
        self.body = None

    async def post(self, url, headers=None, json=None):
        self.body = json
        raise AssertionError("stop after capturing")


def _service(model, **overrides):
    service = LLMService(llm_provider="b-api-openai", llm_model=model)
    for key, value in overrides.items():
        setattr(service, key, value)
    service.http_client = _CapturingClient()
    return service


async def _body_of(service):
    with pytest.raises(AssertionError):
        await service._call_llm([{"role": "user", "content": "x"}])
    return service.http_client.body


@pytest.mark.parametrize(
    "model, expected",
    [
        ("gpt-5.6-luna", True),
        ("gpt-5.4-mini", True),
        ("o3-mini", True),
        ("gpt-4.1-mini", False),
        ("gpt-4o-mini", False),
        ("deepseek-r1", False),
    ],
)
def test_which_models_take_the_reasoning_parameters(model, expected):
    assert uses_reasoning_parameters(model) is expected


@pytest.mark.asyncio
async def test_a_reasoning_model_gets_max_completion_tokens_and_no_temperature():
    body = await _body_of(_service("gpt-5.6-luna"))

    assert body["max_completion_tokens"] == 2000
    assert "max_tokens" not in body
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_a_reasoning_model_carries_verbosity_and_effort():
    body = await _body_of(_service("gpt-5.6-luna"))

    assert body["verbosity"] == "low"
    assert body["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_the_classic_body_is_unchanged_for_older_models():
    """A new default must not rewrite the request for the models already in use."""
    body = await _body_of(_service("gpt-4.1-mini"))

    assert body["max_tokens"] == 2000
    assert body["temperature"] == 0.3
    assert "max_completion_tokens" not in body
    assert "verbosity" not in body
    assert "reasoning_effort" not in body


@pytest.mark.asyncio
async def test_verbosity_and_effort_can_be_switched_off():
    """Empty means: do not send the parameter at all."""
    service = _service("gpt-5.6-luna", verbosity="", reasoning_effort="")

    body = await _body_of(service)

    assert "verbosity" not in body
    assert "reasoning_effort" not in body
