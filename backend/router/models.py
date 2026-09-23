"""Private Structured Output models returned by the routing LLM.

These models deliberately stay inside backend.router: the public wire contract lives
in contracts/models.py and is owned by the integration workstream.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoutedScenario(ModelOutput):
    scenario_id: str = Field(description="Exact SCxx or SYS_* id from the catalog")
    reason: str = Field(min_length=1, max_length=240)


class RoutedAlternative(ModelOutput):
    scenario_id: str = Field(description="Unselected catalog id")
    reason: str = Field(min_length=1, max_length=240)


class ExtractedSlot(ModelOutput):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=300)


class RouterModelOutput(ModelOutput):
    scenarios: list[RoutedScenario] = Field(min_length=1, max_length=6)
    alternatives: list[RoutedAlternative] = Field(default_factory=list, max_length=3)
    language: Literal["ru", "kk", "en", "mixed"]
    language_components: list[Literal["ru", "kk", "en"]] = Field(min_length=1, max_length=3)
    certainty: Literal["high", "medium", "low"]
    rationale: str = Field(min_length=1, max_length=400)
    slots: list[ExtractedSlot] = Field(default_factory=list, max_length=20)
    is_continuation: bool
    topic_operation: Literal["create", "continue", "switch", "resume", "resolve", "none"]
    clarification_question: str | None = Field(default=None, max_length=300)
    requires_confirmation: bool

    @model_validator(mode="after")
    def validate_system_intents(self):
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("selected scenario ids must be unique")
        if "SYS_UNCLEAR" in ids and not self.clarification_question:
            raise ValueError("SYS_UNCLEAR requires clarification_question")
        components = list(dict.fromkeys(self.language_components))
        if components != self.language_components:
            raise ValueError("language_components must be unique")
        if self.language == "mixed" and len(components) < 2:
            raise ValueError("mixed language requires at least two components")
        if self.language != "mixed" and components != [self.language]:
            raise ValueError("single language must match its only component")
        return self


class CompactRouterOutput(ModelOutput):
    """Generate only data used by the application; retain the full public contract."""

    scenario_ids: list[str] = Field(min_length=1, max_length=6)
    language: Literal["ru", "kk", "en", "mixed"]
    language_components: list[Literal["ru", "kk", "en"]] = Field(min_length=1, max_length=3)
    topic_operation: Literal["create", "continue", "switch", "resume", "resolve", "none"]
    slots: list[ExtractedSlot] = Field(default_factory=list, max_length=20)
    certainty: Literal["high", "medium", "low"]
    rationale: str = Field(min_length=1, max_length=180)
    alternatives: list[RoutedAlternative] = Field(default_factory=list, max_length=2)
    clarification_question: str | None = Field(default=None, max_length=300)

    def to_full(self) -> RouterModelOutput:
        return RouterModelOutput(
            scenarios=[RoutedScenario(scenario_id=item, reason=self.rationale)
                       for item in self.scenario_ids],
            alternatives=self.alternatives, language=self.language,
            language_components=self.language_components, certainty=self.certainty,
            rationale=self.rationale, slots=self.slots, topic_operation=self.topic_operation,
            clarification_question=self.clarification_question,
            is_continuation=self.topic_operation == "continue",
            requires_confirmation=False,  # Enforced from catalog, never trusted to the LLM.
        )

    @model_validator(mode="after")
    def validate_semantics(self):
        self.to_full()
        return self
