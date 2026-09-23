"""Validate catalog IDs and slot formats; never infer intent from client text."""
import json
import re
from datetime import date
from functools import lru_cache

from contracts.models import RouterContext, Scenario
from .prompting import DATASET
from .schemas import RouterPrediction


@lru_cache(maxsize=1)
def slot_definitions() -> dict:
    data = json.loads((DATASET / "slots.json").read_text(encoding="utf-8"))
    return {s["name"]: s for s in data["slots"]}


def validate_context(context: RouterContext, catalog: list[Scenario]) -> None:
    valid = {s.id for s in catalog}
    if not valid or len(valid) != len(catalog):
        raise ValueError("Catalog must be nonempty with unique ids")
    if len({t.topic_id for t in context.topics}) != len(context.topics):
        raise ValueError("Duplicate topic ids")
    if sum(t.status == "active" for t in context.topics) > 1:
        raise ValueError("Only one topic may be active")
    if any(t.scenario_id not in valid for t in context.topics):
        raise ValueError("Unknown topic scenario")
    if not context.text.strip() or len(context.text) > 4000:
        raise ValueError("Invalid utterance length")


def _valid_value(value: str, spec: dict) -> bool:
    if not value.strip():
        return False
    kind = spec["type"]
    if kind == "enum":
        return value in {str(v) for v in spec["values"]}
    if kind == "boolean":
        return value in {"true", "false"}
    if kind == "integer":
        return bool(re.fullmatch(r"\d+", value))
    if kind == "date":
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if kind == "list":
        try:
            items = json.loads(value)
        except (ValueError, TypeError):
            return False
        return isinstance(items, list) and bool(items) and all(
            isinstance(v, str) and re.fullmatch(spec.get("pattern", r".+"), v) for v in items)
    return "pattern" not in spec or bool(re.fullmatch(spec["pattern"], value))


def validate_prediction(prediction: RouterPrediction, catalog: list[Scenario]) -> None:
    by_id = {s.id: s for s in catalog}
    ids = [i.scenario_id for i in prediction.intents]
    if any(s not in by_id for s in ids + [a.scenario_id for a in prediction.alternatives]):
        raise ValueError("Prediction id outside catalog")
    if len(ids) > 1 and ({"SYS_UNCLEAR", "SYS_GOODBYE"} & set(ids)):
        raise ValueError("Unclear and goodbye must stand alone")
    if set(ids) & {a.scenario_id for a in prediction.alternatives}:
        raise ValueError("Alternatives must not repeat selected intents")
    definitions = slot_definitions()
    for intent in prediction.intents:
        scenario = by_id[intent.scenario_id]
        allowed = set(scenario.required_slots) | set(scenario.source.get("slots", {}).get("optional", []))
        for slot in intent.slots:
            if slot.name not in allowed or slot.name not in definitions:
                raise ValueError("Slot outside scenario definition")
            if not _valid_value(slot.value, definitions[slot.name]):
                raise ValueError("Slot value does not match official format")
