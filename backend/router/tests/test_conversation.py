import asyncio
from pathlib import Path

import pytest

from backend.router.catalog import load_catalog
from backend.router.conversation import TopicTransitionError, advance_conversation
from backend.router.service import ScenarioRouter
from contracts.models import Decision, RouteResult, RouterContext, Slot, Topic


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(ROOT / "case_2/voice_router_dataset/scenarios.json")


def result(
    scenario_ids: list[str],
    operation: str = "create",
    slots: dict[str, str] | None = None,
) -> RouteResult:
    primary = scenario_ids[0]
    if primary == "SC37":
        action = "transfer"
    elif primary == "SYS_UNCLEAR":
        action = "clarify"
    else:
        action = "route"
    return RouteResult(decision=Decision(
        action=action,
        selected_scenario_id=primary,
        scenario_ids=scenario_ids,
        rationale="test decision",
        certainty="high",
        topic_operation=operation,
        slots=[Slot(name=name, value=value) for name, value in (slots or {}).items()],
        clarification_question="Уточните вопрос" if action == "clarify" else None,
    ))


def advance(context: RouterContext, routed: RouteResult, catalog) -> RouterContext:
    updated = advance_conversation(context, routed, catalog)
    return context.model_copy(update={"topics": updated.topics})


def active(topics: list[Topic]) -> Topic | None:
    matches = [topic for topic in topics if topic.status == "active"]
    assert len(matches) <= 1
    return matches[0] if matches else None


def test_create_and_continue_merge_slots_without_mutating_input(catalog):
    initial = RouterContext(text="start", language="ru")
    first = advance_conversation(
        initial, result(["SC17"], slots={"phone": "+77010000007"}), catalog
    )
    assert initial.topics == []
    assert first.decision.topic_operation == "create"
    assert first.topics[0].status == "active"

    context = RouterContext(text="claim", language="ru", topics=first.topics)
    second = advance_conversation(
        context,
        result(["SC17"], operation="continue", slots={
            "phone": "+77019999999", "claim_number": "CL-500330",
        }),
        catalog,
    )
    values = {slot.name: slot.value for slot in second.topics[0].slots}
    assert second.decision.topic_operation == "continue"
    assert values == {"phone": "+77019999999", "claim_number": "CL-500330"}
    assert context.topics[0].slots[0].value == "+77010000007"


def test_switch_and_exact_resume_restore_parked_slots(catalog):
    context = RouterContext(text="x", language="ru", topics=[Topic(
        topic_id="claim", scenario_id="SC17", status="active",
        slots=[Slot(name="claim_number", value="CL-1")],
    )])
    switched = advance_conversation(context, result(["SC27"], operation="switch"), catalog)
    assert switched.decision.topic_operation == "switch"
    assert [(topic.scenario_id, topic.status) for topic in switched.topics] == [
        ("SC17", "parked"), ("SC27", "active"),
    ]

    resumed_context = context.model_copy(update={"topics": switched.topics})
    resumed = advance_conversation(
        resumed_context, result(["SC17"], operation="resume"), catalog
    )
    assert resumed.decision.topic_operation == "resume"
    assert active(resumed.topics).scenario_id == "SC17"
    assert active(resumed.topics).slots[0].value == "CL-1"
    assert next(topic for topic in resumed.topics if topic.scenario_id == "SC27").status == "parked"


def test_labeled_d03_flow_resumes_related_claim_thread_not_newer_queued_topic(catalog):
    context = RouterContext(text="status", language="ru")
    context = advance(context, result(["SC17"], slots={"phone": "+77010000007"}), catalog)
    context = advance(context, result(["SC27", "SC31"], operation="switch"), catalog)

    assert [(topic.scenario_id, topic.status) for topic in context.topics] == [
        ("SC17", "parked"), ("SC27", "active"), ("SC31", "parked"),
    ]
    resumed = advance_conversation(
        context,
        result(["SC18"], operation="resume", slots={"claim_number": "CL-500330"}),
        catalog,
    )
    current = active(resumed.topics)
    assert current.topic_id == "topic-1"
    assert current.scenario_id == "SC18"
    assert {slot.name: slot.value for slot in current.slots} == {
        "phone": "+77010000007", "claim_number": "CL-500330",
    }


def test_urgent_interruption_parks_then_reactivates_previous_topic(catalog):
    context = RouterContext(text="fraud", language="ru", topics=[Topic(
        topic_id="renewal", scenario_id="SC27", status="active",
    )])
    interrupted = advance_conversation(
        context, result(["SC38"], operation="switch", slots={"fraud_details": "sms"}), catalog
    )
    assert active(interrupted.topics).scenario_id == "SC38"
    assert interrupted.topics[0].status == "parked"

    resolved_context = context.model_copy(update={"topics": interrupted.topics})
    resolved = advance_conversation(
        resolved_context, result(["SC38"], operation="resolve"), catalog
    )
    assert next(topic for topic in resolved.topics if topic.scenario_id == "SC38").status == "resolved"
    assert active(resolved.topics).scenario_id == "SC27"


def test_multi_intent_queue_clarification_goodbye_and_transfer(catalog):
    multi = advance_conversation(
        RouterContext(text="two", language="mixed"),
        result(["SC21", "SC22"]),
        catalog,
    )
    assert [(topic.scenario_id, topic.status) for topic in multi.topics] == [
        ("SC21", "active"), ("SC22", "parked"),
    ]

    context = RouterContext(text="unclear", language="ru", topics=multi.topics)
    clarified = advance_conversation(context, result(["SYS_UNCLEAR"], operation="none"), catalog)
    assert clarified.decision.topic_operation == "none"
    assert clarified.topics == multi.topics

    transferred = advance_conversation(context, result(["SC37"], operation="switch"), catalog)
    assert transferred.decision.topic_operation == "resolve"
    assert active(transferred.topics) is None
    assert transferred.topics[0].status == "transferred"
    assert transferred.topics[1].status == "parked"

    goodbye_context = context.model_copy(update={"topics": multi.topics})
    goodbye = advance_conversation(
        goodbye_context, result(["SYS_GOODBYE"], operation="resolve"), catalog
    )
    assert {topic.status for topic in goodbye.topics} == {"resolved"}


def test_invalid_state_with_two_active_topics_fails_visibly(catalog):
    context = RouterContext(text="x", language="ru", topics=[
        Topic(topic_id="one", scenario_id="SC17", status="active"),
        Topic(topic_id="two", scenario_id="SC27", status="active"),
    ])
    with pytest.raises(TopicTransitionError, match="more than one active"):
        advance_conversation(context, result(["SC17"], operation="continue"), catalog)


def test_scenario_router_applies_reducer_to_provider_result(catalog):
    class FakeProvider:
        async def route(self, context, supplied_catalog):
            return result(["SC25"], slots={"phone": "+77010000008"})

    context = RouterContext(text="check", language="ru")
    routed = asyncio.run(ScenarioRouter(provider=FakeProvider()).route(context, catalog))
    assert routed.decision.topic_operation == "create"
    assert active(routed.topics).scenario_id == "SC25"
    assert context.topics == []
