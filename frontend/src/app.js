/**
 * RouteMap Frontend Application Controller.
 * Manages session lifecycle, push-to-talk recording, TTS playback,
 * turn limitation (10-turn limit), supervisor explainability,
 * latency waterfall tracking (p50/p95), and dataset/session replay.
 */

import { health, createSession, sendTurn, transcribeAudio, synthesizeSpeech, ApiError } from "./api.js";
import { renderSupervisorPanel } from "./supervisor.js";
import { VoiceRecorder, AudioPlayer } from "./audio.js";
import { SessionMetricsTracker, renderMetricsPanel } from "./metrics.js";
import { getLocale } from "./i18n.js";
import { DATASET_SAMPLES, exportSessionToFile, parseSessionFile } from "./replay.js";

// DOM Elements
const uiLangSelect = document.querySelector("#ui-lang-select");
const brandSub = document.querySelector("#brand-sub");
const brandDesc = document.querySelector("#brand-desc");
const statusBadge = document.querySelector("#status-badge");
const sessionInfo = document.querySelector("#session-info");
const turnCounter = document.querySelector("#turn-counter");
const noticeBanner = document.querySelector("#notice-banner");
const noticeText = document.querySelector("#notice-text");

const turnForm = document.querySelector("#turn-form");
const languageSelect = document.querySelector("#language-select");
const languageLabel = document.querySelector("#language-label");
const textInput = document.querySelector("#text-input");
const sendBtn = document.querySelector("#send-btn");
const sendBtnLabel = document.querySelector("#send-btn-label");
const micBtn = document.querySelector("#mic-btn");
const micLabel = document.querySelector("#mic-label");
const resetBtn = document.querySelector("#reset-btn");
const resetBtnLabel = document.querySelector("#reset-btn-label");
const inputError = document.querySelector("#input-error");

const replyHeading = document.querySelector("#reply-heading");
const replyText = document.querySelector("#reply-text");
const audioPlayerContainer = document.querySelector("#audio-player-container");
const ttsAudioPlayer = document.querySelector("#tts-audio-player");

const exportSessionBtn = document.querySelector("#export-session-btn");
const importSessionInput = document.querySelector("#import-session-input");
const datasetSampleSelect = document.querySelector("#dataset-sample-select");

const metricsContainer = document.querySelector("#metrics-container");
const supervisorTrace = document.querySelector("#supervisor-trace");
const rawJsonTrace = document.querySelector("#raw-json-trace");
const toggleJsonBtn = document.querySelector("#toggle-json-btn");

// Subsystems
const voiceRecorder = new VoiceRecorder();
const audioPlayer = new AudioPlayer(ttsAudioPlayer);
const sessionTracker = new SessionMetricsTracker();

// Application State
let currentSessionId = null;
let currentTurnCount = 0;
const MAX_TURNS = 10;
let isBusy = false;
let sessionHistory = [];
let lastSpeechEndTimestamp = null;
let showRawJson = false;
let currentUiLang = "ru";

/**
 * Updates interface text based on selected UI language
 * @param {'ru'|'kk'} lang
 */
function applyLocalization(lang) {
  currentUiLang = lang;
  const dict = getLocale(lang);
  brandSub.textContent = dict.brandSub;
  brandDesc.textContent = dict.brandDesc;
  document.querySelector("#customer-heading").textContent = dict.customerHeading;
  document.querySelector("#supervisor-heading").textContent = dict.supervisorHeading;
  languageLabel.textContent = dict.languageLabel;
  textInput.placeholder = dict.inputPlaceholder;
  sendBtnLabel.textContent = dict.sendBtn;
  micLabel.textContent = dict.micBtn;
  resetBtnLabel.textContent = dict.resetBtn;
  replyHeading.textContent = dict.replyHeading;
  toggleJsonBtn.textContent = showRawJson ? dict.toggleStructure : dict.toggleJson;

  updateTurnCounter();

  // Re-render supervisor and metrics with current language
  const lastTurn = sessionHistory[sessionHistory.length - 1] || null;
  renderSupervisorPanel(supervisorTrace, lastTurn, currentUiLang);
  renderMetricsPanel(metricsContainer, lastTurn ? lastTurn.timings : null, sessionTracker, currentUiLang);
}

