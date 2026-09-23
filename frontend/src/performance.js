import { createSession, synthesizeSpeech } from "./api.js";
import { AudioPlayer } from "./audio.js";

const samples = {
  ru: "Для проверки статуса назовите номер полиса и зарегистрированный телефон. После проверки я помогу разобраться с вашим вопросом.",
  kk: "Полисті тексеру үшін полис нөмірін және тіркелген телефон нөмірін айтыңыз. Тексеруден кейін сұрағыңыз бойынша көмектесемін.",
  en: "To check your policy, please provide its number and your registered phone number. After verification, I can help with your question.",
};
const player = new AudioPlayer(document.querySelector("#audio"));
const button = document.querySelector("#run");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const report = document.querySelector("#report");
let runs = 0;

button.addEventListener("click", async () => {
  button.disabled = true;
  results.replaceChildren();
  report.textContent = "";
  const rows = [];
  try {
    const { session_id } = await createSession();
    const language = document.querySelector("#language").value;
    // Alternate the order between runs so the buffered request is not always cold.
    const modes = runs++ % 2 ? [true, false] : [false, true];
    for (const stream of modes) {
      const mode = stream ? "Поток" : "Полная загрузка";
      status.textContent = `${mode}: ожидаем озвучку…`;
      player.stop();
      const started = performance.now();
      let playedAt = null;
      player.onPlaybackStart = timestamp => { playedAt ??= timestamp; };
      const speech = await synthesizeSpeech(samples[language], language, session_id, stream);
      let downloadedAt;
      if (stream) {
        await player.playResponse(speech.response);
        downloadedAt = player.transferCompletedAt;
      } else {
        downloadedAt = performance.now();
        await player.playBlob(speech.audioBlob);
      }
      const row = { mode, language, first_audio_ms: playedAt === null ? null : Math.round(playedAt - started),
        download_ms: Math.round(downloadedAt - started), played_before_download: playedAt !== null && playedAt < downloadedAt,
        provider_first_byte_ms: speech.ttsMs };
      rows.push(row);
      const tr = document.createElement("tr");
      for (const value of [mode, row.first_audio_ms ?? "Автоплей заблокирован", row.download_ms, row.played_before_download ? "Да" : "Нет"]) {
        const td = document.createElement("td"); td.textContent = value; tr.appendChild(td);
      }
      results.appendChild(tr);
      report.textContent = JSON.stringify(rows, null, 2);
    }
    status.textContent = "Готово. Два измерения — отдельные запросы; повторите для оценки разброса.";
  } catch (err) {
    status.textContent = `Ошибка: ${err.message}`;
  } finally {
    player.onPlaybackStart = null;
    button.disabled = false;
  }
});
