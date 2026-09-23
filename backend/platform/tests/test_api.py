import pytest
from fastapi.testclient import TestClient
from backend.platform.app import create_app
from contracts.models import Decision, RouteResult, TurnResponse

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_MODE", "scaffold")
    with TestClient(create_app()) as test_client:
        yield test_client

def session_id(client):
    response = client.post("/api/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]

def test_static_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["capabilities"]["llm_routing"] is False

def test_text_roundtrip_contract(client):
    sid = session_id(client)
    response = client.post(f"/api/sessions/{sid}/turns", json={"text": "Полис керек", "language": "mixed"})
    assert response.status_code == 200
    parsed = TurnResponse.model_validate(response.json())
    assert parsed.transcript == "Полис керек"
    assert parsed.mode == "scaffold"
    assert parsed.timings.end_to_audio_ms is None
    assert parsed.timings.router_ms >= 0
    assert parsed.decision.selected_scenario_id is None

def test_unknown_session(client):
    assert client.post("/api/sessions/missing/turns", json={"text": "hi"}).status_code == 404

def test_blank_turn_does_not_change_history(client):
    sid = session_id(client)
    assert client.post(f"/api/sessions/{sid}/turns", json={"text": " "}).status_code == 422
    assert not client.app.state.sessions.get(sid).history

def test_session_isolation_and_limit(client):
    first, second = session_id(client), session_id(client)
    for _ in range(10):
        assert client.post(f"/api/sessions/{first}/turns", json={"text": "hello"}).status_code == 200
    assert client.post(f"/api/sessions/{first}/turns", json={"text": "11"}).status_code == 409
    assert not client.app.state.sessions.get(second).history
    assert client.post(f"/api/sessions/{second}/turns", json={"text": "hello"}).status_code == 200

def test_invalid_router_id_rejected_without_state_mutation(client):
    class BadRouter:
        async def route(self, context, catalog):
            return RouteResult(decision=Decision(
                action="route", selected_scenario_id="invented", scenario_ids=["invented"], rationale="bad",
                certainty="high", topic_operation="create"))
    client.app.state.router = BadRouter()
    sid = session_id(client)
    response = client.post(f"/api/sessions/{sid}/turns", json={"text": "hello"})
    assert response.status_code == 502
    assert not client.app.state.sessions.get(sid).history

def test_voice_stubs_explicit(client):
    assert client.post("/api/voice/synthesize", json={"text": "hello"}).status_code == 501
    assert client.post("/api/voice/transcribe", files={"file": ("voice.webm", b"test", "audio/webm")}).status_code == 501

def test_new_app_has_no_previous_sessions():
    assert create_app().state.sessions is not create_app().state.sessions
