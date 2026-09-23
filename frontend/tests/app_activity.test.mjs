import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// Exercise the real controller with an inert DOM and fake APIs; no network/audio.
const source = readFileSync(new URL("../src/app.js", import.meta.url), "utf8")
  .replace(/^import .*;$/gm, "");

function setup(overrides = {}) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, {
      disabled: false, value: "test", options: [], style: {}, hidden: false,
      classList: { add() {}, remove() {} }, addEventListener() {},
    });
    return nodes.get(id);
  };
  const calls = { turns: 0, sessions: 0, plays: 0 };
  const result = () => ({ assistant_text: "Answer", language: "ru", timings: {}, mode: "live" });
  const context = vm.createContext({
    console, document: { querySelector: node, documentElement: { setAttribute() {} } },
    window: { addEventListener() {} }, localStorage: { getItem() { return null; }, setItem() {} },
    getLocale: () => new Proxy({}, { get: () => () => "label" }),
    renderSupervisorPanel() {}, renderMetricsPanel() {}, DATASET_SAMPLES: [],
    exportSessionToFile() {}, parseSessionFile: async () => [],
    health: () => new Promise(() => {}),
    createSession: async () => { calls.sessions++; return { session_id: "new" }; },
    sendTurn: async () => { calls.turns++; return result(); },
    transcribeAudio: async () => ({ text: "Hello", language: "en", stt_ms: 1 }),
    synthesizeSpeech: async () => ({ response: { body: { cancel: async () => {} } }, ttsMs: 1 }),
    ApiError: class extends Error {},
    SessionMetricsTracker: class { reset() {} recordSample() {} },
    VoiceRecorder: class {
      isRecording = false;
      async start() { this.isRecording = true; this.onStateChange("recording"); }
      stop() { this.isRecording = false; this.onStateChange("idle"); }
    },
    AudioPlayer: class { stop() {} async playResponse() { calls.plays++; } },
    ...overrides,
  });
  vm.runInContext(source, context);
  vm.runInContext('currentSessionId = "original"; setBusy(false);', context);
  return { calls, node, run: (code) => vm.runInContext(code, context) };
}

test("recording blocks text/reset/replay while microphone stop remains available", async () => {
  const { calls, node, run } = setup();
  await run("startRecording()");
  await run("handleTextSubmit({ preventDefault() {} })");
  await run("initSession()");
  assert.equal(calls.turns, 0);
  assert.equal(calls.sessions, 0);
  for (const id of ["#send-btn", "#reset-btn", "#import-session-input", "#dataset-sample-select"])
    assert.equal(node(id).disabled, true, id);
  assert.equal(node("#mic-btn").disabled, false);
});

test("stale TTS response is cancelled and cannot play in a replaced session", async () => {
  let completeTts;
  let requested;
  const ttsRequested = new Promise(resolve => { requested = resolve; });
  let cancelled = false;
  const { calls, run } = setup({
    synthesizeSpeech: () => { requested(); return new Promise(resolve => { completeTts = resolve; }); },
  });
  const pending = run('executeTurn("Hello", "en")');
  await ttsRequested;
  run('operationEpoch++; currentSessionId = "replacement";');
  completeTts({ response: { body: { cancel: async () => { cancelled = true; } } }, ttsMs: 1 });
  await pending;
  assert.equal(cancelled, true);
  assert.equal(calls.plays, 0);
});

test("STT-to-turn handover releases busy state after normal voice completion", async () => {
  const { calls, run, node } = setup();
  await run("voiceRecorder.onAudioReady({}, 10)");
  assert.equal(calls.turns, 1);
  assert.equal(calls.plays, 1);
  assert.equal(run("isBusy"), false);
  assert.equal(node("#send-btn").disabled, false);
});

test("a late playing callback cannot write timings into a newer operation", async () => {
  const { run } = setup();
  await run('executeTurn("Hello", "en", 10)');
  run("const obsoleteCallback = audioPlayer.onPlaybackStart; operationEpoch++; obsoleteCallback(100);");
  assert.equal(run("sessionHistory[0].timings.end_to_audio_ms"), undefined);
});

test("new conversation restores real server banner after sample or replay", async () => {
  for (const serverMode of ["live", "scaffold"]) {
    for (const viewedMode of ["sample", "replay"]) {
      const { run, node } = setup({ getLocale: () => new Proxy({
        liveNotice: "LIVE", scaffoldNotice: "OFFLINE",
      }, { get: (target, key) => target[key] ?? (() => "label") }) });
      run(`serverNoticeType = "${serverMode}"; currentNoticeType = "${viewedMode}"; currentSampleTitle = "Old sample";`);
      await run("initSession()");
      assert.equal(run("currentNoticeType"), serverMode);
      assert.equal(run("currentSampleTitle"), "");
      assert.equal(node("#notice-text").textContent, serverMode === "live" ? "LIVE" : "OFFLINE");
      assert.equal(node("#notice-banner").className, serverMode === "live" ? "banner banner-online" : "banner banner-scaffold");
    }
  }
});