/**
 * Updates UI busy/disabled states
 * @param {boolean} busy
 */
function setBusy(busy) {
  isBusy = busy;
  const canSend = !busy && currentSessionId && currentTurnCount < MAX_TURNS;
  sendBtn.disabled = !canSend;
  micBtn.disabled = !canSend;
  resetBtn.disabled = busy;
  exportSessionBtn.disabled = busy || sessionHistory.length === 0;

  if (busy) {
    sendBtnLabel.textContent = currentUiLang === "kk" ? "Жіберілуде…" : "Отправка…";
  } else {
    sendBtnLabel.textContent = getLocale(currentUiLang).sendBtn;
  }
}

/**
 * Updates the turn counter display and warning banners
 */
function updateTurnCounter() {
  const dict = getLocale(currentUiLang);
  turnCounter.textContent = dict.turnCounter(currentTurnCount, MAX_TURNS);
  if (currentTurnCount >= MAX_TURNS) {
    turnCounter.style.color = "var(--accent-red)";
    showError(dict.turnLimitError);
  } else if (currentTurnCount >= 8) {
    turnCounter.style.color = "var(--accent-amber)";
  } else {
    turnCounter.style.color = "var(--accent-cyan)";
  }
}

/**
 * Shows an inline error message
 * @param {string} msg
 */
function showError(msg) {
  if (msg) {
    inputError.textContent = msg;
    inputError.hidden = false;
  } else {
    inputError.textContent = "";
    inputError.hidden = true;
  }
}

/**
 * Starts a fresh conversation session
 */
async function initSession() {
  setBusy(true);
  showError("");
  currentTurnCount = 0;
  sessionHistory = [];
  sessionTracker.reset();
  lastSpeechEndTimestamp = null;
  datasetSampleSelect.value = "";

  updateTurnCounter();
  replyText.textContent = getLocale(currentUiLang).waitingReply;
  audioPlayer.stop();
  audioPlayerContainer.hidden = true;

  renderSupervisorPanel(supervisorTrace, null, currentUiLang);
  renderMetricsPanel(metricsContainer, null, sessionTracker, currentUiLang);
  rawJsonTrace.textContent = "";

  try {
    const sessionData = await createSession();
    currentSessionId = sessionData.session_id;
    sessionInfo.textContent = `Сессия: ${currentSessionId.substring(0, 8)}…`;
    statusBadge.className = "status-pill status-online";
    statusBadge.textContent = "Подключено";
  } catch (err) {
    currentSessionId = null;
    sessionInfo.textContent = "Сессия: ошибка";
    statusBadge.className = "status-pill status-error";
    statusBadge.textContent = "Сбой соединения";
    showError(err.message);
  } finally {
    setBusy(false);
  }
}

/**
 * Executes a dialogue turn (text or transcribed speech)
 * @param {string} text
 * @param {string} lang
 * @param {number|null} [speechEndMs=null]
 */
