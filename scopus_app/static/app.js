/**
 * Frontend Application & Aesthetic SVG/Canvas Visualization Engine
 * for Scopus Scientometrics Studio.
 */

const STATE = {
  settings: {},
  subjectAreas: [],
  institutions: [],
  comparisonRuns: [],
  harvestDatasets: [],
  activeComparison: null, // { run, items }
  activeDataset: null,    // { dataset, publications }
  activeWordcloud: [],    // [{ text, value }]
  selectedInstSet: new Set(),
  activeJobId: null,
  jobPollTimer: null,
};

// Curated Color Palettes matching R packages (ggpomological/Bears, Solarized, RColorBrewer, Viridis)
const PALETTES = {
  pomological: [
    "#c89d7c", "#4b3832", "#6e2625", "#5a4f48", "#3b2f2f",
    "#854442", "#9e5a3c", "#b85d19", "#657459", "#4f6d7a",
    "#be9b7b", "#8c6d53", "#7a6f64", "#8b7d6b", "#c38d9e",
    "#5c6b73", "#9b6a6c", "#b09880", "#d4a373", "#7f5539"
  ],
  solarized: [
    "#b58900", "#cb4b16", "#dc322f", "#d33682", "#6c71c4",
    "#268bd2", "#2aa198", "#859900"
  ],
  paired: [
    "#ff7f00", "#1f78b4", "#33a02c", "#e31a1c", "#6a3d9a",
    "#a6cee3", "#b2df8a", "#fb9a99", "#fdbf6f", "#cab2d6"
  ],
  set2: [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854",
    "#ffd92f", "#e5c494", "#b3b3b3"
  ],
  editorial: [
    "#1e3a8a", "#0f766e", "#b91c1c", "#b45309", "#4338ca",
    "#15803d", "#6d28d9", "#334155"
  ],
  viridis: [
    "#440154", "#482878", "#3e4989", "#31688e", "#26828e",
    "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"
  ],
  dark2: [
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
    "#e6ab02", "#a6761d", "#666666"
  ]
};

const THEMES = {
  pomological: {
    outerBg: "#f6eedc",
    panelBg: "#fbf5e6",
    gridColor: "#eaddc5",
    textColor: "#4a3f35",
    mutedColor: "#7d6e5d",
    vlineColor: "#2b2520",
    palette: PALETTES.pomological,
    paintedDefault: true,
  },
  solarized_light: {
    outerBg: "#fdf6e3",
    panelBg: "#eee8d5",
    gridColor: "#fdf6e3",
    textColor: "#586e75",
    mutedColor: "#839496",
    vlineColor: "#333333",
    palette: PALETTES.solarized,
    paintedDefault: false,
  },
  solarized_dark: {
    outerBg: "#002b36",
    panelBg: "#073642",
    gridColor: "#0d4654",
    textColor: "#eee8d5",
    mutedColor: "#93a1a1",
    vlineColor: "#f59e0b",
    palette: PALETTES.solarized,
    paintedDefault: false,
  },
  editorial: {
    outerBg: "#ffffff",
    panelBg: "#f8fafc",
    gridColor: "#e2e8f0",
    textColor: "#0f172a",
    mutedColor: "#475569",
    vlineColor: "#dc2626",
    palette: PALETTES.editorial,
    paintedDefault: false,
  },
  sector_split: {
    outerBg: "#ffffff",
    panelBg: "#f8fafc",
    gridColor: "#e2e8f0",
    textColor: "#0f172a",
    mutedColor: "#475569",
    vlineColor: "#334155",
    palette: ["#0f766e", "#2563eb", "#d97706"],
    paintedDefault: false,
  },
  viridis: {
    outerBg: "#ffffff",
    panelBg: "#f4f6f9",
    gridColor: "#e2e8f0",
    textColor: "#1e293b",
    mutedColor: "#475569",
    vlineColor: "#e11d48",
    palette: PALETTES.viridis,
    paintedDefault: false,
  }
};

function escapeXml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

// ==================== INITIALIZATION ====================

document.addEventListener("DOMContentLoaded", async () => {
  bindTabNavigation();
  bindComparisonControls();
  bindHarvestControls();
  bindWordcloudControls();
  bindSettingsControls();
  await loadBootstrapData();
});

function bindTabNavigation() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");
      if (btn.dataset.tab === "tab-wordcloud" && STATE.activeWordcloud.length === 0) {
        generateWordCloud();
      }
    });
  });
}

async function loadBootstrapData() {
  const res = await fetch("/api/bootstrap");
  const data = await res.json();
  STATE.settings = data.settings || {};
  STATE.subjectAreas = data.subject_areas || [];
  STATE.institutions = data.institutions || [];
  STATE.comparisonRuns = data.comparison_runs || [];
  STATE.harvestDatasets = data.harvest_datasets || [];

  updateApiStatusPill();
  populateSubjectAreaSelects();
  populateInstitutionChecklists();
  populateComparisonRunsDropdown();
  populateHarvestDatasetsDropdown();
  populateSettingsTab();

  if (STATE.comparisonRuns.length > 0 && !STATE.activeComparison) {
    await loadComparisonRun(STATE.comparisonRuns[0].id);
  }
  if (STATE.harvestDatasets.length > 0 && !STATE.activeDataset) {
    await loadHarvestDataset(STATE.harvestDatasets[0].id);
  }
}

function updateApiStatusPill() {
  const dot = document.getElementById("apiStatusDot");
  const txt = document.getElementById("apiStatusText");
  if (STATE.settings.has_api_key) {
    dot.className = "status-dot ok";
    txt.textContent = `Scopus API Key Activa (${STATE.settings.masked_api_key.slice(0, 6)}...)`;
  } else {
    dot.className = "status-dot warn";
    txt.textContent = "Sin API Key configurada";
  }
}

function populateSubjectAreaSelects() {
  const html = STATE.subjectAreas
    .map((sa) => `<option value="${sa.code}">${sa.code} — ${sa.name_es}</option>`)
    .join("");
  document.getElementById("compQuerySubj").innerHTML = html;
  document.getElementById("harvestSubj").innerHTML = html;
}

// ==================== TAB 1: COMPARISON & AESTHETIC GRAPH STUDIO ====================

function populateComparisonRunsDropdown(selectId = null) {
  const sel = document.getElementById("selectComparisonRun");
  sel.innerHTML = STATE.comparisonRuns
    .map(
      (r) =>
        `<option value="${r.id}">${escapeXml(r.title)} [${r.year} · ${r.subj_area} · ${r.institution_count} inst.]</option>`
    )
    .join("");
  if (selectId) {
    sel.value = String(selectId);
  }
}

async function loadComparisonRun(runId) {
  const res = await fetch(`/api/comparisons/${runId}`);
  if (!res.ok) return;
  const data = await res.json();
  STATE.activeComparison = data;

  const { run, items } = data;
  document.getElementById("selectComparisonRun").value = String(run.id);
  document.getElementById("chartTitleInput").value = run.title || "";
  document.getElementById("chartSubtitleInput").value = run.subtitle || "";
  document.getElementById("chartRefLineVal").value = run.reference_line || 0;

  // Populate city filter from items
  const cities = Array.from(new Set(items.map((i) => i.city).filter(Boolean))).sort();
  const citySel = document.getElementById("chartCityFilter");
  citySel.innerHTML = `<option value="ALL">Todas (${cities.length})</option>` +
    cities.map((c) => `<option value="${escapeXml(c)}">${escapeXml(c)}</option>`).join("");

  // Smart default aspect ratio & theme based on run size
  if (items.length > 25) {
    document.getElementById("chartAspectSelect").value = "tall";
    document.getElementById("chartYLabelInput").value = "Universidades e Institutos de Educación Superior";
  } else {
    document.getElementById("chartAspectSelect").value = "golden";
    document.getElementById("chartYLabelInput").value = "Institutos públicos de investigación / Universidades";
  }
  document.getElementById("chartXLabelInput").value = `Número de publicaciones Scopus (${run.year})`;

  // Update export links
  document.getElementById("btnExportCompCsv").href = `/api/export/comparison/${run.id}?format=csv`;
  document.getElementById("btnExportCompXlsx").href = `/api/export/comparison/${run.id}?format=xlsx`;

  const totalPubs = items.reduce((acc, it) => acc + (it.total_results || 0), 0);
  document.getElementById("comparisonRunMeta").innerHTML = `
    <div><strong>Año:</strong> ${escapeXml(run.year)} &nbsp;|&nbsp; <strong>Área:</strong> ${escapeXml(run.subj_area)}</div>
    <div><strong>Instituciones:</strong> ${items.length} &nbsp;|&nbsp; <strong>Total Publicaciones:</strong> ${totalPubs.toLocaleString()}</div>
    <div><strong>Fuente:</strong> ${escapeXml(run.source)}</div>
  `;

  renderComparisonStage();
}

