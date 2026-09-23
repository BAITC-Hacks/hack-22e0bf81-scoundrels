"""Stable entry point consumed by backend.platform. Replace internals, not signature."""
from contracts.models import Decision, RouteResult, RouterContext, Scenario

class ScenarioRouter:
    async def route(self, context: RouterContext, catalog: list[Scenario]) -> RouteResult:
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
