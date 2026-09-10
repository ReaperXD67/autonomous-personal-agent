import json

import pytest

from app.inference import (
    MAX_MODELS_PER_REQUEST,
    OpenRouterError,
    OpenRouterFreeClient,
    model_power_score,
    rank_free_models,
)


def model(
    model_id: str,
    *,
    prompt: str = "0",
    completion: str = "0",
    request: str = "0",
    context: int = 128_000,
    intelligence: float | None = None,
    coding: float | None = None,
    agentic: float | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": model_id,
        "context_length": context,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "pricing": {"prompt": prompt, "completion": completion, "request": request},
        "supported_parameters": ["max_tokens", "temperature", "response_format"],
    }
    if any(value is not None for value in (intelligence, coding, agentic)):
        result["benchmarks"] = {
            "artificial_analysis": {
                "intelligence_index": intelligence,
                "coding_index": coding,
                "agentic_index": agentic,
            }
        }
    return result


def zdr_endpoints(*model_ids: str) -> dict[str, object]:
    return {
        "data": [
            {"model_id": model_id, "status": 0}
            for model_id in model_ids
        ]
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


def test_dynamic_rank_uses_complete_benchmarks_then_capabilities() -> None:
    catalog = [
        model("large-context:free", context=1_000_000),
        model("coding-only:free", coding=60),
        model("balanced:free", intelligence=30, coding=50, agentic=20),
    ]
    assert model_power_score(catalog[1]) == 18
    assert rank_free_models(catalog, (), 3) == (
        "balanced:free",
        "coding-only:free",
        "large-context:free",
    )


def test_dynamic_rank_intersects_live_zdr_availability() -> None:
    catalog = [
        model("strong-but-retained:free", intelligence=90),
        model("private-primary:free", intelligence=40),
        model("private-fallback:free", intelligence=30),
    ]
    ranked = rank_free_models(
        catalog,
        (),
        4,
        frozenset({"private-primary:free", "private-fallback:free"}),
    )
    assert ranked == ("private-primary:free", "private-fallback:free")


def test_openrouter_plan_caps_request_to_provider_fallback_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.inference.time.monotonic", lambda: 1.0)
    catalog = [
        model(f"provider/model-{index}:free", intelligence=50 - index)
        for index in range(6)
    ]
    model_ids = tuple(str(item["id"]) for item in catalog)
    opener = FakeOpener(
        zdr_endpoints(*model_ids),
        {"data": catalog},
        {"data": {"is_free_tier": True}},
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=(),
        max_models=8,
        free_daily_allowance=50,
        daily_request_cap=40,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    assert len(client.plan().models) == MAX_MODELS_PER_REQUEST


def test_openrouter_plan_keeps_one_private_route_before_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.inference.time.monotonic", lambda: 1.0)
    only_model = model("provider/only-private-route:free", intelligence=25)
    opener = FakeOpener(
        zdr_endpoints("provider/only-private-route:free"),
        {"data": [only_model]},
        {"data": {"is_free_tier": True}},
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=(),
        max_models=4,
        free_daily_allowance=50,
        daily_request_cap=40,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    assert client.plan().models == ("provider/only-private-route:free",)


def test_openrouter_plan_caps_free_tier_and_completion_attests_zero_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A freshly booted host can have monotonic uptime below the metadata TTL.
    monkeypatch.setattr("app.inference.time.monotonic", lambda: 1.0)
    catalog = [model("nvidia/nemotron:free"), model("z-ai/glm:free")]
    opener = FakeOpener(
        zdr_endpoints("nvidia/nemotron:free", "z-ai/glm:free"),
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
    completion_request = opener.requests[3][0]
    completion_body = json.loads(completion_request.data)
    assert len(completion_body["models"]) <= MAX_MODELS_PER_REQUEST - 1


def test_openrouter_refuses_a_nonzero_response_cost() -> None:
    catalog = [model("nvidia/nemotron:free"), model("z-ai/glm:free")]
    opener = FakeOpener(
        zdr_endpoints("nvidia/nemotron:free", "z-ai/glm:free"),
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
        zdr_endpoints("nvidia/nemotron:free", "z-ai/glm:free"),
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


def test_empty_completion_identifies_the_model_for_semantic_failover() -> None:
    catalog = [model("provider/primary:free"), model("provider/second:free")]
    opener = FakeOpener(
        zdr_endpoints("provider/primary:free", "provider/second:free"),
        {"data": catalog},
        {"data": {"is_free_tier": True}},
        {
            "model": "provider/primary:free",
            "choices": [{"message": {"content": ""}}],
            "usage": {"cost": 0},
        },
    )
    client = OpenRouterFreeClient(
        api_key="test-key",
        priority=(),
        max_models=4,
        free_daily_allowance=50,
        daily_request_cap=40,
        data_collection="deny",
        zdr=True,
        opener=opener,  # type: ignore[arg-type]
    )
    with pytest.raises(OpenRouterError, match="empty") as failure:
        client.complete([{"role": "user", "content": "test"}], client.plan())
    assert failure.value.failed_model == "provider/primary:free"
