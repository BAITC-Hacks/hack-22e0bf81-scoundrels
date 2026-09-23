import pytest
from pydantic import ValidationError
from contracts.models import Decision, TurnInput

def decision(**overrides):
    fields = dict(action="clarify", selected_scenario_id=None, rationale="Ambiguous",
                  certainty="low", topic_operation="none", clarification_question="Which topic?")
    return Decision(**(fields | overrides))

def test_routing_requires_id():
    with pytest.raises(ValidationError):
        decision(action="route")

def test_clarification_cannot_claim_route():
    with pytest.raises(ValidationError):
        decision(selected_scenario_id="invented")

def test_clarification_requires_question():
    with pytest.raises(ValidationError):
        decision(clarification_question=None)

@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_blank_input_rejected(text):
    with pytest.raises(ValidationError):
        TurnInput(text=text)

def test_mixed_language_preserved():
    assert TurnInput(text="Полис бар, но не приходит", language="mixed").language == "mixed"

def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        TurnInput(text="hi", api_key="not-a-real-key")

def test_primary_matches_ordered_multi_intents():
    parsed = decision(action="route", selected_scenario_id="SC30",
                      scenario_ids=["SC30", "SC29"], clarification_question=None)
    assert parsed.scenario_ids == ["SC30", "SC29"]
    with pytest.raises(ValidationError):
        decision(action="route", selected_scenario_id="SC29", scenario_ids=["SC30", "SC29"])

def test_handoff_can_retain_selected_scenario():
    parsed = decision(action="transfer", selected_scenario_id="SC37", scenario_ids=["SC37"])
    assert parsed.selected_scenario_id == "SC37"