function getFilteredComparisonItems() {
  if (!STATE.activeComparison) return [];
  let items = [...STATE.activeComparison.items];

  const sector = document.getElementById("chartSectorFilter").value;
  const city = document.getElementById("chartCityFilter").value;
  const hideZero = document.getElementById("chartHideZero").checked;
  const topN = parseInt(document.getElementById("chartTopN").value || "999", 10);

  if (sector !== "ALL") {
    items = items.filter((i) => i.inst_type === sector);
  }
  if (city !== "ALL") {
    items = items.filter((i) => i.city === city);
  }
  if (hideZero) {
    items = items.filter((i) => (i.total_results || 0) > 0);
  }

  items.sort((a, b) => (b.total_results || 0) - (a.total_results || 0));
  return items.slice(0, topN);
}

function renderComparisonStage() {
  const items = getFilteredComparisonItems();
  renderComparisonKpis(items);
  renderComparisonChartSvg(items);
  renderComparisonTable(items);
}

function renderComparisonKpis(items) {
  const total = items.reduce((s, i) => s + (i.total_results || 0), 0);
  const maxItem = items[0];
  const mean = items.length ? (total / items.length).toFixed(1) : "0";
  const sortedVals = items.map((i) => i.total_results || 0).sort((a, b) => a - b);
  const median = sortedVals.length
    ? sortedVals[Math.floor(sortedVals.length / 2)]
    : 0;

  document.getElementById("comparisonKpiStrip").innerHTML = `
    <div class="kpi-chip">Instituciones graficadas: <strong>${items.length}</strong></div>
    <div class="kpi-chip">Suma publicaciones: <strong>${total.toLocaleString()}</strong></div>
    <div class="kpi-chip">Promedio: <strong>${mean}</strong></div>
    <div class="kpi-chip">Mediana: <strong>${median}</strong></div>
    ${maxItem ? `<div class="kpi-chip">Líder: <strong>${escapeXml(maxItem.institution_name)} (${maxItem.total_results})</strong></div>` : ""}
  `;
}

function computeActiveReferenceValue(items) {
  const mode = document.getElementById("chartRefLineMode").value;
  if (mode === "none" || items.length === 0) return null;
  if (mode === "custom") {
    const val = parseFloat(document.getElementById("chartRefLineVal").value);
    return isNaN(val) || val <= 0 ? null : val;
  }
  const vals = items.map((i) => i.total_results || 0).sort((a, b) => a - b);
  if (mode === "max") return vals[vals.length - 1];
  if (mode === "mean") {
    const sum = vals.reduce((a, b) => a + b, 0);
    const mean = Math.round(sum / vals.length);
    document.getElementById("chartRefLineVal").value = mean;
    return mean;
  }
  if (mode === "median") {
    const med = vals[Math.floor(vals.length / 2)];
    document.getElementById("chartRefLineVal").value = med;
    return med;
  }
  return null;
}

function getItemColor(item, idx, themeKey, themeObj) {
  if (themeKey === "sector_split") {
    if (item.category === "Research Institute") return "#d97706";
    return item.inst_type === "Public" ? "#0f766e" : "#2563eb";
  }
  const pal = themeObj.palette;
  return pal[idx % pal.length];
}

function renderComparisonChartSvg(items) {
  const container = document.getElementById("chartCanvasContainer");
  if (!items.length) {
    container.innerHTML = `<div style="padding:40px;color:#64748b;">No hay datos que coincidan con los filtros seleccionados.</div>`;
    return;
  }

  const chartType = document.getElementById("chartTypeSelect").value;
  const themeKey = document.getElementById("chartThemeSelect").value;
  const theme = THEMES[themeKey] || THEMES.pomological;
  const fontFamily = document.getElementById("chartFontSelect").value;
  const showValues = document.getElementById("chartShowValues").checked;
  const paintedEffect = document.getElementById("chartPaintedEffect").checked && themeKey === "pomological";
  const aspect = document.getElementById("chartAspectSelect").value;

  const title = document.getElementById("chartTitleInput").value;
  const subtitle = document.getElementById("chartSubtitleInput").value;
  const xLabel = document.getElementById("chartXLabelInput").value;
  const yLabel = document.getElementById("chartYLabelInput").value;
  const refValue = computeActiveReferenceValue(items);

  if (chartType === "radial") {
    container.innerHTML = buildRadialChartSvg(items, {
      themeKey, theme, fontFamily, showValues, paintedEffect, title, subtitle
    });
    return;
  }

  if (chartType === "vbar") {
    container.innerHTML = buildVerticalBarSvg(items, {
      themeKey, theme, fontFamily, showValues, paintedEffect, title, subtitle, xLabel, yLabel, refValue
    });
    return;
  }

  if (chartType === "city_summary") {
    const cityMap = new Map();
    for (const it of items) {
      const c = it.city || "Otra";
      cityMap.set(c, (cityMap.get(c) || 0) + (it.total_results || 0));
    }
    const cityItems = Array.from(cityMap.entries())
      .map(([c, total]) => ({
        institution_name: c,
        total_results: total,
        inst_type: "Public",
        category: "City",
      }))
      .sort((a, b) => b.total_results - a.total_results);
    container.innerHTML = buildHorizontalChartSvg(cityItems, {
      chartType: "hbar",
      themeKey, theme, fontFamily, showValues, paintedEffect, aspect: "golden",
      title: `${title} — Por Ciudad`,
      subtitle,
      xLabel,
      yLabel: "Ciudad",
      refValue: null,
    });
    return;
  }

  container.innerHTML = buildHorizontalChartSvg(items, {
    chartType, themeKey, theme, fontFamily, showValues, paintedEffect, aspect,
    title, subtitle, xLabel, yLabel, refValue
  });
}

function buildSvgFilterDefs(paintedEffect, outerBg) {
  if (!paintedEffect) return "";
  return `
    <defs>
      <!-- Pomological Painted Watercolor & Parchment Texture Filter -->
      <filter id="pomologicalPaint" x="-2%" y="-2%" width="104%" height="104%">
        <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="3" result="noise" seed="7"/>
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.6" xChannelSelector="R" yChannelSelector="G" result="displaced"/>
      </filter>
      <filter id="paperGrain" x="0%" y="0%" width="100%" height="100%">
        <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" result="fineNoise"/>
        <feColorMatrix type="matrix" values="0 0 0 0 0.82  0 0 0 0 0.76  0 0 0 0 0.65  0 0 0 0.08 0" in="fineNoise" result="tintedNoise"/>
        <feBlend mode="multiply" in="SourceGraphic" in2="tintedNoise"/>
      </filter>
    </defs>
  `;
}

