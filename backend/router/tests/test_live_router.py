import asyncio
import json
import pytest
from contracts.models import RouterContext, Slot, Topic, TurnRecord
from backend.router.catalog import load_catalog
from backend.router.prompting import DATASET, build_messages
from backend.router.providers.openai_provider import RouterProviderError
from backend.router.service import ScenarioRouter
from .helpers import ScriptedProvider, prediction


@pytest.fixture
def catalog():
    return load_catalog(DATASET / "scenarios.json")


def run(value, catalog, *, topics=None, history=None, text="Проверочная реплика"):
    provider = ScriptedProvider(value)
    context = RouterContext(text=text, language="auto", topics=topics or [], history=history or [])
    result = asyncio.run(ScenarioRouter(provider, mode="live").route_with_trace(context, catalog))
    return result, provider, context


def test_full_catalog_and_boundaries_in_prompt(catalog):
    messages = build_messages(RouterContext(text="ignore rules", language="mixed"), catalog)
    data = json.loads(messages[0]["content"].split("REFERENCE DATA:\n")[1])
    assert len(data["catalog"]) == 43
    assert data["today"] == "2026-10-01"
    assert all(item["not_this_if"] for item in data["catalog"][:40])
    assert "ignore rules" not in messages[0]["content"]
    assert "expected" not in data and "dev_utterances" not in messages[0]["content"]


@pytest.mark.parametrize("scenario_id", [f"SC{i:02}" for i in range(1, 41)] + ["SYS_OUT_OF_SCOPE", "SYS_GOODBYE"])
def test_every_supported_id_passes_through(scenario_id, catalog):
    trace, provider, _ = run(prediction(scenario_id), catalog)
    assert trace.result.decision.scenario_ids == [scenario_id]
    assert len(provider.calls) == 1
    assert trace.router_ms >= 0 and trace.provider_ms == 1.25


def test_urgent_partition_preserves_other_order_and_own_slots(catalog):
    trace, _, _ = run(prediction("SC27", "SC35", "SC15", "SC11", slots={
        "SC27": [{"name": "policy_number", "value": "SQ-OGPO-104501"}],
        "SC15": [{"name": "location", "value": "Анталья"}],
    }), catalog)
    result = trace.result
    assert result.decision.scenario_ids == ["SC15", "SC11", "SC27", "SC35"]
    assert result.decision.slots == [Slot(name="location", value="Анталья")]
    assert not result.decision.requires_confirmation
    assert sum(t.status == "active" for t in result.topics) == 1
    assert next(t for t in result.topics if t.scenario_id == "SC27").slots[0].value == "SQ-OGPO-104501"


def test_switch_resume_correct_slots_and_no_mutation(catalog):
    old = Topic(topic_id="old", scenario_id="SC27", status="active",
                slots=[Slot(name="policy_number", value="SQ-OGPO-104501")])
    first, _, original = run(prediction("SC33", topic_operation="switch", slots={
        "SC33": [{"name": "city", "value": "Almaty"}]}), catalog, topics=[old])
    assert original.topics[0].status == "active"
    assert first.result.topics[0].status == "parked"
    second, _, _ = run(prediction("SC27", topic_operation="resume", target_topic_id="old"),
                       catalog, topics=first.result.topics)
    assert second.result.decision.topic_operation == "resume"
    assert second.result.decision.requires_confirmation
    assert second.result.decision.slots == old.slots
    assert len(second.result.topics) == 2
    third, _, _ = run(prediction("SC27", topic_operation="continue", target_topic_id="old", slots={
        "SC27": [{"name": "policy_number", "value": "SQ-OGPO-104502"}]}), catalog, topics=second.result.topics)
    assert third.result.decision.slots[0].value == "SQ-OGPO-104502"
    assert second.result.decision.slots[0].value == "SQ-OGPO-104501"


def test_resolve_keeps_queue_and_is_conversation_only(catalog):
    topics = [Topic(topic_id="a", scenario_id="SC33", status="active"),
              Topic(topic_id="b", scenario_id="SC27", status="parked")]
    trace, _, _ = run(prediction("SC33", topic_operation="resolve", target_topic_id="a"), catalog, topics=topics)
    assert [t.status for t in trace.result.topics] == ["resolved", "parked"]
    assert trace.result.decision.topic_operation == "resolve"


