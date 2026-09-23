/**
 * Frontend API client strictly complying with contracts/models.py and contracts/README.md.
 * Single entry point for all HTTP communication with backend.
 */

export class ApiError extends Error {
  /**
   * @param {number} status
   * @param {string} detail
   * @param {unknown} [raw]
   */
  constructor(status, detail, raw = null) {
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.raw = raw;
    this.isNotImplemented = status === 501;
    this.isTurnLimitReached = status === 409;
    this.isNotFound = status === 404;
    this.isValidationError = status === 422;
  }
}

/**
 * Universal JSON request helper
 * @param {string} path
 * @param {RequestInit} [options={}]
 * @returns {Promise<any>}
 */
async function jsonRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (netErr) {
    throw new ApiError(0, `Сетевая ошибка: ${netErr.message || "Не удалось связаться с сервером"}`, netErr);
  }

  if (!response.ok) {
    let errorPayload = {};
    try {
      errorPayload = await response.json();
    } catch {
      // response might be plain text or empty
    }
    const message = typeof errorPayload.detail === "string" 
      ? errorPayload.detail 
      : `Ошибка сервера (HTTP ${response.status})`;
    throw new ApiError(response.status, message, errorPayload);
  }

  return response.json();
}

/**
 * Health check and capability discovery
 * @returns {Promise<{ status: string, mode: string, schema_version: string, capabilities: { routing: boolean, stt: boolean, tts: boolean }, catalog_count: number }>}
 */
export async function health() {
  return jsonRequest("/api/health");
}

/**
 * Create a new conversation session
 * @returns {Promise<{ session_id: string }>}
 */
export async function createSession() {
  return jsonRequest("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Send a user turn to the dialogue router
 * @param {string} sessionId
 * @param {string} text
 * @param {'auto'|'ru'|'kk'|'mixed'} [language='auto']
 * @returns {Promise<import('../../contracts/models.py').TurnResponse>}
 */
export async function sendTurn(sessionId, text, language = "auto") {
  if (!sessionId) {
    throw new ApiError(400, "Отсутствует идентификатор сессии");
  }
  const cleanText = (text || "").trim();
  if (!cleanText) {
    throw new ApiError(422, "Текст реплики не может быть пустым");
  }

  const payload = {
    text: cleanText,
    language: language || "auto",
  };

  const data = await jsonRequest(`/api/sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return normalizeTurnResponse(data);
}

/**
 * Upload voice audio file for speech-to-text transcription
 * @param {Blob|File} audioBlob
 * @param {string} [filename='speech.webm']
 * @returns {Promise<{ text: string, language: 'ru'|'kk'|'mixed'|'auto', stt_ms: number }>}
 */
export async function transcribeAudio(audioBlob, filename = "speech.webm", sessionId = null) {
  if (!audioBlob) {
    throw new ApiError(400, "Аудиофайл не передан");
  }

  const formData = new FormData();
  formData.append("file", audioBlob, filename);

  let response;
  try {
    response = await fetch("/api/voice/transcribe", {
      method: "POST",
      headers: sessionId ? { "X-Session-ID": sessionId } : {},
      body: formData,
    });
  } catch (netErr) {
    throw new ApiError(0, `Сетевая ошибка при отправке аудио: ${netErr.message}`, netErr);
  }

  if (response.status === 501) {
    throw new ApiError(501, "Голосовой ввод (STT) не подключен в режиме scaffold (HTTP 501)");
  }

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const message = typeof errorPayload.detail === "string" ? errorPayload.detail : `Ошибка STT (HTTP ${response.status})`;
    throw new ApiError(response.status, message, errorPayload);
  }

  const data = await response.json();
  return {
    text: (data.text || "").trim(),
    language: data.language || "auto",
    stt_ms: typeof data.stt_ms === "number" ? data.stt_ms : null,
  };
}

/**
 * Synthesize speech from assistant text
 * @param {string} text
 * @param {'auto'|'ru'|'kk'|'mixed'} [language='auto']
 * @returns {Promise<{ audioBlob: Blob, ttsMs: number|null }>}
 */
export async function synthesizeSpeech(text, language = "auto", sessionId = null, stream = false) {
  const cleanText = (text || "").trim();
  if (!cleanText) {
    throw new ApiError(422, "Текст для озвучивания не может быть пустым");
  }

  let response;
  try {
    response = await fetch(stream ? "/api/voice/synthesize/stream" : "/api/voice/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(sessionId ? { "X-Session-ID": sessionId } : {}) },
      body: JSON.stringify({ text: cleanText, language: language || "auto" }),
    });
  } catch (netErr) {
    throw new ApiError(0, `Сетевая ошибка при запросе синтеза: ${netErr.message}`, netErr);
  }

  if (response.status === 501) {
    throw new ApiError(501, "Голосовой ответ (TTS) не подключен в режиме scaffold (HTTP 501)");
  }

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const message = typeof errorPayload.detail === "string" ? errorPayload.detail : `Ошибка TTS (HTTP ${response.status})`;
    throw new ApiError(response.status, message, errorPayload);
  }

  // Parse optional latency header if provided by backend in the future
  const ttsHeader = response.headers.get("x-tts-first-byte-ms");
  const ttsMs = ttsHeader ? parseFloat(ttsHeader) : null;

  if (stream) return { response, ttsMs };
  const audioBlob = await response.blob();
  return { audioBlob, ttsMs };
}

/**
 * Normalizes and validates the incoming TurnResponse against contracts/models.py
 * Ensures nulls are preserved and no missing keys throw client runtime errors.
 */
function normalizeTurnResponse(raw) {
  if (!raw || typeof raw !== "object") {
    throw new ApiError(502, "Сервер вернул некорректный формат ответа");
  }

  const decision = raw.decision || {};
  const timings = raw.timings || {};

  return {
    schema_version: raw.schema_version || "1.0",
    session_id: raw.session_id || "",
    turn_id: raw.turn_id || "",
    mode: raw.mode === "live" ? "live" : "scaffold",
    transcript: typeof raw.transcript === "string" ? raw.transcript : "",
    language: raw.language || "auto",
    assistant_text: typeof raw.assistant_text === "string" ? raw.assistant_text : "",
    decision: {
      action: decision.action || "route",
      selected_scenario_id: decision.selected_scenario_id ?? null,
      scenario_ids: Array.isArray(decision.scenario_ids) ? decision.scenario_ids : [],
      rationale: typeof decision.rationale === "string" ? decision.rationale : "",
      certainty: decision.certainty || "unavailable",
      alternatives: Array.isArray(decision.alternatives) ? decision.alternatives : [],
      topic_operation: decision.topic_operation || "none",
      slots: Array.isArray(decision.slots) ? decision.slots : [],
      clarification_question: decision.clarification_question ?? null,
      requires_confirmation: Boolean(decision.requires_confirmation),
    },
    topics: Array.isArray(raw.topics) ? raw.topics : [],
    timings: {
      router_ms: typeof timings.router_ms === "number" ? timings.router_ms : null,
      backend_total_ms: typeof timings.backend_total_ms === "number" ? timings.backend_total_ms : null,
      stt_ms: typeof timings.stt_ms === "number" ? timings.stt_ms : null,
      tts_first_byte_ms: typeof timings.tts_first_byte_ms === "number" ? timings.tts_first_byte_ms : null,
      end_to_audio_ms: typeof timings.end_to_audio_ms === "number" ? timings.end_to_audio_ms : null,
    },
  };
}
