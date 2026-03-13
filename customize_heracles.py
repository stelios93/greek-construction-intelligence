#!/usr/bin/env python3
"""
Customize titan_demo.html for HERACLES Group demo:
1. Rebrand header for HERACLES
2. Add HERACLES plant location markers on map
3. Add "Weekly Digest" tab with trend chart
4. Add permits-per-week time series (Chart.js)
"""

import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SRC = DATA_DIR / "titan_demo.html"
DST = DATA_DIR / "heracles_demo.html"

html = SRC.read_text(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════
#  1. REBRAND HEADER
# ═══════════════════════════════════════════════════════════════

html = html.replace(
    '<title>Greek Construction — Cement Demand Map</title>',
    '<title>HERACLES Group — Construction Intelligence Greece</title>'
)

html = html.replace(
    '<h1>Cement Demand Intelligence // <span>Greece</span></h1>',
    '<h1>Construction Intelligence // <span>HERACLES Group</span></h1>'
)

html = html.replace(
    '5,700 permits, 2026-01-01 to today',
    '5,700 permits since Jan 2026 · Prepared for HERACLES Group'
)

# ═══════════════════════════════════════════════════════════════
#  2. ADD VIEW PRESETS FOR HERACLES PLANT REGIONS
# ═══════════════════════════════════════════════════════════════

# Add more view options (Volos, Chalkida near HERACLES plants)
html = html.replace(
    '<option value="crete">Crete</option>',
    '<option value="crete">Crete</option>\n'
    '      <option value="volos">Volos (Plant)</option>\n'
    '      <option value="chalkida">Chalkida (Plant)</option>\n'
    '      <option value="elefsina">Elefsina (Plant)</option>\n'
    '      <option value="patras">Patras Region</option>'
)

# Add the view coordinates in JS
html = html.replace(
    "crete: [35.24, 24.90, 9],",
    "crete: [35.24, 24.90, 9],\n"
    "  volos: [39.36, 22.94, 11],\n"
    "  chalkida: [38.46, 23.60, 11],\n"
    "  elefsina: [38.04, 23.54, 12],\n"
    "  patras: [38.25, 21.74, 11],"
)

# ═══════════════════════════════════════════════════════════════
#  3. ADD HERACLES PLANT MARKERS ON MAP
# ═══════════════════════════════════════════════════════════════

plant_markers_js = """
// HERACLES plant locations
const HERACLES_PLANTS = [
  {name: "HERACLES Volos Plant", lat: 39.3621, lng: 22.9426, type: "Cement Plant"},
  {name: "HERACLES Chalkida Plant", lat: 38.4637, lng: 23.6028, type: "Cement Plant"},
  {name: "HERACLES Elefsina (TITAN)", lat: 38.0418, lng: 23.5422, type: "Cement Terminal"},
  {name: "HERACLES Patras Terminal", lat: 38.2466, lng: 21.7346, type: "Distribution"},
  {name: "HERACLES Aspropyrgos RMC", lat: 38.0597, lng: 23.5865, type: "Ready-mix Concrete"},
  {name: "HERACLES Gerakas RMC", lat: 38.0231, lng: 23.8571, type: "Ready-mix Concrete"},
];

const plantLayer = L.layerGroup().addTo(map);
for (const pl of HERACLES_PLANTS) {
  const icon = L.divIcon({
    html: '<div style="background:#ef4444;border:2px solid #fff;width:14px;height:14px;border-radius:2px;transform:rotate(45deg)"></div>',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    className: ''
  });
  L.marker([pl.lat, pl.lng], {icon}).addTo(plantLayer)
    .bindPopup('<div style="font-size:13px;font-weight:700">' + pl.name + '</div><div style="font-size:11px;color:#666">' + pl.type + '</div>', {className: 'plant-popup'});
}
"""

# Inject after initMap's markerLayer line
html = html.replace(
    "markerLayer = L.layerGroup().addTo(map);",
    "markerLayer = L.layerGroup().addTo(map);\n" + plant_markers_js
)

# ═══════════════════════════════════════════════════════════════
#  4. ADD WEEKLY DIGEST TAB + TREND CHART
# ═══════════════════════════════════════════════════════════════

# Add Chart.js CDN
html = html.replace(
    '<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>',
    '<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>\n'
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>'
)

# Add the third tab button
html = html.replace(
    """<div class="tab" onclick="switchTab('table')">Permit Register</div>""",
    """<div class="tab" onclick="switchTab('table')">Permit Register</div>\n"""
    """  <div class="tab" onclick="switchTab('digest')">Weekly Digest</div>"""
)

# Add CSS for digest tab
digest_css = """
  /* Digest */
  .digest-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
    padding: 1.5rem 2rem;
  }
  @media (max-width: 900px) { .digest-grid { grid-template-columns: 1fr; } }
  .digest-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 1.25rem;
  }
  .digest-card h3 {
    font-size: 0.82rem; font-weight: 700; margin-bottom: 1rem;
    padding-bottom: 0.5rem; border-bottom: 1px solid var(--border);
  }
  .digest-card h3 span { color: var(--cyan); }
  .digest-stat {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 0.4rem 0; border-bottom: 1px solid rgba(30,41,59,0.3);
  }
  .digest-stat .ds-label { color: var(--muted); font-size: 0.78rem; }
  .digest-stat .ds-val { font-weight: 700; font-size: 0.95rem; }
  .digest-full { grid-column: 1 / -1; }
  .chart-container { position: relative; height: 300px; width: 100%; }
  .region-bar { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; font-size: 0.78rem; }
  .region-bar .rb-name { width: 140px; color: var(--muted); text-align: right; flex-shrink: 0; }
  .region-bar .rb-bar { height: 18px; border-radius: 3px; transition: width 0.5s; }
  .region-bar .rb-val { color: var(--text); font-weight: 600; min-width: 50px; }
  .top-engineers { font-size: 0.78rem; }
  .top-engineers .te-row { display: flex; justify-content: space-between; padding: 0.35rem 0; border-bottom: 1px solid rgba(30,41,59,0.3); }
  .te-row .te-name { color: var(--text); }
  .te-row .te-count { color: var(--cyan); font-weight: 700; }
  .te-row .te-tee { color: var(--dim); font-size: 0.7rem; }

  .plant-popup .leaflet-popup-content-wrapper {
    background: #1a2234; border: 1px solid #3b82f6; border-radius: 8px;
  }
  .plant-popup .leaflet-popup-content { color: #e2e8f0; }
  .plant-popup .leaflet-popup-tip { background: #1a2234; }
"""

html = html.replace("</style>", digest_css + "\n</style>")

# Add the digest tab content HTML (before the overlay div)
digest_html = """
<!-- WEEKLY DIGEST TAB -->
<div id="tab-digest" class="tab-content">
  <div class="digest-grid">
    <div class="digest-card">
      <h3>This Week <span id="digestWeekRange"></span></h3>
      <div class="digest-stat"><span class="ds-label">New Permits</span><span class="ds-val" id="dNewPermits" style="color:var(--cyan)">—</span></div>
      <div class="digest-stat"><span class="ds-label">Estimated Cement</span><span class="ds-val" id="dCement" style="color:var(--orange)">—</span></div>
      <div class="digest-stat"><span class="ds-label">New Builds</span><span class="ds-val" id="dNewBuilds" style="color:var(--green)">—</span></div>
      <div class="digest-stat"><span class="ds-label">Avg Cement / Permit</span><span class="ds-val" id="dAvgCem">—</span></div>
      <div class="digest-stat"><span class="ds-label">vs Previous Week</span><span class="ds-val" id="dDelta">—</span></div>
    </div>
    <div class="digest-card">
      <h3>Top Regions <span style="color:var(--dim);font-weight:400">(by cement tonnes)</span></h3>
      <div id="regionBars"></div>
    </div>
    <div class="digest-card digest-full">
      <h3>Permits & Cement per Week <span style="color:var(--dim);font-weight:400">(trend)</span></h3>
      <div class="chart-container"><canvas id="trendChart"></canvas></div>
    </div>
    <div class="digest-card">
      <h3>Top Engineers <span style="color:var(--dim);font-weight:400">(most permits this month)</span></h3>
      <div id="topEngineers" class="top-engineers"></div>
    </div>
    <div class="digest-card">
      <h3>Building Use Breakdown <span style="color:var(--dim);font-weight:400">(this month)</span></h3>
      <div class="chart-container" style="height:220px"><canvas id="useChart"></canvas></div>
    </div>
  </div>
</div>
"""

html = html.replace(
    '<div class="overlay"',
    digest_html + '\n<div class="overlay"'
)

# ═══════════════════════════════════════════════════════════════
#  5. ADD DIGEST JS LOGIC
# ═══════════════════════════════════════════════════════════════

# Update switchTab function to handle 3 tabs
html = html.replace(
    """function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', (name === 'map' && i === 0) || (name === 'table' && i === 1));
  });
  document.getElementById('tab-map').classList.toggle('active', name === 'map');
  document.getElementById('tab-table').classList.toggle('active', name === 'table');
  if (name === 'map') setTimeout(() => map.invalidateSize(), 100);
}""",
    """function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active',
      (name === 'map' && i === 0) || (name === 'table' && i === 1) || (name === 'digest' && i === 2));
  });
  document.getElementById('tab-map').classList.toggle('active', name === 'map');
  document.getElementById('tab-table').classList.toggle('active', name === 'table');
  document.getElementById('tab-digest').classList.toggle('active', name === 'digest');
  if (name === 'map') setTimeout(() => map.invalidateSize(), 100);
  if (name === 'digest' && !digestRendered) renderDigest();
}"""
)

digest_js = """

// ── Weekly Digest ──
let digestRendered = false;
let trendChartInstance = null;
let useChartInstance = null;

function renderDigest() {
  digestRendered = true;

  // Group permits by ISO week
  const byWeek = {};
  const byMonth = {};
  for (const r of TABLE) {
    if (!r.date) continue;
    const d = new Date(r.date);
    // Get ISO week key: YYYY-Www
    const jan1 = new Date(d.getFullYear(), 0, 1);
    const weekNum = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
    const wk = d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
    if (!byWeek[wk]) byWeek[wk] = [];
    byWeek[wk].push(r);

    const mo = r.date.substring(0, 7);
    if (!byMonth[mo]) byMonth[mo] = [];
    byMonth[mo].push(r);
  }

  const weeks = Object.keys(byWeek).sort();
  const thisWeek = weeks[weeks.length - 1];
  const prevWeek = weeks.length > 1 ? weeks[weeks.length - 2] : null;
  const thisData = byWeek[thisWeek] || [];
  const prevData = prevWeek ? (byWeek[prevWeek] || []) : [];

  const thisCem = thisData.reduce((s, r) => s + r.cem, 0);
  const prevCem = prevData.reduce((s, r) => s + r.cem, 0);
  const thisNewBuilds = thisData.filter(r => r.con === 'New Build').length;

  // Week range display
  const latestDate = thisData.length ? thisData.map(r=>r.date).sort().pop() : '';
  const earliestDate = thisData.length ? thisData.map(r=>r.date).sort()[0] : '';
  document.getElementById('digestWeekRange').textContent = '(' + earliestDate + ' → ' + latestDate + ')';

  document.getElementById('dNewPermits').textContent = thisData.length.toLocaleString();
  document.getElementById('dCement').textContent = thisCem.toFixed(0) + 't';
  document.getElementById('dNewBuilds').textContent = thisNewBuilds;
  document.getElementById('dAvgCem').textContent = thisData.length ? (thisCem / thisData.length).toFixed(1) + 't' : '—';

  // Delta vs prev week
  if (prevData.length > 0) {
    const delta = ((thisCem - prevCem) / prevCem * 100);
    const sign = delta >= 0 ? '+' : '';
    const color = delta >= 0 ? 'var(--green)' : 'var(--red)';
    document.getElementById('dDelta').innerHTML = '<span style="color:' + color + '">' + sign + delta.toFixed(0) + '% cement</span>';
  } else {
    document.getElementById('dDelta').textContent = '—';
  }

  // Region bars (top 10 by cement this week → all time actually for more data)
  const regionCem = {};
  for (const r of TABLE) {
    const reg = r.muni || 'Unknown';
    if (reg === 'Unknown' || !reg) continue;
    regionCem[reg] = (regionCem[reg] || 0) + r.cem;
  }
  const topRegions = Object.entries(regionCem).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxReg = topRegions[0] ? topRegions[0][1] : 1;
  const barColors = ['var(--cyan)', 'var(--blue)', 'var(--blue)', 'var(--blue)', 'var(--blue)',
                     'var(--dim)', 'var(--dim)', 'var(--dim)', 'var(--dim)', 'var(--dim)'];
  document.getElementById('regionBars').innerHTML = topRegions.map((e, i) =>
    '<div class="region-bar"><span class="rb-name">' + e[0] + '</span>' +
    '<div class="rb-bar" style="width:' + (e[1]/maxReg*100).toFixed(0) + '%;background:' + barColors[i] + '"></div>' +
    '<span class="rb-val">' + e[1].toFixed(0) + 't</span></div>'
  ).join('');

  // Trend chart
  const weekLabels = weeks.slice(-12);
  const weekPermits = weekLabels.map(w => byWeek[w].length);
  const weekCement = weekLabels.map(w => byWeek[w].reduce((s, r) => s + r.cem, 0));

  const ctx1 = document.getElementById('trendChart').getContext('2d');
  trendChartInstance = new Chart(ctx1, {
    type: 'bar',
    data: {
      labels: weekLabels.map(w => w.replace(/^\\d{4}-/, '')),
      datasets: [
        {
          label: 'Permits',
          data: weekPermits,
          backgroundColor: 'rgba(6, 182, 212, 0.5)',
          borderColor: 'rgba(6, 182, 212, 1)',
          borderWidth: 1,
          yAxisID: 'y',
          order: 2,
        },
        {
          label: 'Cement (t)',
          data: weekCement,
          type: 'line',
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointBackgroundColor: '#f59e0b',
          yAxisID: 'y1',
          order: 1,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 11 } } }
      },
      scales: {
        x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(30,41,59,0.5)' } },
        y: {
          position: 'left',
          title: { display: true, text: 'Permits', color: '#06b6d4', font: { size: 11 } },
          ticks: { color: '#06b6d4' },
          grid: { color: 'rgba(30,41,59,0.5)' },
        },
        y1: {
          position: 'right',
          title: { display: true, text: 'Cement (t)', color: '#f59e0b', font: { size: 11 } },
          ticks: { color: '#f59e0b' },
          grid: { drawOnChartArea: false },
        }
      }
    }
  });

  // Top engineers (this month)
  const months = Object.keys(byMonth).sort();
  const latestMonth = months[months.length - 1];
  const monthData = byMonth[latestMonth] || [];
  const engCement = {};
  const engPermits = {};
  for (const r of monthData) {
    if (!r.eng) continue;
    const key = r.eng + (r.tee ? '|' + r.tee : '');
    engCement[key] = (engCement[key] || 0) + r.cem;
    engPermits[key] = (engPermits[key] || 0) + 1;
  }
  const topEng = Object.entries(engCement).sort((a, b) => b[1] - a[1]).slice(0, 10);
  document.getElementById('topEngineers').innerHTML = topEng.map(e => {
    const parts = e[0].split('|');
    const name = parts[0];
    const tee = parts[1] || '';
    const cem = e[1].toFixed(1);
    const cnt = engPermits[e[0]];
    return '<div class="te-row"><span><span class="te-name">' + name + '</span>' +
      (tee ? ' <span class="te-tee">TEE ' + tee + '</span>' : '') +
      '</span><span class="te-count">' + cem + 't <span style="color:var(--dim)">(' + cnt + ')</span></span></div>';
  }).join('');

  // Use breakdown donut
  const useCount = {};
  for (const r of monthData) {
    useCount[r.use] = (useCount[r.use] || 0) + 1;
  }
  const useEntries = Object.entries(useCount).sort((a, b) => b[1] - a[1]);
  const useColors = ['#06b6d4', '#3b82f6', '#f59e0b', '#22c55e', '#a855f7', '#ef4444', '#64748b'];
  const ctx2 = document.getElementById('useChart').getContext('2d');
  useChartInstance = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels: useEntries.map(e => e[0]),
      datasets: [{
        data: useEntries.map(e => e[1]),
        backgroundColor: useColors.slice(0, useEntries.length),
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#94a3b8', font: { size: 11 }, padding: 12 }
        }
      }
    }
  });
}
"""

# Inject the digest JS before the init calls
html = html.replace(
    "// ── Init ──\ninitMap();\nfilterTable();",
    digest_js + "\n// ── Init ──\ninitMap();\nfilterTable();"
)

# ═══════════════════════════════════════════════════════════════
#  6. UPDATE FOOTER
# ═══════════════════════════════════════════════════════════════

html = html.replace(
    'Cement estimation: floor area heuristic × concrete intensity (0.15–0.22 m³/m²) × 300 kg cement/m³ |\n'
    '  Addresses extracted from official PDF permits via regex | Data: opendata.diavgeia.gov.gr',
    'Prepared for HERACLES Group · Cement estimation: floor area × concrete intensity (0.15–0.22 m³/m²) × 300 kg/m³ |\n'
    '  5,800+ permits parsed from PDF via regex · Source: opendata.diavgeia.gov.gr · Confidential'
)

# ═══════════════════════════════════════════════════════════════
#  7. ADD LEAD SCORING SYSTEM
# ═══════════════════════════════════════════════════════════════

lead_css = """
  /* Lead Score */
  .score-badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-weight: 700; font-size: 0.72rem; min-width: 36px; text-align: center;
  }
  .score-hot { background: rgba(239,68,68,0.2); color: #ef4444; }
  .score-warm { background: rgba(245,158,11,0.2); color: #f59e0b; }
  .score-cool { background: rgba(59,130,246,0.2); color: #3b82f6; }
  .score-cold { background: rgba(100,116,139,0.2); color: #94a3b8; }

  /* Config panel */
  #scoringPanel {
    display: none; position: fixed; top: 0; right: 0; width: 420px; height: 100%;
    background: var(--card); border-left: 1px solid var(--border);
    z-index: 900; overflow-y: auto; padding: 1.5rem;
    box-shadow: -10px 0 30px rgba(0,0,0,0.4);
    transition: transform 0.3s ease;
  }
  #scoringPanel.open { display: block; }
  #scoringPanel h3 { font-size: 0.9rem; margin-bottom: 0.5rem; color: var(--cyan); }
  #scoringPanel .panel-section {
    background: var(--card2); border: 1px solid var(--border); border-radius: 8px;
    padding: 1rem; margin-bottom: 1rem;
  }
  #scoringPanel .panel-section h4 {
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--dim); margin-bottom: 0.75rem;
  }
  .slider-row {
    display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;
    font-size: 0.78rem;
  }
  .slider-row label { min-width: 100px; color: var(--muted); }
  .slider-row input[type=range] {
    flex: 1; accent-color: var(--cyan); height: 4px; cursor: pointer;
  }
  .slider-row .sv { min-width: 35px; text-align: right; font-weight: 700; color: var(--text); }
  .toggle-row {
    display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem;
    font-size: 0.78rem; color: var(--muted);
  }
  .toggle-row input[type=checkbox] { accent-color: var(--cyan); }
  .panel-close {
    position: absolute; top: 1rem; right: 1rem; background: none; border: none;
    color: var(--dim); font-size: 1.3rem; cursor: pointer;
  }
  .panel-close:hover { color: var(--text); }
  .btn-scoring {
    background: var(--card2); color: var(--cyan); border: 1px solid var(--cyan);
    border-radius: 6px; padding: 0.4rem 0.8rem; font-size: 0.72rem;
    font-weight: 600; cursor: pointer; transition: all 0.2s;
  }
  .btn-scoring:hover { background: rgba(6,182,212,0.15); }
  .score-summary {
    background: rgba(6,182,212,0.08); border: 1px solid rgba(6,182,212,0.2);
    border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem;
    display: flex; gap: 1rem; justify-content: space-around; text-align: center;
  }
  .score-summary .ss-val { font-size: 1.1rem; font-weight: 800; }
  .score-summary .ss-lbl { font-size: 0.6rem; color: var(--dim); text-transform: uppercase; }
  .proximity-rings { opacity: 0.15; }

  .preset-btn {
    background: var(--card); border: 1px solid var(--border); border-radius: 6px;
    padding: 0.4rem 0.7rem; font-size: 0.72rem; color: var(--text);
    cursor: pointer; transition: all 0.2s;
  }
  .preset-btn:hover { border-color: var(--cyan); color: var(--cyan); }
  .preset-btn.active { background: rgba(6,182,212,0.15); border-color: var(--cyan); color: var(--cyan); }
"""

# Add config button next to existing filters
html = html.replace(
    '<div><label>Search</label><input id="fSearch" placeholder="keyword..." oninput="filterTable()"></div>',
    '<div><label>Search</label><input id="fSearch" placeholder="keyword..." oninput="filterTable()"></div>\n'
    '        <button class="btn-scoring" onclick="toggleScoring()">Lead Scoring Config</button>'
)

# Add Score column to table header
html = html.replace(
    "<th onclick=\"sortTable('date')\">Date</th>",
    "<th onclick=\"sortTable('score')\" title=\"Lead Score\">Score</th>\n"
    "        <th onclick=\"sortTable('date')\">Date</th>"
)

# Add Score column to table rows (in renderTable)
# Insert scoreBadge calculation before the return statement
html = html.replace(
    "    return '<tr onclick=\"showDetail(\\'",
    "    const scoreBadge = r.score >= 100 ? 'score-hot' : r.score >= 40 ? 'score-warm' : r.score >= 10 ? 'score-cool' : 'score-cold';\n"
    "    return '<tr onclick=\"showDetail(\\'"
)

# Insert score cell before the date cell
html = html.replace(
    "      '<td>' + r.date + '</td>' +",
    "      '<td><span class=\"score-badge ' + scoreBadge + '\">' + r.score + '</span></td>' +\n"
    "      '<td>' + r.date + '</td>' +",
    1  # only first occurrence
)

# Add scoring panel HTML before the overlay
lead_panel_html = """
<!-- Lead Scoring Config Panel -->
<div id="scoringPanel">
  <button class="panel-close" onclick="toggleScoring()">&times;</button>
  <h3>Lead Scoring Configuration</h3>

  <div class="score-summary">
    <div><div class="ss-val" id="ssHot" style="color:var(--red)">0</div><div class="ss-lbl">Hot (&ge;100)</div></div>
    <div><div class="ss-val" id="ssWarm" style="color:var(--orange)">0</div><div class="ss-lbl">Warm (40-99)</div></div>
    <div><div class="ss-val" id="ssCool" style="color:var(--blue)">0</div><div class="ss-lbl">Cool (10-39)</div></div>
    <div><div class="ss-val" id="ssCold" style="color:var(--dim)">0</div><div class="ss-lbl">Cold (&lt;10)</div></div>
  </div>

  <div style="margin-bottom:1rem;display:flex;gap:0.4rem;flex-wrap:wrap">
    <div style="font-size:0.7rem;color:var(--dim);width:100%;margin-bottom:0.3rem">PRESETS</div>
    <button class="preset-btn" onclick="applyPreset('rmx')">Ready-Mix Sales</button>
    <button class="preset-btn" onclick="applyPreset('bags')">Bag Cement Sales</button>
    <button class="preset-btn" onclick="applyPreset('aggregates')">Aggregates</button>
    <button class="preset-btn" onclick="applyPreset('all')">Balanced</button>
  </div>

  <div class="panel-section">
    <h4>Project Size Weights</h4>
    <div class="slider-row"><label>XL (&ge;30t)</label><input type="range" id="wXL" min="0" max="200" value="100" oninput="updateScoring()"><span class="sv" id="vXL">100</span></div>
    <div class="slider-row"><label>L (15-30t)</label><input type="range" id="wL" min="0" max="200" value="70" oninput="updateScoring()"><span class="sv" id="vL">70</span></div>
    <div class="slider-row"><label>M (5-15t)</label><input type="range" id="wM" min="0" max="200" value="40" oninput="updateScoring()"><span class="sv" id="vM">40</span></div>
    <div class="slider-row"><label>S (1-5t)</label><input type="range" id="wS" min="0" max="200" value="15" oninput="updateScoring()"><span class="sv" id="vS">15</span></div>
    <div class="slider-row"><label>XS (&lt;1t)</label><input type="range" id="wXS" min="0" max="200" value="2" oninput="updateScoring()"><span class="sv" id="vXS">2</span></div>
  </div>

  <div class="panel-section">
    <h4>Proximity to Plants</h4>
    <div class="slider-row"><label>&lt;15km</label><input type="range" id="pNear" min="0" max="40" value="20" step="1" oninput="updateScoring()"><span class="sv" id="vNear">&times;2.0</span></div>
    <div class="slider-row"><label>15-30km</label><input type="range" id="pMid" min="0" max="30" value="15" step="1" oninput="updateScoring()"><span class="sv" id="vMid">&times;1.5</span></div>
    <div class="slider-row"><label>30-50km</label><input type="range" id="pFar" min="0" max="20" value="10" step="1" oninput="updateScoring()"><span class="sv" id="vFar">&times;1.0</span></div>
    <div class="slider-row"><label>&gt;50km</label><input type="range" id="pVFar" min="0" max="10" value="3" step="1" oninput="updateScoring()"><span class="sv" id="vVFar">&times;0.3</span></div>
    <div class="toggle-row"><input type="checkbox" id="showRings" onchange="toggleRings()"> Show proximity rings on map</div>
  </div>

  <div class="panel-section">
    <h4>Timeline (Permit Age)</h4>
    <div class="slider-row"><label>&lt;4 weeks</label><input type="range" id="tFresh" min="0" max="30" value="15" step="1" oninput="updateScoring()"><span class="sv" id="vFresh">&times;1.5</span></div>
    <div class="slider-row"><label>4-8 weeks</label><input type="range" id="tMedium" min="0" max="20" value="12" step="1" oninput="updateScoring()"><span class="sv" id="vMedium">&times;1.2</span></div>
    <div class="slider-row"><label>8-16 weeks</label><input type="range" id="tOld" min="0" max="20" value="10" step="1" oninput="updateScoring()"><span class="sv" id="vOld">&times;1.0</span></div>
    <div class="slider-row"><label>&gt;16 weeks</label><input type="range" id="tStale" min="0" max="10" value="6" step="1" oninput="updateScoring()"><span class="sv" id="vStale">&times;0.6</span></div>
  </div>

  <div class="panel-section">
    <h4>Contact & Type Bonuses</h4>
    <div class="slider-row"><label>Has phone</label><input type="range" id="bPhone" min="10" max="20" value="13" step="1" oninput="updateScoring()"><span class="sv" id="vPhone">&times;1.3</span></div>
    <div class="slider-row"><label>Has engineer</label><input type="range" id="bEng" min="10" max="20" value="11" step="1" oninput="updateScoring()"><span class="sv" id="vEng">&times;1.1</span></div>
    <div class="slider-row"><label>New Build bonus</label><input type="range" id="bNew" min="10" max="20" value="12" step="1" oninput="updateScoring()"><span class="sv" id="vNew">&times;1.2</span></div>
  </div>

  <div class="panel-section">
    <h4>Filter by Score</h4>
    <div class="slider-row"><label>Min score</label><input type="range" id="fMinScore" min="0" max="100" value="0" oninput="updateScoring()"><span class="sv" id="vMinScore">0</span></div>
    <div class="toggle-row"><input type="checkbox" id="scoreSort" checked onchange="updateScoring()"> Sort table by score (highest first)</div>
  </div>

  <button class="btn" style="width:100%;margin-top:0.5rem" onclick="updateScoring()">Apply & Recalculate</button>
</div>
"""

html = html.replace(
    '<div class="overlay"',
    lead_panel_html + '\n<div class="overlay"'
)

# Add lead scoring JS
lead_js = """

// ── Lead Scoring Engine ──
const PLANTS = [
  {lat: 39.3621, lng: 22.9426},  // Volos
  {lat: 38.4637, lng: 23.6028},  // Chalkida
  {lat: 38.0418, lng: 23.5422},  // Elefsina
  {lat: 38.0597, lng: 23.5865},  // Aspropyrgos RMC
  {lat: 38.0231, lng: 23.8571},  // Gerakas RMC
  {lat: 38.2466, lng: 21.7346},  // Patras
];

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2-lat1)*Math.PI/180;
  const dLon = (lon2-lon1)*Math.PI/180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function nearestPlantKm(ada) {
  const m = MARKERS.find(x => x.ada === ada);
  if (!m) return 999;
  let min = 999;
  for (const p of PLANTS) min = Math.min(min, haversineKm(m.lat, m.lng, p.lat, p.lng));
  return min;
}

// Cache distances
const distCache = {};
function getDistKm(ada) {
  if (!(ada in distCache)) distCache[ada] = nearestPlantKm(ada);
  return distCache[ada];
}

function getSlider(id) { return parseFloat(document.getElementById(id).value); }

function calcScore(r) {
  // Size base score
  const wXL = getSlider('wXL'), wL = getSlider('wL'), wM = getSlider('wM'), wS = getSlider('wS'), wXS = getSlider('wXS');
  let base;
  if (r.cem >= 30) base = wXL;
  else if (r.cem >= 15) base = wL;
  else if (r.cem >= 5) base = wM;
  else if (r.cem >= 1) base = wS;
  else base = wXS;

  // Proximity multiplier
  const dist = getDistKm(r.ada);
  const pNear = getSlider('pNear')/10, pMid = getSlider('pMid')/10, pFar = getSlider('pFar')/10, pVFar = getSlider('pVFar')/10;
  let proxMult;
  if (dist < 15) proxMult = pNear;
  else if (dist < 30) proxMult = pMid;
  else if (dist < 50) proxMult = pFar;
  else proxMult = pVFar;

  // Timeline multiplier
  const today = new Date();
  const issued = new Date(r.date);
  const weeksOld = Math.max(0, (today - issued) / (7*24*60*60*1000));
  const tFresh = getSlider('tFresh')/10, tMedium = getSlider('tMedium')/10;
  const tOld = getSlider('tOld')/10, tStale = getSlider('tStale')/10;
  let timeMult;
  if (weeksOld < 4) timeMult = tFresh;
  else if (weeksOld < 8) timeMult = tMedium;
  else if (weeksOld < 16) timeMult = tOld;
  else timeMult = tStale;

  // Contact & type bonuses
  const bPhone = getSlider('bPhone')/10, bEng = getSlider('bEng')/10, bNew = getSlider('bNew')/10;
  let contactMult = 1.0;
  if (r.eng && r.tee) contactMult = bEng;
  let typeMult = r.con === 'New Build' ? bNew : 1.0;

  return Math.round(base * proxMult * timeMult * contactMult * typeMult);
}

function updateScoring() {
  // Update slider display values
  document.getElementById('vXL').textContent = getSlider('wXL');
  document.getElementById('vL').textContent = getSlider('wL');
  document.getElementById('vM').textContent = getSlider('wM');
  document.getElementById('vS').textContent = getSlider('wS');
  document.getElementById('vXS').textContent = getSlider('wXS');
  document.getElementById('vNear').textContent = '\\u00d7' + (getSlider('pNear')/10).toFixed(1);
  document.getElementById('vMid').textContent = '\\u00d7' + (getSlider('pMid')/10).toFixed(1);
  document.getElementById('vFar').textContent = '\\u00d7' + (getSlider('pFar')/10).toFixed(1);
  document.getElementById('vVFar').textContent = '\\u00d7' + (getSlider('pVFar')/10).toFixed(1);
  document.getElementById('vFresh').textContent = '\\u00d7' + (getSlider('tFresh')/10).toFixed(1);
  document.getElementById('vMedium').textContent = '\\u00d7' + (getSlider('tMedium')/10).toFixed(1);
  document.getElementById('vOld').textContent = '\\u00d7' + (getSlider('tOld')/10).toFixed(1);
  document.getElementById('vStale').textContent = '\\u00d7' + (getSlider('tStale')/10).toFixed(1);
  document.getElementById('vPhone').textContent = '\\u00d7' + (getSlider('bPhone')/10).toFixed(1);
  document.getElementById('vEng').textContent = '\\u00d7' + (getSlider('bEng')/10).toFixed(1);
  document.getElementById('vNew').textContent = '\\u00d7' + (getSlider('bNew')/10).toFixed(1);
  document.getElementById('vMinScore').textContent = getSlider('fMinScore');

  // Recalculate all scores
  for (const r of TABLE) r.score = calcScore(r);

  // Update summary counts
  let hot=0, warm=0, cool=0, cold=0;
  for (const r of TABLE) {
    if (r.score >= 100) hot++;
    else if (r.score >= 40) warm++;
    else if (r.score >= 10) cool++;
    else cold++;
  }
  document.getElementById('ssHot').textContent = hot;
  document.getElementById('ssWarm').textContent = warm;
  document.getElementById('ssCool').textContent = cool;
  document.getElementById('ssCold').textContent = cold;

  // Apply min score filter
  const minScore = getSlider('fMinScore');
  if (minScore > 0) {
    document.getElementById('fCem').value = '0';
    document.getElementById('fUse').value = '';
    document.getElementById('fCon').value = '';
    document.getElementById('fSearch').value = '';
    filtered = TABLE.filter(r => r.score >= minScore);
  } else {
    filterTable();
    return;
  }

  // Sort by score if checkbox is on
  if (document.getElementById('scoreSort').checked) {
    sortCol = 'score'; sortDir = -1;
  }
  page = 0;
  doSort();
}

function toggleScoring() {
  const panel = document.getElementById('scoringPanel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) updateScoring();
}

let ringLayers = [];
function toggleRings() {
  if (!document.getElementById('showRings').checked) {
    ringLayers.forEach(l => map.removeLayer(l));
    ringLayers = [];
    return;
  }
  const radii = [15000, 30000];
  const colors = ['rgba(6,182,212,0.15)', 'rgba(59,130,246,0.1)'];
  for (const p of PLANTS) {
    for (let i = 0; i < radii.length; i++) {
      const c = L.circle([p.lat, p.lng], {radius: radii[i], color: colors[i], fillColor: colors[i], fillOpacity: 0.08, weight: 1});
      c.addTo(map);
      ringLayers.push(c);
    }
  }
}

// Presets
function applyPreset(name) {
  const presets = {
    rmx: {wXL:150,wL:100,wM:50,wS:10,wXS:0, pNear:25,pMid:20,pFar:5,pVFar:0, tFresh:18,tMedium:14,tOld:10,tStale:5, bPhone:15,bEng:12,bNew:15},
    bags: {wXL:60,wL:70,wM:80,wS:60,wXS:20, pNear:12,pMid:12,pFar:10,pVFar:8, tFresh:15,tMedium:12,tOld:10,tStale:8, bPhone:13,bEng:11,bNew:11},
    aggregates: {wXL:150,wL:120,wM:60,wS:5,wXS:0, pNear:25,pMid:15,pFar:5,pVFar:1, tFresh:15,tMedium:13,tOld:10,tStale:6, bPhone:13,bEng:11,bNew:15},
    all: {wXL:100,wL:70,wM:40,wS:15,wXS:2, pNear:20,pMid:15,pFar:10,pVFar:3, tFresh:15,tMedium:12,tOld:10,tStale:6, bPhone:13,bEng:11,bNew:12},
  };
  const p = presets[name];
  if (!p) return;
  for (const [k,v] of Object.entries(p)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.toggle('active', b.textContent.toLowerCase().includes(name)));
  updateScoring();
}

// Initialize scores on load
for (const r of TABLE) r.score = 0;
setTimeout(() => { for (const r of TABLE) r.score = calcScore(r); }, 100);
"""

# Inject lead scoring JS before the init calls
html = html.replace(
    "// ── Init ──\ninitMap();\nfilterTable();",
    lead_js + "\n// ── Init ──\ninitMap();\nfilterTable();\n// Initial scoring\nsetTimeout(updateScoring, 200);"
)

html = html.replace("</style>", lead_css + "\n</style>")

# ═══════════════════════════════════════════════════════════════
#  8. ADD PASSWORD SCREEN
# ═══════════════════════════════════════════════════════════════

# Password: "heracles2026" → SHA-256 hash
# This is client-side only (good enough for demo privacy, not for secrets)
password_css = """
  #lockScreen {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: linear-gradient(135deg, #0a0e17 0%, #1e1b4b 50%, #0f172a 100%);
    z-index: 9999; display: flex; align-items: center; justify-content: center;
  }
  #lockScreen.hidden { display: none; }
  .lock-box {
    background: rgba(17, 24, 39, 0.95); border: 1px solid #1e293b; border-radius: 16px;
    padding: 2.5rem; width: 380px; text-align: center;
    box-shadow: 0 25px 50px rgba(0,0,0,0.5);
  }
  .lock-box .lock-icon { font-size: 2.5rem; margin-bottom: 1rem; }
  .lock-box h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.3rem; color: #e2e8f0; }
  .lock-box .lock-sub { font-size: 0.75rem; color: #64748b; margin-bottom: 1.5rem; }
  .lock-box input {
    width: 100%; padding: 0.7rem 1rem; background: #1a2234; border: 1px solid #2d3748;
    border-radius: 8px; color: #e2e8f0; font-size: 0.85rem; outline: none;
    text-align: center; letter-spacing: 0.1em;
  }
  .lock-box input:focus { border-color: #06b6d4; }
  .lock-box input::placeholder { color: #4a5568; letter-spacing: 0; }
  .lock-box .lock-btn {
    width: 100%; padding: 0.7rem; margin-top: 0.75rem; background: #06b6d4;
    border: none; border-radius: 8px; color: #0a0e17; font-weight: 700;
    font-size: 0.85rem; cursor: pointer; transition: background 0.2s;
  }
  .lock-box .lock-btn:hover { background: #22d3ee; }
  .lock-box .lock-err { color: #ef4444; font-size: 0.72rem; margin-top: 0.5rem; min-height: 1rem; }
  .lock-box .lock-footer { font-size: 0.6rem; color: #374151; margin-top: 1.5rem; }
"""

password_html = """
<div id="lockScreen">
  <div class="lock-box">
    <div class="lock-icon">🔒</div>
    <h2>Construction Intelligence</h2>
    <div class="lock-sub">HERACLES Group · Confidential Demo</div>
    <input type="password" id="lockPass" placeholder="Enter access code" onkeydown="if(event.key==='Enter')checkPass()">
    <button class="lock-btn" onclick="checkPass()">Access Dashboard</button>
    <div class="lock-err" id="lockErr"></div>
    <div class="lock-footer">Prepared by Stelios · Data from Diavgeia</div>
  </div>
</div>
"""

password_js = """
// Password check (SHA-256 client-side)
const PASS_HASH = '49a7e64a6cede4c7ddeb364c246991b6312b682c0ac17f18e05fa4cf9051e3b7'; // heracles2026
async function sha256(msg) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(msg));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
async function checkPass() {
  const input = document.getElementById('lockPass').value;
  const hash = await sha256(input);
  if (hash === PASS_HASH) {
    document.getElementById('lockScreen').classList.add('hidden');
    sessionStorage.setItem('auth', '1');
  } else {
    document.getElementById('lockErr').textContent = 'Invalid access code';
    document.getElementById('lockPass').value = '';
    document.getElementById('lockPass').focus();
  }
}
// Auto-unlock if already authed this session
if (sessionStorage.getItem('auth') === '1') {
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('lockScreen').classList.add('hidden');
  });
}
"""

html = html.replace("</style>", password_css + "\n</style>")
html = html.replace("<body>", "<body>\n" + password_html)
html = html.replace("initMap();\nfilterTable();",
    password_js + "\ninitMap();\nfilterTable();")

# ═══════════════════════════════════════════════════════════════
#  WRITE OUTPUT
# ═══════════════════════════════════════════════════════════════

DST.write_text(html, encoding="utf-8")
size = DST.stat().st_size
print(f"✓ Generated {DST.name} ({size:,} bytes)")
print(f"  - Rebranded for HERACLES Group")
print(f"  - Added plant location markers (Volos, Chalkida, Elefsina, Aspropyrgos, Gerakas, Patras)")
print(f"  - Added Weekly Digest tab with trend chart, top regions, top engineers, use breakdown")
print(f"  - Added view presets for HERACLES plant regions")
