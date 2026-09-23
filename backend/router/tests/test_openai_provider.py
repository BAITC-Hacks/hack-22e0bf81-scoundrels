import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.router.catalog import load_catalog
from backend.router.models import CompactRouterOutput, RouterModelOutput
from backend.router.providers.openai_provider import (
    OpenAIRouterProvider,
    RouterConfigurationError,
    RouterProviderError,
)
from contracts.models import RouterContext


ROOT = Path(__file__).resolve().parents[3]


def official_catalog():
    return load_catalog(ROOT / "case_2/voice_router_dataset/scenarios.json")


def output(**overrides):
    data = {
        "scenarios": [{"scenario_id": "SC30", "reason": "Списание без полиса"}],
        "alternatives": [{"scenario_id": "SC26", "reason": "Документы могли не прийти"}],
        "language": "ru",
        "language_components": ["ru"],
        "certainty": "high",
        "rationale": "Клиент сообщает о списании, после которого полис не оформлен.",
        "slots": [{"name": "payment_date", "value": "2026-09-30"}],
        "is_continuation": False,
        "topic_operation": "create",
        "clarification_question": None,
        "requires_confirmation": False,
    }
    return RouterModelOutput.model_validate(data | overrides)


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(parsed=None, status="completed", error=None, usage=None):
    response = SimpleNamespace(status=status, output_parsed=parsed, usage=usage)
    responses = FakeResponses(response, error)
    return SimpleNamespace(responses=responses), responses


def run(provider, text="Вчера оплатил, но полис не появился"):
    return asyncio.run(provider.route(
        RouterContext(text=text, language="ru"), official_catalog()
    ))