async function executeTurn(text, lang, speechEndMs = null) {
  if (!text || isBusy || !currentSessionId) return;

  if (currentTurnCount >= MAX_TURNS) {
    showError(getLocale(currentUiLang).turnLimitError);
    return;
  }

  showError("");
  setBusy(true);

  try {
    // 1. Send turn to router
    const result = await sendTurn(currentSessionId, text, lang);
    currentTurnCount += 1;
    updateTurnCounter();

    // 2. Display assistant text response
    replyText.textContent = result.assistant_text || "(Пустой ответ)";

    // 3. Attempt TTS speech synthesis if text is available
    if (result.assistant_text) {
      try {
        const { audioBlob, ttsMs } = await synthesizeSpeech(result.assistant_text, result.language);
        if (typeof ttsMs === "number") {
          result.timings.tts_first_byte_ms = ttsMs;
        }

        // Configure playback listener for monotonic end-to-audio measurement
        if (speechEndMs) {
          audioPlayer.onPlaybackStart = (playTimestamp) => {
            const endToAudio = Math.max(0, playTimestamp - speechEndMs);
            result.timings.end_to_audio_ms = endToAudio;
            sessionTracker.recordSample(endToAudio);
            renderMetricsPanel(metricsContainer, result.timings, sessionTracker, currentUiLang);
            audioPlayer.onPlaybackStart = null;
          };
        }

        audioPlayerContainer.hidden = false;
        await audioPlayer.playBlob(audioBlob);
      } catch (ttsErr) {
        // Honest 501 scaffold handling: log note, do not break text response
        if (ttsErr instanceof ApiError && ttsErr.isNotImplemented) {
          console.info("TTS is not implemented on server yet (HTTP 501)");
        } else {
          console.warn("TTS playback note:", ttsErr.message);
        }
      }
    }

    // 4. Update session history and panels
    sessionHistory.push(result);
    renderSupervisorPanel(supervisorTrace, result, currentUiLang);
    renderMetricsPanel(metricsContainer, result.timings, sessionTracker, currentUiLang);
    rawJsonTrace.textContent = JSON.stringify(result, null, 2);

    // 5. Update server mode indicator
    if (result.mode === "scaffold") {
      noticeBanner.className = "banner banner-scaffold";
      noticeText.textContent = getLocale(currentUiLang).scaffoldNotice;
    } else {
      noticeBanner.className = "banner banner-online";
      noticeText.textContent = getLocale(currentUiLang).liveNotice;
    }

  } catch (err) {
    if (err instanceof ApiError && err.isTurnLimitReached) {
      currentTurnCount = MAX_TURNS;
      updateTurnCounter();
      showError("Сервер отклонил запрос: исчерпан лимит 10 реплик (409 Conflict).");
    } else {
      showError(err.message);
    }
  } finally {
    setBusy(false);
  }
}

/**
 * Handle text form submission
 */
async function handleTextSubmit(event) {
  event.preventDefault();
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = "";
  lastSpeechEndTimestamp = null;
  await executeTurn(text, languageSelect.value, null);
}

// ----------------------------------------------------
// Audio & Push-To-Talk Setup
// ----------------------------------------------------
voiceRecorder.onStateChange = (state) => {
  if (state === "recording") {
    micBtn.classList.add("recording");
    micLabel.textContent = getLocale(currentUiLang).micRecording;
  } else if (state === "processing") {
    micBtn.classList.remove("recording");
    micLabel.textContent = getLocale(currentUiLang).micProcessing;
  } else {
    micBtn.classList.remove("recording");
    micLabel.textContent = getLocale(currentUiLang).micBtn;
  }
};

voiceRecorder.onError = (err) => {
  showError(err.message);
};

voiceRecorder.onAudioReady = async (audioBlob, stopTimestamp) => {
  lastSpeechEndTimestamp = stopTimestamp;
  setBusy(true);
  try {
    const transcriptResult = await transcribeAudio(audioBlob);
    if (transcriptResult.text) {
      textInput.value = transcriptResult.text;
      await executeTurn(transcriptResult.text, transcriptResult.language || languageSelect.value, stopTimestamp);
    } else {
      showError("Речь не распознана или была пустой. Попробуйте снова или введите текст.");
    }
  } catch (err) {
    if (err instanceof ApiError && err.isNotImplemented) {
      showError("Голосовой ввод (STT) честно возвращает HTTP 501 в scaffold-режиме. Используйте текстовый ввод.");
    } else {
      showError(`Ошибка STT: ${err.message}`);
    }
  } finally {
    setBusy(false);
  }
};

