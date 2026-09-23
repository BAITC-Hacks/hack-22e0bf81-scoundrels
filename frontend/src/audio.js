/**
 * Audio subsystem for RouteMap.
 * Handles microphone capture via getUserMedia and MediaRecorder (Push-to-Talk),
 * audio playback for synthesized voice, and monotonic client timing measurements.
 */

export class VoiceRecorder {
  constructor() {
    this.mediaStream = null;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.speechEndTimestamp = null; // Monotonic performance.now() at stop

    // Callbacks
    this.onStateChange = null; // (state: 'idle'|'recording'|'processing') => void
    this.onError = null;       // (err: Error) => void
    this.onAudioReady = null;  // (blob: Blob, endTimestamp: number) => void
  }

  /**
   * Determine best supported audio MIME type
   * @returns {string}
   */
  static getSupportedMimeType() {
    const types = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
      "audio/mp4",
    ];
    for (const t of types) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return "";
  }

  /**
   * Request microphone permission and start recording
   */
  async start() {
    if (this.isRecording) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const err = new Error("Запись аудио не поддерживается данным браузером (getUserMedia недоступен)");
      err.code = "unsupported";
      if (this.onError) this.onError(err);
      throw err;
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      this.audioChunks = [];
      const mimeType = VoiceRecorder.getSupportedMimeType();
      const options = mimeType ? { mimeType } : {};
      
      this.mediaRecorder = new MediaRecorder(this.mediaStream, options);

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        // Include recorder finalization/upload time in the PTT end-to-audio measurement.
        this.speechEndTimestamp ??= performance.now();
        const finalMime = this.mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(this.audioChunks, { type: finalMime });
        
        // Stop all tracks to release hardware microphone
        if (this.mediaStream) {
          this.mediaStream.getTracks().forEach((track) => track.stop());
          this.mediaStream = null;
        }

        this.isRecording = false;
        if (this.onStateChange) this.onStateChange("idle");
        if (this.onAudioReady) this.onAudioReady(audioBlob, this.speechEndTimestamp);
      };

      this.mediaRecorder.start();
      this.speechEndTimestamp = null;
      this.isRecording = true;
      if (this.onStateChange) this.onStateChange("recording");
    } catch (err) {
      this.isRecording = false;
      if (this.onStateChange) this.onStateChange("idle");
      
      let userMessage = "Ошибка доступа к микрофону";
      let code = "generic";
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        userMessage = "Доступ к микрофону отклонен пользователем или политикой браузера.";
        code = "denied";
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        userMessage = "Микрофон не обнаружен на устройстве.";
        code = "not_found";
      } else {
        userMessage = `Сбой записи звука: ${err.message}`;
        code = "generic";
      }

      const friendlyError = new Error(userMessage);
      friendlyError.code = code;
      friendlyError.originalError = err;
      if (this.onError) this.onError(friendlyError);
      throw friendlyError;
    }
  }

  /**
   * Stop recording and trigger onAudioReady with final Blob
   */
  stop() {
    if (!this.isRecording || !this.mediaRecorder) return;
    if (this.onStateChange) this.onStateChange("processing");
    try {
      this.speechEndTimestamp = performance.now();
      this.mediaRecorder.stop();
    } catch (err) {
      if (this.onError) this.onError(err);
    }
  }
}

/**
 * Audio playback manager for TTS output.
 * Measures playback readiness via `playing`, not the earlier `play` request event.
 */
export class AudioPlayer {
  constructor(audioElement) {
    /** @type {HTMLAudioElement} */
    this.audioElement = audioElement || new Audio();
    this.currentBlobUrl = null;
    this.onPlaybackStart = null; // (actualPlayTimestamp: number) => void
    this.onPlaybackEnd = null;   // () => void
    this.onError = null;         // (err: Error) => void
    this._streamAbort = null;
    this._reader = null;
    this.transferCompletedAt = null;

    this._setupListeners();
  }

