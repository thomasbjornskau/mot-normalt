/* MOT NORMALT! – graf (D3 v7)
 *
 * drawChart(container, series, periods, opts)
 *   series : [{date: Date, value, normal, p05, p95}], 90 elementer i datorekkefølge
 *   periods: fra detectPeriods() i app.js, sortert etter viktighet
 *   opts   : {endDate: Date, formatValue, formatDate}
 */

/* global d3 */

const CHART_COLORS = {
  ink: "#1c1c1c",
  band: "#e4e4df",
  warm: "#d64524",
  cold: "#2563a8",
};

function drawChart(container, series, periods, opts) {
  const el = typeof container === "string" ? document.querySelector(container) : container;
  el.innerHTML = "";

  const width = el.clientWidth || 800;
  const narrow = width < 560;
  const height = Math.max(300, Math.min(460, width * 0.55));
  const margin = { top: 46, right: 14, bottom: 30, left: 38 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const svg = d3.select(el).append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet");

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  // Skalaer
  const x = d3.scaleTime()
    .domain(d3.extent(series, d => d.date))
    .range([0, iw]);

  const values = series.flatMap(d => [d.p05, d.p95, d.value]).filter(v => v != null);
  const y = d3.scaleLinear()
    .domain([d3.min(values) - 2, d3.max(values) + 2])
    .range([ih, 0])
    .nice();

  // Akser og rutenett
  g.append("g").attr("class", "grid")
    .call(d3.axisLeft(y).ticks(6).tickSize(-iw).tickFormat(""))
    .call(gr => gr.select(".domain").remove());

  const MONTHS_SHORT = ["jan.", "feb.", "mars", "april", "mai", "juni",
    "juli", "aug.", "sep.", "okt.", "nov.", "des."];
  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(x)
      .ticks(narrow ? 4 : 7)
      .tickFormat(d => `${d.getDate()}. ${MONTHS_SHORT[d.getMonth()]}`)
      .tickSizeOuter(0));

  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).ticks(6).tickFormat(v => `${v}°`))
    .call(gr => gr.select(".domain").remove());

  // Normalvariasjonsbånd (p05–p95)
  g.append("path")
    .datum(series)
    .attr("fill", CHART_COLORS.band)
    .attr("fill-opacity", 0.85)
    .attr("d", d3.area()
      .x(d => x(d.date))
      .y0(d => y(d.p05))
      .y1(d => y(d.p95)));

  // Avviksflater: rødt over normalen, blått under
  const defined = d => d.value != null;

  g.append("path")
    .datum(series)
    .attr("fill", CHART_COLORS.warm)
    .attr("fill-opacity", 0.72)
    .attr("d", d3.area()
      .defined(defined)
      .x(d => x(d.date))
      .y0(d => y(d.normal))
      .y1(d => y(Math.max(d.value, d.normal))));

  g.append("path")
    .datum(series)
    .attr("fill", CHART_COLORS.cold)
    .attr("fill-opacity", 0.72)
    .attr("d", d3.area()
      .defined(defined)
      .x(d => x(d.date))
      .y0(d => y(Math.min(d.value, d.normal)))
      .y1(d => y(d.normal)));

  // Normal-linje
  g.append("path")
    .datum(series)
    .attr("fill", "none")
    .attr("stroke", CHART_COLORS.ink)
    .attr("stroke-width", 1.8)
    .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.normal)));

  // Observert maksimumstemperatur som tynn mørk linje (hull vises som brudd)
  g.append("path")
    .datum(series)
    .attr("fill", "none")
    .attr("stroke", CHART_COLORS.ink)
    .attr("stroke-width", 0.8)
    .attr("stroke-opacity", 0.65)
    .attr("d", d3.line().defined(defined).x(d => x(d.date)).y(d => y(d.value)));

  // Valgt sluttdato
  if (opts.endDate >= series[0].date && opts.endDate <= series[series.length - 1].date) {
    const ex = x(opts.endDate);
    g.append("line")
      .attr("x1", ex).attr("x2", ex).attr("y1", 0).attr("y2", ih)
      .attr("stroke", CHART_COLORS.ink)
      .attr("stroke-opacity", 0.3)
      .attr("stroke-dasharray", "3,3");
  }

  // Annotasjoner
  const maxAnnotations = narrow ? 1 : 3;
  drawAnnotations(g, series, periods.slice(0, maxAnnotations), x, y, iw, narrow, opts);

  // Tooltip
  attachTooltip(svg, g, series, x, y, margin, iw, ih, opts);
}