def test_provider_uses_responses_structured_output_without_storage():
    client, calls = fake_client(output(), usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    seen_usage = []
    provider = OpenAIRouterProvider(
        model="configured-model", client=client, timeout_seconds=3,
        max_output_tokens=500, prompt_cache_key="saqta-router-v1",
        usage_callback=seen_usage.append,
    )
    result = run(provider)
    call = calls.calls[0]
    assert call["model"] == "configured-model"
    assert call["text_format"] is RouterModelOutput
    assert call["store"] is False
    assert call["timeout"] == 3
    assert call["max_output_tokens"] == 500
    assert call["prompt_cache_key"] == "saqta-router-v1"
    assert "text" not in call  # Production behavior stays unchanged by default.
    assert "SC01" in call["instructions"]
    assert '"catalog"' not in call["input"]
    assert result.decision.scenario_ids == ["SC30"]
    assert result.decision.selected_scenario_id == "SC30"
    assert result.decision.slots[0].name == "payment_date"
    assert len(seen_usage) == 1


def test_optional_low_verbosity_retains_full_schema_and_reasoning():
    client, calls = fake_client(output())
    run(OpenAIRouterProvider(model="configured-model", client=client,
                            text_verbosity="low", reasoning_effort="low"))
    assert calls.calls[0]["text"] == {"verbosity": "low"}
    assert calls.calls[0]["text_format"] is RouterModelOutput
    assert calls.calls[0]["reasoning"] == {"effort": "low"}
    with pytest.raises(RouterConfigurationError, match="text_verbosity"):
        OpenAIRouterProvider(model="configured-model", client=client, text_verbosity="bad")


def test_urgent_scenario_is_deterministically_first():
    parsed = output(scenarios=[
        {"scenario_id": "SC29", "reason": "Обновить адрес"},
        {"scenario_id": "SC38", "reason": "Подозрительный звонок"},
    ])
    client, _ = fake_client(parsed)
    result = run(OpenAIRouterProvider(model="configured-model", client=client))
    assert result.decision.scenario_ids == ["SC38", "SC29"]
    assert result.decision.selected_scenario_id == "SC38"


def test_explicit_human_request_precedes_normal_carried_intent():
    parsed = output(scenarios=[
        {"scenario_id": "SC35", "reason": "Existing complaint"},
        {"scenario_id": "SC37", "reason": "User asks for a human"},
    ])
    client, _ = fake_client(parsed)
    result = run(OpenAIRouterProvider(model="configured-model", client=client))
    assert result.decision.scenario_ids == ["SC37", "SC35"]
    assert result.decision.action == "transfer"


def test_three_language_mix_is_preserved_in_detailed_result():
    parsed = output(language="mixed", language_components=["ru", "kk", "en"])
    client, _ = fake_client(parsed)
    detailed = asyncio.run(OpenAIRouterProvider(
        model="configured-model", client=client
    ).route_detailed(RouterContext(text="ru kk en", language="mixed"), official_catalog()))
    assert detailed.detected_language == "mixed"
    assert detailed.language_components == ("ru", "kk", "en")


def test_catalog_confirmation_policy_overrides_model_false():
    parsed = output(scenarios=[{"scenario_id": "SC28", "reason": "Расторгнуть полис"}])
    client, _ = fake_client(parsed)
    result = run(OpenAIRouterProvider(model="configured-model", client=client))
    assert result.decision.requires_confirmation is True


def test_unclear_maps_to_clarification():
    parsed = output(
        scenarios=[{"scenario_id": "SYS_UNCLEAR", "reason": "Недостаточно контекста"}],
        certainty="low",
        clarification_question="Вас интересует статус выплаты или её сумма?",
    )
    client, _ = fake_client(parsed)
    decision = run(OpenAIRouterProvider(model="configured-model", client=client)).decision
    assert decision.action == "clarify"
    assert decision.selected_scenario_id == "SYS_UNCLEAR"
    assert decision.clarification_question


@pytest.mark.parametrize("status,parsed", [("incomplete", output()), ("completed", None)])
def test_incomplete_or_unparsed_response_is_visible_failure(status, parsed):
    client, _ = fake_client(parsed, status=status)
    provider = OpenAIRouterProvider(model="configured-model", client=client)
    with pytest.raises(RouterProviderError):
        run(provider)


def test_network_failure_is_visible_and_keeps_cause():
    client, _ = fake_client(error=TimeoutError("secret transport detail"))
    provider = OpenAIRouterProvider(model="configured-model", client=client)
    with pytest.raises(RouterProviderError, match="request failed") as exc:
        run(provider)
    assert isinstance(exc.value.__cause__, TimeoutError)
    assert "secret transport detail" not in str(exc.value)


def test_unknown_model_id_is_rejected_before_contract_leak():
    parsed = output(scenarios=[{"scenario_id": "SC99", "reason": "invented"}])
    client, _ = fake_client(parsed)
    provider = OpenAIRouterProvider(model="configured-model", client=client)
    with pytest.raises(RouterProviderError, match="unknown scenario ids"):
        run(provider)


def test_model_must_be_explicitly_configured():
    client, _ = fake_client(output())
    with pytest.raises(RouterConfigurationError, match="OPENAI_ROUTER_MODEL"):
        OpenAIRouterProvider(model="", client=client)


def test_compact_schema_preserves_order_language_slots_and_catalog_confirmation():
    parsed = CompactRouterOutput(
        scenario_ids=["SC28", "SC38"], language="mixed", language_components=["kk", "ru"],
        topic_operation="switch", slots=[{"name": "policy_number", "value": "TEST-1"}],
        certainty="high", rationale="Расторжение и подозрительный звонок",
        alternatives=[], clarification_question=None,
    )
    client, calls = fake_client(parsed)
    result = run(OpenAIRouterProvider(model="configured-model", client=client, compact_output=True))
    assert calls.calls[0]["text_format"] is CompactRouterOutput
    assert result.decision.scenario_ids == ["SC38", "SC28"]
    assert result.decision.requires_confirmation is True
    assert result.decision.slots[0].value == "TEST-1"


def test_compact_schema_keeps_unclear_and_language_validation():
    from pydantic import ValidationError
    base = dict(scenario_ids=["SYS_UNCLEAR"], language="mixed", language_components=["kk", "ru"],
                topic_operation="none", slots=[], certainty="low", rationale="Нужен контекст")
    with pytest.raises(ValidationError):
        CompactRouterOutput(**base)
    with pytest.raises(ValidationError):
        CompactRouterOutput(**(base | {"language_components": ["ru"]}), clarification_question="Что случилось?")
