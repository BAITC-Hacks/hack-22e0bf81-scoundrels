/**
 * Replay & Session History Manager.
 * Handles export/import of real recorded sessions with [REPLAY] badge,
 * and provides verified reference samples from dialogs_sample.json with [DATASET SAMPLE] badge.
 * Never fabricates fake LLM responses.
 */

export const DATASET_SAMPLES = [
  {
    id: "D03",
    title: "D03: Смена темы и возврат (SC17 → SC27 → SC31 → SC18)",
    turns: [
      {
        turn_id: "D03-T1",
        mode: "dataset_sample",
        transcript: "Здравствуйте, я подавал на выплату по ДТП две недели назад. Какой статус дела?",
        language: "ru",
        assistant_text: "Здравствуйте! Назовите номер страхового случая или ИИН, я проверю статус.",
        decision: {
          action: "route",
          selected_scenario_id: "SC17",
          scenario_ids: ["SC17"],
          rationale: "Клиент запрашивает статус дела по ранее зарегистрированному страховому случаю.",
          certainty: "high",
          alternatives: [{ scenario_id: "SC18", reason: "Запрос касается статуса, а не предоставления документов." }],
          topic_operation: "create",
          slots: [],
          clarification_question: null,
          requires_confirmation: false,
        },
        topics: [
          { topic_id: "T1", scenario_id: "SC17", status: "active", slots: [] }
        ],
        timings: { router_ms: null, backend_total_ms: null, stt_ms: null, tts_first_byte_ms: null, end_to_audio_ms: null },
      },
      {
        turn_id: "D03-T2",
        mode: "dataset_sample",
        transcript: "Кстати, у меня еще полис ОГПО заканчивается на следующей неделе, можно его продлить?",
        language: "ru",
        assistant_text: "Да, конечно. Давайте сначала оформим продление полиса ОГПО. Госномер прежний?",
        decision: {
          action: "route",
          selected_scenario_id: "SC27",
          scenario_ids: ["SC27"],
          rationale: "Клиент сменил тему: запрос на пролонгацию действующего полиса ОГПО.",
          certainty: "high",
          alternatives: [{ scenario_id: "SC01", reason: "Продление существующего полиса, а не первичный расчет." }],
          topic_operation: "switch",
          slots: [],
          clarification_question: null,
          requires_confirmation: false,
        },
        topics: [
          { topic_id: "T1", scenario_id: "SC17", status: "parked", slots: [] },
          { topic_id: "T2", scenario_id: "SC27", status: "active", slots: [] }
        ],
        timings: { router_ms: null, backend_total_ms: null, stt_ms: null, tts_first_byte_ms: null, end_to_audio_ms: null },
      },
      {
        turn_id: "D03-T3",
        mode: "dataset_sample",
        transcript: "Вернемся к страховому случаю. Какие документы мне нужно довезти?",
        language: "ru",
        assistant_text: "По вашему делу требуется акт осмотра и протокол полиции. Вы можете загрузить их в приложении.",
        decision: {
          action: "route",
          selected_scenario_id: "SC18",
          scenario_ids: ["SC18"],
          rationale: "Клиент возвращается к теме страхового случая с уточнением пакета документов.",
          certainty: "high",
          alternatives: [{ scenario_id: "SC17", reason: "Конкретный вопрос о списке документов для дела." }],
          topic_operation: "resume",
          slots: [],
          clarification_question: null,
          requires_confirmation: false,
        },
        topics: [
          { topic_id: "T1", scenario_id: "SC18", status: "active", slots: [] },
          { topic_id: "T2", scenario_id: "SC27", status: "resolved", slots: [] }
        ],
        timings: { router_ms: null, backend_total_ms: null, stt_ms: null, tts_first_byte_ms: null, end_to_audio_ms: null },
      }
    ]
  },
  {
    id: "D05",
    title: "D05: Уточнение намерения (SYS_UNCLEAR)",
    turns: [
      {
        turn_id: "D05-T1",
        mode: "dataset_sample",
        transcript: "Здравствуйте, мне нужно оформить кое-что по машине.",
        language: "ru",
        assistant_text: "Здравствуйте! Уточните, пожалуйста: вы хотите рассчитать и купить новый полис или заявить о страховом случае?",
        decision: {
          action: "clarify",
          selected_scenario_id: null,
          scenario_ids: ["SYS_UNCLEAR"],
          rationale: "Запрос не позволяет различить покупку полиса (SC01/SC02) и урегулирование убытка (SC11/SC13).",
          certainty: "low",
          alternatives: [
            { scenario_id: "SC01", reason: "Возможна покупка автострахования." },
            { scenario_id: "SC13", reason: "Возможно заявление об ущербе." }
          ],
          topic_operation: "create",
          slots: [],
          clarification_question: "Вы хотите оформить новый полис или заявить о страховом случае?",
          requires_confirmation: false,
        },
        topics: [
          { topic_id: "T1", scenario_id: null, status: "active", slots: [] }
        ],
        timings: { router_ms: null, backend_total_ms: null, stt_ms: null, tts_first_byte_ms: null, end_to_audio_ms: null },
      }
    ]
  },
  {
    id: "D06",
    title: "D06: Жалоба и перевод на оператора (SC35 → SC37)",
    turns: [
      {
        turn_id: "D06-T1",
        mode: "dataset_sample",
        transcript: "Меня абсолютно не устраивает обслуживание! Переведите меня на живого человека немедленно!",
        language: "ru",
        assistant_text: "Мне очень жаль, что вы столкнулись с трудностями. Перевожу разговор на старшего специалиста.",
        decision: {
          action: "transfer",
          selected_scenario_id: "SC37",
          scenario_ids: ["SC37", "SC35"],
          rationale: "Клиент требует соединение с оператором и выражает недовольство качеством сервиса.",
          certainty: "high",
          alternatives: [{ scenario_id: "SC35", reason: "Жалоба на сервис уступает прямому требованию оператора." }],
          topic_operation: "create",
          slots: [{ name: "urgency", value: "high" }],
          clarification_question: null,
          requires_confirmation: false,
        },
        topics: [
          { topic_id: "T1", scenario_id: "SC37", status: "transferred", slots: [] }
        ],
        timings: { router_ms: null, backend_total_ms: null, stt_ms: null, tts_first_byte_ms: null, end_to_audio_ms: null },
      }
    ]
  }
];

/**
 * Exports current session history to a downloadable JSON file
 * @param {string} sessionId
 * @param {Array<import('../../contracts/models.py').TurnResponse>} history
 */
export function exportSessionToFile(sessionId, history) {
  if (!history || history.length === 0) return;
  const payload = {
    exported_at: new Date().toISOString(),
    session_id: sessionId,
    turns_count: history.length,
    turns: history,
  };

  const jsonStr = JSON.stringify(payload, null, 2);
  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement("a");
  a.href = url;
  a.download = `routemap-trace-${(sessionId || "session").substring(0, 8)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Parses and validates an uploaded session trace JSON file
 * @param {File} file
 * @returns {Promise<Array<import('../../contracts/models.py').TurnResponse>>}
 */
export async function parseSessionFile(file) {
  const text = await file.text();
  const parsed = JSON.parse(text);
  const rawTurns = Array.isArray(parsed.turns) ? parsed.turns : (Array.isArray(parsed) ? parsed : []);
  
  return rawTurns.map((turn) => ({
    ...turn,
    mode: "replay", // Mark imported traces as REPLAY to ensure transparency
  }));
}