function buildHorizontalChartSvg(items, opts) {
  const {
    chartType, themeKey, theme, fontFamily, showValues, paintedEffect, aspect,
    title, subtitle, xLabel, yLabel, refValue
  } = opts;

  const n = items.length;
  let width = 1080;
  let rowHeight = n > 35 ? 19 : n > 18 ? 26 : 48;
  let minHeight = aspect === "golden" ? 668 : aspect === "wide" ? 608 : aspect === "square" ? 960 : 720;
  const marginTop = subtitle ? 76 : 58;
  const marginBottom = 72;
  const maxNameLen = Math.max(...items.map((i) => i.institution_name.length), 20);
  const marginLeft = Math.min(430, Math.max(250, maxNameLen * 6.4 + 45));
  const marginRight = 70;

  const height = Math.max(minHeight, marginTop + marginBottom + n * rowHeight + 20);
  const plotW = width - marginLeft - marginRight;
  const plotH = height - marginTop - marginBottom;

  const maxDataVal = Math.max(...items.map((i) => i.total_results || 0), refValue || 0, 10);
  const xMax = maxDataVal * 1.08;
  const xScale = (v) => marginLeft + (v / xMax) * plotW;

  // Nice X ticks
  const tickCount = 5;
  const rawStep = maxDataVal / tickCount;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)));
  const residual = rawStep / mag;
  const niceStep = residual > 5 ? 10 * mag : residual > 2 ? 5 * mag : residual > 1 ? 2 * mag : mag;
  const ticks = [];
  for (let t = 0; t <= xMax; t += niceStep) {
    ticks.push(Math.round(t));
  }

  const filterAttr = paintedEffect ? `filter="url(#pomologicalPaint)"` : "";
  const labelFontSize = n > 40 ? 11.2 : n > 20 ? 12.5 : 13.5;

  let svg = `<svg id="mainRenderedSvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" style="font-family: ${escapeXml(fontFamily)};">`;
  svg += buildSvgFilterDefs(paintedEffect, theme.outerBg);

  // Outer background
  svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="${theme.outerBg}"/>`;
  // Plot panel background
  svg += `<rect x="${marginLeft}" y="${marginTop}" width="${plotW}" height="${plotH}" fill="${theme.panelBg}" rx="3"/>`;

  // Horizontal & Vertical Gridlines
  for (const t of ticks) {
    const x = xScale(t).toFixed(1);
    svg += `<line x1="${x}" y1="${marginTop}" x2="${x}" y2="${marginTop + plotH}" stroke="${theme.gridColor}" stroke-width="1.2"/>`;
    svg += `<text x="${x}" y="${marginTop + plotH + 22}" text-anchor="middle" fill="${theme.mutedColor}" font-size="12.5">${t.toLocaleString()}</text>`;
  }

  const stepY = plotH / n;
  svg += `<g ${filterAttr}>`;

  items.forEach((item, idx) => {
    const cy = marginTop + stepY * (idx + 0.5);
    const val = item.total_results || 0;
    const xEnd = xScale(val);
    const xStart = xScale(0);
    const color = getItemColor(item, idx, themeKey, theme);

    // Subtle horizontal guide line
    svg += `<line x1="${marginLeft}" y1="${cy.toFixed(1)}" x2="${marginLeft + plotW}" y2="${cy.toFixed(1)}" stroke="${theme.gridColor}" stroke-width="0.9"/>`;

    if (chartType === "lollipop") {
      const strokeW = n > 40 ? 5.2 : n > 20 ? 6.8 : 8.5;
      const radius = n > 40 ? 4.8 : n > 20 ? 6.2 : 8.0;
      svg += `<line x1="${xStart.toFixed(1)}" y1="${cy.toFixed(1)}" x2="${xEnd.toFixed(1)}" y2="${cy.toFixed(1)}" stroke="${color}" stroke-width="${strokeW}" stroke-linecap="butt"/>`;
      svg += `<circle cx="${xEnd.toFixed(1)}" cy="${cy.toFixed(1)}" r="${radius}" fill="${color}" stroke="${theme.panelBg}" stroke-width="1"/>`;
    } else {
      const barH = Math.max(6, stepY * 0.68);
      const barW = Math.max(2, xEnd - xStart);
      svg += `<rect x="${xStart.toFixed(1)}" y="${(cy - barH / 2).toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" rx="2.5"/>`;
    }

    if (showValues) {
      const valX = xEnd + (n > 40 ? 8 : 11);
      svg += `<text x="${valX.toFixed(1)}" y="${(cy + labelFontSize * 0.34).toFixed(1)}" fill="${theme.textColor}" font-size="${labelFontSize - 0.5}" font-weight="600">${val.toLocaleString()}</text>`;
    }
  });

  // Reference vertical dashed line (geom_vline)
  if (refValue !== null && refValue >= 0 && refValue <= xMax) {
    const rx = xScale(refValue).toFixed(1);
    svg += `<line x1="${rx}" y1="${marginTop}" x2="${rx}" y2="${marginTop + plotH}" stroke="${theme.vlineColor}" stroke-width="1.6" stroke-dasharray="6,6"/>`;
    svg += `<text x="${(parseFloat(rx) - 6).toFixed(1)}" y="${marginTop + 16}" text-anchor="end" fill="${theme.vlineColor}" font-size="11.5" font-weight="700">Ref: ${refValue.toLocaleString()}</text>`;
  }

  svg += `</g>`;

  // Institution Y-axis Labels
  items.forEach((item, idx) => {
    const cy = marginTop + stepY * (idx + 0.5);
    svg += `<line x1="${marginLeft - 4}" y1="${cy.toFixed(1)}" x2="${marginLeft}" y2="${cy.toFixed(1)}" stroke="${theme.mutedColor}" stroke-width="1"/>`;
    svg += `<text x="${marginLeft - 8}" y="${(cy + labelFontSize * 0.34).toFixed(1)}" text-anchor="end" fill="${theme.mutedColor}" font-size="${labelFontSize}">${escapeXml(item.institution_name)}</text>`;
  });

  // Titles & Axis Labels
  svg += `<text x="${marginLeft}" y="32" fill="${theme.textColor}" font-size="20" font-weight="700">${escapeXml(title)}</text>`;
  if (subtitle) {
    svg += `<text x="${marginLeft}" y="53" fill="${theme.mutedColor}" font-size="13.5">${escapeXml(subtitle)}</text>`;
  }

  // X-axis Title
  svg += `<text x="${(marginLeft + plotW / 2).toFixed(1)}" y="${height - 20}" text-anchor="middle" fill="${theme.textColor}" font-size="14.5" font-weight="600">${escapeXml(xLabel)}</text>`;

  // Y-axis Rotated Title
  const yTitleY = (marginTop + plotH / 2).toFixed(1);
  svg += `<text transform="translate(22, ${yTitleY}) rotate(-90)" text-anchor="middle" fill="${theme.textColor}" font-size="14.5" font-weight="600">${escapeXml(yLabel)}</text>`;

  // Legend if sector_split theme is active
  if (themeKey === "sector_split") {
    svg += `
      <g transform="translate(${width - marginRight - 240}, 20)">
        <circle cx="8" cy="8" r="5" fill="#0f766e"/><text x="18" y="12" fill="${theme.textColor}" font-size="12">Pública</text>
        <circle cx="82" cy="8" r="5" fill="#2563eb"/><text x="92" y="12" fill="${theme.textColor}" font-size="12">Privada</text>
        <circle cx="156" cy="8" r="5" fill="#d97706"/><text x="166" y="12" fill="${theme.textColor}" font-size="12">Instituto</text>
      </g>
    `;
  }

  svg += `</svg>`;
  return svg;
}

function buildVerticalBarSvg(items, opts) {
  const {
    themeKey, theme, fontFamily, showValues, paintedEffect,
    title, subtitle, xLabel, yLabel, refValue
  } = opts;

  const displayItems = items.slice(0, 25); // Keep vertical bars readable
  const n = displayItems.length;
  const width = Math.max(920, n * 54 + 180);
  const height = 680;
  const marginTop = subtitle ? 76 : 56;
  const marginBottom = 185;
  const marginLeft = 90;
  const marginRight = 40;

  const plotW = width - marginLeft - marginRight;
  const plotH = height - marginTop - marginBottom;

  const maxDataVal = Math.max(...displayItems.map((i) => i.total_results || 0), refValue || 0, 10);
  const yMax = maxDataVal * 1.1;
  const yScale = (v) => marginTop + plotH - (v / yMax) * plotH;

  let svg = `<svg id="mainRenderedSvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" style="font-family: ${escapeXml(fontFamily)};">`;
  svg += buildSvgFilterDefs(paintedEffect, theme.outerBg);
  svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="${theme.outerBg}"/>`;
  svg += `<rect x="${marginLeft}" y="${marginTop}" width="${plotW}" height="${plotH}" fill="${theme.panelBg}" rx="3"/>`;

  // Y gridlines
  for (let i = 0; i <= 5; i++) {
    const val = Math.round((maxDataVal / 5) * i);
    const y = yScale(val).toFixed(1);
    svg += `<line x1="${marginLeft}" y1="${y}" x2="${marginLeft + plotW}" y2="${y}" stroke="${theme.gridColor}" stroke-width="1.2"/>`;
    svg += `<text x="${marginLeft - 10}" y="${(parseFloat(y) + 4).toFixed(1)}" text-anchor="end" fill="${theme.mutedColor}" font-size="12">${val.toLocaleString()}</text>`;
  }

  const colW = plotW / n;
  const barW = Math.min(58, colW * 0.68);

  displayItems.forEach((item, idx) => {
    const cx = marginLeft + colW * (idx + 0.5);
    const val = item.total_results || 0;
    const yTop = yScale(val);
    const barH = Math.max(2, marginTop + plotH - yTop);
    const color = themeKey === "solarized_light" ? "#69b3a2" : getItemColor(item, idx, themeKey, theme);

    svg += `<rect x="${(cx - barW / 2).toFixed(1)}" y="${yTop.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" rx="2"/>`;
    if (showValues) {
      svg += `<text x="${cx.toFixed(1)}" y="${(yTop - 7).toFixed(1)}" text-anchor="middle" fill="${theme.textColor}" font-size="11.5" font-weight="600">${val.toLocaleString()}</text>`;
    }

    // Rotated 45-degree wrapped label (matching plot.R)
    const shortName = item.institution_name.length > 34
      ? item.institution_name.slice(0, 32) + "…"
      : item.institution_name;
    svg += `<text transform="translate(${cx.toFixed(1)}, ${marginTop + plotH + 16}) rotate(-40)" text-anchor="end" fill="${theme.mutedColor}" font-size="11.5">${escapeXml(shortName)}</text>`;
  });

  svg += `<text x="${marginLeft + plotW / 2}" y="34" text-anchor="middle" fill="${theme.textColor}" font-size="20" font-weight="700">${escapeXml(title)}</text>`;
  if (subtitle) {
    svg += `<text x="${marginLeft + plotW / 2}" y="54" text-anchor="middle" fill="${theme.mutedColor}" font-size="13">${escapeXml(subtitle)}</text>`;
  }
  svg += `<text x="${marginLeft + plotW / 2}" y="${height - 16}" text-anchor="middle" fill="${theme.textColor}" font-size="14" font-weight="600">${escapeXml(yLabel)}</text>`;
  svg += `<text transform="translate(24, ${marginTop + plotH / 2}) rotate(-90)" text-anchor="middle" fill="${theme.textColor}" font-size="14" font-weight="600">${escapeXml(xLabel)}</text>`;
  svg += `</svg>`;
  return svg;
}

