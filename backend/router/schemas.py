"""Private LLM schema. Shared v1 wire models stay unchanged."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExtractedSlot(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)


class Intent(StrictModel):
    scenario_id: str
    slots: list[ExtractedSlot] = Field(max_length=43)

    @model_validator(mode="after")
    def unique_slots(self):
        if len({s.name for s in self.slots}) != len(self.slots):
            raise ValueError("Duplicate slot names")
        return self


class Candidate(StrictModel):
    scenario_id: str
    reason: str = Field(min_length=1, max_length=300)


class RouterPrediction(StrictModel):
    # All fields required, including nullable fields, for strict structured outputs.
    intents: list[Intent] = Field(min_length=1, max_length=43)
    language: Literal["ru", "kk", "mixed"]
    certainty: Literal["high", "medium", "low"]
    rationale: str = Field(min_length=1, max_length=500)
    alternatives: list[Candidate] = Field(max_length=3)
    clarification_question: str | None = Field(max_length=300)
    topic_operation: Literal["create", "continue", "switch", "resume", "resolve", "none"]
    target_topic_id: str | None

    @model_validator(mode="after")
    def unique_intents(self):
        ids = [i.scenario_id for i in self.intents]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate scenario ids")
        if len({a.scenario_id for a in self.alternatives}) != len(self.alternatives):
            raise ValueError("Duplicate alternatives")
        return self
