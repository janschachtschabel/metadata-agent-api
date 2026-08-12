"""
The examples in /docs are what people copy.

A request body shown in the Swagger UI is the first thing anyone tries, so a
model name there is a recommendation whether it was meant as one or not. Two of
the names that stood in the examples had stopped working: `deepseek-r1` answers
`404 Model Not Found`, and `gpt-4.1-mini` rejects the `verbosity` and
`reasoning_effort` parameters this service now sends by default with `400`.

Nothing else notices when a default moves — the examples are free text.
"""

import json

import pytest

from src.config import Settings
from src.main import app

# Names that were the default once and no longer work. Keeping them out of the
# API surface is the point of this file.
RETIRED = ["gpt-4.1-mini", "deepseek-r1"]

PROVIDERS = ["b-api-openai", "b-api-academiccloud", "openai"]


@pytest.fixture(scope="module")
def openapi_text():
    return json.dumps(app.openapi(), ensure_ascii=False)


@pytest.mark.parametrize("model", RETIRED)
def test_no_retired_model_is_named_anywhere_in_the_api(openapi_text, model):
    assert model not in openapi_text


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_provider_default_is_named(openapi_text, provider):
    """
    Whoever reads the description should be able to see which model they get
    without opening the deployment's environment.
    """
    model = Settings().get_llm_config(provider_override=provider)["model"]

    assert model in openapi_text


def test_the_request_examples_name_a_provider_and_a_model_that_belong_together():
    """
    An example pairing b-api-academiccloud with an OpenAI model would 404 on the
    first try. Each example that names both has to be a pair that works.
    """
    spec = app.openapi()
    settings = Settings()
    allowed = {
        provider: settings.get_llm_config(provider_override=provider)["model"]
        for provider in PROVIDERS
    }

    methods = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
    seen = 0
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            # 'parameters' and 'summary' sit next to the methods and are not
            # operation objects.
            if method not in methods:
                continue
            content = (operation.get("requestBody") or {}).get("content", {})
            for media in content.values():
                for name, example in (media.get("examples") or {}).items():
                    # An example may be given as {"value": {...}} or as the
                    # value itself; only the former carries a request body.
                    if not isinstance(example, dict):
                        continue
                    value = example.get("value")
                    if not isinstance(value, dict):
                        continue
                    provider = value.get("llm_provider")
                    model = value.get("llm_model")
                    if not provider or not model:
                        continue
                    seen += 1
                    assert provider in allowed, f"{path} {name}: {provider}"
                    assert model == allowed[provider], (
                        f"{path} {name}: {provider} bekommt {model}, "
                        f"erwartet {allowed[provider]}"
                    )

    assert seen > 0, "keine Beispiele mit Provider und Modell gefunden"


def test_every_example_field_id_exists_in_the_schema_it_names():
    """
    'schema:startDate' with 'event.json' answered 404 Field not found: the field
    was renamed to ccm:oeh_event_begin in 2.0.0 and the example kept pointing at
    the old one. Copying it produced an error that reads like a broken request.
    """
    from src.utils.schema_loader import get_schema_fields

    spec = app.openapi()
    methods = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
    checked = 0

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in methods:
                continue
            content = (operation.get("requestBody") or {}).get("content", {})
            for media in content.values():
                for name, example in (media.get("examples") or {}).items():
                    value = example.get("value") if isinstance(example, dict) else None
                    if not isinstance(value, dict):
                        continue
                    field_id = value.get("field_id")
                    schema_file = value.get("schema_file")
                    if not field_id or not schema_file or schema_file == "auto":
                        continue

                    context = value.get("context", "default")
                    version = value.get("version", "latest")
                    known = {
                        f["id"]
                        for f in get_schema_fields(context, version, "core.json")
                    }
                    if schema_file != "core.json":
                        known |= {
                            f["id"]
                            for f in get_schema_fields(context, version, schema_file)
                        }

                    checked += 1
                    assert field_id in known, (
                        f"{path} {name}: '{field_id}' steht nicht in "
                        f"{schema_file} ({context}@{version})"
                    )

    assert checked > 0, "keine Beispiele mit field_id und schema_file gefunden"
