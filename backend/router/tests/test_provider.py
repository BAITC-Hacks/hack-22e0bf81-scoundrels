import asyncio
import json
from types import SimpleNamespace

import httpx2
import pytest
from openai import AsyncOpenAI

from backend.router.providers.openai_provider import OpenAIProvider, ProviderSettings, RouterProviderError
from .helpers import RecordingBudget, ScriptedClient, prediction, sdk_response, wire_response


def make(*responses, retries=0, budget=None):
    client = ScriptedClient(*responses)
    budget = budget or RecordingBudget()
    provider = OpenAIProvider(client=client, budget=budget,
                              settings=ProviderSettings(model="offline-model", max_retries=retries))
    return provider, client, budget


def test_strict_request_bounded_output_and_usage():
    provider, client, budget = make(sdk_response(prediction("SC33")))
    reply = asyncio.run(provider.predict([{"role": "user", "content": "test"}]))
    assert reply.prediction.intents[0].scenario_id == "SC33"
    assert client.options == {"max_retries": 0, "timeout": 20.0}
    request = client.calls[0]
    assert request["text"]["format"]["strict"] is True
    assert request["max_output_tokens"] == 1800 and request["store"] is False
    assert budget.estimates[0].input_tokens_upper_bound > 4096
    assert budget.settlements[0][1].cached_input_tokens == 10


@pytest.mark.parametrize(("override", "code"), [
    ({"status": "incomplete"}, "incomplete_response"),
    ({"output_text": "not json"}, "invalid_structured_output"),
    ({"output_text": ""}, "missing_structured_output"),
    ({"usage": None}, "missing_usage"),
    ({"output": [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]}, "provider_refusal"),
])
def test_failure_is_visible_and_still_accounted(override, code):
    provider, client, budget = make(sdk_response(prediction("SC33"), **override))
    with pytest.raises(RouterProviderError, match=code):
        asyncio.run(provider.predict([]))
    assert len(client.calls) == len(budget.settlements) == 1


def test_timeout_bounded_retry_accounts_unknown_charge():
    provider, client, budget = make(TimeoutError(), sdk_response(prediction("SC33")), retries=1)
    reply = asyncio.run(provider.predict([]))
    assert reply.attempts == len(client.calls) == len(budget.estimates) == 2
    assert budget.settlements[0][1] is None


def test_budget_denial_happens_before_network():
    provider, client, _ = make(budget=RecordingBudget(deny=True))
    with pytest.raises(RuntimeError, match="budget_exceeded"):
        asyncio.run(provider.predict([]))
    assert not client.calls


def test_no_secret_or_payload_in_public_error():
    provider, _, _ = make(RuntimeError("secret-key and private customer data"))
    with pytest.raises(RouterProviderError) as exc:
        asyncio.run(provider.predict([]))
    assert str(exc.value) == "provider_error"


def test_input_limit_denies_before_reservation():
    provider, client, budget = make()
    with pytest.raises(RouterProviderError, match="input_too_large"):
        asyncio.run(provider.predict([{"role": "user", "content": "x" * 160001}]))
    assert not client.calls and not budget.estimates


def test_model_must_be_explicit(monkeypatch):
    monkeypatch.delenv("OPENAI_ROUTER_MODEL", raising=False)
    with pytest.raises(ValueError, match="explicitly"):
        ProviderSettings.from_env()


def test_actual_openai_sdk_through_mock_transport():
    # No live key, DNS or socket: tests SDK request serialization and response parsing.
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=wire_response(prediction("SC33")))

    async def scenario():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            client = AsyncOpenAI(api_key="offline-test-key", http_client=http, max_retries=0)
            provider = OpenAIProvider(client=client, budget=RecordingBudget(),
                                      settings=ProviderSettings(model="offline-model"))
            reply = await provider.predict([{"role": "user", "content": "Где офис?"}])
            assert reply.prediction.intents[0].scenario_id == "SC33"
            assert reply.usage.input_tokens == 100
    asyncio.run(scenario())
    assert len(requests) == 1
    assert requests[0]["text"]["format"]["schema"]["additionalProperties"] is False


def test_sdk_rate_limit_has_at_most_one_explicit_retry():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(429, json={"error": {"message": "private upstream detail", "type": "rate_limit"}})

    async def scenario():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            budget = RecordingBudget()
            provider = OpenAIProvider(client=AsyncOpenAI(api_key="offline-test-key", http_client=http),
                                      budget=budget, settings=ProviderSettings(model="offline-model", max_retries=1))
            with pytest.raises(RouterProviderError, match="provider_http_error"):
                await provider.predict([])
            assert len(budget.estimates) == len(budget.settlements) == 2
    asyncio.run(scenario())
    assert len(requests) == 2


def test_wall_clock_timeout_and_cancellation_settle_unknown():
    class SlowClient(ScriptedClient):
        async def create(self, **kwargs):
            await asyncio.sleep(10)

    async def scenario():
        budget = RecordingBudget()
        provider = OpenAIProvider(client=SlowClient(), budget=budget,
                                  settings=ProviderSettings(model="offline-model", timeout_seconds=0.01))
        with pytest.raises(RouterProviderError, match="timeout"):
            await provider.predict([])
        assert budget.settlements == [("1", None)]
        pending = asyncio.create_task(provider.predict([]))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert budget.settlements[-1] == ("2", None)
    asyncio.run(scenario())
