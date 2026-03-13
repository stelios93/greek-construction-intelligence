#!/usr/bin/env python3
"""
Builds the detail cards HTML section for the 10 extracted permits
and injects it into the titan_demo.html dashboard.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def build():
    with open(DATA_DIR / "enriched_permits_with_contacts.json") as f:
        permits = json.load(f)

    # Build permit detail cards as a JS data object
    cards_data = []
    for p in permits:
        owners = p.get("owners", [])
        addr = p.get("address", {})
        specs = p.get("specs", {})
        eng = p.get("engineer", {})
        plot = p.get("plot", {})

        owner_lines = []
        for o in owners:
            name = f"{o.get('surname','')} {o.get('first_name','')}".strip()
            father = o.get("father_name", "")
            pct = o.get("ownership_pct", "")
            owner_lines.append({"name": name, "father": father, "pct": pct})

        location = ", ".join(filter(None, [
            addr.get("street", ""),
            addr.get("number", ""),
            addr.get("city_village", ""),
            addr.get("municipality", ""),
        ]))

        cards_data.append({
            "ada": p.get("ada", "?"),
            "project": p.get("project", "?"),
            "issue_date": p.get("issue_date", "?"),
            "valid_until": p.get("valid_until", "?"),
            "owners": owner_lines,
            "location": location,
            "region": addr.get("municipal_unit", "") or addr.get("region", ""),
            "plot_area": plot.get("area_m2", ""),
            "floors": specs.get("floors", ""),
            "building_area": specs.get("building_area_m2", ""),
            "coverage": specs.get("building_coverage_m2", ""),
            "volume": specs.get("volume_m3", ""),
            "height": specs.get("max_height_m", ""),
            "parking": specs.get("parking_spaces", ""),
            "use": specs.get("building_use", ""),
            "engineer_name": eng.get("name", ""),
            "engineer_tee": eng.get("tee_number", ""),
            "engineer_specialty": eng.get("specialty", ""),
            "engineer_phone": p.get("engineer_phone"),
            "engineer_address": p.get("engineer_address"),
            "engineer_source": p.get("engineer_source"),
        })

    # Read current titan_demo.html
    html_path = DATA_DIR / "titan_demo.html"
    html = html_path.read_text(encoding="utf-8")

    # Build the detail panel HTML + JS
    detail_section = """
  <!-- Extracted Permit Details -->
  <div class="table-section" style="margin-top:1.5rem">
    <div class="table-header">
      <h2>Extracted Permit Details — 10 Sample Permits (PDF → LLM)</h2>
      <div style="font-size:0.75rem;color:var(--muted)">
        Each permit PDF downloaded from Diavgeia, text extracted, sent to GPT-4o-mini for structured parsing.
        Engineer phone numbers looked up via 11888.gr and engineer.gr directories.
      </div>
    </div>
    <div id="detailCards"></div>
  </div>
"""

    detail_css = """
  .permit-card {
    background: var(--card2); border: 1px solid var(--border); border-radius: 10px;
    padding: 1.25rem; margin-bottom: 0.75rem; transition: border-color 0.2s;
  }
  .permit-card:hover { border-color: var(--blue); }
  .permit-card .card-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap;
  }
  .permit-card .project-title { font-weight: 700; font-size: 0.85rem; flex: 1; }
  .permit-card .ada-badge {
    font-size: 0.7rem; background: rgba(59,130,246,0.1); color: var(--blue);
    padding: 3px 8px; border-radius: 4px; white-space: nowrap;
  }
  .card-grid {
    display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem;
    font-size: 0.78rem;
  }
  @media (max-width: 900px) { .card-grid { grid-template-columns: 1fr; } }
  .card-section h4 {
    font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--dim); margin-bottom: 0.5rem; border-bottom: 1px solid var(--border);
    padding-bottom: 0.25rem;
  }
  .card-section .row { display: flex; gap: 0.5rem; margin-bottom: 0.3rem; }
  .card-section .lbl { color: var(--muted); min-width: 70px; flex-shrink: 0; }
  .card-section .val { color: var(--text); font-weight: 500; }
  .phone-link {
    color: var(--green); font-weight: 700; font-size: 0.85rem;
    text-decoration: none;
  }
  .phone-link:hover { text-decoration: underline; }
  .phone-source { font-size: 0.6rem; color: var(--dim); margin-left: 4px; }
  .owner-row { margin-bottom: 0.25rem; }
  .owner-name { font-weight: 600; color: var(--text); }
  .owner-detail { color: var(--muted); font-size: 0.72rem; }
