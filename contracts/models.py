"""Wire models shared by router, platform and UI; v1 is the source of truth."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["ru", "kk", "mixed", "auto"]

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Slot(Contract):
    name: str
    value: str

class Alternative(Contract):
    scenario_id: str
    reason: str

class Topic(Contract):
    topic_id: str
    scenario_id: str | None = None
    status: Literal["active", "parked", "resolved", "transferred"]
    slots: list[Slot] = Field(default_factory=list)

class Decision(Contract):
    action: Literal["route", "clarify", "transfer"]
    selected_scenario_id: str | None
    scenario_ids: list[str] = Field(default_factory=list)
    rationale: str
    # Qualitative self-report, NOT a calibrated probability.
    certainty: Literal["high", "medium", "low", "unavailable"]
    alternatives: list[Alternative] = Field(default_factory=list, max_length=3)
    topic_operation: Literal["create", "continue", "switch", "resume", "resolve", "none"]
    slots: list[Slot] = Field(default_factory=list)
    clarification_question: str | None = None
    requires_confirmation: bool = False

    @model_validator(mode="after")
    def check_action(self):
        if self.action == "route" and not self.selected_scenario_id:
            raise ValueError("route requires selected_scenario_id")
        if self.selected_scenario_id is not None and (
            not self.scenario_ids or self.scenario_ids[0] != self.selected_scenario_id
        ):
            raise ValueError("selected scenario must be first in ordered scenario_ids")
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        if self.action == "clarify" and not self.clarification_question:
            raise ValueError("clarify requires a question")
        return self

class Scenario(Contract):
    """Normalized routing view with original data retained for the executor."""
    id: str
    purpose: str
    boundaries: list[str] = Field(default_factory=list)
    required_slots: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    examples_ru: list[str] = Field(default_factory=list)
    examples_kk: list[str] = Field(default_factory=list)
    priority: Literal["normal", "high", "urgent"] = "normal"
    requires_identification: bool = False
    requires_confirmation: bool = False
    source: dict = Field(default_factory=dict)

class TurnInput(Contract):
    text: str = Field(min_length=1, max_length=4000)
    language: Language = "auto"

    @model_validator(mode="after")
    def reject_blank(self):
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("text must not be blank")
        return self

class TurnRecord(Contract):
    user_text: str
    assistant_text: str
    decision: Decision

class RouterContext(Contract):
    text: str
    language: Language
    history: list[TurnRecord] = Field(default_factory=list, max_length=10)
    topics: list[Topic] = Field(default_factory=list)

class RouteResult(Contract):
    decision: Decision
    topics: list[Topic] = Field(default_factory=list)

class Timings(Contract):
    router_ms: float = Field(ge=0)
    backend_total_ms: float = Field(ge=0)
    stt_ms: float | None = Field(default=None, ge=0)
    tts_first_byte_ms: float | None = Field(default=None, ge=0)
    # Must be measured in browser from end of speech to actual playback.
    end_to_audio_ms: float | None = Field(default=None, ge=0)

class TurnResponse(Contract):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    turn_id: str
    mode: Literal["scaffold", "live"]
    transcript: str
    language: Language
    assistant_text: str
    decision: Decision
    topics: list[Topic]
    timings: Timings

class SessionCreated(Contract):
    session_id: str

class SpeechRequest(Contract):
    text: str = Field(min_length=1, max_length=2000)
    language: Language = "auto"

class Transcript(Contract):
    text: str
    language: Language
    stt_ms: float = Field(ge=0)
