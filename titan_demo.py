#!/usr/bin/env python3
"""
TITAN Cement Sales Demo
========================
Transforms raw Diavgeia building permit data into a structured,
sortable intelligence report optimized for a building materials company.

Extracts from each permit subject:
- Permit category (new build / renovation / small works / revision)
- Building scale (floors, basement, pool)
- Building use (residential / commercial / industrial / tourism)
- Cement demand signal (high / medium / low / negligible)
- Weekly volume trends
"""

import pandas as pd
import json
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def classify_permit(subject: str) -> dict:
    """Extract structured fields from a Greek building permit subject line."""
    s = subject.upper()
    result = {}

    # ── Permit Category ──
    if "ΠΡΟΕΓΚΡΙΣΗ" in s:
        result["permit_stage"] = "Pre-approval"
    elif "ΑΝΑΘΕΩΡΗΣΗ" in s or "ΑΝΑΘΕΏΡΗΣΗ" in s:
        result["permit_stage"] = "Revision"
    elif "ΕΝΗΜΕΡΩΣΗ" in s or "ΕΝΗΜΈΡΩΣΗ" in s:
        result["permit_stage"] = "Update"
    elif "ΕΡΓΑΣΙΩΝ ΔΟΜΗΣΗΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ" in s or "ΕΡΓΑΣΙΏΝ ΔΌΜΗΣΗΣ ΜΙΚΡΉΣ" in s:
        result["permit_stage"] = "Small Works"
    elif "ΟΙΚΟΔΟΜΙΚΗ ΑΔΕΙΑ" in s or "ΟΙΚΟΔΟΜΙΚΉ ΆΔΕΙΑ" in s or "ΑΔΕΙΑ ΔΟΜΗΣΗΣ" in s or "ΆΔΕΙΑ ΔΌΜΗΣΗΣ" in s:
        result["permit_stage"] = "Full Permit"
    else:
        result["permit_stage"] = "Other"

    # ── Construction Type ──
    if any(k in s for k in ["ΑΝΕΓΕΡΣΗ", "ΑΝΈΓΕΡΣΗ", "ΝΕΑ ", "ΝΕΑΣ ", "ΝΕΩΝ ", "ΝΕΟΥ ", "ΝΕΟ "]):
        result["construction_type"] = "New Build"
    elif any(k in s for k in ["ΠΡΟΣΘΗΚΗ", "ΠΡΟΣΘΉΚΗ"]):
        result["construction_type"] = "Addition"
    elif any(k in s for k in ["ΑΛΛΑΓΗ ΧΡΗΣΗΣ", "ΑΛΛΑΓΉ ΧΡΉΣΗΣ"]):
        result["construction_type"] = "Change of Use"
    elif any(k in s for k in ["ΕΠΙΣΚΕΥ", "ΑΝΑΚΑΙΝΙ", "ΑΠΟΚΑΤΑΣΤ"]):
        result["construction_type"] = "Renovation"
    elif any(k in s for k in ["ΚΑΤΕΔΑΦ"]):
        result["construction_type"] = "Demolition"
    elif any(k in s for k in ["ΝΟΜΙΜΟΠΟΙ", "ΑΥΘΑΙΡΕΤ"]):
        result["construction_type"] = "Legalization"
    elif any(k in s for k in ["ΠΕΡΙΦΡΑΞΗ", "ΦΡΑΧΤ", "ΦΡΆΧΤ"]):
        result["construction_type"] = "Fencing"
    else:
        result["construction_type"] = "Other/Mixed"

    # ── Floors ──
    floors = 0
    if any(k in s for k in ["ΙΣΟΓΕΙ", "ΙΣΌΓΕΙ"]):
        floors = max(floors, 1)
    if any(k in s for k in ["ΔΙΩΡΟΦ", "ΔΙΌΡΟΦ", "ΔΙΏΡΟΦ"]):
        floors = max(floors, 2)
    if any(k in s for k in ["ΤΡΙΩΡΟΦ", "ΤΡΙΌΡΟΦ", "ΤΡΙΏΡΟΦ"]):
        floors = max(floors, 3)
    if any(k in s for k in ["ΤΕΤΡΑΩΡΟΦ", "ΤΕΤΡΑΌΡΟΦ"]):
        floors = max(floors, 4)
    if any(k in s for k in ["ΠΕΝΤΑΩΡΟΦ", "ΠΕΝΤΑΌΡΟΦ"]):
        floors = max(floors, 5)
    if any(k in s for k in ["ΕΞΑΩΡΟΦ", "ΕΞΑΌΡΟΦ"]):
        floors = max(floors, 6)
    if any(k in s for k in ["ΠΟΛΥΩΡΟΦ", "ΠΟΛΥΌΡΟΦ", "ΠΟΛΥΏΡΟΦ"]):
        floors = max(floors, 7)
    # Check for "Α' ΟΡΟΦ", "Β' ΟΡΟΦ", etc.
    floor_matches = re.findall(r'(\d+)\s*(?:ΟΥ?\s*)?(?:ΟΡΟΦ|ΟΡ\.)', s)
    if floor_matches:
        floors = max(floors, max(int(m) for m in floor_matches))
    # "2 ΚΑΤΟΙΚΙΕΣ", "4 ΚΑΤΟΙΚΙΩΝ" etc.
    unit_match = re.search(r'(\d+)\s*(?:ΚΑΤΟΙΚΙ|ΔΙΑΜΕΡΙΣΜ)', s)
    units = int(unit_match.group(1)) if unit_match else 0

    result["floors"] = floors
    result["units"] = units

    # ── Features ──
    result["has_basement"] = 1 if any(k in s for k in ["ΥΠΟΓΕΙ", "ΥΠΌΓΕΙ"]) else 0
    result["has_pool"] = 1 if any(k in s for k in ["ΠΙΣΙΝ", "ΚΟΛΥΜΒ"]) else 0
    result["has_roof_structure"] = 1 if any(k in s for k in ["ΣΤΕΓΗ", "ΣΤΈΓΗ"]) else 0
    result["has_parking"] = 1 if any(k in s for k in ["ΣΤΑΘΜΕΥΣ", "PARKING", "ΓΚΑΡΑΖ", "ΓΚΑΡΆΖ"]) else 0
    result["is_photovoltaic"] = 1 if any(k in s for k in ["ΦΩΤΟΒΟΛΤ", "ΗΛΙΑΚ"]) else 0
    result["is_thermal_insulation"] = 1 if any(k in s for k in ["ΘΕΡΜΟΜΟΝΩΣ", "ΘΕΡΜΟΜΌΝΩΣ", "ΕΞΟΙΚΟΝΟΜ"]) else 0

    # ── Building Use ──
    if any(k in s for k in ["ΚΑΤΟΙΚΙΑ", "ΚΑΤΟΙΚΊA", "ΚΑΤΟΙΚΙΑΣ", "ΚΑΤΟΙΚΙΩΝ", "ΚΑΤΟΙΚΙΕΣ",
                             "ΜΟΝΟΚΑΤΟΙΚ", "ΜΕΖΟΝΕΤ", "ΔΙΑΜΕΡΙΣΜ"]):
        result["building_use"] = "Residential"
    elif any(k in s for k in ["ΞΕΝΟΔΟΧ", "ΤΟΥΡΙΣΤ", "RESORT", "VILLA", "ΒΙΛΑ", "ΒΊΛΑ", "ΚΑΤΑΛΥΜΑ"]):
        result["building_use"] = "Tourism"
    elif any(k in s for k in ["ΚΑΤΑΣΤΗΜ", "ΕΜΠΟΡΙΚ", "ΓΡΑΦΕΙ", "ΕΠΑΓΓΕΛΜΑΤ", "ΚΤΙΡΙΟ ΓΡΑΦ"]):
        result["building_use"] = "Commercial"
    elif any(k in s for k in ["ΒΙΟΜΗΧΑΝ", "ΕΡΓΟΣΤΑΣ", "ΑΠΟΘΗΚ", "ΕΡΓΑΣΤΗΡ", "LOGISTICS"]):
        result["building_use"] = "Industrial/Logistics"
    elif any(k in s for k in ["ΣΧΟΛ", "ΕΚΠΑΙΔ", "ΝΟΣΟΚΟΜ", "ΥΓΕΙΟΝ", "ΕΚΚΛΗΣ", "ΑΘΛΗΤ", "ΓΥΜΝΑΣΤ"]):
        result["building_use"] = "Public/Institutional"
    elif any(k in s for k in ["ΑΓΡΟΤ", "ΓΕΩΡΓ", "ΣΤΑΒΛ", "ΘΕΡΜΟΚΗΠ"]):
        result["building_use"] = "Agricultural"
    elif any(k in s for k in ["ΦΩΤΟΒΟΛΤ", "ΗΛΙΑΚ", "ΑΝΕΜΟΓΕΝ"]):
        result["building_use"] = "Energy"
    else:
        result["building_use"] = "Unclassified"

    # ── Cement Demand Signal ──
    # New builds with multiple floors and basements = HIGH cement
    # Renovations and small works = LOW cement
    # Fencing, PV installations, insulation = NEGLIGIBLE
    score = 0
    if result["construction_type"] == "New Build":
        score += 3
    elif result["construction_type"] == "Addition":
        score += 2
    elif result["construction_type"] in ("Renovation", "Other/Mixed"):
        score += 1

    if result["permit_stage"] == "Full Permit":
        score += 2
    elif result["permit_stage"] == "Pre-approval":
        score += 1

    score += min(result["floors"], 5)
    score += result["has_basement"] * 2
    score += result["has_pool"] * 1
    score += result["has_parking"] * 1

    if result["construction_type"] in ("Fencing", "Demolition"):
        score = 0
    if result["is_photovoltaic"] and result["construction_type"] != "New Build":
        score = 0
    if result["is_thermal_insulation"] and result["construction_type"] != "New Build":
        score = 0

    if score >= 7:
        result["cement_demand"] = "HIGH"
    elif score >= 4:
        result["cement_demand"] = "MEDIUM"
    elif score >= 1:
        result["cement_demand"] = "LOW"
    else:
        result["cement_demand"] = "NEGLIGIBLE"

    result["cement_score"] = score

    return result


