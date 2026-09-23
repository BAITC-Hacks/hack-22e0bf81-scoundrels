/**
 * Metrics and Latency Analysis Module.
 * Tracks per-turn waterfall timings and computes session aggregate statistics (p50 median, p95).
 * Strictly renders null as "—" (never fake "0 ms").
 */

/**
 * Calculates a given percentile from an array of numbers
 * @param {number[]} values
 * @param {number} p - Percentile between 0 and 100
 * @returns {number|null}
 */
export function calculatePercentile(values, p) {
  if (!values || values.length === 0) return null;
  const sorted = [...values].filter((v) => typeof v === "number" && !isNaN(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return null;
  
  const index = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  const weight = index - lower;

  if (lower === upper) return sorted[lower];
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

/**
 * Session latency tracker
 */
export class SessionMetricsTracker {
  constructor() {
    /** @type {number[]} */
    this.endToAudioSamples = [];
  }

  /**
   * Reset session samples
   */
  reset() {
    this.endToAudioSamples = [];
  }

  /**
   * Record a valid end-to-audio latency measurement
   * @param {number|null} ms
   */
  recordSample(ms) {
    if (typeof ms === "number" && ms > 0) {
      this.endToAudioSamples.push(ms);
    }
  }

  /**
   * Returns session summary statistics
   */
  getSummary() {
    const count = this.endToAudioSamples.length;
    if (count === 0) {
      return { count: 0, p50: null, p95: null, min: null, max: null };
    }
    return {
      count,
      p50: Math.round(calculatePercentile(this.endToAudioSamples, 50)),
      p95: Math.round(calculatePercentile(this.endToAudioSamples, 95)),
      min: Math.round(Math.min(...this.endToAudioSamples)),
      max: Math.round(Math.max(...this.endToAudioSamples)),
    };
  }
}

/**
 * Formats a latency value: null is rendered as "—"
 * @param {number|null|undefined} ms
 * @returns {string}
 */
export function formatMs(ms) {
  if (ms === null || ms === undefined || isNaN(ms)) {
    return "—";
  }
  return `${Math.round(ms)} мс`;
}

/**
 * Renders the latency waterfall card and session aggregates
 * @param {HTMLElement} container
 * @param {import('../../contracts/models.py').Timings|null} timings
 * @param {SessionMetricsTracker} tracker
 * @param {'ru'|'kk'} [lang='ru']
 */
export function renderMetricsPanel(container, timings, tracker, lang = "ru") {
  container.replaceChildren();

  const card = document.createElement("div");
  card.className = "trace-card metrics-card";

  const titleRow = document.createElement("div");
  titleRow.className = "card-header-row";
  const h3 = document.createElement("h3");
  h3.className = "card-title";
  h3.textContent = lang === "kk" ? "Кідіріс өлшемдері (Latency Waterfall)" : "Замеры задержек (Latency Waterfall)";
  titleRow.appendChild(h3);

  const disclaimer = document.createElement("span");
  disclaimer.className = "metrics-disclaimer";
  disclaimer.textContent = lang === "kk"
    ? "PTT жуықтауы: түймені жіберуден → дыбыс ойнатуға дейін"
    : "Приближение PTT: от отпускания кнопки → до начала воспроизведения";
  titleRow.appendChild(disclaimer);
  card.appendChild(titleRow);

  // Per-turn grid
  const grid = document.createElement("div");
  grid.className = "metrics-grid";

  const stages = [
    {
      key: "stt",
      label: "STT (Дауыс/Речь)",
      value: timings ? timings.stt_ms : null,
      target: null,
    },
    {
      key: "router",
      label: "Router LLM",
      value: timings ? timings.router_ms : null,
      target: 500, // Goal: ~500ms
    },
    {
      key: "backend",
      label: "Backend Total",
      value: timings ? timings.backend_total_ms : null,
      target: null,
    },
    {
      key: "tts",
      label: "TTS First Byte",
      value: timings ? timings.tts_first_byte_ms : null,
      target: null,
    },
    {
      key: "end_to_audio",
      label: "End-to-Audio (Client)",
      value: timings ? timings.end_to_audio_ms : null,
      target: 1500, // Goal: ~1500ms
      highlight: true,
    },
  ];

  stages.forEach((stage) => {
    const item = document.createElement("div");
    item.className = `metric-box ${stage.highlight ? "metric-highlight" : ""}`;

    const label = document.createElement("div");
    label.className = "metric-label";
    label.textContent = stage.label;
    item.appendChild(label);

    const valEl = document.createElement("div");
    valEl.className = "metric-value";
    valEl.textContent = formatMs(stage.value);

    // Apply color thresholds if value exists
    if (typeof stage.value === "number") {
      if (stage.key === "router") {
        valEl.classList.add(stage.value <= 500 ? "val-good" : "val-warn");
      } else if (stage.key === "end_to_audio") {
        if (stage.value <= 1500) valEl.classList.add("val-good"); // +2 points
        else if (stage.value <= 3000) valEl.classList.add("val-warn"); // +1 point
        else valEl.classList.add("val-bad");
      }
    } else {
      valEl.classList.add("val-null");
    }

    item.appendChild(valEl);

    if (stage.target) {
      const targetHint = document.createElement("div");
      targetHint.className = "metric-target";
      targetHint.textContent = `Ориентир: ≤ ${stage.target} мс`;
      item.appendChild(targetHint);
    }

    grid.appendChild(item);
  });
  card.appendChild(grid);

  // Session Aggregates Row (p50 / p95)
  const summary = tracker.getSummary();
  const summaryRow = document.createElement("div");
  summaryRow.className = "metrics-summary-row";

  const statsBadge = document.createElement("div");
  statsBadge.className = "session-stats-badge";
  
  const countText = lang === "kk" ? `Өлшемдер: ${summary.count}` : `Замеров: ${summary.count}`;
  const p50Text = `p50 (медиана): ${formatMs(summary.p50)}`;
  const p95Text = `p95: ${formatMs(summary.p95)}`;

  statsBadge.textContent = `${countText} · ${p50Text} · ${p95Text}`;
  summaryRow.appendChild(statsBadge);

  if (summary.count > 0 && summary.p50 !== null) {
    const bonusTag = document.createElement("span");
    if (summary.p50 <= 1500) {
      bonusTag.className = "badge badge-success";
      bonusTag.textContent = "Медиана ≤ 1.5 с (+2 балла)";
    } else if (summary.p50 <= 3000) {
      bonusTag.className = "badge badge-warning";
      bonusTag.textContent = "Медиана ≤ 3.0 с (+1 балл)";
    } else {
      bonusTag.className = "badge badge-normal";
      bonusTag.textContent = "Медиана > 3.0 с";
    }
    summaryRow.appendChild(bonusTag);
  }

  card.appendChild(summaryRow);
  container.appendChild(card);
}
