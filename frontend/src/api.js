async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `HTTP ${response.status}`);
  }
  return response.json();
}
export const health = () => request("/api/health");
export const createSession = () => request("/api/sessions", { method: "POST" });
export const sendTurn = (sessionId, text, language) => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/turns`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, language }) }
);
