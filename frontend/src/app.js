import { health, createSession, sendTurn } from "./api.js";

const status = document.querySelector("#status");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
let sessionId = null;

async function newSession() {
  send.disabled = true;
  reset.disabled = true;
  try {
    sessionId = (await createSession()).session_id;
    document.querySelector("#trace").textContent = "Новый разговор.";
    document.querySelector("#reply").textContent = "Ожидание реплики.";
    status.textContent = "Подключено · scaffold · платные API не вызываются";
  } catch (error) {
    sessionId = null;
    status.textContent = error.message;
  } finally {
    send.disabled = !sessionId;
    reset.disabled = false;
  }
}

document.querySelector("#turn-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = document.querySelector("#text").value.trim();
  if (!sessionId || !text) return;
  send.disabled = true;
  reset.disabled = true;
  try {
    const result = await sendTurn(sessionId, text, document.querySelector("#language").value);
    document.querySelector("#reply").textContent = result.assistant_text;
    document.querySelector("#trace").textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    status.textContent = error.message;
  } finally {
    send.disabled = !sessionId;
    reset.disabled = false;
  }
});
reset.addEventListener("click", newSession);
try {
  await health();
  await newSession();
} catch (error) {
  status.textContent = "Сервер недоступен: " + error.message;
}