def build_titan_dataset():
    """Load permits and enrich with TITAN-relevant classifications."""
    print("Loading permits...")
    df = pd.read_csv(DATA_DIR / "diavgeia_building_permits.csv")
    print(f"  {len(df)} raw permits loaded")

    # Apply classification
    print("Classifying permits...")
    classifications = df["subject"].apply(classify_permit).apply(pd.Series)
    df = pd.concat([df, classifications], axis=1)

    # Clean up dates
    df["issue_date"] = pd.to_datetime(df["issue_date"])
    df["week"] = df["issue_date"].dt.isocalendar().week.astype(int)
    df["year_month"] = df["issue_date"].dt.to_period("M").astype(str)

    # Sort by cement demand score descending
    df = df.sort_values(["cement_score", "issue_date"], ascending=[False, False]).reset_index(drop=True)

    # Save enriched dataset
    csv_path = DATA_DIR / "titan_enriched_permits.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  Saved enriched dataset → {csv_path.name}")

    return df


def generate_titan_html(df):
    """Generate an interactive, sortable HTML report for TITAN Cement."""

    # ── Aggregate stats ──
    total = len(df)
    new_builds = len(df[df["construction_type"] == "New Build"])
    high_cement = len(df[df["cement_demand"] == "HIGH"])
    med_cement = len(df[df["cement_demand"] == "MEDIUM"])
    full_permits = len(df[df["permit_stage"] == "Full Permit"])
    with_basement = df["has_basement"].sum()
    multi_floor = len(df[df["floors"] >= 2])
    residential = len(df[df["building_use"] == "Residential"])
    commercial = len(df[df["building_use"] == "Commercial"])
    tourism = len(df[df["building_use"] == "Tourism"])
    industrial = len(df[df["building_use"] == "Industrial/Logistics"])
    date_min = df["issue_date"].min().strftime("%Y-%m-%d")
    date_max = df["issue_date"].max().strftime("%Y-%m-%d")

    # ── Weekly trend data ──
    weekly = df.groupby([df["issue_date"].dt.to_period("W").astype(str)]).agg(
        permits=("ada", "count"),
        new_builds=("construction_type", lambda x: (x == "New Build").sum()),
        high_cement=("cement_demand", lambda x: (x == "HIGH").sum()),
    ).reset_index()
    weekly_labels = weekly["issue_date"].tolist()
    weekly_permits = weekly["permits"].tolist()
    weekly_new = weekly["new_builds"].tolist()
    weekly_high = weekly["high_cement"].tolist()

    # ── Building use breakdown ──
    use_counts = df["building_use"].value_counts()
    use_labels = use_counts.index.tolist()
    use_values = use_counts.values.tolist()

    # ── Cement demand breakdown ──
    cement_counts = df["cement_demand"].value_counts()
    cement_labels = cement_counts.index.tolist()
    cement_values = cement_counts.values.tolist()

    # ── Construction type breakdown ──
    ct_counts = df["construction_type"].value_counts()
    ct_labels = ct_counts.index.tolist()
    ct_values = ct_counts.values.tolist()

    # ── Permit stage breakdown ──
    stage_counts = df["permit_stage"].value_counts()
    stage_labels = stage_counts.index.tolist()
    stage_values = stage_counts.values.tolist()

    # ── Table rows (all permits) ──
    table_data = []
    for _, r in df.iterrows():
        desc = str(r["subject"])
        # Extract just the description part after the colon
        if ":" in desc:
            desc = desc.split(":", 1)[1].strip()
        desc = desc[:100]

        table_data.append({
            "date": r["issue_date"].strftime("%Y-%m-%d"),
            "ada": r["ada"],
            "desc": desc,
            "stage": r["permit_stage"],
            "type": r["construction_type"],
            "use": r["building_use"],
            "floors": int(r["floors"]) if r["floors"] > 0 else "",
            "basement": "Yes" if r["has_basement"] else "",
            "pool": "Yes" if r["has_pool"] else "",
            "cement": r["cement_demand"],
            "score": int(r["cement_score"]),
        })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Greek Building Permits — Construction Materials Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0b0f19; --card: #111827; --card2: #1a2332; --border: #1e293b;
    --text: #e2e8f0; --muted: #94a3b8; --dim: #64748b;
    --blue: #3b82f6; --green: #10b981; --orange: #f59e0b;
    --red: #ef4444; --purple: #8b5cf6; --cyan: #06b6d4;
    --high: #ef4444; --med: #f59e0b; --low: #3b82f6; --neg: #374151;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }}

  .header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 2.5rem 2rem 2rem;
    border-bottom: 1px solid var(--border);
  }}
  .header-inner {{ max-width: 1500px; margin: 0 auto; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; }}
  .header h1 span {{ color: var(--orange); }}
  .header .sub {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.4rem; }}
  .header .sub strong {{ color: var(--text); }}
  .header .pitch {{
    margin-top: 1rem; padding: 0.75rem 1rem;
    background: rgba(245,158,11,0.08); border-left: 3px solid var(--orange);
    border-radius: 0 8px 8px 0; font-size: 0.82rem; color: var(--muted);
    max-width: 900px;
  }}
  .header .pitch strong {{ color: var(--orange); }}

  .container {{ max-width: 1500px; margin: 0 auto; padding: 1.5rem; }}

  .kpi-strip {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.75rem; margin-bottom: 1.5rem;
  }}
  .kpi {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem 1.1rem; text-align: center;
  }}
  .kpi .num {{ font-size: 1.6rem; font-weight: 800; }}
  .kpi .lbl {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-top: 0.2rem; }}

  .charts-grid {{
    display: grid; grid-template-columns: 2fr 1fr 1fr;
    gap: 1rem; margin-bottom: 1.5rem;
  }}
  @media (max-width: 1000px) {{ .charts-grid {{ grid-template-columns: 1fr; }} }}
  .chart-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.25rem;
  }}
  .chart-card h3 {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem; }}

  .table-section {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.25rem; overflow: hidden;
  }}
  .table-header {{
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem;
  }}
  .table-header h2 {{ font-size: 1rem; font-weight: 700; }}
  .filters {{
    display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
  }}
  .filters select, .filters input {{
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 0.4rem 0.6rem; font-size: 0.75rem;
    outline: none;
  }}
  .filters select:focus, .filters input:focus {{ border-color: var(--blue); }}
  .filters label {{ font-size: 0.7rem; color: var(--muted); }}

  .table-wrap {{ overflow-x: auto; max-height: 70vh; overflow-y: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.75rem; white-space: nowrap; }}
  thead {{ position: sticky; top: 0; z-index: 10; }}
  th {{
    background: var(--card2); color: var(--muted); font-weight: 600;
    text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em;
    padding: 0.65rem 0.6rem; text-align: left; border-bottom: 2px solid var(--border);
    cursor: pointer; user-select: none;
  }}
  th:hover {{ color: var(--text); }}
  th .sort-arrow {{ margin-left: 3px; font-size: 0.6rem; }}
  td {{ padding: 0.55rem 0.6rem; border-bottom: 1px solid rgba(30,41,59,0.6); }}
  tr:hover {{ background: rgba(59,130,246,0.04); }}
  .badge {{
    display: inline-block; padding: 2px 7px; border-radius: 4px;
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.02em;
  }}
  .badge-high {{ background: rgba(239,68,68,0.15); color: var(--high); }}
  .badge-med {{ background: rgba(245,158,11,0.15); color: var(--med); }}
  .badge-low {{ background: rgba(59,130,246,0.12); color: var(--low); }}
  .badge-neg {{ background: rgba(55,65,81,0.4); color: var(--dim); }}
  .badge-new {{ background: rgba(16,185,129,0.15); color: var(--green); }}
  .badge-add {{ background: rgba(6,182,212,0.15); color: var(--cyan); }}
  .badge-reno {{ background: rgba(139,92,246,0.12); color: var(--purple); }}

  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  .export-btn {{
    background: var(--blue); color: white; border: none; border-radius: 6px;
    padding: 0.4rem 1rem; font-size: 0.75rem; font-weight: 600; cursor: pointer;
  }}
  .export-btn:hover {{ opacity: 0.9; }}

  .footer {{
    text-align: center; padding: 1.5rem; color: var(--dim); font-size: 0.7rem;
    border-top: 1px solid var(--border); margin-top: 1.5rem;
  }}
  .count-display {{ font-size: 0.75rem; color: var(--muted); }}
  .pager {{ display: flex; gap: 4px; align-items: center; }}
  .pager button {{
    background: var(--bg); color: var(--muted); border: 1px solid var(--border);
    border-radius: 5px; padding: 4px 10px; font-size: 0.72rem; cursor: pointer;
  }}
  .pager button:hover {{ color: var(--text); border-color: var(--blue); }}
  .pager button:disabled {{ opacity: 0.3; cursor: default; }}
  .pager button.active {{ background: var(--blue); color: #fff; border-color: var(--blue); }}
  .pager span {{ font-size: 0.72rem; color: var(--dim); padding: 0 4px; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <h1>Building Permits Intelligence <span>// Greece</span></h1>
    <div class="sub">
      <strong>{total:,}</strong> permits from <strong>{date_min}</strong> to <strong>{date_max}</strong>
      &nbsp;|&nbsp; Source: Diavgeia Government Transparency Portal (real-time) + ELSTAT
    </div>
    <div class="pitch">
      <strong>{high_cement + med_cement:,} permits</strong> flagged as medium-to-high cement demand.
      <strong>{new_builds:,} new builds</strong> identified.
      This feed updates daily from the official Greek government permit registry.
      Each permit is classified by construction type, building use, scale, and estimated material demand.
    </div>
  </div>
</div>

<div class="container">

  <!-- KPI Strip -->
  <div class="kpi-strip">
    <div class="kpi"><div class="num" style="color:var(--text)">{total:,}</div><div class="lbl">Total Permits</div></div>
    <div class="kpi"><div class="num" style="color:var(--green)">{new_builds:,}</div><div class="lbl">New Builds</div></div>
    <div class="kpi"><div class="num" style="color:var(--high)">{high_cement:,}</div><div class="lbl">High Cement</div></div>
    <div class="kpi"><div class="num" style="color:var(--med)">{med_cement:,}</div><div class="lbl">Medium Cement</div></div>
    <div class="kpi"><div class="num" style="color:var(--blue)">{full_permits:,}</div><div class="lbl">Full Permits</div></div>
    <div class="kpi"><div class="num" style="color:var(--cyan)">{multi_floor:,}</div><div class="lbl">Multi-Floor</div></div>
    <div class="kpi"><div class="num" style="color:var(--purple)">{int(with_basement):,}</div><div class="lbl">With Basement</div></div>
    <div class="kpi"><div class="num" style="color:var(--orange)">{tourism:,}</div><div class="lbl">Tourism</div></div>
  </div>

  <!-- Charts -->
  <div class="charts-grid">
    <div class="chart-card">
      <h3>Weekly Permit Volume & Cement Demand</h3>
      <canvas id="weeklyChart" height="90"></canvas>
    </div>
    <div class="chart-card">
      <h3>Cement Demand Signal</h3>
      <canvas id="cementChart" height="140"></canvas>
    </div>
    <div class="chart-card">
      <h3>Building Use</h3>
      <canvas id="useChart" height="140"></canvas>
    </div>
  </div>

  <!-- Table -->
  <div class="table-section">
    <div class="table-header">
      <h2>Permit Register</h2>
      <div class="filters">
        <div>
          <label>Cement Demand</label><br>
          <select id="filterCement" onchange="applyFilters()">
            <option value="">All</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
            <option value="NEGLIGIBLE">NEGLIGIBLE</option>
          </select>
        </div>
        <div>
          <label>Construction</label><br>
          <select id="filterType" onchange="applyFilters()">
            <option value="">All</option>
            <option value="New Build">New Build</option>
            <option value="Addition">Addition</option>
            <option value="Renovation">Renovation</option>
            <option value="Change of Use">Change of Use</option>
            <option value="Fencing">Fencing</option>
            <option value="Other/Mixed">Other/Mixed</option>
          </select>
        </div>
        <div>
          <label>Building Use</label><br>
          <select id="filterUse" onchange="applyFilters()">
            <option value="">All</option>
            <option value="Residential">Residential</option>
            <option value="Tourism">Tourism</option>
            <option value="Commercial">Commercial</option>
            <option value="Industrial/Logistics">Industrial</option>
            <option value="Public/Institutional">Public</option>
            <option value="Agricultural">Agricultural</option>
          </select>
        </div>
        <div>
          <label>Search</label><br>
          <input id="filterSearch" type="text" placeholder="keyword..." oninput="applyFilters()" style="width:140px">
        </div>
        <div style="padding-top:14px">
          <button class="export-btn" onclick="exportCSV()">Export CSV</button>
        </div>
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem">
      <div class="count-display" id="countDisplay"></div>
      <div class="pager" id="pager"></div>
    </div>
    <div class="table-wrap">
      <table id="permitTable">
        <thead>
          <tr>
            <th onclick="sortTable(0)">Date <span class="sort-arrow">▼</span></th>
            <th onclick="sortTable(1)">ADA</th>
            <th onclick="sortTable(2)" style="min-width:250px">Description</th>
            <th onclick="sortTable(3)">Stage</th>
            <th onclick="sortTable(4)">Construction</th>
            <th onclick="sortTable(5)">Use</th>
            <th onclick="sortTable(6)">Floors</th>
            <th onclick="sortTable(7)">Basement</th>
            <th onclick="sortTable(8)">Pool</th>
            <th onclick="sortTable(9)">Cement</th>
            <th onclick="sortTable(10)">Score</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.75rem;flex-wrap:wrap;gap:0.5rem">
      <div class="count-display" id="countDisplay2"></div>
      <div class="pager" id="pager2"></div>
    </div>
  </div>

</div>

<div class="footer">
  Data source: opendata.diavgeia.gov.gr — Greek Government Transparency Portal<br>
  Permit classification and cement demand scoring by Construction Intelligence Pipeline v1.0
</div>

<script>
const DATA = {json.dumps(table_data, ensure_ascii=False)};
let filteredData = [...DATA];
let sortCol = 0, sortAsc = false;
let page = 0;
const PAGE_SIZE = 50;

function cementBadge(c) {{
  const m = {{HIGH:'high',MEDIUM:'med',LOW:'low',NEGLIGIBLE:'neg'}};
  return '<span class="badge badge-'+(m[c]||'neg')+'">'+c+'</span>';
}}
function typeBadge(t) {{
  const m = {{'New Build':'new',Addition:'add',Renovation:'reno'}};
  return m[t] ? '<span class="badge badge-'+m[t]+'">'+t+'</span>' : t;
}}

function renderTable() {{
  const start = page * PAGE_SIZE;
  const slice = filteredData.slice(start, start + PAGE_SIZE);
  const parts = new Array(slice.length);
  for (let i = 0; i < slice.length; i++) {{
    const r = slice[i];
    const sc = r.score >= 7 ? 'var(--high)' : r.score >= 4 ? 'var(--med)' : 'var(--muted)';
    parts[i] = '<tr><td>'+r.date+'</td><td><a href="https://diavgeia.gov.gr/decision/view/'+r.ada+'" target="_blank">'+r.ada+'</a></td><td style="white-space:normal;max-width:350px">'+r.desc+'</td><td>'+r.stage+'</td><td>'+typeBadge(r.type)+'</td><td>'+r.use+'</td><td style="text-align:center">'+(r.floors||'')+'</td><td style="text-align:center;color:var(--cyan)">'+r.basement+'</td><td style="text-align:center;color:var(--blue)">'+r.pool+'</td><td>'+cementBadge(r.cement)+'</td><td style="text-align:center;font-weight:700;color:'+sc+'">'+r.score+'</td></tr>';
  }}
  document.getElementById('tableBody').innerHTML = parts.join('');
  const total = filteredData.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const showing = total === 0 ? 'No matches' : 'Showing '+(start+1)+'\u2013'+Math.min(start+PAGE_SIZE,total)+' of '+total.toLocaleString()+' permits';
  document.getElementById('countDisplay').textContent = showing;
  document.getElementById('countDisplay2').textContent = showing;
  ['pager','pager2'].forEach(id => {{
    const el = document.getElementById(id);
    if (pages <= 1) {{ el.innerHTML = ''; return; }}
    let h = '<button '+(page===0?'disabled':'')+' onclick="goPage('+(page-1)+')">Prev</button>';
    const maxBtns = 7;
    let s = Math.max(0, page - 3), e = Math.min(pages, s + maxBtns);
    if (e - s < maxBtns) s = Math.max(0, e - maxBtns);
    if (s > 0) h += '<button onclick="goPage(0)">1</button><span>...</span>';
    for (let p = s; p < e; p++) h += '<button class="'+(p===page?'active':'')+'" onclick="goPage('+p+')">'+(p+1)+'</button>';
    if (e < pages) h += '<span>...</span><button onclick="goPage('+(pages-1)+')">'+pages+'</button>';
    h += '<button '+(page>=pages-1?'disabled':'')+' onclick="goPage('+(page+1)+')">Next</button>';
    el.innerHTML = h;
  }});
}}

function goPage(p) {{ page = p; renderTable(); document.getElementById('permitTable').scrollIntoView({{behavior:'smooth',block:'start'}}); }}

function applyFilters() {{
  const cement = document.getElementById('filterCement').value;
  const type = document.getElementById('filterType').value;
  const use = document.getElementById('filterUse').value;
  const search = document.getElementById('filterSearch').value.toLowerCase();
  filteredData = DATA.filter(r => {{
    if (cement && r.cement !== cement) return false;
    if (type && r.type !== type) return false;
    if (use && r.use !== use) return false;
    if (search && !r.desc.toLowerCase().includes(search) && !r.ada.toLowerCase().includes(search)) return false;
    return true;
  }});
  page = 0;
  renderTable();
}}

function sortTable(col) {{
  if (sortCol === col) {{ sortAsc = !sortAsc; }} else {{ sortCol = col; sortAsc = true; }}
  const keys = ['date','ada','desc','stage','type','use','floors','basement','pool','cement','score'];
  const key = keys[col];
  filteredData.sort((a, b) => {{
    let va = a[key], vb = b[key];
    if (typeof va === 'number' && typeof vb === 'number') return sortAsc ? va - vb : vb - va;
    return String(va).localeCompare(String(vb)) * (sortAsc ? 1 : -1);
  }});
  page = 0;
  renderTable();
}}

function exportCSV() {{
  const headers = ['Date','ADA','Description','Stage','Construction Type','Building Use','Floors','Basement','Pool','Cement Demand','Score'];
  const rows = filteredData.map(r => [r.date, r.ada, '"'+r.desc.replace(/"/g,'""')+'"', r.stage, r.type, r.use, r.floors, r.basement, r.pool, r.cement, r.score]);
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\\n');
  const blob = new Blob(['\\uFEFF' + csv], {{ type: 'text/csv;charset=utf-8;' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'greek_building_permits_'+new Date().toISOString().slice(0,10)+'.csv';
  a.click(); URL.revokeObjectURL(url);
}}

renderTable();

// Charts
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#1e293b';

new Chart(document.getElementById('weeklyChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(weekly_labels)},
    datasets: [
      {{ label: 'All Permits', data: {json.dumps(weekly_permits)}, backgroundColor: 'rgba(59,130,246,0.3)', borderRadius: 3 }},
      {{ label: 'New Builds', data: {json.dumps(weekly_new)}, backgroundColor: 'rgba(16,185,129,0.6)', borderRadius: 3 }},
      {{ label: 'High Cement', data: {json.dumps(weekly_high)}, backgroundColor: 'rgba(239,68,68,0.7)', borderRadius: 3 }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ boxWidth: 12, font: {{ size: 10 }} }} }} }},
    scales: {{
      x: {{ stacked: false, ticks: {{ font: {{ size: 9 }}, maxRotation: 45 }} }},
      y: {{ beginAtZero: true }}
    }}
  }}
}});

new Chart(document.getElementById('cementChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(cement_labels)},
    datasets: [{{ data: {json.dumps(cement_values)}, backgroundColor: ['#ef4444','#f59e0b','#3b82f6','#374151'], borderWidth: 0 }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }} }}
}});

