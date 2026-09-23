"""Load normalized fixtures or the original Saqta starter-kit catalog."""
import json
from pathlib import Path
from contracts.models import Scenario

def load_catalog(path: Path) -> list[Scenario]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        scenarios = [Scenario.model_validate(item) for item in raw]
    else:
        scenarios = [Scenario(
            id=item["scenario_id"], purpose=item["description"],
            boundaries=[f"{b['condition']} -> {b['use_instead']}" for b in item["not_this_if"]],
            required_slots=item["slots"]["required"], allowed_actions=item["actions"],
            examples_ru=item["examples"]["ru"], examples_kk=item["examples"]["kk"],
            priority=item["priority"], requires_identification=item["requires_identification"],
            requires_confirmation=item["requires_confirmation"], source=item,
        ) for item in raw["scenarios"]]
        scenarios.extend(Scenario(id=item["id"], purpose=item["description"], source=item)
                         for item in raw["system_intents"])
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Scenario ids must be unique")
    return scenarios

def validate_decision_ids(result, catalog: list[Scenario]) -> None:
    valid = {s.id for s in catalog}
    chosen = result.decision.selected_scenario_id
    ids = list(result.decision.scenario_ids) + [a.scenario_id for a in result.decision.alternatives]
    ids.extend(topic.scenario_id for topic in result.topics if topic.scenario_id is not None)
    if chosen is not None:
        ids.append(chosen)
    if any(scenario_id not in valid for scenario_id in ids):
        raise ValueError("Router returned an id outside the catalog")
