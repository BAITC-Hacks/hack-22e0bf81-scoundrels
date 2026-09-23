"""Full-catalog prompt, without dev labels or lexical candidate filtering."""
import json
from pathlib import Path
from contracts.models import RouterContext, Scenario

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "case_2" / "voice_router_dataset"


def build_messages(context: RouterContext, catalog: list[Scenario]) -> list[dict]:
    if not catalog or len({s.id for s in catalog}) != len(catalog):
        raise ValueError("A nonempty catalog with unique ids is required")
    rules = Path(__file__).with_name("prompts").joinpath("router.md").read_text(encoding="utf-8")
    slots = json.loads((DATASET / "slots.json").read_text(encoding="utf-8"))["slots"]
    catalog_data = [{
        "id": s.id, "purpose": s.purpose, "not_this_if": s.boundaries,
        "priority": s.priority, "required_slots": s.required_slots,
        "optional_slots": s.source.get("slots", {}).get("optional", []),
        "requires_confirmation": s.requires_confirmation,
        "examples_ru": s.examples_ru[:2], "examples_kk": s.examples_kk[:2],
    } for s in catalog]
    reference = {"today": "2026-10-01", "catalog": catalog_data,
                 "slot_definitions": [{k: v for k, v in slot.items() if k != "prompt"}
                                      for slot in slots]}
    return [
        {"role": "system", "content": rules + "\nREFERENCE DATA:\n" + json.dumps(reference, ensure_ascii=False)},
        {"role": "user", "content": json.dumps(context.model_dump(mode="json"), ensure_ascii=False)},
    ]
