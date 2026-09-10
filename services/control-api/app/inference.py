from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, Request, build_opener

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_CATALOG_BYTES = 4_000_000
MAX_COMPLETION_BYTES = 1_000_000
CATALOG_TTL_SECONDS = 3600
KEY_INFO_TTL_SECONDS = 900
MODEL_COOLDOWN_SECONDS = 900
# OpenRouter accepts one primary `model` plus at most three entries in the
# `models` fallback array. Keep this provider contract close to request
# construction so a larger discovery pool can never produce an invalid call.
MAX_MODELS_PER_REQUEST = 4


class OpenRouterError(RuntimeError):
    def __init__(
        self, message: str, *, code: str, failed_model: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.failed_model = failed_model


@dataclass(frozen=True, slots=True)
class OpenRouterPlan:
    models: tuple[str, ...]
    daily_limit: int
    free_tier: bool | None


@dataclass(frozen=True, slots=True)
class InferenceResult:
    content: str
    selected_model: str
    selected_route: str
    selected_provider: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: Decimal
    latency_ms: int
    fallback_attempt: int


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _nonnegative_integer(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError) as exc:
        raise OpenRouterError(
            "OpenRouter returned invalid usage accounting",
            code="OPENROUTER_USAGE_INVALID_RESPONSE",
        ) from exc


def is_zero_cost_text_model(model: dict[str, Any]) -> bool:
    model_id = model.get("id")
    if not isinstance(model_id, str) or not model_id.endswith(":free"):
        return False
    architecture = model.get("architecture") or {}
    output_modalities = architecture.get("output_modalities") or ["text"]
    input_modalities = architecture.get("input_modalities") or ["text"]
    if "text" not in output_modalities or "text" not in input_modalities:
        return False
    pricing = model.get("pricing")
    if not isinstance(pricing, dict):
        return False
    for field in ("prompt", "completion", "request"):
        price = _decimal(pricing.get(field, "0"))
        if price is None or price != 0:
            return False
    excluded_fragments = ("content-safety", "moderation", "embedding")
    return not any(fragment in model_id.casefold() for fragment in excluded_fragments)


def _finite_benchmark(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0 <= parsed <= 100 else None


def model_power_score(model: dict[str, Any]) -> float | None:
    """Return a bounded, transparent general-purpose quality score when present."""
    benchmarks = model.get("benchmarks")
    if not isinstance(benchmarks, dict):
        return None
    analysis = benchmarks.get("artificial_analysis")
    if not isinstance(analysis, dict):
        return None
    intelligence = _finite_benchmark(analysis.get("intelligence_index"))
    coding = _finite_benchmark(analysis.get("coding_index"))
    agentic = _finite_benchmark(analysis.get("agentic_index"))
    weighted = [
        (intelligence, 0.50),
        (coding, 0.30),
        (agentic, 0.20),
    ]
    if not any(value is not None for value, _ in weighted):
        return None
    # Missing dimensions are not evidence of strength. Treat them as zero
    # instead of letting a model with one reported metric dominate a model with
    # complete benchmark coverage.
    return sum((value or 0) * weight for value, weight in weighted)


def rank_free_models(
    catalog: list[dict[str, Any]],
    priority: tuple[str, ...],
    max_models: int,
    available_models: frozenset[str] | None = None,
) -> tuple[str, ...]:
    priority_index = {model_id: index for index, model_id in enumerate(priority)}

    def rank(model: dict[str, Any]) -> tuple[int, int, int, float, float, float, str]:
        model_id = str(model["id"])
        explicitly_ranked = model_id in priority_index
        explicit = priority_index.get(model_id, len(priority))
        parameters = set(model.get("supported_parameters") or [])
        capability_score = float(
            2 * ("structured_outputs" in parameters)
            + ("response_format" in parameters)
            + ("tools" in parameters)
            + 0.5 * ("reasoning" in parameters)
        )
        power = model_power_score(model)
        context = max(1, int(model.get("context_length") or 1))
        return (
            0 if explicitly_ranked else 1,
            explicit,
            0 if power is not None else 1,
            -(power or 0),
            -capability_score,
            -math.log2(context),
            model_id,
        )

    eligible = [
        model
        for model in catalog
        if is_zero_cost_text_model(model)
        and (
            available_models is None
            or str(model.get("id", "")) in available_models
        )
    ]
    eligible.sort(key=rank)
    return tuple(str(model["id"]) for model in eligible[:max_models])


def _safe_http_error_code(failure_code: str, status: int, payload: bytes) -> str:
    """Classify known provider failures without surfacing provider response data."""
    message = ""
    try:
        envelope = json.loads(payload)
        error = envelope.get("error") if isinstance(envelope, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"].casefold()
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    if status == 400 and "models" in message and "3 items or fewer" in message:
        return f"{failure_code}_MODEL_FALLBACK_LIMIT"
    if status == 400 and "data policy" in message:
        return f"{failure_code}_PRIVACY_UNAVAILABLE"
    if status == 429:
        return f"{failure_code}_RATE_LIMITED"
    if status in {401, 403}:
        return f"{failure_code}_AUTHENTICATION"
    return f"{failure_code}_{status}"


def _bounded_json_response(
    opener: OpenerDirector,
    request: Request,
    *,
    timeout: int,
    max_bytes: int,
    failure_code: str,
) -> dict[str, Any]:
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(max_bytes + 1)
    except HTTPError as exc:
        error_payload = exc.read(65_537)
        raise OpenRouterError(
            f"OpenRouter returned HTTP {exc.code}",
            code=_safe_http_error_code(failure_code, exc.code, error_payload),
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise OpenRouterError(
            "OpenRouter could not be reached", code=f"{failure_code}_UNAVAILABLE"
        ) from exc
    if len(payload) > max_bytes:
        raise OpenRouterError(
            "OpenRouter response exceeded the size limit",
            code=f"{failure_code}_TOO_LARGE",
        )
    try:
        envelope = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OpenRouterError(
            "OpenRouter returned invalid JSON", code=f"{failure_code}_INVALID_JSON"
        ) from exc
    if not isinstance(envelope, dict):
        raise OpenRouterError(
            "OpenRouter returned an invalid response object",
            code=f"{failure_code}_INVALID_RESPONSE",
        )
    return envelope


class OpenRouterFreeClient:
    def __init__(
        self,
        *,
        api_key: str,
        priority: tuple[str, ...],
        max_models: int,
        free_daily_allowance: int,
        daily_request_cap: int,
        data_collection: str,
        zdr: bool,
        opener: OpenerDirector | None = None,
    ) -> None:
        self._api_key = api_key
        self._priority = priority
        self._max_models = max_models
        self._free_daily_allowance = free_daily_allowance
        self._daily_request_cap = daily_request_cap
        self._data_collection = data_collection
        self._zdr = zdr
        self._opener = opener or build_opener()
        self._catalog: list[dict[str, Any]] = []
        self._catalog_loaded_at = 0.0
        self._zdr_models: frozenset[str] = frozenset()
        self._zdr_models_loaded_at = 0.0
        self._free_tier: bool | None = None
        self._key_info_loaded_at: float | None = None
        self._model_cooldowns: dict[str, float] = {}

    @property
    def privacy_mode(self) -> str:
        collection = "no_collection" if self._data_collection == "deny" else "collection_allowed"
        retention = "zdr" if self._zdr else "provider_retention_allowed"
        return f"{collection}+{retention}"

    def reject_model(self, model: str) -> None:
        """Temporarily demote a route whose syntactically valid output failed policy."""
        self._model_cooldowns[model] = time.monotonic() + MODEL_COOLDOWN_SECONDS

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": "https://github.com/ReaperXD67/autonomous-personal-agent",
            "X-Title": "Hermes Autonomous Personal Agent",
        }

    def _load_catalog(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._catalog and now - self._catalog_loaded_at < CATALOG_TTL_SECONDS:
            return self._catalog
        request = Request(  # noqa: S310
            f"{OPENROUTER_BASE_URL}/models?output_modalities=text",
            headers=self._headers(),
        )
        envelope = _bounded_json_response(
            self._opener,
            request,
            timeout=30,
            max_bytes=MAX_CATALOG_BYTES,
            failure_code="OPENROUTER_CATALOG",
        )
        data = envelope.get("data")
        if not isinstance(data, list):
            raise OpenRouterError(
                "OpenRouter catalog did not contain a model list",
                code="OPENROUTER_CATALOG_INVALID_RESPONSE",
            )
        self._catalog = [model for model in data if isinstance(model, dict)]
        self._catalog_loaded_at = now
        return self._catalog

    def _load_zdr_models(self) -> frozenset[str]:
        now = time.monotonic()
        if (
            self._zdr_models
            and now - self._zdr_models_loaded_at < CATALOG_TTL_SECONDS
        ):
            return self._zdr_models
        request = Request(  # noqa: S310
            f"{OPENROUTER_BASE_URL}/endpoints/zdr", headers=self._headers()
        )
        envelope = _bounded_json_response(
            self._opener,
            request,
            timeout=30,
            max_bytes=MAX_CATALOG_BYTES,
            failure_code="OPENROUTER_ZDR_ENDPOINTS",
        )
        data = envelope.get("data")
        if not isinstance(data, list):
            raise OpenRouterError(
                "OpenRouter ZDR endpoint catalog did not contain a list",
                code="OPENROUTER_ZDR_ENDPOINTS_INVALID_RESPONSE",
            )
        available: set[str] = set()
        for endpoint in data:
            if not isinstance(endpoint, dict):
                continue
            model_id = endpoint.get("model_id")
            status = endpoint.get("status")
            if isinstance(model_id, str) and model_id.endswith(":free") and (
                status is None or status == 0 or status == "0"
            ):
                available.add(model_id)
        self._zdr_models = frozenset(available)
        self._zdr_models_loaded_at = now
        return self._zdr_models

    def _load_key_tier(self) -> bool | None:
        now = time.monotonic()
        if (
            self._key_info_loaded_at is not None
            and now - self._key_info_loaded_at < KEY_INFO_TTL_SECONDS
        ):
            return self._free_tier
        request = Request(  # noqa: S310
            f"{OPENROUTER_BASE_URL}/key", headers=self._headers()
        )
        try:
            envelope = _bounded_json_response(
                self._opener,
                request,
                timeout=15,
                max_bytes=100_000,
                failure_code="OPENROUTER_KEY_INFO",
            )
            data = envelope.get("data")
            value = data.get("is_free_tier") if isinstance(data, dict) else None
            self._free_tier = value if isinstance(value, bool) else None
        except OpenRouterError:
            # Key metadata is advisory. A conservative local cap remains in force.
            self._free_tier = None
        self._key_info_loaded_at = now
        return self._free_tier

    def plan(self) -> OpenRouterPlan:
        available_models = self._load_zdr_models() if self._zdr else None
        ranked = rank_free_models(
            self._load_catalog(),
            self._priority,
            min(self._max_models, MAX_MODELS_PER_REQUEST),
            available_models,
        )
        now = time.monotonic()
        active = [model for model in ranked if self._model_cooldowns.get(model, 0) <= now]
        cooling = [model for model in ranked if self._model_cooldowns.get(model, 0) > now]
        models = tuple((active + cooling)[: self._max_models])
        if not models:
            raise OpenRouterError(
                "No verified zero-cost OpenRouter model is available",
                code="OPENROUTER_FREE_POOL_EMPTY",
            )
        free_tier = self._load_key_tier()
        # /key.is_free_tier only proves whether credits were ever purchased; it
        # cannot attest OpenRouter's USD 10 all-time threshold. The allowance is
        # therefore an explicit operator assertion, defaulting conservatively.
        upstream_headroom = {50: 40, 1000: 900}[self._free_daily_allowance]
        return OpenRouterPlan(
            models=models,
            daily_limit=min(self._daily_request_cap, upstream_headroom),
            free_tier=free_tier,
        )

    def complete(
        self, messages: list[dict[str, str]], plan: OpenRouterPlan
    ) -> InferenceResult:
        request_body: dict[str, Any] = {
            "model": plan.models[0],
            "models": list(plan.models[1:MAX_MODELS_PER_REQUEST]),
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 1800,
            "provider": {
                "allow_fallbacks": True,
                "require_parameters": True,
                "data_collection": self._data_collection,
                "zdr": self._zdr,
            },
        }
        catalog_by_id = {
            str(model.get("id")): model
            for model in self._catalog
            if isinstance(model.get("id"), str)
        }
        if all(
            "reasoning"
            in set(
                catalog_by_id.get(model, {}).get("supported_parameters") or []
            )
            for model in plan.models
        ):
            # Preserve output space on reasoning-first free models. OpenRouter
            # maps the portable effort value to each supported provider.
            request_body["reasoning"] = {"effort": "minimal", "exclude": True}
        body = json.dumps(request_body).encode("utf-8")
        headers = self._headers()
        headers["X-OpenRouter-Metadata"] = "enabled"
        request = Request(  # noqa: S310
            f"{OPENROUTER_BASE_URL}/chat/completions",
            data=body,
            method="POST",
            headers=headers,
        )
        started = time.monotonic()
        envelope = _bounded_json_response(
            self._opener,
            request,
            timeout=180,
            max_bytes=MAX_COMPLETION_BYTES,
            failure_code="OPENROUTER_COMPLETION",
        )
        latency_ms = round((time.monotonic() - started) * 1000)
        try:
            content = envelope["choices"][0]["message"]["content"]
            selected_model = envelope["model"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(
                "OpenRouter completion omitted required fields",
                code="OPENROUTER_COMPLETION_INVALID_RESPONSE",
            ) from exc
        selected_route = None
        if isinstance(selected_model, str):
            for route in plan.models:
                catalog_model = next(
                    (model for model in self._catalog if model.get("id") == route), None
                )
                aliases = {route}
                if catalog_model is not None and isinstance(
                    catalog_model.get("canonical_slug"), str
                ):
                    aliases.add(catalog_model["canonical_slug"])
                if selected_model in aliases:
                    selected_route = route
                    break
        if selected_route is None:
            raise OpenRouterError(
                "OpenRouter selected a model outside the verified free chain",
                code="OPENROUTER_MODEL_POLICY_VIOLATION",
            )
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError(
                "OpenRouter completion was empty",
                code="OPENROUTER_COMPLETION_EMPTY",
                failed_model=selected_route,
            )
        usage = envelope.get("usage") or {}
        if not isinstance(usage, dict):
            raise OpenRouterError(
                "OpenRouter returned invalid usage accounting",
                code="OPENROUTER_USAGE_INVALID_RESPONSE",
            )
        cost = _decimal(usage.get("cost"))
        if cost is None or cost != 0:
            raise OpenRouterError(
                "OpenRouter did not attest a zero-cost completion",
                code="OPENROUTER_COST_POLICY_VIOLATION",
            )
        prompt_tokens = _nonnegative_integer(usage.get("prompt_tokens"))
        completion_tokens = _nonnegative_integer(usage.get("completion_tokens"))
        total_tokens = _nonnegative_integer(usage.get("total_tokens"))
        selected_index = plan.models.index(selected_route)
        now = time.monotonic()
        for unavailable_model in plan.models[:selected_index]:
            self._model_cooldowns[unavailable_model] = now + MODEL_COOLDOWN_SECONDS
        self._model_cooldowns.pop(selected_route, None)
        metadata = envelope.get("openrouter_metadata") or {}
        selected_provider = None
        endpoints = metadata.get("endpoints") if isinstance(metadata, dict) else None
        available = endpoints.get("available") if isinstance(endpoints, dict) else None
        if isinstance(available, list):
            selected = next(
                (
                    endpoint
                    for endpoint in available
                    if isinstance(endpoint, dict) and endpoint.get("selected") is True
                ),
                None,
            )
            if selected is not None and isinstance(selected.get("provider"), str):
                selected_provider = selected["provider"][:120]
        attempt = metadata.get("attempt", 1) if isinstance(metadata, dict) else 1
        return InferenceResult(
            content=content,
            selected_model=selected_model,
            selected_route=selected_route,
            selected_provider=selected_provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            latency_ms=max(0, latency_ms),
            fallback_attempt=max(1, int(attempt or 1)),
        )
