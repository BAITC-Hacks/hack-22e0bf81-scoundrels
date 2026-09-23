"""Standalone eval spending cap. Production session budgets belong to platform."""
import asyncio
from decimal import Decimal
from backend.router.providers.openai_provider import RequestEstimate, TokenUsage


class EvalBudget:
    def __init__(self, *, max_usd: Decimal, input_rate: Decimal, output_rate: Decimal, max_calls: int):
        if any(not n.is_finite() or n <= 0 for n in (max_usd, input_rate, output_rate)) or max_calls < 1:
            raise ValueError("Positive finite rates, budget and call limit required")
        self.max_usd, self.input_rate, self.output_rate = max_usd, input_rate, output_rate
        self.max_calls = max_calls
        self.calls = 0
        self.charged_or_reserved = Decimal(0)
        self._pending = {}
        self._lock = asyncio.Lock()

    def _cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        # No cached-input discount: intentionally conservative.
        return (input_tokens*self.input_rate + output_tokens*self.output_rate) / Decimal(1000000)

    async def authorize(self, estimate: RequestEstimate) -> str:
        cost = self._cost(estimate.input_tokens_upper_bound, estimate.max_output_tokens)
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
                self.charged_or_reserved += self._cost(usage.input_tokens, usage.output_tokens) - reserved
            # Unknown charge remains fully reserved; never retry for free.
