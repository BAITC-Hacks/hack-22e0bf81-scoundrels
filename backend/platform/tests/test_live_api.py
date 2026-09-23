from pathlib import Path
from decimal import Decimal
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi.testclient import TestClient

from backend.platform.app import ManagedSpeechResponse, create_app
from backend.platform.config import Settings
from backend.platform.services.responses import ReplyComposer
from backend.router.providers.openai_provider import RouterProviderError
from backend.voice.stt import TranscriptionResult
from backend.voice.tts import SpeechError, SpeechResult, SpeechStream
from contracts.models import Decision, RouteResult, Slot


ROOT = Path(__file__).resolve().parents[3]


def live_settings(**overrides):
    values = dict(
        app_mode="live", openai_api_key="test-key", openai_router_model="gpt-6-luna",
        openai_stt_model="gpt-transcribe", openai_tts_model="gpt-4o-mini-tts",
        run_budget_usd=0.06, session_budget_usd=0.06,
    )
    values.update(overrides)
    return Settings(**values)


class FakeRouter:
    async def route_with_language(self, context, catalog):
        return RouteResult(decision=Decision(
            action="route", selected_scenario_id="SC25", scenario_ids=["SC25"],
            rationale="Проверить полис", certainty="high", topic_operation="create",
        )), "ru"


class FakeSTT:
    async def transcribe(self, audio, *, filename, language_hint):
        assert audio == b"webm-data"
        assert filename == "speech.webm"
        assert language_hint == "mixed"
        return TranscriptionResult(
            text="Полис действует?", language="ru", detected_languages=("ru",),
            stt_ms=123.4, usage={"seconds": 2}, model="gpt-transcribe",
        )


class FakeTTS:
    async def synthesize(self, text, *, language):
        assert text == "Тестовый ответ"
        assert language == "ru"
        return SpeechResult(
            audio=b"mp3-data", content_type="audio/mpeg", tts_first_byte_ms=42.0,
            tts_total_ms=66.0, model="gpt-4o-mini-tts", voice="marin",
            input_characters=len(text), usage=None,
        )


def test_live_full_http_path_is_bounded_and_no_fake_business_action():
    app = create_app(live_settings())
    app.state.router = FakeRouter()
    app.state.stt = FakeSTT()
    app.state.tts = FakeTTS()
    with TestClient(app) as client:
        assert client.get("/api/health").json()["capabilities"] == {
            "llm_routing": True, "stt": True, "tts": True,
        }
        sid = client.post("/api/sessions").json()["session_id"]
        transcript = client.post(
            "/api/voice/transcribe",
            headers={"X-Session-ID": sid},
            files={"file": ("speech.webm", b"webm-data", "audio/webm")},
        )
        assert transcript.status_code == 200
        assert transcript.json()["text"] == "Полис действует?"
        turn = client.post(f"/api/sessions/{sid}/turns", json={
            "text": transcript.json()["text"], "language": "auto",
        })
        assert turn.status_code == 200
        body = turn.json()
        assert body["mode"] == "live"
        assert body["decision"]["scenario_ids"] == ["SC25"]
        assert "номер полиса" in body["assistant_text"]
        audio = client.post("/api/voice/synthesize", headers={"X-Session-ID": sid}, json={
            "text": "Тестовый ответ", "language": "ru",
        })
        assert audio.status_code == 200
        assert audio.content == b"mp3-data"
        assert audio.headers["content-type"].startswith("audio/mpeg")
        assert audio.headers["x-tts-first-byte-ms"] == "42.0"
        assert app.state.budget._session_reserved[sid] == Decimal("0.06")
        assert client.post(f"/api/sessions/{sid}/turns", json={"text": "again"}).status_code == 429


def test_live_rejects_unsupported_audio_before_paid_reservation():
    app = create_app(live_settings())
    with TestClient(app) as client:
        assert client.post("/api/voice/transcribe", files={
            "file": ("sample.exe", b"bad", "application/octet-stream"),
        }).status_code == 415
        assert client.post("/api/voice/transcribe", files={
            "file": ("speech.webm", b"", "audio/webm"),
        }).status_code == 422
        assert app.state.budget.run_reserved_usd == 0


def test_router_failure_does_not_write_session_history():
    class FailingRouter:
        async def route_with_language(self, context, catalog):
            raise RouterProviderError("provider internals")

    app = create_app(live_settings())
    app.state.router = FailingRouter()
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        response = client.post(f"/api/sessions/{sid}/turns", json={"text": "Hello"})
        assert response.status_code == 502
        assert "provider internals" not in response.text
        assert app.state.sessions.get(sid).history == []