function buildRadialChartSvg(items, opts) {
  const { themeKey, theme, fontFamily, showValues, title, subtitle } = opts;
  const displayItems = items.slice(0, 30);
  const n = displayItems.length;
  const width = 920;
  const height = 820;
  const cx = width / 2;
  const cy = height / 2 + 25;
  const innerR = 105;
  const maxOuterR = 305;

  const maxVal = Math.max(...displayItems.map((i) => i.total_results || 0), 10);

  let svg = `<svg id="mainRenderedSvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" style="font-family: ${escapeXml(fontFamily)};">`;
  svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="${theme.outerBg}"/>`;

  // Concentric reference rings
  [0.25, 0.5, 0.75, 1.0].forEach((frac) => {
    const r = innerR + frac * (maxOuterR - innerR);
    const ringVal = Math.round(maxVal * frac);
    svg += `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="none" stroke="${theme.gridColor}" stroke-dasharray="4,4" stroke-width="1.1"/>`;
    svg += `<text x="${cx}" y="${(cy - r + 12).toFixed(1)}" text-anchor="middle" fill="${theme.mutedColor}" font-size="10">${ringVal}</text>`;
  });

  const angleStep = (2 * Math.PI) / n;

  displayItems.forEach((item, idx) => {
    const val = item.total_results || 0;
    const angle = idx * angleStep - Math.PI / 2;
    const barLen = Math.max(6, (val / maxVal) * (maxOuterR - innerR));
    const rEnd = innerR + barLen;
    const color = getItemColor(item, idx, themeKey, theme);

    const x1 = cx + innerR * Math.cos(angle);
    const y1 = cy + innerR * Math.sin(angle);
    const x2 = cx + rEnd * Math.cos(angle);
    const y2 = cy + rEnd * Math.sin(angle);

    svg += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${color}" stroke-width="${Math.max(5, Math.min(16, 260 / n))}" stroke-linecap="round"/>`;
    svg += `<circle cx="${x2.toFixed(1)}" cy="${y2.toFixed(1)}" r="4.5" fill="${color}"/>`;

    const labelR = rEnd + 12;
    const lx = cx + labelR * Math.cos(angle);
    const ly = cy + labelR * Math.sin(angle);
    const deg = (angle * 180) / Math.PI;
    const flip = deg > 90 && deg < 270;
    const rot = flip ? deg + 180 : deg;
    const anchor = flip ? "end" : "start";
    const shortName = item.institution_name.replace(/^Universidad /i, "U. ").slice(0, 26);
    const labelText = showValues ? `${shortName} (${val})` : shortName;

    svg += `<text transform="translate(${lx.toFixed(1)}, ${ly.toFixed(1)}) rotate(${rot.toFixed(1)})" text-anchor="${anchor}" alignment-baseline="middle" fill="${theme.textColor}" font-size="10.5" font-weight="500">${escapeXml(labelText)}</text>`;
  });

  svg += `<circle cx="${cx}" cy="${cy}" r="${innerR - 4}" fill="${theme.panelBg}" stroke="${theme.gridColor}"/>`;
  svg += `<text x="${cx}" y="${cy - 6}" text-anchor="middle" fill="${theme.textColor}" font-size="14" font-weight="700">SCOPUS</text>`;
  svg += `<text x="${cx}" y="${cy + 14}" text-anchor="middle" fill="${theme.mutedColor}" font-size="11">Top ${n} IES</text>`;

  svg += `<text x="${cx}" y="38" text-anchor="middle" fill="${theme.textColor}" font-size="20" font-weight="700">${escapeXml(title)}</text>`;
  if (subtitle) {
    svg += `<text x="${cx}" y="60" text-anchor="middle" fill="${theme.mutedColor}" font-size="13">${escapeXml(subtitle)}</text>`;
  }
  svg += `</svg>`;
  return svg;
}

