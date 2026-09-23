"""Stable v1 route() plus per-call trace for the platform's live integration."""
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from contracts.models import Alternative, Decision, RouteResult, RouterContext, Scenario, Slot
from .catalog import validate_decision_ids
from .conversation import transition_topics
from .prompting import build_messages
from .providers.openai_provider import ProviderReply, RouterProviderError, TokenUsage
from .schemas import Intent
from .validation import validate_context, validate_prediction


class RoutingProvider(Protocol):
    async def predict(self, messages: list[dict]) -> ProviderReply: ...


@dataclass(frozen=True)
class RoutingTrace:
    result: RouteResult
    language: str
    router_ms: float
    provider_ms: float | None
    usage: TokenUsage | None
    attempts: int


class ScenarioRouter:
    def __init__(self, provider: RoutingProvider | None = None, *, mode: str = "scaffold"):
        if mode not in {"scaffold", "live"}:
            raise ValueError("Unknown router mode")
        if mode == "live" and provider is None:
            raise ValueError("Live routing requires an explicit provider")
        if mode == "scaffold" and provider is not None:
            raise ValueError("Provider injection requires explicit mode=live")
        self.provider = provider
        self.mode = mode

    async def route(self, context: RouterContext, catalog: list[Scenario]) -> RouteResult:
        return (await self.route_with_trace(context, catalog)).result

    async def route_with_trace(self, context: RouterContext, catalog: list[Scenario]) -> RoutingTrace:
        started = perf_counter()
        if self.mode == "scaffold":
            question = "Қандай сұрақты шешкіңіз келеді?" if context.language == "kk" else "Какой вопрос вы хотите решить?"
            result = RouteResult(decision=Decision(
                action="clarify", selected_scenario_id=None,
                rationale="Каркас: LLM-маршрутизация не включена.", certainty="unavailable",
                topic_operation="none", clarification_question=question,
            ), topics=[t.model_copy(deep=True) for t in context.topics])
            return RoutingTrace(result, context.language, (perf_counter()-started)*1000, None, None, 0)

        validate_context(context, catalog)
        reply = await self.provider.predict(build_messages(context, catalog))
        prediction = reply.prediction
        by_id = {s.id: s for s in catalog}
        try:
            validate_prediction(prediction, catalog)
            # Stable partition: high priority does NOT jump ahead of normal.
            intents = sorted(prediction.intents, key=lambda i: by_id[i.scenario_id].priority != "urgent")
            ids = [i.scenario_id for i in intents]
            alternatives = [Alternative(**a.model_dump()) for a in prediction.alternatives]
            uncertain = prediction.certainty != "high" or ids == ["SYS_UNCLEAR"]
            question = None
            action = "route"
            if uncertain:
                # Never place uncertain candidates into the selected routes or topic state.
                candidates = [Alternative(scenario_id=i.scenario_id, reason=prediction.rationale)
                              for i in intents if i.scenario_id != "SYS_UNCLEAR"] + alternatives
                alternatives = list({a.scenario_id: a for a in candidates}.values())[:3]
                intents = [Intent(scenario_id="SYS_UNCLEAR", slots=[])]
                ids = ["SYS_UNCLEAR"]
                previous = context.history[-1].decision if context.history else None
                repeated = previous is not None and previous.scenario_ids == ["SYS_UNCLEAR"]
                action = "transfer" if repeated else "clarify"
                if action == "clarify":
                    question = prediction.clarification_question or (
                        "Сақтандыру бойынша қандай сұрағыңыз бар?" if prediction.language == "kk"
                        else "Какой вопрос по страхованию вы хотите решить?")
            elif "SC37" in ids:
                action = "transfer"

            topics, operation = transition_topics(
                context.topics, intents, action=action,
                requested_operation="none" if uncertain or action == "transfer" else prediction.topic_operation,
                target_topic_id=None if uncertain else prediction.target_topic_id,
            )
            primary = ids[0]
            selected_topic = next((t for t in reversed(topics)
                                   if t.scenario_id == primary and t.status in {"active", "transferred"}), None)
            if operation == "resolve":
                selected_topic = next(t for t in topics if t.topic_id == prediction.target_topic_id)
            slots = selected_topic.slots if selected_topic else [Slot(**s.model_dump()) for s in intents[0].slots]
            decision = Decision(
                action=action, selected_scenario_id=primary, scenario_ids=ids,
                rationale=prediction.rationale, certainty=prediction.certainty,
                alternatives=alternatives, topic_operation=operation, slots=slots,
                clarification_question=question,
                requires_confirmation=by_id[primary].requires_confirmation if action == "route" and operation != "resolve" else False,
            )
            result = RouteResult(decision=decision, topics=topics)
            validate_decision_ids(result, catalog)
        except ValueError:
            raise RouterProviderError("invalid_routing_decision") from None
        return RoutingTrace(result, prediction.language, (perf_counter()-started)*1000,
                            reply.elapsed_ms, reply.usage, reply.attempts)