def test_policy_lookup_requires_matching_phone_and_uses_dataset_date():
    composer = ReplyComposer(ROOT / "case_2/voice_router_dataset/mock_backend.json")
    decision = Decision(
        action="route", selected_scenario_id="SC25", scenario_ids=["SC25"],
        rationale="check", certainty="high", topic_operation="create",
        slots=[Slot(name="policy_number", value="SQ-OGPO-104501"),
               Slot(name="phone", value="+77010000001")],
    )
    result = composer.compose(decision, [], "ru")
    assert "2027-03-14" in result
    assert "2026-10-01" in result
    decision.slots[1].value = "+77010000002"
    assert "не удалось" in composer.compose(decision, [], "ru").lower()


def test_mixed_reply_uses_kazakh_and_acknowledges_second_intent():
    composer = ReplyComposer(ROOT / "case_2/voice_router_dataset/mock_backend.json")
    decision = Decision(
        action="route", selected_scenario_id="SC25", scenario_ids=["SC25", "SC29"],
        rationale="two requests", certainty="high", topic_operation="create",
    )
    reply = composer.compose(decision, [], "mixed", "Сәлем, check policy and change phone")
    assert "полис нөмірін" in reply
    assert "телефонды өзгертуге" in reply


def test_read_only_claim_and_office_use_mock_and_knowledge_base():
    composer = ReplyComposer(ROOT / "case_2/voice_router_dataset/mock_backend.json")
    claim = Decision(
        action="route", selected_scenario_id="SC17", scenario_ids=["SC17"],
        rationale="claim", certainty="high", topic_operation="create",
        slots=[Slot(name="claim_number", value="CL-500198"),
               Slot(name="phone", value="+77010000001")],
    )
    assert "paid" in composer.compose(claim, [], "en")
    claim.slots[1].value = "+77010000002"
    assert "did not match" in composer.compose(claim, [], "en")

    office = Decision(
        action="route", selected_scenario_id="SC33", scenario_ids=["SC33"],
        rationale="office", certainty="high", topic_operation="create",
        slots=[Slot(name="city", value="Алматы")],
    )
    assert "Abai Ave 150" in composer.compose(office, [], "ru")

    payments = Decision(
        action="route", selected_scenario_id="SC31", scenario_ids=["SC31"],
        rationale="payments", certainty="high", topic_operation="create",
    )
    assert "ОГПО" in composer.compose(payments, [], "ru")


def test_streaming_http_reserves_budget_once_and_closes_provider_on_success_or_error():
    class StreamingTTS:
        closed = 0
        fail = False

        @asynccontextmanager
        async def stream(self, text, *, language):
            try:
                if self.fail:
                    raise SpeechError("provider details")
                async def chunks():
                    yield b"first"
                    yield b"last"
                yield SpeechStream(chunks=chunks(), tts_first_byte_ms=10, started_at=0)
            finally:
                self.closed += 1

    app = create_app(live_settings())
    tts = app.state.tts = StreamingTTS()
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        response = client.post("/api/voice/synthesize/stream", json={"text": "Hello"},
                               headers={"X-Session-ID": sid})
        assert response.content == b"firstlast"
        assert response.headers["x-tts-first-byte-ms"] == "10"
        assert "x-tts-total-ms" not in response.headers
        assert tts.closed == 1
        assert app.state.budget._session_reserved[sid] == Decimal("0.02")
        tts.fail = True
        assert client.post("/api/voice/synthesize/stream", json={"text": "Hello"}).status_code == 502
        assert tts.closed == 2
        assert app.state.paid_slots._value == 2


def test_stream_disconnect_before_body_releases_resources():
    closed = []

    async def check():
        resources = AsyncExitStack()
        resources.callback(lambda: closed.append(True))
        async def body():
            yield b"unused"
        response = ManagedSpeechResponse(body(), resources=resources)
        async def send(message):
            raise OSError("client disconnected before headers")
        async def receive():
            return {"type": "http.disconnect"}
        try:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        except Exception:
            pass
        assert closed == [True]
    asyncio.run(check())


def test_stream_late_failure_releases_provider_and_paid_slot():
    async def check(disconnect):
        slots = asyncio.Semaphore(1)
        resources = AsyncExitStack()
        closed = []
        await resources.enter_async_context(slots)
        resources.callback(lambda: closed.append(True))

        async def body():
            yield b"first"
            raise SpeechError("provider failed after first audio")

        response = ManagedSpeechResponse(body(), resources=resources)
        sent = []

        async def send(message):
            sent.append(message)
            if disconnect and message["type"] == "http.response.body":
                raise OSError("client disconnected during audio")

        async def receive():
            return {"type": "http.disconnect"}

        try:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        except Exception:
            pass
        else:
            raise AssertionError("A truncated stream must not complete successfully")
        assert sent[0]["type"] == "http.response.start"
        assert sent[1]["body"] == b"first"
        assert closed == [True]
        assert slots._value == 1

    asyncio.run(check(disconnect=True))
    asyncio.run(check(disconnect=False))