function renderComparisonTable(items) {
  const search = (document.getElementById("compTableSearch").value || "").toLowerCase().trim();
  const totalSum = items.reduce((s, i) => s + (i.total_results || 0), 0) || 1;
  const tbody = document.querySelector("#comparisonDataTable tbody");

  const filtered = search
    ? items.filter(
        (i) =>
          i.institution_name.toLowerCase().includes(search) ||
          (i.city || "").toLowerCase().includes(search)
      )
    : items;

  tbody.innerHTML = filtered
    .map((item, idx) => {
      const pct = (((item.total_results || 0) / totalSum) * 100).toFixed(1);
      const badgeClass =
        item.category === "Research Institute"
          ? "badge-institute"
          : item.inst_type === "Public"
          ? "badge-public"
          : "badge-private";
      return `
        <tr>
          <td>${idx + 1}</td>
          <td><strong>${escapeXml(item.institution_name)}</strong></td>
          <td>${escapeXml(item.category)}</td>
          <td><span class="badge ${badgeClass}">${escapeXml(item.inst_type)}</span></td>
          <td>${escapeXml(item.city || "—")}</td>
          <td class="num-col">${(item.total_results || 0).toLocaleString()}</td>
          <td class="num-col">${pct}%</td>
          <td><code style="font-size:0.72rem;color:#475569;">${escapeXml(item.query_used)}</code></td>
        </tr>
      `;
    })
    .join("");
}

function bindComparisonControls() {
  document.getElementById("selectComparisonRun").addEventListener("change", (e) => {
    loadComparisonRun(parseInt(e.target.value, 10));
  });

  // Live reactive graph controls
  [
    "chartTypeSelect", "chartThemeSelect", "chartTitleInput", "chartSubtitleInput",
    "chartXLabelInput", "chartYLabelInput", "chartTopN", "chartSectorFilter",
    "chartCityFilter", "chartRefLineMode", "chartRefLineVal", "chartAspectSelect",
    "chartFontSelect", "chartShowValues", "chartPaintedEffect", "chartHideZero"
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", () => renderComparisonStage());
      el.addEventListener("change", () => renderComparisonStage());
    }
  });

  document.getElementById("compTableSearch").addEventListener("input", () => {
    renderComparisonTable(getFilteredComparisonItems());
  });

  // Toggle New Comparison Query Builder
  document.getElementById("btnOpenNewComparison").addEventListener("click", () => {
    document.getElementById("newComparisonCard").classList.remove("hidden");
  });
  document.getElementById("btnCloseNewComparison").addEventListener("click", () => {
    document.getElementById("newComparisonCard").classList.add("hidden");
  });

  // Preset selection pills
  document.querySelectorAll(".pill-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyInstitutionPreset(btn.dataset.preset));
  });

  document.getElementById("instFilterSearch").addEventListener("input", () => {
    renderInstitutionChecklistItems();
  });

  ["compQueryYear", "compQuerySubj", "compQueryOA"].forEach((id) => {
    document.getElementById(id).addEventListener("input", updateQueryPreview);
    document.getElementById(id).addEventListener("change", updateQueryPreview);
  });

  document.getElementById("btnRunComparisonJob").addEventListener("click", launchComparisonJob);

  document.getElementById("btnDeleteCompRun").addEventListener("click", async () => {
    if (!STATE.activeComparison) return;
    if (!confirm(`¿Eliminar la evaluación "${STATE.activeComparison.run.title}"?`)) return;
    await fetch(`/api/comparisons/${STATE.activeComparison.run.id}`, { method: "DELETE" });
    STATE.activeComparison = null;
    await loadBootstrapData();
  });

  // Export SVG & 300-DPI PNG
  document.getElementById("btnDownloadSvg").addEventListener("click", () => {
    const svgEl = document.getElementById("mainRenderedSvg");
    if (!svgEl) return;
    downloadSvgElement(svgEl, `Scopus_Graph_${Date.now()}.svg`);
  });

  document.getElementById("btnDownloadPng").addEventListener("click", () => {
    const svgEl = document.getElementById("mainRenderedSvg");
    if (!svgEl) return;
    downloadSvgAsPng(svgEl, `Scopus_Graph_300DPI_${Date.now()}.png`, 3.0);
  });
}

function populateInstitutionChecklists() {
  // Default preset: 6 Public Research Institutes
  STATE.selectedInstSet.clear();
  STATE.institutions
    .filter((i) => i.category === "Research Institute")
    .forEach((i) => STATE.selectedInstSet.add(i.name));

  renderInstitutionChecklistItems();
  updateQueryPreview();

  // Also populate Harvester institution dropdown
  const harvSel = document.getElementById("harvestInstSelect");
  harvSel.innerHTML = STATE.institutions
    .map((i) => `<option value="${escapeXml(i.name)}">${escapeXml(i.name)} (${escapeXml(i.category)})</option>`)
    .join("");
  harvSel.value = "Instituto Nacional de Biodiversidad";
}

function applyInstitutionPreset(preset) {
  STATE.selectedInstSet.clear();
  if (preset === "institutes") {
    STATE.institutions
      .filter((i) => i.category === "Research Institute")
      .forEach((i) => STATE.selectedInstSet.add(i.name));
  } else if (preset === "agri6") {
    [
      "Pontificia Universidad Católica del Ecuador",
      "Universidad de las Fuerzas Armadas",
      "Universidad Regional Amazónica Ikiam",
      "Instituto Nacional de Biodiversidad",
      "Universidad de Las Américas",
      "Universidad San Francisco de Quito"
    ].forEach((n) => STATE.selectedInstSet.add(n));
  } else if (preset === "public_univ") {
    STATE.institutions
      .filter((i) => i.category === "University" && i.inst_type === "Public")
      .forEach((i) => STATE.selectedInstSet.add(i.name));
  } else if (preset === "private_univ") {
    STATE.institutions
      .filter((i) => i.category === "University" && i.inst_type === "Private")
      .forEach((i) => STATE.selectedInstSet.add(i.name));
  } else if (preset === "all_univ") {
    STATE.institutions
      .filter((i) => i.category === "University")
      .forEach((i) => STATE.selectedInstSet.add(i.name));
  }
  renderInstitutionChecklistItems();
  updateQueryPreview();
}

function renderInstitutionChecklistItems() {
  const filter = (document.getElementById("instFilterSearch").value || "").toLowerCase().trim();
  const box = document.getElementById("instChecklist");
  document.getElementById("selectedInstCount").textContent = String(STATE.selectedInstSet.size);

  const list = filter
    ? STATE.institutions.filter(
        (i) =>
          i.name.toLowerCase().includes(filter) ||
          (i.city || "").toLowerCase().includes(filter)
      )
    : STATE.institutions;

  box.innerHTML = list
    .map((inst) => {
      const checked = STATE.selectedInstSet.has(inst.name) ? "checked" : "";
      return `
        <div class="checklist-item">
          <label>
            <input type="checkbox" data-inst-name="${escapeXml(inst.name)}" ${checked} />
            <span>${escapeXml(inst.name)}</span>
          </label>
          <span class="city-tag">${escapeXml(inst.city || inst.category)}</span>
        </div>
      `;
    })
    .join("");

  box.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const name = cb.dataset.instName;
      if (cb.checked) STATE.selectedInstSet.add(name);
      else STATE.selectedInstSet.delete(name);
      document.getElementById("selectedInstCount").textContent = String(STATE.selectedInstSet.size);
      updateQueryPreview();
    });
  });
}

