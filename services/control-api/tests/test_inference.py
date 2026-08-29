import json

import pytest

from app.inference import OpenRouterError, OpenRouterFreeClient, rank_free_models


def model(
    model_id: str,
    *,
    prompt: str = "0",
    completion: str = "0",
    request: str = "0",
    context: int = 128_000,
) -> dict[str, object]:
    return {
        "id": model_id,
        "context_length": context,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "pricing": {"prompt": prompt, "completion": completion, "request": request},
        "supported_parameters": ["max_tokens", "temperature", "response_format"],
    }


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.payload[:size]


class FakeOpener:
    def __init__(self, *payloads: dict[str, object]) -> None:
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request: object, timeout: int) -> FakeResponse:
        self.requests.append((request, timeout))
        return FakeResponse(self.payloads.pop(0))


def test_free_catalog_rejects_paid_and_non_attested_models() -> None:
    catalog = [
        model("paid/frontier", prompt="0"),
        model("nvidia/expensive:free", completion="0.0001"),
        model("nvidia/nemotron:free"),
        model("z-ai/glm:free", context=256_000),
    ]
    ranked = rank_free_models(
        catalog,
        ("z-ai/glm:free", "nvidia/nemotron:free"),
        8,
    )
    assert ranked == ("z-ai/glm:free", "nvidia/nemotron:free")


def test_openrouter_plan_caps_free_tier_and_completion_attests_zero_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A freshly booted host can have monotonic uptime below the metadata TTL.
    monkeypatch.setattr("app.inference.time.monotonic", lambda: 1.0)
    catalog = [model("nvidia/nemotron:free"), model("z-ai/glm:free")]
    opener = FakeOpener(
        {"data": catalog},
        {"data": {"is_free_tier": True}},
        {
            "model": "z-ai/glm:free",
            "choices": [{"message": {"content": "{\"ok\": true}"}}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "total_tokens": 16,
                "cost": 0,
            },
            "openrouter_metadata": {
                "attempt": 2,
                "endpoints": {
                    "available": [
                        {
                            "provider": "Example ZDR provider",
                            "model": "z-ai/glm:free",
                            "selected": True,
                        }
                    ]
                },
            },
        },
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=("nvidia/nemotron:free", "z-ai/glm:free"),
        max_models=8,
        free_daily_allowance=50,
        daily_request_cap=900,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    plan = client.plan()
    assert plan.daily_limit == 40
    assert plan.models == ("nvidia/nemotron:free", "z-ai/glm:free")
    result = client.complete([{"role": "user", "content": "test"}], plan)
    assert result.selected_model == "z-ai/glm:free"
    assert result.selected_provider == "Example ZDR provider"
    assert result.fallback_attempt == 2
    assert result.cost == 0
    assert client.plan().models[0] == "z-ai/glm:free"


def test_openrouter_refuses_a_nonzero_response_cost() -> None:
    catalog = [model("nvidia/nemotron:free"), model("z-ai/glm:free")]
    opener = FakeOpener(
        {"data": catalog},
        {"data": {"is_free_tier": False}},
        {
            "model": "nvidia/nemotron:free",
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"cost": "0.00001"},
        },
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=("nvidia/nemotron:free", "z-ai/glm:free"),
        max_models=8,
        free_daily_allowance=1000,
        daily_request_cap=900,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    plan = client.plan()
    assert plan.daily_limit == 900
    with pytest.raises(OpenRouterError, match="zero-cost"):
        client.complete([{"role": "user", "content": "test"}], plan)

    # A rejected, potentially billable response must not change the next route.
    assert client.plan().models[0] == "nvidia/nemotron:free"


def test_openrouter_refuses_invalid_usage_accounting() -> None:
    catalog = [model("nvidia/nemotron:free"), model("z-ai/glm:free")]
    opener = FakeOpener(
        {"data": catalog},
        {"data": {"is_free_tier": False}},
        {
            "model": "nvidia/nemotron:free",
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": "not-a-number", "cost": 0},
        },
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=("nvidia/nemotron:free", "z-ai/glm:free"),
        max_models=8,
        free_daily_allowance=50,
        daily_request_cap=900,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    with pytest.raises(OpenRouterError, match="usage accounting"):
        client.complete(
            [{"role": "user", "content": "test"}],
            client.plan(),
        )
