import test from "node:test";
import assert from "node:assert/strict";
import { AudioPlayer } from "../src/audio.js";

class FakeAudio extends EventTarget {
  currentTime = 0;
  plays = 0;
  pause() {}
  async play() {
    this.plays++;
    this.dispatchEvent(new Event("play"));
    queueMicrotask(() => this.dispatchEvent(new Event("playing")));
  }
}

class FakeBuffer extends EventTarget {
  chunks = [];
  appendBuffer(value) {
    this.chunks.push(value);
    queueMicrotask(() => this.dispatchEvent(new Event("updateend")));
  }
}

class FakeMediaSource extends EventTarget {
  static supported = true;
  static isTypeSupported() { return this.supported; }
  readyState = "open";
  buffer = new FakeBuffer();
  addSourceBuffer() { return this.buffer; }
  endOfStream() { this.readyState = "ended"; }
}

function setup(t) {
  t.mock.method(URL, "createObjectURL", (media) => {
    if (media instanceof FakeMediaSource) queueMicrotask(() => media.dispatchEvent(new Event("sourceopen")));
    return "blob:test";
  });
  t.mock.method(URL, "revokeObjectURL", () => {});
  const previous = globalThis.MediaSource;
  globalThis.MediaSource = FakeMediaSource;
  FakeMediaSource.supported = true;
  t.after(() => { globalThis.MediaSource = previous; });
  const audio = new FakeAudio();
  return { audio, player: new AudioPlayer(audio) };
}

test("starts playback from first chunk while network tail is still pending", async (t) => {
  const { player, audio } = setup(t);
  let controller;
  const body = new ReadableStream({ start(c) { controller = c; c.enqueue(new Uint8Array([1])); } });
  let resolvePlaying;
  const playing = new Promise(resolve => { resolvePlaying = resolve; });
  player.onPlaybackStart = resolvePlaying;
  let completed = false;
  const consumption = player.playResponse(new Response(body)).then(() => { completed = true; });
  await playing;
  assert.equal(audio.plays, 1);
  assert.equal(completed, false);
  controller.enqueue(new Uint8Array([2]));
  controller.close();
  await consumption;
  assert.equal(player._reader, null);
});

test("unsupported MSE buffers the same response without another request", async (t) => {
  const { player, audio } = setup(t);
  FakeMediaSource.supported = false;
  await player.playResponse(new Response(new Uint8Array([1, 2])));
  assert.equal(audio.plays, 1);
});

test("stopping stream cancels the pending download", async (t) => {
  const { player } = setup(t);
  let cancelled = false;
  const body = new ReadableStream({ cancel() { cancelled = true; } });
  const consumption = player.playResponse(new Response(body));
  player.stop();
  await assert.rejects(consumption, { name: "AbortError" });
  assert.equal(cancelled, true);
});

test("play request is not counted as audible playback readiness", async (t) => {
  const { player, audio } = setup(t);
  let events = 0;
  player.onPlaybackStart = () => { events++; };
  audio.dispatchEvent(new Event("play"));
  assert.equal(events, 0);
  audio.dispatchEvent(new Event("playing"));
  assert.equal(events, 1);
});
