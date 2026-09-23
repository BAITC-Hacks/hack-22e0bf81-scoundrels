import asyncio
import json
import pytest
from pathlib import Path
from contracts.models import RouterContext, Topic
from backend.router.service import ScenarioRouter
from backend.router.catalog import load_catalog

def test_scaffold_does_not_invent_scenario():
    result = asyncio.run(ScenarioRouter().route(RouterContext(text="Страховка", language="ru"), []))
    assert result.decision.action == "clarify"
    assert result.decision.selected_scenario_id is None
    assert result.decision.certainty == "unavailable"

def test_scaffold_preserves_existing_topics():
    topic = Topic(topic_id="t1", status="parked")
    result = asyncio.run(ScenarioRouter().route(
        RouterContext(text="жалғастырайық", language="kk", topics=[topic]), []))
    assert result.topics == [topic]

def test_duplicate_catalog_ids_rejected(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([{"id": "a", "purpose": "A"}, {"id": "a", "purpose": "B"}]))
    with pytest.raises(ValueError, match="unique"):
        load_catalog(path)

def test_official_catalog_preserves_ids_and_execution_rules():
    root = Path(__file__).resolve().parents[3]
    scenarios = load_catalog(root / "case_2/voice_router_dataset/scenarios.json")
    by_id = {s.id: s for s in scenarios}
    assert len(scenarios) == 43
    assert {f"SC{i:02}" for i in range(1, 41)} <= set(by_id)
    assert {"SYS_UNCLEAR", "SYS_GOODBYE", "SYS_OUT_OF_SCOPE"} <= set(by_id)
    assert by_id["SC11"].priority == "urgent"
    assert by_id["SC28"].requires_confirmation
    assert by_id["SC28"].source["requires_confirmation"]
    assert by_id["SC01"].boundaries
    assert by_id["SC01"].examples_kk
