"""Standalone eval spending cap. Production session budgets belong to platform."""
import asyncio
from decimal import Decimal
from backend.router.providers.openai_provider import RequestEstimate, TokenUsage


class EvalBudget:
    def __init__(self, *, max_usd: Decimal, input_rate: Decimal, cached_input_rate: Decimal,
                 cache_write_rate: Decimal, output_rate: Decimal, max_calls: int):
        rates = (max_usd, input_rate, cached_input_rate, cache_write_rate, output_rate)
        if any(not n.is_finite() or n <= 0 for n in rates) or max_calls < 1:
            raise ValueError("Positive finite rates, budget and call limit required")
        self.max_usd, self.input_rate = max_usd, input_rate
        self.cached_input_rate, self.cache_write_rate = cached_input_rate, cache_write_rate
        self.output_rate = output_rate
        self.max_calls = max_calls
        self.calls = 0
        self.charged_or_reserved = Decimal(0)
        self._pending = {}
        self._lock = asyncio.Lock()

    def _reserve_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        # Any uncached prefix may be billed as a cache write, whose rate can exceed input.
        input_rate = max(self.input_rate, self.cache_write_rate)
        return (input_tokens*input_rate + output_tokens*self.output_rate) / Decimal(1000000)

    def _usage_cost(self, usage: TokenUsage) -> Decimal:
        uncached = usage.input_tokens - usage.cached_input_tokens
        if uncached < 0:
            raise ValueError("cached input cannot exceed total input")
        # Usage does not expose cache-write tokens, so price all uncached input at the
        # higher of ordinary input and cache-write rates.
        uncached_rate = max(self.input_rate, self.cache_write_rate)
        return (uncached*uncached_rate + usage.cached_input_tokens*self.cached_input_rate
                + usage.output_tokens*self.output_rate) / Decimal(1000000)

    async def authorize(self, estimate: RequestEstimate) -> str:
        cost = self._reserve_cost(estimate.input_tokens_upper_bound, estimate.max_output_tokens)
        async with self._lock:
            if self.calls >= self.max_calls or self.charged_or_reserved + cost > self.max_usd:
                raise RuntimeError("eval_budget_exceeded")
            self.calls += 1
            key = str(self.calls)
            self._pending[key] = cost
            self.charged_or_reserved += cost
            return key

    async def settle(self, reservation: str, usage: TokenUsage | None) -> None:
        async with self._lock:
            reserved = self._pending.pop(reservation)
            if usage is not None:
                self.charged_or_reserved += self._usage_cost(usage) - reserved
            # Unknown charge remains fully reserved; never retry for free.