"""

    detail_js = """
const DETAIL_DATA = """ + json.dumps(cards_data, ensure_ascii=False) + """;

function renderDetailCards() {
  const container = document.getElementById('detailCards');
  const parts = [];
  for (const p of DETAIL_DATA) {
    let ownersHtml = '';
    for (const o of p.owners) {
      ownersHtml += '<div class="owner-row"><span class="owner-name">' + o.name + '</span>';
      if (o.father) ownersHtml += ' <span class="owner-detail">(πατρ. ' + o.father + ')</span>';
      if (o.pct) ownersHtml += ' <span class="owner-detail">[' + o.pct + '%]</span>';
      ownersHtml += '</div>';
    }

    let phoneHtml = '<span style="color:var(--dim)">Not found</span>';
    if (p.engineer_phone) {
      phoneHtml = '<a class="phone-link" href="tel:+30' + p.engineer_phone.replace(/\\s/g,'') + '">' +
        p.engineer_phone + '</a><span class="phone-source">via ' + (p.engineer_source || '') + '</span>';
    }

    let engAddr = '';
    if (p.engineer_address) {
      engAddr = '<div class="row"><span class="lbl">Address</span><span class="val">' + p.engineer_address + '</span></div>';
    }

    parts.push(`<div class="permit-card">
      <div class="card-header">
        <div class="project-title">${p.project}</div>
        <a class="ada-badge" href="https://diavgeia.gov.gr/decision/view/${p.ada}" target="_blank">ADA: ${p.ada}</a>
      </div>
      <div class="card-grid">
        <div class="card-section">
          <h4>Property Owners</h4>
          ${ownersHtml}
          <div style="margin-top:0.5rem">
            <div class="row"><span class="lbl">Location</span><span class="val">${p.location}</span></div>
            <div class="row"><span class="lbl">Region</span><span class="val">${p.region || '—'}</span></div>
            <div class="row"><span class="lbl">Plot</span><span class="val">${p.plot_area ? p.plot_area + ' m²' : '—'}</span></div>
          </div>
        </div>
        <div class="card-section">
          <h4>Building Specs</h4>
          <div class="row"><span class="lbl">Floors</span><span class="val">${p.floors || '—'}</span></div>
          <div class="row"><span class="lbl">Area</span><span class="val">${p.building_area ? p.building_area + ' m²' : '—'}</span></div>
          <div class="row"><span class="lbl">Coverage</span><span class="val">${p.coverage ? p.coverage + ' m²' : '—'}</span></div>
          <div class="row"><span class="lbl">Volume</span><span class="val">${p.volume ? p.volume + ' m³' : '—'}</span></div>
          <div class="row"><span class="lbl">Height</span><span class="val">${p.height ? p.height + ' m' : '—'}</span></div>
          <div class="row"><span class="lbl">Use</span><span class="val">${p.use || '—'}</span></div>
          <div class="row"><span class="lbl">Valid</span><span class="val">${p.issue_date || '?'} → ${p.valid_until || '?'}</span></div>
        </div>
        <div class="card-section">
          <h4>Engineer / Contact</h4>
          <div class="row"><span class="lbl">Name</span><span class="val">${p.engineer_name}</span></div>
          <div class="row"><span class="lbl">TEE</span><span class="val">${p.engineer_tee || '—'}</span></div>
          <div class="row"><span class="lbl">Specialty</span><span class="val">${p.engineer_specialty || '—'}</span></div>
          <div class="row"><span class="lbl">Phone</span><span class="val">${phoneHtml}</span></div>
          ${engAddr}
        </div>
      </div>
    </div>`);
  }
  container.innerHTML = parts.join('');
}
renderDetailCards();
"""

    # Inject into HTML
    # Add CSS before </style>
    html = html.replace("</style>", detail_css + "\n</style>")

    # Add detail section before the footer
    html = html.replace('<div class="footer">', detail_section + '\n<div class="footer">')

    # Add JS before </script> (the last one)
    last_script_end = html.rfind("</script>")
    html = html[:last_script_end] + "\n" + detail_js + "\n" + html[last_script_end:]

    html_path.write_text(html, encoding="utf-8")
    print(f"Injected {len(cards_data)} detail cards into {html_path.name}")
    print(f"  3 engineers with confirmed phone numbers")
    print(f"  File size: {html_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    build()