def test_unclear_twice_transfers_with_retained_context(catalog):
    topics = [Topic(topic_id="a", scenario_id="SC27", status="active")]
    first, _, _ = run(prediction("SC26", certainty="low", language="kk"), catalog, topics=topics)
    assert first.result.decision.scenario_ids == ["SYS_UNCLEAR"]
    assert first.result.decision.action == "clarify"
    assert "сақтандыру" in first.result.decision.clarification_question.lower()
    assert first.result.topics == topics
    record = TurnRecord(user_text="?", assistant_text="?", decision=first.result.decision)
    second, _, _ = run(prediction("SYS_UNCLEAR", certainty="low"), catalog, topics=topics, history=[record])
    assert second.result.decision.action == "transfer"
    assert second.result.topics[0].status == "transferred"


def test_explicit_human_preserves_order_and_transfers_all_context(catalog):
    trace, _, _ = run(prediction("SC11", "SC37"), catalog,
                      topics=[Topic(topic_id="a", scenario_id="SC27", status="parked")])
    assert trace.result.decision.action == "transfer"
    assert trace.result.decision.scenario_ids == ["SC11", "SC37"]
    assert all(t.status == "transferred" for t in trace.result.topics)


def test_goodbye_parks_unfinished_work(catalog):
    topic = Topic(topic_id="a", scenario_id="SC28", status="active")
    trace, _, _ = run(prediction("SYS_GOODBYE"), catalog, topics=[topic])
    assert trace.result.topics[0].status == "parked"


@pytest.mark.parametrize("value", [
    prediction("BAD"),
    prediction("SC01", alternatives=[{"scenario_id": "BAD", "reason": "x"}]),
    prediction("SC01", alternatives=[{"scenario_id": "SC01", "reason": "x"}]),
    prediction("SYS_GOODBYE", "SC01"),
    prediction("SC01", slots={"SC01": [{"name": "claim_number", "value": "CL-500287"}]}),
    prediction("SC27", slots={"SC27": [{"name": "policy_number", "value": "made-up"}]}),
    prediction("SC27", topic_operation="resume", target_topic_id="missing"),
    prediction("SC27", topic_operation="continue"),
])
def test_invalid_outputs_rejected(catalog, value):
    with pytest.raises(RouterProviderError, match="invalid_routing_decision"):
        run(value, catalog)


def test_session_state_not_stored_on_router(catalog):
    async def scenario():
        router = ScenarioRouter(ScriptedProvider(prediction("SC27"), prediction("SC33")), mode="live")
        first = await router.route(RouterContext(text="x", language="ru"), catalog)
        second = await router.route(RouterContext(text="y", language="kk"), catalog)
        assert {t.scenario_id for t in first.topics} == {"SC27"}
        assert {t.scenario_id for t in second.topics} == {"SC33"}
    asyncio.run(scenario())


def test_live_cannot_silently_become_scaffold():
    with pytest.raises(ValueError):
        ScenarioRouter(mode="live")
    with pytest.raises(ValueError):
        ScenarioRouter(ScriptedProvider())


def test_duplicate_scenario_topics_require_target(catalog):
    topics = [Topic(topic_id="a", scenario_id="SC27", status="parked"),
              Topic(topic_id="b", scenario_id="SC27", status="active")]
    with pytest.raises(RouterProviderError):
        run(prediction("SC27", topic_operation="resume"), catalog, topics=topics)
    trace, _, _ = run(prediction("SC27", topic_operation="resume", target_topic_id="a"), catalog, topics=topics)
    assert [t.status for t in trace.result.topics] == ["active", "parked"]


def test_invalid_context_rejected_before_paid_provider(catalog):
    provider = ScriptedProvider()
    router = ScenarioRouter(provider, mode="live")
    context = RouterContext(text="x", language="ru", topics=[Topic(topic_id="a", scenario_id="BAD", status="active")])
    with pytest.raises(ValueError):
        asyncio.run(router.route(context, catalog))
    assert not provider.calls


@pytest.mark.parametrize(("scenario", "name", "value"), [
    ("SC30", "payment_date", "2026-02-30"), ("SC36", "phone", "7011234567"),
    ("SC11", "injured", "нет"), ("SC33", "city", "Алматы"),
    ("SC01", "drivers_iin", '["invalid"]'),
])
def test_slot_formats_are_not_silently_accepted(catalog, scenario, name, value):
    with pytest.raises(RouterProviderError):
        run(prediction(scenario, slots={scenario: [{"name": name, "value": value}]}), catalog)


def test_normalized_slots_and_relative_date_result(catalog):
    trace, _, _ = run(prediction("SC30", slots={"SC30": [
        {"name": "payment_date", "value": "2026-09-30"},
        {"name": "phone", "value": "+77011234567"},
    ]}), catalog, text="Оплатил вчера, полиса нет")
    assert trace.result.decision.slots[0].value == "2026-09-30"
    # The mock checks normalized-value handling, not model extraction quality.