function updateQueryPreview() {
  const sampleInst = Array.from(STATE.selectedInstSet)[0] || "Pontificia Universidad Católica del Ecuador";
  const year = document.getElementById("compQueryYear").value || "2025";
  const subj = document.getElementById("compQuerySubj").value || "ALL";
  const oa = document.getElementById("compQueryOA").checked;

  const normSample = sampleInst.toLowerCase();
  let q =
    normSample === "universidad nacional de educación"
      ? `(AFFIL("Universidad Nacional de Educación") AND AFFIL("Azogues"))`
      : normSample === "universidad de las américas"
      ? `AF-ID(60104441)`
      : normSample.includes("yachay")
      ? `(AF-ID(60105012) OR (AFFIL("Yachay") AND AFFILCOUNTRY(Ecuador)))`
      : `AFFIL("${sampleInst}") AND AFFILCOUNTRY(Ecuador)`;
  if (subj !== "ALL") q += ` AND SUBJAREA(${subj})`;
  q += ` AND PUBYEAR = ${year}`;
  if (oa) q += ` AND ACCESSTYPE(OA)`;
  document.getElementById("compQueryPreview").textContent = q;
}

async function launchComparisonJob() {
  const institutions = Array.from(STATE.selectedInstSet);
  if (institutions.length === 0) {
    alert("Selecciona al menos una institución para consultar en Scopus.");
    return;
  }
  const year = document.getElementById("compQueryYear").value || "2025";
  const subj_area = document.getElementById("compQuerySubj").value || "ALL";
  const open_access_only = document.getElementById("compQueryOA").checked;
  const sleep_time = parseFloat(document.getElementById("compSleepTime").value || "0.5");
  const title =
    document.getElementById("compQueryTitle").value.trim() ||
    `Publicaciones Scopus (${year} — ${subj_area})`;

  const res = await fetch("/api/jobs/comparison", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      year,
      subj_area,
      open_access_only,
      sleep_time,
      institutions,
    }),
  });
  const data = await res.json();
  if (data.job_id) {
    startJobMonitoring(data.job_id);
  }
}

// ==================== TAB 2: HARVESTER & PUBLICATIONS CATALOG ====================

function populateHarvestDatasetsDropdown(selectId = null) {
  const html = STATE.harvestDatasets
    .map(
      (d) =>
        `<option value="${d.id}">${escapeXml(d.title)} [${d.total_records} artículos]</option>`
    )
    .join("");
  document.getElementById("selectHarvestDataset").innerHTML = html;
  document.getElementById("wcDatasetSelect").innerHTML = html;
  if (selectId) {
    document.getElementById("selectHarvestDataset").value = String(selectId);
    document.getElementById("wcDatasetSelect").value = String(selectId);
  }
}

async function loadHarvestDataset(dsId) {
  const res = await fetch(`/api/datasets/${dsId}`);
  if (!res.ok) return;
  const data = await res.json();
  STATE.activeDataset = data;

  const { dataset, publications } = data;
  document.getElementById("selectHarvestDataset").value = String(dataset.id);
  document.getElementById("wcDatasetSelect").value = String(dataset.id);

  document.getElementById("btnExportDatasetCsv").href = `/api/export/dataset/${dataset.id}?format=csv`;
  document.getElementById("btnExportDatasetXlsx").href = `/api/export/dataset/${dataset.id}?format=xlsx`;

  document.getElementById("harvestDatasetMeta").innerHTML = `
    <div><strong>Institución:</strong> ${escapeXml(dataset.institution_name)}</div>
    <div><strong>Año:</strong> ${escapeXml(dataset.year)} &nbsp;|&nbsp; <strong>Vista:</strong> ${escapeXml(dataset.view_mode)}</div>
    <div><strong>Artículos únicos:</strong> ${publications.length}</div>
    <div><strong>Consulta:</strong> <code>${escapeXml(dataset.query_used)}</code></div>
  `;

  renderDatasetJournalsChart(publications);
  renderPublicationsTable(publications);
}

function renderDatasetJournalsChart(publications) {
  const journalCounts = new Map();
  let withDoi = 0;
  for (const p of publications) {
    const j = (p.journal_name || "Sin Revista").trim();
    journalCounts.set(j, (journalCounts.get(j) || 0) + 1);
    if (p.doi) withDoi++;
  }
  const topJournals = Array.from(journalCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  document.getElementById("datasetKpiPills").innerHTML = `
    <div class="kpi-chip">Total artículos: <strong>${publications.length}</strong></div>
    <div class="kpi-chip">Revistas distintas: <strong>${journalCounts.size}</strong></div>
    <div class="kpi-chip">Con DOI: <strong>${withDoi}</strong></div>
  `;

  if (topJournals.length === 0) {
    document.getElementById("datasetJournalsChart").innerHTML = "";
    return;
  }

  const maxCount = topJournals[0][1] || 1;
  const width = 940;
  const rowH = 26;
  const height = topJournals.length * rowH + 30;
  const leftM = 320;
  const barAreaW = width - leftM - 60;

  let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}">`;
  topJournals.forEach(([jName, count], idx) => {
    const y = idx * rowH + 16;
    const w = Math.max(4, (count / maxCount) * barAreaW);
    const color = PALETTES.paired[idx % PALETTES.paired.length];
    const shortJ = jName.length > 44 ? jName.slice(0, 42) + "…" : jName;
    svg += `<text x="${leftM - 10}" y="${y + 11}" text-anchor="end" font-size="11.5" fill="#334155">${escapeXml(shortJ)}</text>`;
    svg += `<rect x="${leftM}" y="${y}" width="${w.toFixed(1)}" height="15" rx="3" fill="${color}"/>`;
    svg += `<text x="${(leftM + w + 8).toFixed(1)}" y="${y + 12}" font-size="11.5" font-weight="700" fill="#0f172a">${count}</text>`;
  });
  svg += `</svg>`;
  document.getElementById("datasetJournalsChart").innerHTML = svg;
}

function renderPublicationsTable(publications) {
  const q = (document.getElementById("pubTableSearch").value || "").toLowerCase().trim();
  const tbody = document.querySelector("#publicationsDataTable tbody");

  const filtered = q
    ? publications.filter(
        (p) =>
          (p.article_name || "").toLowerCase().includes(q) ||
          (p.journal_name || "").toLowerCase().includes(q) ||
          (p.authors_list || "").toLowerCase().includes(q) ||
          (p.affiliations || "").toLowerCase().includes(q) ||
          (p.doi || "").toLowerCase().includes(q)
      )
    : publications;

  tbody.innerHTML = filtered
    .map((p, idx) => {
      const doiHtml = p.doi
        ? `<a class="doi-link" href="https://doi.org/${encodeURIComponent(p.doi)}" target="_blank" rel="noopener">${escapeXml(p.doi)}</a>`
        : "—";
      return `
        <tr>
          <td>${idx + 1}</td>
          <td><strong>${escapeXml(p.article_name)}</strong></td>
          <td>${escapeXml(p.journal_name || "—")}</td>
          <td style="white-space:nowrap;">${escapeXml(p.date_publication || "—")}</td>
          <td>${escapeXml(p.issn_isbn || "—")}</td>
          <td>${escapeXml(p.authors_list || "—")}</td>
          <td style="font-size:0.75rem;color:#475569;">${escapeXml(p.affiliations || "—")}</td>
          <td>${doiHtml}</td>
        </tr>
      `;
    })
    .join("");
}

