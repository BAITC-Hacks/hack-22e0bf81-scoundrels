"""Stable entry point consumed by backend.platform."""
from typing import Protocol

from contracts.models import Decision, RouteResult, RouterContext, Scenario
from backend.router.conversation import advance_conversation


class RouterProvider(Protocol):
    async def route(self, context: RouterContext, catalog: list[Scenario]) -> RouteResult: ...


class ScenarioRouter:
    def __init__(self, provider: RouterProvider | None = None):
        self.provider = provider

    async def route(self, context: RouterContext, catalog: list[Scenario]) -> RouteResult:
        if self.provider is not None:
            result = await self.provider.route(context, catalog)
            return advance_conversation(context, result, catalog)
        # Intentional scaffold: no classifier, no fake LLM, no test-phrase mapping.
        question = "Какой вопрос вы хотите решить?"
        return RouteResult(
            decision=Decision(
                action="clarify",
                selected_scenario_id=None,
                rationale="Каркас: LLM-маршрутизация ещё не подключена.",
                certainty="unavailable",
                topic_operation="none",
                clarification_question=question,
            ),
            topics=context.topics,
        )

    async def route_with_language(
        self, context: RouterContext, catalog: list[Scenario]
    ) -> tuple[RouteResult, str]:
        """Return the validated route and LLM-detected language in one paid call."""
        if self.provider is not None and hasattr(self.provider, "route_detailed"):
            detailed = await self.provider.route_detailed(context, catalog)
            return advance_conversation(context, detailed.result, catalog), detailed.detected_language
        return await self.route(context, catalog), context.language
