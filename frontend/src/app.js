/**
 * RouteMap Frontend Application Controller.
 * Manages session lifecycle, push-to-talk recording, TTS playback,
 * turn limitation (10-turn limit), supervisor explainability,
 * latency waterfall tracking (p50/p95), full bilingual localization (RU/KK),
 * and dataset/session replay.
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

const replayToolsHeading = document.querySelector("#replay-tools-heading");
const exportSessionBtn = document.querySelector("#export-session-btn");
const importSessionLabel = document.querySelector("#import-session-label");
const importSessionInput = document.querySelector("#import-session-input");
const datasetSampleSelect = document.querySelector("#dataset-sample-select");

const metricsContainer = document.querySelector("#metrics-container");
const supervisorTrace = document.querySelector("#supervisor-trace");
const rawJsonTrace = document.querySelector("#raw-json-trace");
const toggleJsonBtn = document.querySelector("#toggle-json-btn");

const themeToggleBtn = document.querySelector("#theme-toggle-btn");
const themeIcon = document.querySelector("#theme-icon");
const themeLabel = document.querySelector("#theme-label");

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
let currentTheme = localStorage.getItem("routemap_theme") || "dark";

// System status tracking for bilingual updates
let currentConnectionStatus = "connecting"; // 'connecting' | 'online' | 'error' | 'unavailable'
let currentNoticeType = "scaffold"; // 'scaffold' | 'live' | 'ready' | 'replay' | 'sample'
let currentSampleTitle = "";

/**
 * Sets active theme (dark or light)
 * @param {'dark'|'light'} theme
 */
function applyTheme(theme) {
  currentTheme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("routemap_theme", theme);
  } catch {
    // ignore storage restrictions
  }
  const dict = getLocale(currentUiLang);
  if (themeIcon) themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
  if (themeLabel) themeLabel.textContent = theme === "dark" ? dict.themeDark : dict.themeLight;
  if (themeToggleBtn) themeToggleBtn.title = dict.themeToggleTitle;
}

/**
 * Updates interface text based on selected UI language
 * @param {'ru'|'kk'} lang
 */
