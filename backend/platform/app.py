"""FastAPI composition for the safe scaffold and bounded live demo."""

import asyncio
from contextlib import AsyncExitStack
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from anyio import CancelScope

from contracts.models import (
    RouterContext, SessionCreated, SpeechRequest, Timings, Transcript,
    TurnInput, TurnRecord, TurnResponse,
)
from backend.router.catalog import load_catalog, validate_decision_ids
from backend.router.providers.openai_provider import OpenAIRouterProvider, RouterProviderError
from backend.router.service import ScenarioRouter
from backend.voice.stt import OpenAITranscriber, TranscriptionError
from backend.voice.tts import OpenAISynthesizer, SpeechError
from .config import ROOT, Settings
from .services.budget import BudgetExceeded, DemoBudget
from .services.responses import ReplyComposer
from .sessions import SessionStore


MAX_UPLOAD_BYTES = 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/ogg", "audio/flac", "audio/x-m4a",
}


class ManagedSpeechResponse(StreamingResponse):
    """Release upstream stream and paid semaphore even if ASGI disconnects before iteration."""

    def __init__(self, *args, resources: AsyncExitStack, **kwargs):
        super().__init__(*args, **kwargs)
        self.resources = resources

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self.resources.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="RouteMap · Voice Router", version="0.2.0")
    app.state.settings = settings
    app.state.sessions = SessionStore()
    app.state.catalog = load_catalog(ROOT / "case_2/voice_router_dataset/scenarios.json")
    app.state.replies = ReplyComposer(ROOT / "case_2/voice_router_dataset/mock_backend.json")
    app.state.budget = None
    app.state.stt = None
    app.state.tts = None
    app.state.paid_slots = asyncio.Semaphore(2)
    if settings.app_mode == "live":
        key = settings.openai_api_key.get_secret_value()
        provider = OpenAIRouterProvider(
            model=settings.openai_router_model, api_key=key, timeout_seconds=12,
            max_output_tokens=600, reasoning_effort=settings.openai_router_reasoning_effort,
            prompt_cache_key="saqta-router-v1",
            compact_output=settings.openai_router_compact_output,
        )
        app.state.router = ScenarioRouter(provider=provider)
        app.state.stt = OpenAITranscriber(model=settings.openai_stt_model, api_key=key)
        app.state.tts = OpenAISynthesizer(
            model=settings.openai_tts_model, api_key=key, voice=settings.openai_tts_voice,
        )
        app.state.budget = DemoBudget(
            run_usd=settings.run_budget_usd, session_usd=settings.session_budget_usd,
        )
    else:
        app.state.router = ScenarioRouter()

    @app.get("/api/health")
    async def health():
        live = settings.app_mode == "live"
        return {
            "status": "ok", "mode": settings.app_mode, "schema_version": "1.0",
            "capabilities": {"llm_routing": live, "stt": live, "tts": live},
            "catalog_count": len(app.state.catalog),
        }

    @app.post("/api/sessions", response_model=SessionCreated, status_code=201)
    async def create_session():
        try:
            return SessionCreated(session_id=app.state.sessions.create())
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/sessions/{session_id}/turns", response_model=TurnResponse)
    async def turn(session_id: str, payload: TurnInput):
        started = perf_counter()
        session = app.state.sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        async with session.lock:
            if len(session.history) >= 10:
                raise HTTPException(409, "10 user turns reached; create a new session")
            context = RouterContext(
                text=payload.text, language=payload.language,
                history=session.history, topics=session.topics,
            )
            route_started = perf_counter()
            if settings.app_mode == "live":
                try:
                    async with app.state.paid_slots:
                        await app.state.budget.reserve("router", session_id=session_id)
                        result, detected_language = await app.state.router.route_with_language(
                            context, app.state.catalog
                        )
                except BudgetExceeded as exc:
                    raise HTTPException(429, str(exc)) from exc
                except RouterProviderError as exc:
                    raise HTTPException(502, "LLM routing is temporarily unavailable") from exc
            else:
                result = await app.state.router.route(context, app.state.catalog)
                detected_language = payload.language
            try:
                validate_decision_ids(result, app.state.catalog)
            except ValueError as exc:
                raise HTTPException(502, "Router returned invalid scenario ids") from exc
            route_ms = (perf_counter() - route_started) * 1000
            if detected_language not in {"ru", "kk", "en", "mixed"}:
                detected_language = payload.language
            if settings.app_mode == "live":
                reply = app.state.replies.compose(
                    result.decision, app.state.catalog, detected_language, payload.text,
                )
            else:
                reply = result.decision.clarification_question or "Передаю вопрос оператору."
            response = TurnResponse(
                session_id=session_id, turn_id=str(uuid4()), mode=settings.app_mode,
                transcript=payload.text, language=detected_language,
                assistant_text=reply, decision=result.decision, topics=result.topics,
                timings=Timings(
                    router_ms=round(route_ms, 1),
                    backend_total_ms=round((perf_counter() - started) * 1000, 1),
                ),
            )
            session.history.append(TurnRecord(
                user_text=payload.text, assistant_text=reply, decision=result.decision,
            ))
            session.topics = result.topics
            return response

    @app.post("/api/voice/transcribe", response_model=Transcript)
    async def transcribe(file: UploadFile = File(...), session_id: str | None = Header(None, alias="X-Session-ID")):
        if settings.app_mode != "live":
            await file.close()
            raise HTTPException(501, "STT is disabled in scaffold mode")
        mime = (file.content_type or "").split(";", 1)[0].lower()
        if mime not in ALLOWED_AUDIO_TYPES:
            await file.close()
            raise HTTPException(415, "Unsupported audio content type")
        try:
            audio = await file.read(MAX_UPLOAD_BYTES + 1)
        finally:
            await file.close()
        if len(audio) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Audio exceeds 1 MiB demo limit")
        if not audio:
            raise HTTPException(422, "Audio is empty")
        try:
            async with app.state.paid_slots:
                await app.state.budget.reserve("stt", session_id=session_id)
                result = await app.state.stt.transcribe(
                    audio, filename=file.filename or "recording.webm", language_hint="mixed",
                )
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc)) from exc
        except TranscriptionError as exc:
            raise HTTPException(502, "Audio transcription failed") from exc
        return Transcript(text=result.text, language=result.language, stt_ms=result.stt_ms)

    @app.post("/api/voice/synthesize", responses={200: {"content": {"audio/mpeg": {}}}})
    async def synthesize(payload: SpeechRequest, session_id: str | None = Header(None, alias="X-Session-ID")):
        if settings.app_mode != "live":
            raise HTTPException(501, "TTS is disabled in scaffold mode")
        if len(payload.text) > 500:
            raise HTTPException(422, "Demo speech is limited to 500 characters")
        try:
            async with app.state.paid_slots:
                await app.state.budget.reserve("tts", session_id=session_id)
                result = await app.state.tts.synthesize(payload.text, language=payload.language)
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc)) from exc
        except SpeechError as exc:
            raise HTTPException(502, "Speech generation failed") from exc
        return Response(
            content=result.audio, media_type=result.content_type,
            headers={
                "X-TTS-First-Byte-Ms": str(result.tts_first_byte_ms),
                "X-TTS-Total-Ms": str(result.tts_total_ms),
            },
        )

    @app.post("/api/voice/synthesize/stream", responses={200: {"content": {"audio/mpeg": {}}}})
    async def synthesize_stream(payload: SpeechRequest, session_id: str | None = Header(None, alias="X-Session-ID")):
        if settings.app_mode != "live":
            raise HTTPException(501, "TTS is disabled in scaffold mode")
        if len(payload.text) > 500:
            raise HTTPException(422, "Demo speech is limited to 500 characters")
        resources = AsyncExitStack()
        try:
            await resources.enter_async_context(app.state.paid_slots)
            await app.state.budget.reserve("tts", session_id=session_id)
            stream = await resources.enter_async_context(
                app.state.tts.stream(payload.text, language=payload.language))
        except BaseException as exc:
            with CancelScope(shield=True):
                await resources.aclose()
            if isinstance(exc, BudgetExceeded):
                raise HTTPException(429, str(exc)) from exc
            if isinstance(exc, SpeechError):
                raise HTTPException(502, "Speech generation failed") from exc
            raise
        return ManagedSpeechResponse(
            stream.chunks, resources=resources, media_type=stream.content_type,
            headers={"X-TTS-First-Byte-Ms": str(stream.tts_first_byte_ms),
                     "Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "src"), name="static")
    return app


app = create_app()
