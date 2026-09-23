"""One structured Responses call; no network until predict(), no silent fallback."""
import asyncio
import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from openai import AsyncOpenAI, APIConnectionError, APIStatusError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.router.schemas import RouterPrediction


class RouterProviderError(RuntimeError):
    """Safe code only: never expose SDK bodies, input text or secrets to clients."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=20, gt=0, le=60)
    max_output_tokens: int = Field(default=1800, ge=256, le=8192)
    max_retries: int = Field(default=0, ge=0, le=1)
    max_input_bytes: int = Field(default=160000, ge=1024, le=500000)

    @classmethod
    def from_env(cls):
        model = os.environ.get("OPENAI_ROUTER_MODEL", "").strip()
        if not model:
            raise ValueError("OPENAI_ROUTER_MODEL must be explicitly configured")
        return cls(
            model=model,
            timeout_seconds=float(os.environ.get("ROUTER_TIMEOUT_SECONDS", "20")),
            max_output_tokens=int(os.environ.get("ROUTER_MAX_OUTPUT_TOKENS", "1800")),
            max_retries=int(os.environ.get("ROUTER_MAX_RETRIES", "0")),
        )


@dataclass(frozen=True)
class RequestEstimate:
    model: str
    input_tokens_upper_bound: int
    max_output_tokens: int


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


class BudgetGuard(Protocol):
    """Platform adapter, bound to session/run; must reserve atomically before I/O.

    settle(None) means UNKNOWN charge, never zero: retain the full reservation.
    Exceptions deny the call. Each retry requires a separate reservation.
    """

    async def authorize(self, estimate: RequestEstimate) -> str: ...
    async def settle(self, reservation: str, usage: TokenUsage | None) -> None: ...


@dataclass(frozen=True)
class ProviderReply:
    prediction: RouterPrediction
    usage: TokenUsage
    elapsed_ms: float
    attempts: int


def _usage(response) -> TokenUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    counts = (getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    if any(type(n) is not int or n < 0 for n in (*counts, cached)) or cached > counts[0]:
        return None
    return TokenUsage(*counts, cached)


class OpenAIProvider:
    def __init__(self, *, client, settings: ProviderSettings, budget: BudgetGuard):
        if budget is None:
            raise ValueError("An explicit budget guard is required")
        # Disable the SDK's own retry loop, including on injected clients.
        self.client = client.with_options(max_retries=0, timeout=settings.timeout_seconds)
        self.settings = settings
        self.budget = budget

    @classmethod
    def from_env(cls, *, budget: BudgetGuard):
        settings = ProviderSettings.from_env()
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise ValueError("OPENAI_API_KEY must be set locally")
        return cls(client=AsyncOpenAI(max_retries=0), settings=settings, budget=budget)

    async def aclose(self):
        await self.client.close()

    async def predict(self, messages: list[dict]) -> ProviderReply:
        started = perf_counter()
        payload = {
            "model": self.settings.model, "input": messages, "store": False,
            "max_output_tokens": self.settings.max_output_tokens,
            "text": {"format": {"type": "json_schema", "name": "router_prediction",
                                "strict": True, "schema": RouterPrediction.model_json_schema()}},
        }
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if size > self.settings.max_input_bytes:
            raise RouterProviderError("input_too_large")
        # UTF-8 byte count + framing allowance is deliberately conservative, not a tokenizer.
        estimate = RequestEstimate(self.settings.model, size + 4096, self.settings.max_output_tokens)
        for attempt in range(self.settings.max_retries + 1):
            reservation = await self.budget.authorize(estimate)
            usage = None
            error = None
            retryable = False
            response = None
            try:
                async with asyncio.timeout(self.settings.timeout_seconds):
                    response = await self.client.responses.create(**payload)
                usage = _usage(response)
            except (TimeoutError, APIConnectionError):
                error, retryable = "provider_timeout_or_connection", True
            except APIStatusError as exc:
                error = "provider_http_error"
                retryable = exc.status_code == 429 or exc.status_code >= 500
            except asyncio.CancelledError:
                raise
            except Exception:
                error = "provider_error"
            finally:
                # Account even for refusal, invalid JSON and ambiguous network failures.
                await asyncio.shield(self.budget.settle(reservation, usage))
            if error:
                if retryable and attempt < self.settings.max_retries:
                    await asyncio.sleep(0.2)
                    continue
                raise RouterProviderError(error) from None
            if getattr(response, "status", None) != "completed":
                raise RouterProviderError("incomplete_response")
            for item in getattr(response, "output", []):
                for content in getattr(item, "content", []):
                    if getattr(content, "type", None) == "refusal":
                        raise RouterProviderError("provider_refusal")
            raw = getattr(response, "output_text", "")
            if not isinstance(raw, str) or not raw.strip():
                raise RouterProviderError("missing_structured_output")
            try:
                prediction = RouterPrediction.model_validate_json(raw)
            except ValidationError:
                raise RouterProviderError("invalid_structured_output") from None
            if usage is None:
                raise RouterProviderError("missing_usage")
            return ProviderReply(prediction, usage, (perf_counter() - started) * 1000, attempt + 1)
        raise AssertionError("Unreachable retry state")
