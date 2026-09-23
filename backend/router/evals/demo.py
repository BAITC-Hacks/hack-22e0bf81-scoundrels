"""Reproducible six-turn integration demo with scripted SDK transport, not an LLM."""
import asyncio
import json
from pathlib import Path

import httpx2
from openai import AsyncOpenAI
from contracts.models import RouterContext, TurnRecord
from backend.router.catalog import load_catalog
from backend.router.prompting import DATASET
from backend.router.providers.openai_provider import OpenAIProvider, ProviderSettings
from backend.router.schemas import RouterPrediction
from backend.router.service import ScenarioRouter

ROOT = Path(__file__).resolve().parents[1]


class OfflineGuard:
    """Only used with the closed MockTransport below; no credentials/network."""
    async def authorize(self, estimate):
        return "mock"

    async def settle(self, reservation, usage):
        pass


async def run_demo() -> dict:
    fixture = json.loads((ROOT / "data" / "demo_dialog.json").read_text(encoding="utf-8"))
    catalog = load_catalog(DATASET / "scenarios.json")
    script = iter(fixture["turns"])

    def handler(request):
        row = next(script)
        context = json.loads(json.loads(request.content)["input"][1]["content"])
        target = next((t["topic_id"] for t in context["topics"]
                       if t["scenario_id"] == row.get("target_scenario")), None)
        value = RouterPrediction(
            intents=row["intents"], language=row["language"], certainty=row["certainty"],
            rationale="Заранее заданный mock-ответ; не вывод модели.", alternatives=[],
            clarification_question=row.get("question"), topic_operation=row["operation"], target_topic_id=target)
        return httpx2.Response(200, json={
            "id": "resp_demo", "object": "response", "created_at": 0, "model": "scripted-mock",
            "status": "completed", "output": [{"id": "msg_demo", "type": "message", "role": "assistant",
                "status": "completed", "content": [{"type": "output_text", "text": value.model_dump_json(), "annotations": []}]}],
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        })

    history, topics, results = [], [], []
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        provider = OpenAIProvider(client=AsyncOpenAI(api_key="offline-demo-key", http_client=http),
                                  settings=ProviderSettings(model="scripted-mock"), budget=OfflineGuard())
        router = ScenarioRouter(provider, mode="live")  # Exercises live code with no live transport.
        for row in fixture["turns"]:
            trace = await router.route_with_trace(
                RouterContext(text=row["text"], language="auto", topics=topics, history=history), catalog)
            result = trace.result
            history.append(TurnRecord(user_text=row["text"], assistant_text="[mock executor]", decision=result.decision))
            topics = result.topics
            results.append({"text": row["text"], "language": trace.language, **result.model_dump(mode="json"),
                            "router_ms": trace.router_ms, "provider_ms": trace.provider_ms})
    return {"mode": "mock", "notice": fixture["notice"], "paid_api_calls": 0, "turns": results}


def main():
    result = asyncio.run(run_demo())
    output = ROOT / "artifacts" / "demo.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MOCK DEMO ONLY; paid API calls: 0")
    for index, row in enumerate(result["turns"], 1):
        decision = row["decision"]
        print(f"{index}: {decision['scenario_ids']} / {decision['action']} / {decision['topic_operation']} / {row['language']}")
    print(output)


if __name__ == "__main__":
    main()
