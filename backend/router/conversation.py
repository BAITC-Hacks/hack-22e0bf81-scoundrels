"""Deterministic, session-local topic transitions for router decisions.

The platform owns persistence. This reducer copies RouterContext.topics and returns a
new RouteResult, so concurrent sessions never share mutable state.
"""
from contracts.models import Decision, RouteResult, RouterContext, Scenario, Slot, Topic


class TopicTransitionError(RuntimeError):
    """The supplied topic state is inconsistent or references an unknown scenario."""


def _merge_slots(existing: list[Slot], incoming: list[Slot]) -> list[Slot]:
    """Preserve slot order, replace changed values, then append newly learned slots."""
    merged = [slot.model_copy(deep=True) for slot in existing]
    positions = {slot.name: index for index, slot in enumerate(merged)}
    for slot in incoming:
        copied = slot.model_copy(deep=True)
        if slot.name in positions:
            merged[positions[slot.name]] = copied
        else:
            positions[slot.name] = len(merged)
            merged.append(copied)
    return merged


def _next_topic_id(topics: list[Topic]) -> str:
    existing = {topic.topic_id for topic in topics}
    number = 1
    while f"topic-{number}" in existing:
        number += 1
    return f"topic-{number}"


def _active_index(topics: list[Topic]) -> int | None:
    indexes = [index for index, topic in enumerate(topics) if topic.status == "active"]
    if len(indexes) > 1:
        raise TopicTransitionError("topic state contains more than one active topic")
    return indexes[0] if indexes else None


def _same_thread(first_id: str | None, second_id: str, by_id: dict[str, Scenario]) -> bool:
    if not first_id or first_id not in by_id or second_id not in by_id:
        return False
    first = by_id[first_id].source
    second = by_id[second_id].source
    return (
        first.get("domain") == second.get("domain")
        and first.get("category") == second.get("category")
    )


def _parked_resume_index(
    topics: list[Topic], scenario_id: str, by_id: dict[str, Scenario], allow_related: bool
) -> int | None:
    parked = [index for index, topic in enumerate(topics) if topic.status == "parked"]
    for index in reversed(parked):
        if topics[index].scenario_id == scenario_id:
            return index
    if allow_related:
        for index in reversed(parked):
            if _same_thread(topics[index].scenario_id, scenario_id, by_id):
                return index
        # Explicit resume falls back to the most recently parked topic (stack behavior).
        if parked:
            return parked[-1]
    return None


def _activate(
    topics: list[Topic], index: int, scenario_id: str, slots: list[Slot]
) -> None:
    topic = topics[index]
    topics[index] = topic.model_copy(update={
        "scenario_id": scenario_id,
        "status": "active",
        "slots": _merge_slots(topic.slots, slots),
    })


def _new_topic(
    topics: list[Topic], scenario_id: str, status: str, slots: list[Slot] | None = None
) -> int:
    topics.append(Topic(
        topic_id=_next_topic_id(topics),
        scenario_id=scenario_id,
        status=status,
        slots=[slot.model_copy(deep=True) for slot in (slots or [])],
    ))
    return len(topics) - 1


def _with_operation(decision: Decision, operation: str) -> Decision:
    return decision.model_copy(update={"topic_operation": operation})


def advance_conversation(
    context: RouterContext, result: RouteResult, catalog: list[Scenario]
) -> RouteResult:
    """Apply a validated decision to topic state without mutating the input context."""
    topics = [topic.model_copy(deep=True) for topic in context.topics]
    decision = result.decision
    by_id = {scenario.id: scenario for scenario in catalog}

    for topic in topics:
        if topic.scenario_id is not None and topic.scenario_id not in by_id:
            raise TopicTransitionError(
                f"topic {topic.topic_id!r} references unknown scenario {topic.scenario_id!r}"
            )
    active_index = _active_index(topics)
    selected = decision.scenario_ids
    business_ids = [scenario_id for scenario_id in selected if scenario_id.startswith("SC")]

    if "SYS_GOODBYE" in selected:
        changed = False
        for index, topic in enumerate(topics):
            if topic.status in {"active", "parked"}:
                topics[index] = topic.model_copy(update={"status": "resolved"})
                changed = True
        return RouteResult(
            decision=_with_operation(decision, "resolve" if changed else "none"), topics=topics
        )

    # Clarification and out-of-scope answers must not erase in-progress work.
    if not business_ids:
        return RouteResult(decision=_with_operation(decision, "none"), topics=topics)

    unknown = set(business_ids) - set(by_id)
    if unknown:
        raise TopicTransitionError(f"decision references unknown scenario ids: {sorted(unknown)}")

    primary = business_ids[0]
    slots = decision.slots

    if decision.action == "transfer":
        if active_index is None:
            _new_topic(topics, primary, "transferred", slots)
        else:
            current = topics[active_index]
            topics[active_index] = current.model_copy(update={
                "status": "transferred",
                "slots": _merge_slots(current.slots, slots),
            })
        return RouteResult(decision=_with_operation(decision, "resolve"), topics=topics)

    if decision.topic_operation == "resolve":
        target = active_index
        if target is None:
            target = _parked_resume_index(topics, primary, by_id, allow_related=False)
        if target is None:
            _new_topic(topics, primary, "resolved", slots)
        else:
            current = topics[target]
            topics[target] = current.model_copy(update={
                "scenario_id": primary,
                "status": "resolved",
                "slots": _merge_slots(current.slots, slots),
            })
        # Completing an interruption exposes the most recently parked topic again.
        for index in range(len(topics) - 1, -1, -1):
            if topics[index].status == "parked":
                topics[index] = topics[index].model_copy(update={"status": "active"})
                break
        return RouteResult(decision=_with_operation(decision, "resolve"), topics=topics)

    operation: str
    active_index = _active_index(topics)
    if active_index is not None and topics[active_index].scenario_id == primary:
        _activate(topics, active_index, primary, slots)
        operation = "continue"
    elif active_index is not None and decision.topic_operation == "continue":
        # One business thread may advance from status -> documents or quote -> purchase.
        _activate(topics, active_index, primary, slots)
        operation = "continue"
    else:
        resume_index = _parked_resume_index(
            topics,
            primary,
            by_id,
            allow_related=decision.topic_operation == "resume",
        )
        if resume_index is not None:
            if active_index is not None:
                topics[active_index] = topics[active_index].model_copy(update={"status": "parked"})
            _activate(topics, resume_index, primary, slots)
            operation = "resume"
        elif active_index is None:
            _new_topic(topics, primary, "active", slots)
            operation = "create"
        else:
            topics[active_index] = topics[active_index].model_copy(update={"status": "parked"})
            _new_topic(topics, primary, "active", slots)
            operation = "switch"

    # Multi-intent work is queued in model/mention order after the primary topic.
    open_ids = {
        topic.scenario_id for topic in topics if topic.status in {"active", "parked"}
    }
    for scenario_id in business_ids[1:]:
        if scenario_id not in open_ids:
            _new_topic(topics, scenario_id, "parked")
            open_ids.add(scenario_id)

    return RouteResult(decision=_with_operation(decision, operation), topics=topics)
