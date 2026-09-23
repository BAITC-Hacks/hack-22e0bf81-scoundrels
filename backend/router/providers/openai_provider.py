"""Structured OpenAI Responses provider for scenario routing.

Live wiring and usage accounting are intentionally deferred until the shared budget
guard is available. Offline tests inject a fake client and never contact OpenAI.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from contracts.models import Alternative, Decision, RouteResult, RouterContext, Scenario, Slot
from backend.router.models import RouterModelOutput
from backend.router.prompting import build_router_instructions, build_turn_input


class RouterProviderError(RuntimeError):
    """The provider could not return a usable routing decision."""


class RouterConfigurationError(RouterProviderError):
    """Required live provider configuration is absent."""


@dataclass(frozen=True)
class DetailedRoute:
    result: RouteResult
    detected_language: str
    language_components: tuple[str, ...]
    usage: Any | None


class OpenAIRouterProvider:
    def __init__(
        self,
        *,
        model: str | None,
        api_key: str | None = None,
        client: Any | None = None,
        timeout_seconds: float = 8.0,
        max_output_tokens: int = 900,
        reasoning_effort: str | None = None,
        prompt_cache_key: str | None = None,
        usage_callback: Callable[[Any], None] | None = None,
    ):
        if not model or not model.strip():
            raise RouterConfigurationError("OPENAI_ROUTER_MODEL must be configured explicitly")
        if timeout_seconds <= 0:
            raise RouterConfigurationError("router timeout must be positive")
        if not 128 <= max_output_tokens <= 2048:
            raise RouterConfigurationError("max_output_tokens must be between 128 and 2048")
        if client is None and not api_key:
            raise RouterConfigurationError("OPENAI_API_KEY is required for a live client")

        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.prompt_cache_key = prompt_cache_key
        self.usage_callback = usage_callback
        # One SDK retry means at most two paid attempts. The budget guard may later set zero.
        self.client = client or AsyncOpenAI(api_key=api_key, max_retries=1)

    async def route(self, context: RouterContext, catalog: list[Scenario]) -> RouteResult:
        return (await self.route_detailed(context, catalog)).result

    async def route_detailed(self, context: RouterContext, catalog: list[Scenario]) -> DetailedRoute:
        if not catalog:
            raise RouterProviderError("scenario catalog is empty")
        try:
            request = dict(
                model=self.model,
                instructions=build_router_instructions(catalog),
                input=build_turn_input(context),
                text_format=RouterModelOutput,
                max_output_tokens=self.max_output_tokens,
                store=False,
                timeout=self.timeout_seconds,
            )
            if self.reasoning_effort:
                request["reasoning"] = {"effort": self.reasoning_effort}
            if self.prompt_cache_key:
                request["prompt_cache_key"] = self.prompt_cache_key
            response = await self.client.responses.parse(**request)
        except Exception as exc:
            raise RouterProviderError("OpenAI routing request failed") from exc

        if getattr(response, "status", None) != "completed":
            raise RouterProviderError(
                f"OpenAI routing response was not completed: {getattr(response, 'status', None)!r}"
            )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise RouterProviderError("OpenAI routing response has no parsed output")
        if not isinstance(parsed, RouterModelOutput):
            parsed = RouterModelOutput.model_validate(parsed)

        usage = getattr(response, "usage", None)
        if self.usage_callback is not None:
            self.usage_callback(usage)
        return DetailedRoute(
            result=self._to_contract(parsed, catalog, context),
            detected_language=parsed.language,
            language_components=tuple(parsed.language_components),
            usage=usage,
        )

    @staticmethod
    def _to_contract(
        output: RouterModelOutput,
        catalog: list[Scenario],
        context: RouterContext,
    ) -> RouteResult:
        by_id = {scenario.id: scenario for scenario in catalog}
        raw_ids = [scenario.scenario_id for scenario in output.scenarios]
        unknown = set(raw_ids) - set(by_id)
        unknown.update(item.scenario_id for item in output.alternatives if item.scenario_id not in by_id)
        if unknown:
            raise RouterProviderError(f"model returned unknown scenario ids: {sorted(unknown)}")

        # Urgency is deterministic policy; among equal priorities keep model/mention order.
        urgent = [scenario_id for scenario_id in raw_ids if by_id[scenario_id].priority == "urgent"]
        ordered_ids = urgent + [scenario_id for scenario_id in raw_ids if scenario_id not in urgent]
        primary = ordered_ids[0]
        clarification = "SYS_UNCLEAR" in ordered_ids
        transfer = primary == "SC37"
        action = "clarify" if clarification else "transfer" if transfer else "route"

        alternatives = [
            Alternative(scenario_id=item.scenario_id, reason=item.reason)
            for item in output.alternatives
            if item.scenario_id not in ordered_ids
        ]
        selected_requires_confirmation = any(by_id[item].requires_confirmation for item in ordered_ids)
        decision = Decision(
            action=action,
            selected_scenario_id=primary,
            scenario_ids=ordered_ids,
            rationale=output.rationale,
            certainty=output.certainty,
            alternatives=alternatives,
            topic_operation=output.topic_operation,
            slots=[Slot(name=item.name, value=item.value) for item in output.slots],
            clarification_question=output.clarification_question if clarification else None,
            # Catalog policy wins over model output; model cannot waive confirmation.
            requires_confirmation=selected_requires_confirmation,
        )
        return RouteResult(decision=decision, topics=context.topics)
