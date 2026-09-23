"""TODO owner 2: allowlisted mock actions with explicit confirmation + idempotency.

Confirmation binds to one action, current slots and session. Never treat LLM confidence
as authorization. Cancellation and topic change invalidate a pending confirmation.
"""
