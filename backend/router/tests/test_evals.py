import asyncio
from decimal import Decimal
import json
import pytest

from backend.router.catalog import load_catalog
from backend.router.evals.budget import EvalBudget
from backend.router.evals.demo import run_demo
from backend.router.evals.run import collect, metrics, parser, run
from backend.router.prompting import DATASET
from backend.router.providers.openai_provider import RequestEstimate, TokenUsage
from backend.router.service import ScenarioRouter
from .helpers import ScriptedProvider, prediction


def test_eval_uses_decision_order_without_gold_in_prompt():
    rows = [{"id": "synthetic", "text": "unseen request", "lang": "mixed", "type": "multi_intent", "expected": ["SC11", "SC27"]}]
    provider = ScriptedProvider(prediction("SC27", "SC11"))
    result, timings, failures = asyncio.run(collect(ScenarioRouter(provider, mode="live"),
        load_catalog(DATASET / "scenarios.json"), rows))
    assert result == {"synthetic": ["SC11", "SC27"]}
    context = json.loads(provider.calls[0][1]["content"])
    assert "expected" not in context and context["language"] == "auto"
    assert timings and not failures


def test_official_set_match_is_not_ordered_match():
    rows = [{"id": "a", "lang": "kk", "type": "multi_intent", "expected": ["SC11", "SC27"]}]
    summary = metrics(rows, {"a": ["SC27", "SC11"]})
    assert summary["all"]["full_match"] == 1
    assert summary["all"]["primary_accuracy"] == 0
    assert summary["all"]["ordered_exact_match"] == 0
    assert summary["lang=kk"]["intent_recall"] == 1


def test_live_eval_requires_separate_opt_in_before_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    args = parser().parse_args(["--mode", "live"])
    with pytest.raises(ValueError, match="Live requires"):
        asyncio.run(run(args))


def test_eval_writes_only_own_scope(tmp_path):
    args = parser().parse_args(["--output-dir", str(tmp_path)])
    with pytest.raises(ValueError, match="inside backend/router"):
        asyncio.run(run(args))


def test_eval_budget_reserve_settle_unknown_and_call_limit():
    async def scenario():
        budget = EvalBudget(max_usd=Decimal("1"), input_rate=Decimal("10"),
                            cached_input_rate=Decimal("1"), cache_write_rate=Decimal("12.5"),
                            output_rate=Decimal("20"), max_calls=2)
        estimate = RequestEstimate("model", 10000, 1000)
        first = await budget.authorize(estimate)
        assert budget.charged_or_reserved == Decimal("0.145")
        await budget.settle(first, TokenUsage(1000, 100, cached_input_tokens=800))
        assert budget.charged_or_reserved == Decimal("0.0053")
        second = await budget.authorize(estimate)
        await budget.settle(second, None)
        assert budget.charged_or_reserved == Decimal("0.1503")
        with pytest.raises(RuntimeError, match="budget_exceeded"):
            await budget.authorize(estimate)
    asyncio.run(scenario())


def test_budget_rejects_oversized_reservation_and_nonfinite_rates():
    async def scenario():
        budget = EvalBudget(max_usd=Decimal("0.01"), input_rate=Decimal("10"),
                            cached_input_rate=Decimal("1"), cache_write_rate=Decimal("12.5"),
                            output_rate=Decimal("20"), max_calls=10)
        with pytest.raises(RuntimeError):
            await budget.authorize(RequestEstimate("model", 10000, 1000))
        assert budget.calls == 0
    asyncio.run(scenario())
    with pytest.raises(ValueError):
        EvalBudget(max_usd=Decimal("NaN"), input_rate=Decimal(1), cached_input_rate=Decimal(1),
                   cache_write_rate=Decimal(1), output_rate=Decimal(1), max_calls=1)


def test_demo_main_scenario_through_real_sdk_mock_transport():
    demo = asyncio.run(run_demo())
    assert demo["mode"] == "mock" and demo["paid_api_calls"] == 0
    turns = demo["turns"]
    assert turns[2]["decision"]["topic_operation"] == "resume"
    assert turns[2]["decision"]["slots"] == [{"name": "policy_number", "value": "SQ-OGPO-104501"}]
    assert turns[3]["decision"]["scenario_ids"] == ["SC11", "SC27"]
    assert turns[4]["decision"]["action"] == "clarify"
    assert turns[5]["decision"]["action"] == "transfer"
    assert all(t["status"] == "transferred" for t in turns[-1]["topics"])
