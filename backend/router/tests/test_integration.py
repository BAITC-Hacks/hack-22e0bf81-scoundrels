import pytest
from fastapi.testclient import TestClient
from contracts.models import TurnResponse
from backend.platform.app import create_app
from backend.router.service import ScenarioRouter
from backend.router.providers.openai_provider import RouterProviderError
from .helpers import ScriptedProvider, prediction


def test_platform_consumes_v1_route_and_persists_topics(monkeypatch):
    monkeypatch.setenv("APP_MODE", "scaffold")
    app = create_app()
    app.state.router = ScenarioRouter(ScriptedProvider(prediction("SC27")), mode="live")
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        response = client.post(f"/api/sessions/{sid}/turns", json={"text": "Хочу продлить", "language": "ru"})
        parsed = TurnResponse.model_validate(response.json())
        assert parsed.decision.scenario_ids == ["SC27"]
        assert parsed.topics[0].status == "active"
        assert app.state.sessions.get(sid).topics == parsed.topics
        # This app is still scaffold; final answer/live mode are the integrator's work.
        assert parsed.mode == "scaffold"


def test_failed_provider_does_not_mutate_platform_session(monkeypatch):
    monkeypatch.setenv("APP_MODE", "scaffold")
    app = create_app()
    app.state.router = ScenarioRouter(ScriptedProvider(prediction("unknown")), mode="live")
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        # Existing platform still needs RouterProviderError -> HTTP 502 mapping.
        with pytest.raises(RouterProviderError):
            client.post(f"/api/sessions/{sid}/turns", json={"text": "запрос"})
        session = app.state.sessions.get(sid)
        assert session.topics == [] and session.history == []
