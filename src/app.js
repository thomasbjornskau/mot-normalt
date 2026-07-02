/* MOT NORMALT! – applikasjonslogikk
 *
 * Leser ferdigbygde JSON-filer fra /data/, bygger 90-dagersserien,
 * finner perioder utenfor normalvariasjonen og genererer forklaringstekst.
 *
 * Periodedeteksjonen speiler scripts/utils.py (detect_periods).
 */

/* global d3, drawChart */

const WINDOW_DAYS = 90;
const MIN_PERIOD_LENGTH = 7;
const MAX_PERIODS_IN_TEXT = 3;

const MONTHS = ["januar", "februar", "mars", "april", "mai", "juni",
  "juli", "august", "september", "oktober", "november", "desember"];

const state = {
  stations: [],
  stationId: null,
  endDate: null,       // Date
  data: null,          // gjeldende stasjonsfil
  cache: new Map(),
};

// ---------------------------------------------------------------------------
// Hjelpere
// ---------------------------------------------------------------------------

const fmtValue = v =>
  v.toLocaleString("nb-NO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function parseDate(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function fmtDate(d, withYear = false) {
  return `${d.getDate()}. ${MONTHS[d.getMonth()]}${withYear ? " " + d.getFullYear() : ""}`;
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function monthDay(d) {
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Serie og periodedeteksjon
// ---------------------------------------------------------------------------

function buildSeries(data, endDate) {
  const clim = new Map(data.climatology.map(c => [c.month_day, c]));
  const obs = new Map(data.observations.map(o => [o.date, o.value]));
  const series = [];
  for (let i = WINDOW_DAYS - 1; i >= 0; i--) {
    const date = addDays(endDate, -i);
    const c = clim.get(monthDay(date)) || clim.get("02-28"); // fallback (bør ikke skje)
    const value = obs.has(iso(date)) ? obs.get(iso(date)) : null;
    series.push({ date, value, normal: c.normal, p05: c.p05, p95: c.p95 });
  }
  return series;
}

/** Speiler detect_periods i scripts/utils.py. */
function detectPeriods(series, minLength = MIN_PERIOD_LENGTH) {
  const periods = [];
  let run = [];
  let runKind = null;

  const flush = () => {
    if (runKind && run.length >= minLength) periods.push(summarise(run, runKind));
    run = [];
    runKind = null;
  };

  for (const d of series) {
    if (d.value == null) { flush(); continue; }
    const kind = d.value > d.p95 ? "warm" : d.value < d.p05 ? "cold" : null;
    if (kind !== runKind) { flush(); runKind = kind; }
    if (kind) run.push(d);
  }
  flush();

  periods.sort((a, b) =>
    Math.abs(b.peakDeviation) - Math.abs(a.peakDeviation) || b.lengthDays - a.lengthDays);
  return periods;
}

function summarise(run, kind) {
  const peak = kind === "warm"
    ? run.reduce((a, b) => (b.value - b.normal > a.value - a.normal ? b : a))
    : run.reduce((a, b) => (b.value - b.normal < a.value - a.normal ? b : a));
  const hotDays = run.filter(d => d.value > 25).length;
  return {
    kind,
    start: run[0].date,
    end: run[run.length - 1].date,
    lengthDays: run.length,
    peakDate: peak.date,
    peakValue: peak.value,
    peakNormal: peak.normal,
    peakDeviation: peak.value - peak.normal,
    isHeatwave: kind === "warm" && hotDays >= run.length - 1,
  };
}

// ---------------------------------------------------------------------------
// Forklaringstekst
// ---------------------------------------------------------------------------

function explanationHTML(periods, series) {
  const spansYears = series[0].date.getFullYear() !== series[series.length - 1].date.getFullYear();

  if (periods.length === 0) {
    return `<p>De siste 90 dagene hadde ingen sammenhengende perioder på minst
      sju døgn utenfor normalvariasjonen.</p>`;
  }

  return periods.slice(0, MAX_PERIODS_IN_TEXT).map(p => {
    const from = fmtDate(p.start, spansYears);
    const sameMonth = p.start.getMonth() === p.end.getMonth() &&
                      p.start.getFullYear() === p.end.getFullYear();
    const to = sameMonth ? `${p.end.getDate()}. ${MONTHS[p.end.getMonth()]}` : fmtDate(p.end, spansYears);
    const fromShort = sameMonth ? `${p.start.getDate()}.` : from;

    if (p.kind === "warm") {
      const label = p.isHeatwave ? "heteperioden" : null;
      let text = `Fra ${fromShort} til ${to} lå maksimumstemperaturen over
        normalvariasjonen i ${p.lengthDays} døgn på rad. Den høyeste verdien var
        ${fmtValue(p.peakValue)} °C den ${fmtDate(p.peakDate, false)},
        ${fmtValue(Math.abs(p.peakDeviation))} grader over normalen for dagen.`;
      if (label) {
        text += ` Perioden kan kalles en heteperiode: så godt som alle døgn hadde
          maksimumstemperatur over 25 °C.`;
      }
      return `<p class="warm">${text}</p>`;
    }
    return `<p class="cold">Fra ${fromShort} til ${to} lå maksimumstemperaturen under
      normalvariasjonen i ${p.lengthDays} døgn på rad. Laveste maksimumstemperatur var
      ${fmtValue(p.peakValue)} °C den ${fmtDate(p.peakDate, false)},
      ${fmtValue(Math.abs(p.peakDeviation))} grader under normalen for dagen.</p>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

const els = {
  select: document.getElementById("station-select"),
  date: document.getElementById("end-date"),
  reset: document.getElementById("reset-btn"),
  notice: document.getElementById("notice"),
  explanation: document.getElementById("explanation"),
  latestDate: document.getElementById("latest-date"),
  sourceName: document.getElementById("source-name"),
  chart: document.getElementById("chart"),
};

function setNotice(text, isError = false) {
  els.notice.hidden = !text;
  els.notice.textContent = text || "";
  els.notice.classList.toggle("error", isError);
}

function updateURL() {
  const params = new URLSearchParams();
  params.set("station", state.stationId);
  params.set("date", iso(state.endDate));
  history.replaceState(null, "", `?${params}`);
}

async function loadStation(id) {
  if (!state.cache.has(id)) {
    const resp = await fetch(`data/${id}.json`);
    if (!resp.ok) throw new Error(`Fant ikke data for ${id}`);
    state.cache.set(id, await resp.json());
  }
  return state.cache.get(id);
}

function clampEndDate(requested, data) {
  const latest = parseDate(data.metadata.latest_observation_date);
  const firstObs = parseDate(data.observations[0].date);
  const earliestValid = addDays(firstObs, WINDOW_DAYS - 1);

  if (requested > latest) {
    return { date: latest, notice: `Siste tilgjengelige observasjon er ${fmtDate(latest, true)}. Sluttdatoen er justert.` };
  }
  if (requested < earliestValid) {
    return {
      date: null,
      notice: `Valgt sluttdato ligger før tilgjengelig observasjonsperiode. Velg en dato fra og med ${fmtDate(earliestValid, true)}.`,
      error: true,
    };
  }
  return { date: requested, notice: null };
}

async function render() {
  const data = await loadStation(state.stationId);
  state.data = data;

  const today = new Date();
  const latest = parseDate(data.metadata.latest_observation_date);

  let requested = state.endDate || (today > latest ? latest : today);
  const clamped = clampEndDate(requested, data);
  if (!clamped.date) {
    setNotice(clamped.notice, true);
    return;
  }
  state.endDate = clamped.date;

  let notice = clamped.notice;
  if (!notice && iso(state.endDate) === iso(latest) && iso(latest) !== iso(today)) {
    notice = `Siste tilgjengelige observasjon er ${fmtDate(latest, true)}.`;
  }
  setNotice(notice);

  els.date.value = iso(state.endDate);
  els.date.max = iso(latest);
  els.latestDate.textContent = fmtDate(latest, true);
  els.sourceName.textContent = data.metadata.source === "Frost / MET Norway"
    ? "Meteorologisk institutt / Frost"
    : data.metadata.source;

  const series = buildSeries(data, state.endDate);
  const periods = detectPeriods(series);

  drawChart(els.chart, series, periods, {
    endDate: state.endDate,
    formatValue: fmtValue,
    formatDate: fmtDate,
  });
  els.explanation.innerHTML = explanationHTML(periods, series);
  updateURL();
}

async function init() {
  const resp = await fetch("data/stations.json");
  state.stations = await resp.json();

  for (const st of state.stations) {
    const opt = document.createElement("option");
    opt.value = st.id;
    opt.textContent = st.name;
    els.select.appendChild(opt);
  }

  const params = new URLSearchParams(location.search);
  const wanted = params.get("station");
  state.stationId = state.stations.some(s => s.id === wanted)
    ? wanted
    : (state.stations.find(s => s.id === "SN18700") || state.stations[0]).id;
  els.select.value = state.stationId;

  const wantedDate = params.get("date");
  if (wantedDate && /^\d{4}-\d{2}-\d{2}$/.test(wantedDate)) {
    state.endDate = parseDate(wantedDate);
  }

  els.select.addEventListener("change", () => {
    state.stationId = els.select.value;
    render().catch(showError);
  });

  els.date.addEventListener("change", () => {
    if (!els.date.value) return;
    state.endDate = parseDate(els.date.value);
    render().catch(showError);
  });

  els.reset.addEventListener("click", () => {
    state.endDate = null;
    render().catch(showError);
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => render().catch(showError), 150);
  });

  await render();
}

function showError(err) {
  console.error(err);
  setNotice("Noe gikk galt ved lasting av data. Prøv å laste siden på nytt.", true);
}

init().catch(showError);