function bindHarvestControls() {
  document.getElementById("selectHarvestDataset").addEventListener("change", (e) => {
    loadHarvestDataset(parseInt(e.target.value, 10));
  });

  document.getElementById("pubTableSearch").addEventListener("input", () => {
    if (STATE.activeDataset) {
      renderPublicationsTable(STATE.activeDataset.publications);
    }
  });

  document.getElementById("harvestInstSelect").addEventListener("change", (e) => {
    const val = e.target.value;
    document.getElementById("harvestTargetPattern").value = val.includes("Biodiversidad")
      ? "Instituto Nacional de Biodiversidad|INABIO"
      : val;
  });

  document.getElementById("btnRunHarvestJob").addEventListener("click", async () => {
    const customInst = document.getElementById("harvestCustomInst").value.trim();
    const institution_name = customInst || document.getElementById("harvestInstSelect").value;
    const year = document.getElementById("harvestYear").value.trim() || "2025";
    const subj_area = document.getElementById("harvestSubj").value || "ALL";
    const view_mode = document.getElementById("harvestViewMode").value || "STANDARD";
    const max_records = parseInt(document.getElementById("harvestMaxRecords").value || "500", 10);
    const target_pattern = document.getElementById("harvestTargetPattern").value.trim();
    const open_access_only = document.getElementById("harvestOAOnly").checked;

    const res = await fetch("/api/jobs/harvest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        institution_name,
        year,
        subj_area,
        view_mode,
        max_records,
        target_pattern,
        open_access_only,
      }),
    });
    const data = await res.json();
    if (data.job_id) {
      startJobMonitoring(data.job_id);
    }
  });

  document.getElementById("btnSendToWordcloud").addEventListener("click", () => {
    document.querySelector('.tab-btn[data-tab="tab-wordcloud"]').click();
    generateWordCloud();
  });

  document.getElementById("btnDeleteDataset").addEventListener("click", async () => {
    if (!STATE.activeDataset) return;
    if (!confirm(`¿Eliminar el dataset "${STATE.activeDataset.dataset.title}"?`)) return;
    await fetch(`/api/datasets/${STATE.activeDataset.dataset.id}`, { method: "DELETE" });
    STATE.activeDataset = null;
    await loadBootstrapData();
  });
}

// ==================== TAB 3: WORD CLOUD & TEXT ANALYTICS STUDIO ====================

function bindWordcloudControls() {
  document.getElementById("btnGenerateWordcloud").addEventListener("click", generateWordCloud);
  [
    "wcDatasetSelect", "wcSourceField", "wcPaletteSelect",
    "wcBgSelect", "wcMaxWords", "wcMinFreq", "wcRotPer"
  ].forEach((id) => {
    document.getElementById(id).addEventListener("change", generateWordCloud);
  });

  document.getElementById("btnDownloadWcSvg").addEventListener("click", () => {
    const svgEl = document.getElementById("wcRenderedSvg");
    if (svgEl) downloadSvgElement(svgEl, `Wordcloud_Scopus_${Date.now()}.svg`);
  });

  document.getElementById("btnDownloadWcPng").addEventListener("click", () => {
    const svgEl = document.getElementById("wcRenderedSvg");
    if (svgEl) downloadSvgAsPng(svgEl, `Wordcloud_Scopus_1200px_${Date.now()}.png`, 2.0);
  });
}

async function generateWordCloud() {
  const dsId = document.getElementById("wcDatasetSelect").value;
  if (!dsId) return;

  const source_field = document.getElementById("wcSourceField").value;
  const max_words = parseInt(document.getElementById("wcMaxWords").value || "110", 10);
  const min_freq = parseInt(document.getElementById("wcMinFreq").value || "1", 10);
  const extra_stopwords = document.getElementById("wcExtraStopwords").value || "";
  const split_mode = source_field === "affiliations" || source_field === "authors_list" ? "entities" : "words";

  const res = await fetch(`/api/datasets/${dsId}/wordcloud`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_field,
      max_words,
      min_freq,
      extra_stopwords,
      split_mode,
    }),
  });
  const data = await res.json();
  STATE.activeWordcloud = data.words || [];

  const fieldNames = {
    article_name: "Títulos de Artículos",
    journal_name: "Revistas Científicas (Journals)",
    affiliations: "Instituciones Coautoras",
    authors_list: "Autores e Investigadores",
  };
  document.getElementById("wcStageTitle").textContent = `Nube de Palabras — ${fieldNames[source_field] || source_field}`;
  document.getElementById("wcStageSubtitle").textContent = `${STATE.activeWordcloud.length} términos representados de ${data.total_documents || 0} publicaciones`;

  renderWordCloudSvg(STATE.activeWordcloud);
  renderWordCloudBarChart(STATE.activeWordcloud.slice(0, 25));
}

function renderWordCloudSvg(words) {
  const wrapper = document.getElementById("wordcloudCanvasWrapper");
  if (!words.length) {
    wrapper.innerHTML = `<div style="padding:40px;color:#64748b;">No hay términos que cumplan la frecuencia mínima.</div>`;
    return;
  }

  const palKey = document.getElementById("wcPaletteSelect").value;
  const palette = PALETTES[palKey] || PALETTES.paired;
  const bgColor = document.getElementById("wcBgSelect").value || "#ffffff";
  const rotPer = parseFloat(document.getElementById("wcRotPer").value || "12") / 100.0;

  const size = 760;
  const cx = size / 2;
  const cy = size / 2;

  const maxVal = words[0].value || 1;
  const minVal = words[words.length - 1].value || 1;

  // Deterministic pseudo-random helper so regeneration is clean
  let seed = 42;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };

  const placedBoxes = [];
  const placedNodes = [];

  const intersects = (box) => {
    for (const b of placedBoxes) {
      if (
        box.x1 < b.x2 &&
        box.x2 > b.x1 &&
        box.y1 < b.y2 &&
        box.y2 > b.y1
      ) {
        return true;
      }
    }
    return false;
  };

  words.forEach((w, idx) => {
    const norm = maxVal === minVal ? 1 : (w.value - minVal) / (maxVal - minVal);
    const fontSize = Math.round(13 + Math.pow(norm, 0.78) * 58);
    const isVert = idx > 0 && rand() < rotPer;
    const displayWord = w.text.length > 34 ? w.text.slice(0, 32) + "…" : w.text;

    const approxW = displayWord.length * fontSize * 0.56 + 8;
    const approxH = fontSize * 1.05 + 6;
    const boxW = isVert ? approxH : approxW;
    const boxH = isVert ? approxW : approxH;

    // Archimedean spiral search from center (matching R wordcloud(random.order = FALSE))
    let placed = false;
    for (let step = 0; step < 2600; step++) {
      const theta = step * 0.35;
      const radius = 1.9 * theta;
      const x = cx + radius * Math.cos(theta);
      const y = cy + radius * Math.sin(theta);

      const candidate = {
        x1: x - boxW / 2,
        y1: y - boxH / 2,
        x2: x + boxW / 2,
        y2: y + boxH / 2,
      };

      if (
        candidate.x1 >= 16 &&
        candidate.x2 <= size - 16 &&
        candidate.y1 >= 16 &&
        candidate.y2 <= size - 16 &&
        !intersects(candidate)
      ) {
        placedBoxes.push(candidate);
        const color = palette[idx % palette.length];
        placedNodes.push({
          text: displayWord,
          value: w.value,
          x,
          y,
          fontSize,
          isVert,
          color,
        });
        placed = true;
        break;
      }
    }
  });

  let svg = `<svg id="wcRenderedSvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" style="font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;">`;
  svg += `<rect x="0" y="0" width="${size}" height="${size}" fill="${bgColor}"/>`;

  placedNodes.forEach((n) => {
    const transform = n.isVert
      ? `translate(${n.x.toFixed(1)}, ${n.y.toFixed(1)}) rotate(-90)`
      : `translate(${n.x.toFixed(1)}, ${n.y.toFixed(1)})`;
    svg += `<text transform="${transform}" text-anchor="middle" dominant-baseline="central" font-size="${n.fontSize}" font-weight="${n.fontSize > 34 ? 700 : 500}" fill="${n.color}"><title>${escapeXml(n.text)}: ${n.value}</title>${escapeXml(n.text)}</text>`;
  });

  svg += `</svg>`;
  wrapper.innerHTML = svg;
}

