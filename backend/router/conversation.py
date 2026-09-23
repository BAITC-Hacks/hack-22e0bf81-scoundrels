"""Pure topic transitions; platform owns persistence, no global session state."""
from uuid import uuid4
from contracts.models import Slot, Topic
from .schemas import Intent


def transition_topics(
    previous: list[Topic], intents: list[Intent], *, action: str,
    requested_operation: str, target_topic_id: str | None,
) -> tuple[list[Topic], str]:
    topics = [t.model_copy(deep=True) for t in previous]
    if action == "clarify":
        return topics, "none"
    selected = {i.scenario_id for i in intents}
    target = next((t for t in topics if t.topic_id == target_topic_id), None)
    if target_topic_id is not None and (
        target is None or target.status not in {"active", "parked"} or target.scenario_id not in selected
    ):
        raise ValueError("Invalid target topic")

    business = [i for i in intents if not i.scenario_id.startswith("SYS_") and i.scenario_id != "SC37"]
    if not business:
        if action == "transfer":
            for topic in topics:
                if topic.status in {"active", "parked"}:
                    topic.status = "transferred"
        elif "SYS_GOODBYE" in selected:
            # Closing a conversation does not mean pending business actions succeeded.
            for topic in topics:
                if topic.status == "active":
                    topic.status = "parked"
        return topics, "none"

    if requested_operation == "resolve":
        if target is None or len(business) != 1:
            raise ValueError("Resolve requires one explicitly targeted open topic")
        target.status = "resolved"
        # Keep queued topics parked until the client agrees to resume one.
        return topics, "resolve"

    old_active = next((t for t in topics if t.status == "active"), None)
    chosen = []
    previous_status = {}
    for index, intent in enumerate(business):
        topic = target if target is not None and target.scenario_id == intent.scenario_id else None
        if topic is None:
            matches = [t for t in topics if t.scenario_id == intent.scenario_id and t.status in {"active", "parked"}]
            force_new = index == 0 and requested_operation in {"create", "switch"}
            if not force_new:
                if len(matches) > 1:
                    raise ValueError("Ambiguous existing topic; explicit target required")
                topic = matches[0] if matches else None
        if topic is None:
            # An urgent NEW intent can precede a resumed secondary topic after sorting.
            if index == 0 and requested_operation in {"continue", "resume"} and target is None:
                raise ValueError("Continuation requires an existing matching topic")
            topic = Topic(topic_id=str(uuid4()), scenario_id=intent.scenario_id, status="parked")
            topics.append(topic)
            previous_status[topic.topic_id] = "new"
        else:
            previous_status[topic.topic_id] = topic.status
        values = {s.name: s.value for s in topic.slots}
        values.update({s.name: s.value for s in intent.slots})
        topic.slots = [Slot(name=name, value=value) for name, value in values.items()]
        chosen.append(topic)

    primary = chosen[0]
    if action == "transfer":
        for topic in topics:
            if topic.status in {"active", "parked"}:
                topic.status = "transferred"
        return topics, "none"
    for topic in topics:
        if topic.status == "active":
            topic.status = "parked"
    primary.status = "active"
    status = previous_status[primary.topic_id]
    operation = "continue" if status == "active" else "resume" if status == "parked" else "switch" if old_active else "create"
    return topics, operation