function applyLocalization(lang) {
  currentUiLang = lang;
  const dict = getLocale(lang);

  // Brand and headers
  brandSub.textContent = dict.brandSub;
  brandDesc.textContent = dict.brandDesc;
  document.querySelector("#customer-heading").textContent = dict.customerHeading;
  document.querySelector("#supervisor-heading").textContent = dict.supervisorHeading;

  // Form labels & buttons
  languageLabel.textContent = dict.languageLabel;
  textInput.placeholder = dict.inputPlaceholder;
  sendBtnLabel.textContent = dict.sendBtn;
  micLabel.textContent = dict.micBtn;
  resetBtnLabel.textContent = dict.resetBtn;
  replyHeading.textContent = dict.replyHeading;
  toggleJsonBtn.textContent = showRawJson ? dict.toggleStructure : dict.toggleJson;

  // Replay tools section
  if (replayToolsHeading) replayToolsHeading.textContent = dict.replayToolsHeading;
  exportSessionBtn.textContent = dict.exportSession;
  if (importSessionLabel) importSessionLabel.textContent = dict.importSession;

  // Request Language Select Options (Auto, RU, KK, Mixed)
  const langOpts = dict.requestLanguageOptions;
  if (langOpts) {
    Array.from(languageSelect.options).forEach((opt) => {
      if (langOpts[opt.value]) {
        opt.textContent = langOpts[opt.value];
      }
    });
  }

  // Dataset Sample Select Options
  const sampleOpts = dict.datasetSampleOptions;
  if (sampleOpts) {
    Array.from(datasetSampleSelect.options).forEach((opt) => {
      const key = opt.value || "default";
      if (sampleOpts[key]) {
        opt.textContent = sampleOpts[key];
      }
    });
  }

  // Connection status pill in the header
  if (currentConnectionStatus === "connecting") {
    statusBadge.textContent = dict.statusConnecting;
  } else if (currentConnectionStatus === "online") {
    statusBadge.textContent = dict.statusOnline;
  } else if (currentConnectionStatus === "error") {
    statusBadge.textContent = dict.statusError;
  } else if (currentConnectionStatus === "unavailable") {
    statusBadge.textContent = dict.statusUnavailable;
  }

  // Session ID label
  if (currentSessionId) {
    sessionInfo.textContent = dict.sessionLabel(currentSessionId.substring(0, 8));
  } else {
    sessionInfo.textContent = dict.sessionError;
  }

  // Notice banner
  if (currentNoticeType === "scaffold") {
    noticeText.textContent = dict.scaffoldNotice;
  } else if (currentNoticeType === "live") {
    noticeText.textContent = dict.liveNotice;
  } else if (currentNoticeType === "ready") {
    noticeText.textContent = dict.serverReadyNotice;
  } else if (currentNoticeType === "replay") {
    noticeText.textContent = dict.replayBanner;
  } else if (currentNoticeType === "sample") {
    noticeText.textContent = dict.datasetSampleBanner(currentSampleTitle);
  }

  // Waiting reply text if no turns sent yet
  if (sessionHistory.length === 0) {
    replyText.textContent = dict.waitingReply;
  }

  // Theme button label and title
  if (themeIcon) themeIcon.textContent = currentTheme === "dark" ? "🌙" : "☀️";
  if (themeLabel) themeLabel.textContent = currentTheme === "dark" ? dict.themeDark : dict.themeLight;
  if (themeToggleBtn) themeToggleBtn.title = dict.themeToggleTitle;

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

  const dict = getLocale(currentUiLang);
  updateTurnCounter();
  replyText.textContent = dict.waitingReply;
  audioPlayer.stop();
  audioPlayer.onPlaybackStart = null;
  audioPlayerContainer.hidden = true;

  renderSupervisorPanel(supervisorTrace, null, currentUiLang);
  renderMetricsPanel(metricsContainer, null, sessionTracker, currentUiLang);
  rawJsonTrace.textContent = "";

  try {
    currentConnectionStatus = "connecting";
    statusBadge.className = "status-pill status-connecting";
    statusBadge.textContent = dict.statusConnecting;

    const sessionData = await createSession();
    currentSessionId = sessionData.session_id;
    currentConnectionStatus = "online";
    sessionInfo.textContent = dict.sessionLabel(currentSessionId.substring(0, 8));
    statusBadge.className = "status-pill status-online";
    statusBadge.textContent = dict.statusOnline;
  } catch (err) {
    currentSessionId = null;
    currentConnectionStatus = "error";
    sessionInfo.textContent = dict.sessionError;
    statusBadge.className = "status-pill status-error";
    statusBadge.textContent = dict.statusError;
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
 * @param {boolean} [fromRecording=false] Continue while STT owns the busy state.
 * @param {number|null} [sttMs=null] Server transcription duration, if measured.
 */
async function executeTurn(text, lang, speechEndMs = null, fromRecording = false, sttMs = null) {
  if (!text || (isBusy && !fromRecording) || !currentSessionId) return;

  const dict = getLocale(currentUiLang);

  if (currentTurnCount >= MAX_TURNS) {
    showError(dict.turnLimitError);
    return;
  }

  showError("");
  setBusy(true);
  audioPlayer.stop();
  audioPlayer.onPlaybackStart = null;

  try {
    // 1. Send turn to router
    const result = await sendTurn(currentSessionId, text, lang);
    if (typeof sttMs === "number") result.timings.stt_ms = sttMs;
    currentTurnCount += 1;
    updateTurnCounter();

    // 2. Display assistant text response
    replyText.textContent = result.assistant_text || "(Пустой ответ)";
    // Show the routing decision as soon as it is ready, independently of TTS.
    sessionHistory.push(result);
    renderSupervisorPanel(supervisorTrace, result, currentUiLang);
    renderMetricsPanel(metricsContainer, result.timings, sessionTracker, currentUiLang);
    rawJsonTrace.textContent = JSON.stringify(result, null, 2);

    // 3. Attempt TTS speech synthesis if text is available
    if (result.assistant_text) {
      try {
        const { response, ttsMs } = await synthesizeSpeech(result.assistant_text, result.language, currentSessionId, true);
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
            rawJsonTrace.textContent = JSON.stringify(result, null, 2);
            audioPlayer.onPlaybackStart = null;
          };
        }

        audioPlayerContainer.hidden = false;
        await audioPlayer.playResponse(response);
      } catch (ttsErr) {
        // Honest 501 scaffold handling: log note, do not break text response
        if (ttsErr instanceof ApiError && ttsErr.isNotImplemented) {
          console.info("TTS is not implemented on server yet (HTTP 501)");
        } else {
          console.warn("TTS playback note:", ttsErr.message);
          showError(`Не удалось воспроизвести голосовой ответ: ${ttsErr.message}`);
        }
      }
    }

    // 4. Update session history and panels
    renderSupervisorPanel(supervisorTrace, result, currentUiLang);
    renderMetricsPanel(metricsContainer, result.timings, sessionTracker, currentUiLang);
    rawJsonTrace.textContent = JSON.stringify(result, null, 2);

    // 5. Update server mode indicator
    if (result.mode === "scaffold") {
      currentNoticeType = "scaffold";
      noticeBanner.className = "banner banner-scaffold";
      noticeText.textContent = dict.scaffoldNotice;
    } else {
      currentNoticeType = "live";
      noticeBanner.className = "banner banner-online";
      noticeText.textContent = dict.liveNotice;
    }

  } catch (err) {
    if (err instanceof ApiError && err.isTurnLimitReached) {
      currentTurnCount = MAX_TURNS;
      updateTurnCounter();
      showError(dict.serverConflictError);
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
  const dict = getLocale(currentUiLang);
  if (state === "recording") {
    micBtn.classList.add("recording");
    micLabel.textContent = dict.micRecording;
  } else if (state === "processing") {
    micBtn.classList.remove("recording");
    micLabel.textContent = dict.micProcessing;
  } else {
    micBtn.classList.remove("recording");
    micLabel.textContent = dict.micBtn;
  }
};

voiceRecorder.onError = (err) => {
  const dict = getLocale(currentUiLang);
  let msg = dict.micGenericError(err.message);
  if (err.code === "denied") {
    msg = dict.micDeniedError;
  } else if (err.code === "not_found") {
    msg = dict.micNotFoundError;
  } else if (err.code === "unsupported") {
    msg = dict.micUnsupportedError;
  }
  showError(msg);
};

voiceRecorder.onAudioReady = async (audioBlob, stopTimestamp) => {
  lastSpeechEndTimestamp = stopTimestamp;
  setBusy(true);
  const dict = getLocale(currentUiLang);
  try {
    const transcriptResult = await transcribeAudio(audioBlob, "speech.webm", currentSessionId);
    if (transcriptResult.text) {
      textInput.value = transcriptResult.text;
      await executeTurn(transcriptResult.text, transcriptResult.language || languageSelect.value,
                        stopTimestamp, true, transcriptResult.stt_ms);
    } else {
      showError(dict.sttEmptyError);
    }
  } catch (err) {
    if (err instanceof ApiError && err.isNotImplemented) {
      showError(dict.sttScaffoldError);
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
    // Permission may resolve after pointerup; do not leave the microphone open.
    if (!pttPointerDown) voiceRecorder.stop();
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

// Space/Enter produce a keyboard click (detail=0): toggle recording accessibly.
micBtn.addEventListener("click", async (e) => {
  if (e.detail !== 0 || isBusy || !currentSessionId || currentTurnCount >= MAX_TURNS) return;
  if (voiceRecorder.isRecording) {
    voiceRecorder.stop();
  } else {
    showError("");
    try { await voiceRecorder.start(); } catch { /* onError already displayed */ }
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

  const dict = getLocale(currentUiLang);

  try {
    const loadedTurns = await parseSessionFile(file);
    if (loadedTurns.length === 0) {
      showError(dict.emptyHistoryError);
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

    currentNoticeType = "replay";
    noticeBanner.className = "banner banner-scaffold";
    noticeText.textContent = dict.replayBanner;
    exportSessionBtn.disabled = false;
  } catch (err) {
    showError(dict.fileReadError(err.message));
  } finally {
    importSessionInput.value = "";
  }
});

datasetSampleSelect.addEventListener("change", (e) => {
  const selectedId = e.target.value;
  if (!selectedId) return;

  const found = DATASET_SAMPLES.find((s) => s.id === selectedId);
  if (!found) return;

  const dict = getLocale(currentUiLang);
  const lastTurn = found.turns[found.turns.length - 1];
  replyText.textContent = lastTurn.assistant_text;
  renderSupervisorPanel(supervisorTrace, lastTurn, currentUiLang);
  renderMetricsPanel(metricsContainer, lastTurn.timings, sessionTracker, currentUiLang);
  rawJsonTrace.textContent = JSON.stringify(found, null, 2);

  currentNoticeType = "sample";
  currentSampleTitle = found.title;
  noticeBanner.className = "banner banner-scaffold";
  noticeText.textContent = dict.datasetSampleBanner(found.title);
});

// UI Language Switch
uiLangSelect.addEventListener("change", (e) => {
  applyLocalization(e.target.value);
});

// Theme Toggle Button
if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });
}

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
  applyTheme(currentTheme);
  applyLocalization("ru");
  const dict = getLocale("ru");
  try {
    const healthData = await health();
    if (healthData.capabilities && healthData.capabilities.llm_routing) {
      currentNoticeType = "live";
      noticeBanner.className = "banner banner-online";
      noticeText.textContent = dict.liveNotice;
    }
    await initSession();
  } catch (err) {
    currentConnectionStatus = "unavailable";
    statusBadge.className = "status-pill status-error";
    statusBadge.textContent = dict.statusUnavailable;
    showError(dict.serverUnavailableHint(err.message));
  }
})();