function renderWordCloudBarChart(topWords) {
  const container = document.getElementById("wcTopTermsBarChart");
  if (!topWords.length) {
    container.innerHTML = "";
    return;
  }
  const maxVal = topWords[0].value || 1;
  const width = 920;
  const rowH = 24;
  const height = topWords.length * rowH + 24;
  const leftM = 280;
  const barWMax = width - leftM - 70;
  const palKey = document.getElementById("wcPaletteSelect").value;
  const palette = PALETTES[palKey] || PALETTES.paired;

  let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}">`;
  topWords.forEach((w, idx) => {
    const y = idx * rowH + 12;
    const bw = Math.max(4, (w.value / maxVal) * barWMax);
    const color = palette[idx % palette.length];
    const shortT = w.text.length > 38 ? w.text.slice(0, 36) + "…" : w.text;
    svg += `<text x="${leftM - 10}" y="${y + 12}" text-anchor="end" font-size="11.5" fill="#334155">${escapeXml(shortT)}</text>`;
    svg += `<rect x="${leftM}" y="${y}" width="${bw.toFixed(1)}" height="15" rx="3" fill="${color}"/>`;
    svg += `<text x="${(leftM + bw + 8).toFixed(1)}" y="${y + 12}" font-size="11.5" font-weight="700" fill="#0f172a">${w.value}</text>`;
  });
  svg += `</svg>`;
  container.innerHTML = svg;
}

// ==================== TAB 4: INSTITUTIONS DIRECTORY & API SETTINGS ====================

function populateSettingsTab() {
  document.getElementById("settingsApiKey").value = STATE.settings.masked_api_key || "";
  document.getElementById("settingsInstToken").value = STATE.settings.inst_token || "";
  document.getElementById("settingsSleepTime").value = STATE.settings.sleep_time || "1.0";
  document.getElementById("settingsDefaultView").value = STATE.settings.default_view || "STANDARD";

  renderInstitutionsDirectoryTable();
}

function renderInstitutionsDirectoryTable() {
  const q = (document.getElementById("dirSearchInput").value || "").toLowerCase().trim();
  const list = q
    ? STATE.institutions.filter(
        (i) =>
          i.name.toLowerCase().includes(q) ||
          (i.city || "").toLowerCase().includes(q) ||
          (i.category || "").toLowerCase().includes(q)
      )
    : STATE.institutions;

  document.getElementById("dirTotalCount").textContent = String(list.length);
  const tbody = document.querySelector("#institutionsDirTable tbody");
  tbody.innerHTML = list
    .map((inst) => {
      const badgeClass =
        inst.category === "Research Institute"
          ? "badge-institute"
          : inst.inst_type === "Public"
          ? "badge-public"
          : "badge-private";
      return `
        <tr>
          <td><strong>${escapeXml(inst.name)}</strong></td>
          <td>${escapeXml(inst.category)}</td>
          <td><span class="badge ${badgeClass}">${escapeXml(inst.inst_type)}</span></td>
          <td>${escapeXml(inst.city || "—")}</td>
          <td><code>${escapeXml(inst.afid || "—")}</code></td>
          <td>
            <button class="btn btn-sm btn-ghost-danger" data-del-inst="${inst.id}">Eliminar</button>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("[data-del-inst]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.delInst;
      await fetch(`/api/institutions/${id}`, { method: "DELETE" });
      await loadBootstrapData();
    });
  });
}

function bindSettingsControls() {
  document.getElementById("dirSearchInput").addEventListener("input", renderInstitutionsDirectoryTable);

  document.getElementById("btnSaveSettings").addEventListener("click", async () => {
    const api_key = document.getElementById("settingsApiKey").value.trim();
    const inst_token = document.getElementById("settingsInstToken").value.trim();
    const sleep_time = document.getElementById("settingsSleepTime").value;
    const default_view = document.getElementById("settingsDefaultView").value;

    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, inst_token, sleep_time, default_view }),
    });
    const box = document.getElementById("apiTestResultBox");
    box.className = "alert-box success";
    box.textContent = "Configuración guardada correctamente.";
    box.classList.remove("hidden");
    await loadBootstrapData();
  });

  document.getElementById("btnTestApiKey").addEventListener("click", async () => {
    const box = document.getElementById("apiTestResultBox");
    box.className = "alert-box";
    box.textContent = "Conectando con api.elsevier.com...";
    box.classList.remove("hidden");

    const api_key = document.getElementById("settingsApiKey").value.trim();
    const inst_token = document.getElementById("settingsInstToken").value.trim();
    const res = await fetch("/api/test-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, inst_token }),
    });
    const data = await res.json();
    box.className = data.ok ? "alert-box success" : "alert-box error";
    box.textContent = data.message;
  });

  document.getElementById("btnAddInstitution").addEventListener("click", async () => {
    const name = document.getElementById("newInstName").value.trim();
    if (!name) {
      alert("Ingresa el nombre oficial de la institución.");
      return;
    }
    const category = document.getElementById("newInstCategory").value;
    const inst_type = document.getElementById("newInstType").value;
    const city = document.getElementById("newInstCity").value.trim();
    const afid = document.getElementById("newInstAfid").value.trim();

    await fetch("/api/institutions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, category, inst_type, city, afid }),
    });
    document.getElementById("newInstName").value = "";
    document.getElementById("newInstCity").value = "";
    document.getElementById("newInstAfid").value = "";
    await loadBootstrapData();
  });
}

// ==================== BACKGROUND JOB MONITORING ====================

function startJobMonitoring(jobId) {
  STATE.activeJobId = jobId;
  const banner = document.getElementById("jobProgressBanner");
  banner.classList.remove("hidden");

  document.getElementById("jobCancelBtn").onclick = async () => {
    await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  };

  if (STATE.jobPollTimer) clearInterval(STATE.jobPollTimer);
  STATE.jobPollTimer = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) return;
    const job = await res.json();

    document.getElementById("jobBannerTitle").textContent = job.title || "Consultando Scopus...";
    document.getElementById("jobBannerMessage").textContent = job.message || "";
    document.getElementById("jobBannerPercent").textContent = `${job.percent || 0}%`;
    document.getElementById("jobProgressBar").style.width = `${job.percent || 0}%`;
    document.getElementById("jobLogsConsole").textContent = (job.logs || []).join("\n");

    if (job.status === "completed" || job.status === "error" || job.status === "cancelled") {
      clearInterval(STATE.jobPollTimer);
      STATE.jobPollTimer = null;

      await loadBootstrapData();
      if (job.result_run_id) {
        document.getElementById("newComparisonCard").classList.add("hidden");
        await loadComparisonRun(job.result_run_id);
      }
      if (job.result_dataset_id) {
        await loadHarvestDataset(job.result_dataset_id);
      }
      setTimeout(() => {
        if (job.status === "completed") banner.classList.add("hidden");
      }, 3500);
    }
  }, 800);
}

// ==================== HIGH-RESOLUTION SVG & 300-DPI PNG EXPORT ====================

function downloadSvgElement(svgEl, filename) {
  const serializer = new XMLSerializer();
  let source = serializer.serializeToString(svgEl);
  if (!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)) {
    source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + source], {
    type: "image/svg+xml;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadSvgAsPng(svgEl, filename, scale = 3.0) {
  const serializer = new XMLSerializer();
  const svgStr = serializer.serializeToString(svgEl);
  const viewBox = (svgEl.getAttribute("viewBox") || "0 0 1000 700").split(/\s+/).map(Number);
  const w = viewBox[2] || 1000;
  const h = viewBox[3] || 700;

  const img = new Image();
  const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);

  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    URL.revokeObjectURL(url);

    canvas.toBlob((pngBlob) => {
      const pngUrl = URL.createObjectURL(pngBlob);
      const a = document.createElement("a");
      a.href = pngUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(pngUrl);
    }, "image/png");
  };
  img.src = url;
}