new Chart(document.getElementById('useChart'), {{
  type: 'doughnut',
  data: {{
    labels: {json.dumps(use_labels)},
    datasets: [{{ data: {json.dumps(use_values)}, backgroundColor: ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#06b6d4','#ef4444','#ec4899','#64748b'], borderWidth: 0 }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }} }}
}});
</script>
</body>
</html>"""

    out_path = DATA_DIR / "titan_demo.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  Dashboard saved → {out_path}")
    return out_path


if __name__ == "__main__":
    df = build_titan_dataset()

    # Print summary for TITAN
    print("\n" + "=" * 60)
    print("  TITAN CEMENT — PERMIT INTELLIGENCE SUMMARY")
    print("=" * 60)

    print(f"\n  Total permits analyzed: {len(df):,}")
    print(f"  Date range: {df['issue_date'].min().strftime('%Y-%m-%d')} → {df['issue_date'].max().strftime('%Y-%m-%d')}")

    print("\n  CEMENT DEMAND SIGNAL:")
    for level in ["HIGH", "MEDIUM", "LOW", "NEGLIGIBLE"]:
        count = len(df[df["cement_demand"] == level])
        pct = count / len(df) * 100
        bar = "█" * int(pct / 2)
        print(f"    {level:12s}  {count:5,}  ({pct:4.1f}%)  {bar}")

    print("\n  CONSTRUCTION TYPE:")
    for ct, count in df["construction_type"].value_counts().items():
        print(f"    {ct:20s}  {count:5,}")

    print("\n  BUILDING USE:")
    for use, count in df["building_use"].value_counts().items():
        print(f"    {use:25s}  {count:5,}")

    print("\n  SCALE INDICATORS:")
    print(f"    Multi-floor (2+):     {len(df[df['floors'] >= 2]):,}")
    print(f"    With basement:        {int(df['has_basement'].sum()):,}")
    print(f"    With pool:            {int(df['has_pool'].sum()):,}")
    print(f"    With parking:         {int(df['has_parking'].sum()):,}")

    path = generate_titan_html(df)
    print(f"\n  Open: file://{path.resolve()}")
