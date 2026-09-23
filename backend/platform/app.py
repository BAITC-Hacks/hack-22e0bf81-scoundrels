from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contracts.models import (
    RouterContext, SessionCreated, SpeechRequest, Timings, Transcript,
    TurnInput, TurnRecord, TurnResponse,
)
from backend.router.catalog import load_catalog, validate_decision_ids
from backend.router.service import ScenarioRouter
from .config import ROOT, Settings
from .sessions import SessionStore

def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="RouteMap · Voice Router", version="0.1.0")
    app.state.sessions = SessionStore()
    app.state.router = ScenarioRouter()
    app.state.catalog = load_catalog(ROOT / "case_2/voice_router_dataset/scenarios.json")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok", "mode": settings.app_mode, "schema_version": "1.0",
            "capabilities": {"llm_routing": False, "stt": False, "tts": False},
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
            result = await app.state.router.route(context, app.state.catalog)
            try:
                validate_decision_ids(result, app.state.catalog)
            except ValueError as exc:
                raise HTTPException(502, "Router returned invalid scenario ids") from exc
            route_ms = (perf_counter() - route_started) * 1000
            # No business actions implemented; scaffold only asks for clarification.
            reply = result.decision.clarification_question or "Передаю вопрос оператору."
            response = TurnResponse(
                session_id=session_id, turn_id=str(uuid4()), mode="scaffold",
                transcript=payload.text, language=payload.language,
                assistant_text=reply, decision=result.decision, topics=result.topics,
                timings=Timings(router_ms=route_ms, backend_total_ms=(perf_counter()-started)*1000),
            )
            session.history.append(TurnRecord(
                user_text=payload.text, assistant_text=reply, decision=result.decision))
            session.topics = result.topics
            return response

    @app.post("/api/voice/transcribe", response_model=Transcript)
    async def transcribe(file: UploadFile = File(...)):
        await file.close()
        raise HTTPException(501, "STT provider: owner 1; HTTP integration: owner 2; not connected yet")

    @app.post("/api/voice/synthesize", responses={200: {"content": {"audio/mpeg": {}}}})
    async def synthesize(payload: SpeechRequest):
        raise HTTPException(501, "TTS provider: owner 1; HTTP integration: owner 2; not connected yet")

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "src"), name="static")
    return app

app = create_app()
