# API contract v1

Source of truth: models.py, exposed through GET /openapi.json and /docs.
Shared owner: role 2. Public v1 shapes are fixed before parallel work.

## HTTP
- GET /api/health → status, mode, schema_version, capabilities, catalog_count.
  Scaffold: routing=false, stt=false, tts=false; 43 catalog items.
- POST /api/sessions → 201 {"session_id": "..."}.
- POST /api/sessions/{id}/turns → TurnResponse.
  Body: {"text":"Полис керек","language":"mixed"}.
  Errors: 404 unknown session, 409 after 10 user turns, 422 invalid input.
- POST /api/voice/transcribe → multipart field file; target response Transcript.
  Scaffold returns 501. Provider belongs to role 1 (backend/voice); endpoint to role 2.
  Language auto-detection belongs to STT/triage.
- POST /api/voice/synthesize → SpeechRequest; target response audio/mpeg bytes.
  Scaffold returns 501. TTS provider belongs to role 1; endpoint to role 2.
  API key never goes to browser.
- GET / → frontend; /static/* → frontend/src/*.

First complete voice integration uses upload/transcribe → turns → synthesize/playback.
Streaming/WebSocket is optional and added after this path works; do not assume an
undocumented WebSocket endpoint exists.

## Python
ScenarioRouter.route(context: RouterContext, catalog: list[Scenario]) -> RouteResult
is async. Platform owns session storage; router owns topic transitions.
Context includes text, requested language, last turns and topic state.
RouterContext.language=auto is a hint, not a detected language.
Platform must replace auto with detected RU/KK/mixed in live TurnResponse.

Decision.scenario_ids = ordered IDs including system intents, for official evaluator.
selected_scenario_id = primary (first list item) or null if no route selected.
action is next step, distinct from classification: SC37 may have action=transfer;
SYS_UNCLEAR may have action=clarify. Classification and execution are separate.
Scaffold returns an empty ID list + explicit unavailable certainty, never a fake prediction.
clarify requires clarification_question. Alternatives are not selected intentions.
certainties are qualitative self-reports, NOT calibrated probabilities.
If numeric confidence is later added, label it uncalibrated until validated.

Scenario normalizes catalog fields and retains source (full original record), including
identification, confirmation, slot rules and response templates. Loader does not run actions.
Any chosen ID, alternative ID or topic scenario ID must exist in the catalog.

## Trace and measurement
TurnResponse contains schema_version, session_id, turn_id, mode, transcript, language,
assistant_text, decision, topics, timings.
timings.router_ms = time through fully validated decision, not first token.
backend_total_ms = API handler duration; does not include microphone, STT, playback.
stt_ms / tts_first_byte_ms / end_to_audio_ms are null until measured.
Never use 0 to imply a measurement was taken. Browser measures true end-to-audio
from actual end of speech to audible playback with one monotonic browser clock;
don't subtract server timestamps from client timestamps.
Future streaming events must retain turn_id to prevent overlapping-turn UI corruption.

## Error & safety boundaries
Invalid router IDs → 502 without adding a turn. Provider errors must remain visible.
Irreversible actions require preview and explicit confirmation, enforced in platform.
UI can display status but cannot authorize an action by modifying request flags.
Scaffold has no action endpoint and performs no business changes.
