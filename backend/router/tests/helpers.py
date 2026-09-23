"""Scripted test responses are fixtures, never an intent classifier or LLM score."""
import json
from types import SimpleNamespace
from backend.router.schemas import RouterPrediction
from backend.router.providers.openai_provider import ProviderReply, TokenUsage


def prediction(*ids, slots=None, **overrides):
    values = dict(
        intents=[{"scenario_id": i, "slots": (slots or {}).get(i, [])} for i in ids],
        language="ru", certainty="high", rationale="Запрошен указанный сценарий.",
        alternatives=[], clarification_question=None, topic_operation="create", target_topic_id=None,
    )
    values.update(overrides)
    return RouterPrediction.model_validate(values)


class ScriptedProvider:
    def __init__(self, *predictions):
        self.predictions = iter(predictions)
        self.calls = []

    async def predict(self, messages):
        self.calls.append(messages)
        return ProviderReply(next(self.predictions), TokenUsage(100, 50), 1.25, 1)


class RecordingBudget:
    def __init__(self, deny=False):
        self.estimates = []
        self.settlements = []
        self.deny = deny

    async def authorize(self, estimate):
        if self.deny:
            raise RuntimeError("budget_exceeded")
        self.estimates.append(estimate)
        return str(len(self.estimates))

    async def settle(self, reservation, usage):
        self.settlements.append((reservation, usage))


def sdk_response(value, **overrides):
    result = dict(status="completed", output=[], output_text=value.model_dump_json(),
                  usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                                        input_tokens_details=SimpleNamespace(cached_tokens=10)))
    result.update(overrides)
    return SimpleNamespace(**result)


class ScriptedClient:
    def __init__(self, *responses):
        self.script = iter(responses)
        self.calls = []
        self.options = None
        self.responses = self

    def with_options(self, **options):
        self.options = options
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.script)
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self):
        pass


def wire_response(value):
    return {
        "id": "resp_mock", "object": "response", "created_at": 0,
        "model": "offline-model", "status": "completed", "error": None,
        "incomplete_details": None,
        "output": [{"id": "msg_mock", "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": value.model_dump_json(), "annotations": []}]}],
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                  "input_tokens_details": {"cached_tokens": 10},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    }
