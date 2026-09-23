/**
 * Supervisor Explainability Panel component.
 * Renders structured decisions, catalog enrichment, certainty, alternatives,
 * slot entities, and topic stack strictly using safe DOM APIs (no innerHTML XSS).
 */

import { getScenarioMeta } from "./catalog.js";

/** Label only explicitly known live responses as API-backed. */
export function getModeBadge(mode) {
  switch (mode) {
    case "live": return { text: "LIVE LLM", variant: "success" };
    case "dataset_sample": return { text: "DEMO / NO API", variant: "info" };
    case "replay": return { text: "REPLAY / NO API", variant: "info" };
    case "scaffold": return { text: "SCAFFOLD MODE", variant: "warning" };
    default: return { text: "UNKNOWN MODE", variant: "muted" };
  }
}

/**
 * Creates an element with text content and optional class names
 * @param {string} tag
 * @param {string} [text=""]
 * @param {string} [className=""]
 * @returns {HTMLElement}
 */
function el(tag, text = "", className = "") {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

/**
 * Creates a badge element
 * @param {string} text
 * @param {'normal'|'urgent'|'high'|'warning'|'success'|'info'|'muted'} [variant='normal']
 * @returns {HTMLElement}
 */
function createBadge(text, variant = "normal") {
  return el("span", text, `badge badge-${variant}`);
}

/**
 * Renders the entire supervisor panel
 * @param {HTMLElement} container
 * @param {import('../../contracts/models.py').TurnResponse|null} turnResponse
 * @param {'ru'|'kk'} [lang='ru']
 */
export function renderSupervisorPanel(container, turnResponse, lang = "ru") {
  container.replaceChildren();

  if (!turnResponse) {
    const emptyState = el("div", "", "supervisor-empty");
    const emptyMsg = lang === "kk" 
      ? "Реплика күтілуде. Бағыттау, тақырыптар және дәлелдер осында көрсетіледі." 
      : "Ожидание реплики. Маршрутизация, стек тем и обоснование отобразятся здесь.";
    emptyState.appendChild(el("p", emptyMsg, "muted-text"));
    container.appendChild(emptyState);
    return;
  }

  const { mode, turn_id, decision, topics, language } = turnResponse;
  const isScaffold = mode === "scaffold";

  // 1. Session & Turn Metadata Bar
  const metaBar = el("div", "", "trace-meta-bar");
  
  const badge = getModeBadge(mode);
  const modeBadge = createBadge(badge.text, badge.variant);
  metaBar.appendChild(modeBadge);

  if (turn_id) {
    metaBar.appendChild(el("span", `Turn: ${turn_id}`, "meta-item"));
  }
  metaBar.appendChild(el("span", `Lang: ${language.toUpperCase()}`, "meta-item"));
  container.appendChild(metaBar);

  // 2. Decision Card
  const decisionCard = el("div", "", "trace-card decision-card");
  const cardTitle = el("h3", lang === "kk" ? "Шешім және бағыттау" : "Решение и маршрутизация", "card-title");
  decisionCard.appendChild(cardTitle);

  // Action status badge
  const actionRow = el("div", "", "trace-row");
  actionRow.appendChild(el("span", lang === "kk" ? "Әрекет түрі:" : "Действие:", "field-label"));
  
  let actionVariant = "info";
  let actionText = decision.action;
  if (decision.action === "route") {
    actionVariant = "success";
    actionText = lang === "kk" ? "Сценарийді таңдау (route)" : "Выбор сценария (route)";
  } else if (decision.action === "clarify") {
    actionVariant = "warning";
    actionText = lang === "kk" ? "Нақтылау қажет (clarify)" : "Уточнение (clarify)";
  } else if (decision.action === "transfer") {
    actionVariant = "urgent";
    actionText = lang === "kk" ? "Операторға қосу (transfer)" : "Перевод на оператора (transfer)";
  }
  actionRow.appendChild(createBadge(actionText, actionVariant));
  decisionCard.appendChild(actionRow);

  // Clarification Question (if action == clarify)
  if (decision.action === "clarify" && decision.clarification_question) {
    const clarifyBox = el("div", "", "clarify-box");
    clarifyBox.appendChild(el("strong", lang === "kk" ? "Нақтылау сұрағы: " : "Уточняющий вопрос: "));
    clarifyBox.appendChild(el("span", decision.clarification_question));
    decisionCard.appendChild(clarifyBox);
  }

  // Selected Primary Scenario
  const scenarioMeta = getScenarioMeta(decision.selected_scenario_id, lang);
  const scenarioRow = el("div", "", "trace-row primary-scenario-row");
  scenarioRow.appendChild(el("span", lang === "kk" ? "Негізгі сценарий:" : "Основной сценарий:", "field-label"));

  if (decision.selected_scenario_id) {
    const scContent = el("div", "", "scenario-pill");
    scContent.appendChild(el("strong", decision.selected_scenario_id, "scenario-id"));
    scContent.appendChild(el("span", ` · ${scenarioMeta.name}`, "scenario-name"));

    // Priority badge
    if (scenarioMeta.priority === "urgent") {
      scContent.appendChild(createBadge("URGENT", "urgent"));
    } else if (scenarioMeta.priority === "high") {
      scContent.appendChild(createBadge("HIGH", "high"));
    }
    scenarioRow.appendChild(scContent);
  } else {
    const noSc = el("span", isScaffold ? "Не выбран (scaffold)" : "Не определен", "muted-text");
    scenarioRow.appendChild(noSc);
  }
  decisionCard.appendChild(scenarioRow);

  // Ordered Scenario IDs (for multi-intent)
  if (decision.scenario_ids && decision.scenario_ids.length > 1) {
    const multiRow = el("div", "", "trace-row");
    multiRow.appendChild(el("span", lang === "kk" ? "Ниеттер тізбегі:" : "Очередь намерений:", "field-label"));
    const multiPills = el("div", "", "pills-list");
    decision.scenario_ids.forEach((scId, idx) => {
      const meta = getScenarioMeta(scId, lang);
      const pill = el("span", `${idx + 1}. ${scId} (${meta.name})`, "pill-mini");
      multiPills.appendChild(pill);
    });
    multiRow.appendChild(multiPills);
    decisionCard.appendChild(multiRow);
  }

  // Certainty (Qualitative self-report)
  const certRow = el("div", "", "trace-row");
  certRow.appendChild(el("span", lang === "kk" ? "Сенімділік деңгейі:" : "Уверенность LLM:", "field-label"));
  
  const certMap = {
    high: { ru: "Высокая", kk: "Жоғары", variant: "success" },
    medium: { ru: "Средняя", kk: "Орташа", variant: "warning" },
    low: { ru: "Низкая", kk: "Төмен", variant: "urgent" },
    unavailable: { ru: "Недоступна (scaffold)", kk: "Қолжетімсіз", variant: "muted" },
  };
  const certInfo = certMap[decision.certainty] || certMap.unavailable;
  const certText = lang === "kk" ? certInfo.kk : certInfo.ru;
  certRow.appendChild(createBadge(certText, certInfo.variant));
  decisionCard.appendChild(certRow);

  // Rationale
  if (decision.rationale) {
    const rationaleRow = el("div", "", "trace-rationale");
    rationaleRow.appendChild(el("span", lang === "kk" ? "Дәлелдеу (Explainability):" : "Обоснование решения:", "field-label"));
    const rationaleText = el("blockquote", decision.rationale, "rationale-quote");
    rationaleRow.appendChild(rationaleText);
    decisionCard.appendChild(rationaleRow);
  }

  // Confirmation status (Critical: preview only, cannot mutate server)
  if (decision.requires_confirmation) {
    const confirmWarning = el("div", "", "confirmation-banner");
    confirmWarning.appendChild(el("span", "⚠️ ", "banner-icon"));
    const warningText = lang === "kk"
      ? "Қайтарымсыз әрекет алдында клиенттен нақты растау «иә» қажет"
      : "Требуется явное подтверждение клиента («да») перед необратимым действием";
    confirmWarning.appendChild(el("strong", warningText));
    decisionCard.appendChild(confirmWarning);
  }

  // Alternatives
  if (decision.alternatives && decision.alternatives.length > 0) {
    const altSection = el("div", "", "trace-sub-section");
    altSection.appendChild(el("span", lang === "kk" ? "Қарастырылған баламалар:" : "Рассмотренные альтернативы:", "field-label"));
    const altList = el("ul", "", "alternatives-list");
    decision.alternatives.forEach((alt) => {
      const li = el("li", "", "alt-item");
      const altMeta = getScenarioMeta(alt.scenario_id, lang);
      li.appendChild(el("strong", `${alt.scenario_id} (${altMeta.name}): `));
      li.appendChild(el("span", alt.reason || "Отсечен"));
      altList.appendChild(li);
    });
    altSection.appendChild(altList);
    decisionCard.appendChild(altSection);
  }

  container.appendChild(decisionCard);

  // 3. Extracted Slots Card
  const slotsCard = el("div", "", "trace-card");
  slotsCard.appendChild(el("h3", lang === "kk" ? "Бөлінген параметрлер (Slots)" : "Извлечённые слоты (Сущности)", "card-title"));

  if (decision.slots && decision.slots.length > 0) {
    const table = el("table", "", "slots-table");
    const thead = el("thead");
    const trH = el("tr");
    trH.appendChild(el("th", lang === "kk" ? "Параметр" : "Параметр"));
    trH.appendChild(el("th", lang === "kk" ? "Мән" : "Значение"));
    thead.appendChild(trH);
    table.appendChild(thead);

    const tbody = el("tbody");
    decision.slots.forEach((slot) => {
      const tr = el("tr");
      tr.appendChild(el("td", slot.name, "slot-name"));
      tr.appendChild(el("td", slot.value, "slot-value"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    slotsCard.appendChild(table);
  } else {
    slotsCard.appendChild(el("p", lang === "kk" ? "Слоттар табылған жоқ" : "Слоты не извлечены", "muted-text"));
  }
  container.appendChild(slotsCard);

  // 4. Topic Management Stack Card
  const topicsCard = el("div", "", "trace-card");
  const topicsHeader = el("div", "", "topics-header");
  topicsHeader.appendChild(el("h3", lang === "kk" ? "Тақырыптарды басқару (Topic Stack)" : "Управление темами (Стек тем)", "card-title"));
  
  if (decision.topic_operation && decision.topic_operation !== "none") {
    topicsHeader.appendChild(createBadge(`op: ${decision.topic_operation}`, "info"));
  }
  topicsCard.appendChild(topicsHeader);

  if (topics && topics.length > 0) {
    const topicsList = el("div", "", "topics-list");
    topics.forEach((top) => {
      const item = el("div", "", `topic-item topic-status-${top.status}`);
      const topMeta = getScenarioMeta(top.scenario_id, lang);
      
      const titleRow = el("div", "", "topic-title-row");
      titleRow.appendChild(el("strong", top.scenario_id ? `${top.scenario_id} · ${topMeta.name}` : top.topic_id));
      
      let statusVariant = "normal";
      if (top.status === "active") statusVariant = "success";
      else if (top.status === "parked") statusVariant = "warning";
      else if (top.status === "resolved") statusVariant = "muted";
      else if (top.status === "transferred") statusVariant = "urgent";

      titleRow.appendChild(createBadge(top.status.toUpperCase(), statusVariant));
      item.appendChild(titleRow);

      if (top.slots && top.slots.length > 0) {
        const slotSummary = top.slots.map(s => `${s.name}: ${s.value}`).join(", ");
        item.appendChild(el("div", `Параметры темы: ${slotSummary}`, "topic-slots-text"));
      }

      topicsList.appendChild(item);
    });
    topicsCard.appendChild(topicsList);
  } else {
    topicsCard.appendChild(el("p", lang === "kk" ? "Тақырыптар стегі бос" : "Стек тем пуст", "muted-text"));
  }
  container.appendChild(topicsCard);
}
