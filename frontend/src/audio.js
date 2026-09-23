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
        this.speechEndTimestamp = performance.now();
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
      this.mediaRecorder.stop();
    } catch (err) {
      if (this.onError) this.onError(err);
    }
  }
}

/**
 * Audio playback manager for TTS output.
 * Tracks actual playback start via audio.onplay for monotonic end-to-audio latency calculation.
 */
export class AudioPlayer {
  constructor(audioElement) {
    /** @type {HTMLAudioElement} */
    this.audioElement = audioElement || new Audio();
    this.currentBlobUrl = null;
    this.onPlaybackStart = null; // (actualPlayTimestamp: number) => void
    this.onPlaybackEnd = null;   // () => void
    this.onError = null;         // (err: Error) => void

    this._setupListeners();
  }

  _setupListeners() {
    this.audioElement.addEventListener("play", () => {
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

  /**
   * Stop current playback
   */
  stop() {
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