// Push-to-Talk (Hold to speak, release to send) + Click-toggle for accessibility
let pttPointerDown = false;

micBtn.addEventListener("pointerdown", async (e) => {
  if (isBusy || !currentSessionId || currentTurnCount >= MAX_TURNS) return;
  e.preventDefault();
  pttPointerDown = true;
  showError("");
  try {
    await voiceRecorder.start();
  } catch (err) {
    pttPointerDown = false;
  }
});

window.addEventListener("pointerup", (e) => {
  if (pttPointerDown) {
    pttPointerDown = false;
    voiceRecorder.stop();
  }
});

// ----------------------------------------------------
// Replay & Export / Import Handlers
// ----------------------------------------------------
exportSessionBtn.addEventListener("click", () => {
  if (sessionHistory.length === 0) return;
  exportSessionToFile(currentSessionId, sessionHistory);
});

importSessionInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;

  try {
    const loadedTurns = await parseSessionFile(file);
    if (loadedTurns.length === 0) {
      showError("Файл не содержит записей ходов.");
      return;
    }
    sessionHistory = loadedTurns;
    currentTurnCount = loadedTurns.length;
    updateTurnCounter();
    
    // Display last turn
    const last = loadedTurns[loadedTurns.length - 1];
    replyText.textContent = last.assistant_text || "(Ответ из Replay)";
    renderSupervisorPanel(supervisorTrace, last, currentUiLang);
    renderMetricsPanel(metricsContainer, last.timings, sessionTracker, currentUiLang);
    rawJsonTrace.textContent = JSON.stringify(last, null, 2);

    noticeBanner.className = "banner banner-scaffold";
    noticeText.textContent = "Режим Replay: отображается ранее сохраненная сессия.";
    exportSessionBtn.disabled = false;
  } catch (err) {
    showError(`Ошибка чтения файла сессии: ${err.message}`);
  } finally {
    importSessionInput.value = "";
  }
});

datasetSampleSelect.addEventListener("change", (e) => {
  const selectedId = e.target.value;
  if (!selectedId) return;

  const found = DATASET_SAMPLES.find((s) => s.id === selectedId);
  if (!found) return;

  const lastTurn = found.turns[found.turns.length - 1];
  replyText.textContent = lastTurn.assistant_text;
  renderSupervisorPanel(supervisorTrace, lastTurn, currentUiLang);
  renderMetricsPanel(metricsContainer, lastTurn.timings, sessionTracker, currentUiLang);
  rawJsonTrace.textContent = JSON.stringify(found, null, 2);

  noticeBanner.className = "banner banner-scaffold";
  noticeText.textContent = `Образец из датасета (${found.title}) · Без вызова LLM.`;
});

// UI Language Switch
uiLangSelect.addEventListener("change", (e) => {
  applyLocalization(e.target.value);
});

// Toggle Raw JSON
toggleJsonBtn.addEventListener("click", () => {
  showRawJson = !showRawJson;
  rawJsonTrace.hidden = !showRawJson;
  supervisorTrace.hidden = showRawJson;
  const dict = getLocale(currentUiLang);
  toggleJsonBtn.textContent = showRawJson ? dict.toggleStructure : dict.toggleJson;
});

// Form and Reset
turnForm.addEventListener("submit", handleTextSubmit);
resetBtn.addEventListener("click", initSession);

// Bootstrap
(async function bootstrap() {
  applyLocalization("ru");
  try {
    const healthData = await health();
    if (healthData.capabilities && healthData.capabilities.routing) {
      noticeBanner.className = "banner banner-online";
      noticeText.textContent = "Сервер готов: маршрутизация активна.";
    }
    await initSession();
  } catch (err) {
    statusBadge.className = "status-pill status-error";
    statusBadge.textContent = "Сервер недоступен";
    showError(`Сервер недоступен: ${err.message}. Запустите сервер: python run.py`);
  }
})();
