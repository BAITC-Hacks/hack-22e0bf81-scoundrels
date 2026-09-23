"""Conservative single-process demo request reservation, never a provider invoice."""

import asyncio
from collections import defaultdict
from decimal import Decimal


RESERVATION_USD = {
    "router": Decimal("0.02"),
    "stt": Decimal("0.02"),
    "tts": Decimal("0.02"),
}


class BudgetExceeded(RuntimeError):
    """The configured local demo allowance has been exhausted."""


class DemoBudget:
    """Preflight cap for one process; charges reservations even on provider error.

    The fixed amounts deliberately exceed observed demo costs for short inputs,
    but are not an API-side billing limit. Use an OpenAI project spend limit too.
    """

    def __init__(self, *, run_usd: float, session_usd: float):
        self.run_limit = Decimal(str(run_usd))
        self.session_limit = Decimal(str(session_usd))
        if self.run_limit <= 0 or self.session_limit <= 0:
            raise ValueError("budget limits must be positive")
        self._run_reserved = Decimal("0")
        self._session_reserved: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        self._lock = asyncio.Lock()

    async def reserve(self, kind: str, *, session_id: str | None = None) -> None:
        amount = RESERVATION_USD[kind]
        async with self._lock:
            if self._run_reserved + amount > self.run_limit:
                raise BudgetExceeded("Run request allowance exhausted")
            if session_id is not None and self._session_reserved[session_id] + amount > self.session_limit:
                raise BudgetExceeded("Session request allowance exhausted")
            self._run_reserved += amount
            if session_id is not None:
                self._session_reserved[session_id] += amount

    @property
    def run_reserved_usd(self) -> float:
        return float(self._run_reserved)