function drawAnnotations(g, series, periods, x, y, iw, narrow, opts) {
  const byDate = new Map(series.map(d => [+d.date, d]));
  const placed = [];

  periods.forEach(p => {
    const peak = byDate.get(+p.peakDate);
    if (!peak) return;

    const warm = p.kind === "warm";
    const px = x(peak.date);
    const py = y(peak.value);

    const label = warm ? (p.isHeatwave ? "Heteperiode" : "Varm periode") : "Kald periode";
    const sub = `${p.lengthDays} døgn, inntil ${opts.formatValue(Math.abs(p.peakDeviation))} °C ` +
                `${warm ? "over" : "under"} normalen`;

    // Etikett over toppunktet for varme perioder, under for kalde
    let ly = warm ? py - 34 : py + 34;
    let lx = Math.max(4, Math.min(px, iw - (narrow ? 120 : 250)));

    // Enkel kollisjonshåndtering: skyv nedover/oppover hvis for nær en annen
    placed.forEach(q => {
      if (Math.abs(q.lx - lx) < 170 && Math.abs(q.ly - ly) < 30) {
        ly += warm ? -30 : 30;
      }
    });
    ly = Math.max(-38, Math.min(ly, y.range()[0] + 26));
    placed.push({ lx, ly });

    const a = g.append("g").attr("class", "annotation");
    a.append("line")
      .attr("x1", px).attr("y1", py + (warm ? -3 : 3))
      .attr("x2", Math.min(Math.max(lx + 4, 8), iw - 8))
      .attr("y2", ly + (warm ? 12 : -14));
    const t = a.append("text").attr("x", lx).attr("y", ly);
    t.append("tspan").text(label + " ");
    if (!narrow) {
      t.append("tspan").attr("class", "sub").attr("x", lx).attr("dy", "1.2em").text(sub);
    }
  });
}

function attachTooltip(svg, g, series, x, y, margin, iw, ih, opts) {
  const tooltip = document.getElementById("tooltip");
  if (!tooltip) return;

  const bisect = d3.bisector(d => d.date).center;
  const marker = g.append("circle")
    .attr("r", 3.5)
    .attr("fill", CHART_COLORS.ink)
    .style("display", "none");

  const overlay = g.append("rect")
    .attr("width", iw).attr("height", ih)
    .attr("fill", "transparent");

  function show(event) {
    const [mx] = d3.pointer(event, g.node());
    const d = series[bisect(series, x.invert(mx))];
    if (!d) return hide();

    const rows = [`<strong>${opts.formatDate(d.date, true)}</strong>`];
    if (d.value != null) {
      const dev = d.value - d.normal;
      const devClass = dev >= 0 ? "dev-warm" : "dev-cold";
      const devText = `${opts.formatValue(Math.abs(dev))} °C ${dev >= 0 ? "over" : "under"} normalen`;
      rows.push(`Observert maks: ${opts.formatValue(d.value)} °C`);
      rows.push(`<span class="${devClass}">${devText}</span>`);
      marker.style("display", null).attr("cx", x(d.date)).attr("cy", y(d.value));
    } else {
      rows.push("Ingen observasjon");
      marker.style("display", "none");
    }
    rows.push(`Normal: ${opts.formatValue(d.normal)} °C`);
    rows.push(`Normalvariasjon: ${opts.formatValue(d.p05)} til ${opts.formatValue(d.p95)} °C`);

    tooltip.innerHTML = rows.join("<br>");
    tooltip.hidden = false;
    const pad = 14;
    const rect = tooltip.getBoundingClientRect();
    let tx = event.clientX + pad;
    if (tx + rect.width > window.innerWidth - 8) tx = event.clientX - rect.width - pad;
    let ty = event.clientY - rect.height - pad;
    if (ty < 8) ty = event.clientY + pad;
    tooltip.style.left = `${tx}px`;
    tooltip.style.top = `${ty}px`;
  }

  function hide() {
    tooltip.hidden = true;
    marker.style("display", "none");
  }

  overlay
    .on("pointermove", show)
    .on("pointerdown", show)
    .on("pointerleave", hide);
}