  _setupListeners() {
    this.audioElement.addEventListener("playing", () => {
      const playTimestamp = performance.now();
      if (this.onPlaybackStart) {
        this.onPlaybackStart(playTimestamp);
      }
    });

    this.audioElement.addEventListener("ended", () => {
      this._cleanupUrl();
      if (this.onPlaybackEnd) this.onPlaybackEnd();
    });

    this.audioElement.addEventListener("error", (e) => {
      const err = new Error("Ошибка воспроизведения аудио-ответа");
      if (this.onError) this.onError(err);
    });
  }

  /**
   * Play an audio Blob received from TTS endpoint
   * @param {Blob} audioBlob
   * @returns {Promise<void>}
   */
  async playBlob(audioBlob) {
    this._cleanupUrl();
    if (!audioBlob || audioBlob.size === 0) return;

    this.currentBlobUrl = URL.createObjectURL(audioBlob);
    this.audioElement.src = this.currentBlobUrl;
    
    try {
      await this.audioElement.play();
    } catch (playErr) {
      // Browsers may block autoplay if not triggered by user interaction
      console.warn("Audio autoplay blocked by browser policy:", playErr);
    }
  }

  /** Play incoming MP3 frames before EOF, with a same-request buffered fallback. */
  async playResponse(response) {
    this.stop();
    this.transferCompletedAt = null;
    const mime = "audio/mpeg";
    if (!response.body || typeof MediaSource === "undefined" || !MediaSource.isTypeSupported(mime)) {
      const blob = await response.blob();
      this.transferCompletedAt = performance.now();
      await this.playBlob(blob);
      return;
    }
    const controller = new AbortController();
    this._streamAbort = controller;
    const { signal } = controller;
    const reader = response.body.getReader();
    this._reader = reader;
    const media = new MediaSource();
    this.currentBlobUrl = URL.createObjectURL(media);
    const opened = mediaEvent(media, "sourceopen", signal);
    this.audioElement.src = this.currentBlobUrl;
    let playPromise = null;
    try {
      await opened;
      const buffer = media.addSourceBuffer(mime);
      while (true) {
        const { done, value } = await reader.read();
        signal.throwIfAborted();
        if (done) break;
        if (!value.byteLength) continue;
        const appended = mediaEvent(buffer, "updateend", signal, () => buffer.appendBuffer(value));
        await appended;
        if (!playPromise) {
          playPromise = this.audioElement.play().catch((err) => {
            // Keep downloading: the visible audio controls still allow a manual play.
            console.info("Audio autoplay unavailable:", err.message);
          });
        }
      }
      this.transferCompletedAt = performance.now();
      if (media.readyState === "open") media.endOfStream();
      if (playPromise) await playPromise;
    } catch (err) {
      if (media.readyState === "open") {
        try { media.endOfStream("network"); } catch { /* source already closing */ }
      }
      throw err;
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
      if (this._reader === reader) this._reader = null;
      if (this._streamAbort === controller) this._streamAbort = null;
    }
  }

  /**
   * Stop current playback
   */
  stop() {
    this._streamAbort?.abort();
    this._reader?.cancel().catch(() => {});
    this.audioElement.pause();
    this.audioElement.currentTime = 0;
    this._cleanupUrl();
  }

  _cleanupUrl() {
    if (this.currentBlobUrl) {
      URL.revokeObjectURL(this.currentBlobUrl);
      this.currentBlobUrl = null;
    }
  }
}

/** Register before triggering a media action so fast events cannot be missed. */
function mediaEvent(target, event, signal, action = null) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      target.removeEventListener(event, done);
      target.removeEventListener("error", failed);
      signal.removeEventListener("abort", aborted);
    };
    const done = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(new Error("Audio stream could not be decoded")); };
    const aborted = () => { cleanup(); reject(new DOMException("Playback stopped", "AbortError")); };
    target.addEventListener(event, done, { once: true });
    target.addEventListener("error", failed, { once: true });
    signal.addEventListener("abort", aborted, { once: true });
    if (signal.aborted) { aborted(); return; }
    try { action?.(); } catch (err) { cleanup(); reject(err); }
  });
}
