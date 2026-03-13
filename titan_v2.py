#!/usr/bin/env python3
"""
TITAN Dashboard v2
==================
Lean, fast dashboard with:
- Cement tonnage estimation per permit
- Click-to-expand detail cards
- No OpenAI dependency
- Regex-based PDF parser for on-demand detail extraction
"""

import pandas as pd
import json
import re
import os
import requests
import time
from datetime import datetime
from pathlib import Path
from io import BytesIO
from PyPDF2 import PdfReader

DATA_DIR = Path(__file__).parent / "data"

# ═══════════════════════════════════════════════════════════════════════════════
#  CEMENT ESTIMATION MODEL
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Reinforced concrete construction in Greece:
#  - Concrete volume ≈ 0.12–0.22 m³ per m² of gross floor area
#     Residential:    0.15 m³/m²
#     Commercial:     0.20 m³/m²
#     Industrial:     0.22 m³/m²
#     Tourism:        0.18 m³/m²
#  - Cement content:  ~300 kg per m³ of concrete (C25/30 typical)
#  - So cement ≈ floor_area × concrete_intensity × 0.3 tonnes
#
#  Floor area estimation from subject line:
#     Ground floor only (ΙΣΟΓΕΙΑ):     80–100 m²  → use 90
#     Two-story (ΔΙΩΡΟΦΗ):             180–220 m² → use 200
#     Three-story (ΤΡΙΩΡΟΦΗ):          270–330 m² → use 300
#     4+ story:                        floors × 110 m²
#     If units mentioned:              units × 85 m²
#     Piloti (ΠΥΛΩΤΗ) adds:            +70 m² slab
#     Basement (ΥΠΟΓΕΙΟ) adds:         +40% to concrete (foundation + retaining walls)
#     Pool:                            +5 m³ concrete → +1.5 tonnes cement
#     Fencing/PV/insulation:           0 cement
#     Renovation:                      ~5% of equivalent new build
#     Small works (minor):             ~0 cement
# ═══════════════════════════════════════════════════════════════════════════════


def classify_and_estimate(subject: str) -> dict:
    """Extract building features and estimate cement usage from permit subject."""
    s = subject.upper()
    r = {}

    # ── Permit Stage ──
    if "ΠΡΟΕΓΚΡΙΣΗ" in s or "ΠΡΟΈΓΚΡΙΣΗ" in s:
        r["stage"] = "Pre-approval"
    elif "ΑΝΑΘΕΩΡΗΣΗ" in s or "ΑΝΑΘΕΏΡΗΣΗ" in s:
        r["stage"] = "Revision"
    elif "ΕΝΗΜΕΡΩΣΗ" in s or "ΕΝΗΜΈΡΩΣΗ" in s:
        r["stage"] = "Update"
    elif "ΕΡΓΑΣΙΩΝ ΔΟΜΗΣΗΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ" in s or "ΕΡΓΑΣΙΏΝ ΔΌΜΗΣΗΣ" in s:
        r["stage"] = "Small Works"
    elif "ΟΙΚΟΔΟΜΙΚΗ ΑΔΕΙΑ" in s or "ΟΙΚΟΔΟΜΙΚΉ ΆΔΕΙΑ" in s or "ΑΔΕΙΑ ΔΟΜΗΣΗΣ" in s:
        r["stage"] = "Full Permit"
    else:
        r["stage"] = "Other"

    # ── Construction Type ──
    if any(k in s for k in ["ΑΝΕΓΕΡΣΗ", "ΑΝΈΓΕΡΣΗ", "ΝΕΑ ", "ΝΕΑΣ ", "ΝΕΩΝ ", "ΝΕΟΥ ", "ΝΕΟ ", "ΝΕΕΣ "]):
        r["construction"] = "New Build"
    elif any(k in s for k in ["ΠΡΟΣΘΗΚΗ", "ΠΡΟΣΘΉΚΗ"]):
        r["construction"] = "Addition"
    elif any(k in s for k in ["ΑΛΛΑΓΗ ΧΡΗΣΗΣ", "ΑΛΛΑΓΉ ΧΡΉΣΗΣ"]):
        r["construction"] = "Change of Use"
    elif any(k in s for k in ["ΕΠΙΣΚΕΥ", "ΑΝΑΚΑΙΝΙ", "ΑΠΟΚΑΤΑΣΤ", "ΔΙΑΡΡΥΘΜΙΣ", "ΤΡΟΠΟΠΟΙ",
                                "ΕΣΩΤΕΡΙΚ", "ΕΡΓΑΣΙΕΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ"]):
        r["construction"] = "Renovation"
    elif any(k in s for k in ["ΚΑΤΕΔΑΦ"]):
        r["construction"] = "Demolition"
    elif any(k in s for k in ["ΝΟΜΙΜΟΠΟΙ", "ΑΥΘΑΙΡΕΤ"]):
        r["construction"] = "Legalization"
    elif any(k in s for k in ["ΠΕΡΙΦΡΑΞΗ", "ΦΡΑΧΤ"]):
        r["construction"] = "Fencing"
    else:
        r["construction"] = "Other/Mixed"

    # ── Building Use ──
    if any(k in s for k in ["ΚΑΤΟΙΚΙΑ", "ΚΑΤΟΙΚΙΑΣ", "ΚΑΤΟΙΚΙΩΝ", "ΚΑΤΟΙΚΙΕΣ",
                             "ΜΟΝΟΚΑΤΟΙΚ", "ΜΕΖΟΝΕΤ", "ΔΙΑΜΕΡΙΣΜ", "ΟΙΚΟΔΟΜΗ", "ΟΙΚΟΔΟΜΕΣ"]):
        r["use"] = "Residential"
    elif any(k in s for k in ["ΞΕΝΟΔΟΧ", "ΤΟΥΡΙΣΤ", "RESORT", "ΒΙΛΑ", "ΒΊΛΑ", "ΚΑΤΑΛΥΜΑ"]):
        r["use"] = "Tourism"
    elif any(k in s for k in ["ΚΑΤΑΣΤΗΜ", "ΕΜΠΟΡΙΚ", "ΓΡΑΦΕΙ", "ΕΠΑΓΓΕΛΜΑΤ"]):
        r["use"] = "Commercial"
    elif any(k in s for k in ["ΒΙΟΜΗΧΑΝ", "ΕΡΓΟΣΤΑΣ", "ΑΠΟΘΗΚ", "ΕΡΓΑΣΤΗΡ", "LOGISTICS"]):
        r["use"] = "Industrial"
    elif any(k in s for k in ["ΣΧΟΛ", "ΕΚΠΑΙΔ", "ΝΟΣΟΚΟΜ", "ΕΚΚΛΗΣ", "ΑΘΛΗΤ"]):
        r["use"] = "Public"
    elif any(k in s for k in ["ΦΩΤΟΒΟΛΤ", "ΗΛΙΑΚ", "ΑΝΕΜΟΓΕΝ"]):
        r["use"] = "Energy"
    else:
        r["use"] = "Other"

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
    if any(k in s for k in ["ΠΟΛΥΩΡΟΦ", "ΠΟΛΥΌΡΟΦ"]):
        floors = max(floors, 6)
    # Match "Xόροφο/Xώροφο" building descriptions, but NOT "Xου ορόφου" (location on a floor)
    # "ΣΕ ΔΙΑΜΕΡΙΣΜΑ 5ου ΟΡΟΦΟΥ" = on the 5th floor, NOT a 5-story building
    floor_matches = re.findall(r'(\d+)\s*(?:ΟΥ?\s*)?ΟΡΟΦ', s)
    if floor_matches:
        # Only use floor count from subject if it looks like a building description,
        # not a location reference like "ΣΕ ... Xου ΟΡΟΦΟΥ"
        if not re.search(r'(?:ΣΕ|ΣΤΟΝ?|ΣΤΟ)\s+(?:ΔΙΑΜΕΡΙΣΜΑ|ΟΡΟΦΟ|ΧΩΡΟ)', s):
            floors = max(floors, max(int(m) for m in floor_matches))
    r["floors"] = floors

    # ── Units ──
    # Only match explicit dwelling counts, NOT permit reference numbers
    unit_match = re.search(r'(\d+)\s*(?:ΚΑΤΟΙΚΙ|ΔΙΑΜΕΡΙΣΜ)', s)
    units = int(unit_match.group(1)) if unit_match else (1 if floors > 0 else 0)
    # Sanity cap: no single permit realistically has > 200 units
    if units > 200:
        units = 1
    r["units"] = units

    # ── Features ──
    has_basement = 1 if any(k in s for k in ["ΥΠΟΓΕΙ", "ΥΠΌΓΕΙ"]) else 0
    has_pool = 1 if any(k in s for k in ["ΠΙΣΙΝ", "ΚΟΛΥΜΒ"]) else 0
    has_piloti = 1 if "ΠΥΛΩΤ" in s else 0
    has_attic = 1 if any(k in s for k in ["ΣΟΦΙΤΑ", "ΣΟΦΊΤΑ"]) else 0
    r["has_basement"] = has_basement
    r["has_pool"] = has_pool

    is_zero_cement = (
        r["construction"] in ("Fencing", "Demolition") or
        r["use"] == "Energy" or
        (any(k in s for k in ["ΘΕΡΜΟΜΟΝΩΣ", "ΕΞΟΙΚΟΝΟΜ", "ΚΟΥΦΩΜΑ", "ΧΡΩΜΑΤΙΣΜ", "ΒΑΨΙΜΟ",
                                "ΚΟΠΗ ΔΕΝΔΡ", "ΑΝΤΛΙ", "ΚΛΙΜΑΤΙΣ", "ΑΝΕΛΚΥΣΤΗΡ", "ΑΣΑΝΣΕΡ",
                                "ΗΛΕΚΤΡΟΛΟΓ", "ΥΔΡΑΥΛΙΚ", "ΜΟΝΩΣ", "ΑΔΕΙΑ ΛΕΙΤΟΥΡΓ",
                                "ΠΙΝΑΚΙΔ", "ΤΕΝΤ", "ΣΤΕΓΑΣΤΡ",
                                "Φ/Β", "ΦΩΤΟΒΟΛΤΑΪΚ", "ΦΩΤΟΒΟΛΤΑ"]) and
         r["construction"] != "New Build")
    )

    if is_zero_cement:
        r["cement_tonnes"] = 0.0
        r["cement_source"] = "zero (non-structural)"
        return r

    # ── Floor Area Estimation ──
    if units > 1:
        est_area = units * 85
    elif floors >= 4:
        est_area = floors * 110
    elif floors == 3:
        est_area = 300
    elif floors == 2:
        est_area = 200
    elif floors == 1:
        est_area = 90
    else:
        # Unknown floors — use average from ELSTAT: ~230 m²/permit in recent years
        if r["construction"] == "New Build":
            est_area = 200
        elif r["construction"] == "Addition":
            est_area = 60
        elif r["construction"] == "Renovation":
            est_area = 120
        else:
            est_area = 100

    if has_attic:
        est_area += 40
    if has_piloti:
        est_area += 70

    r["est_floor_area_m2"] = est_area

    # ── Concrete Intensity (m³ concrete per m² floor area) ──
    use_intensity = {
        "Residential": 0.15, "Tourism": 0.18, "Commercial": 0.20,
        "Industrial": 0.22, "Public": 0.20, "Other": 0.16,
    }
    intensity = use_intensity.get(r["use"], 0.16)

    # Agricultural storage/sheds: simple slab-on-grade, metal frame, much less concrete
    if any(k in s for k in ["ΑΓΡΟΤΙΚ", "ΑΠΟΘΗΚ", "ΣΤΑΣΙΣ", "ΣΤΑΒΛ", "ΘΕΡΜΟΚΗΠ"]):
        intensity = min(intensity, 0.10)

    # ── Calculate ──
    concrete_m3 = est_area * intensity

    # Basement: adds retaining walls + floor slab (~40% more concrete)
    if has_basement:
        concrete_m3 *= 1.4

    # Pool: ~5 m³ concrete per pool
    pool_count = 1
    pool_match = re.search(r'(\d+)\s*ΠΙΣΙΝ', s)
    if pool_match:
        pool_count = int(pool_match.group(1))
    if has_pool:
        concrete_m3 += 5 * pool_count

    # Construction type multiplier
    if r["construction"] == "Renovation":
        concrete_m3 *= 0.05  # Renovation: minimal structural work
    elif r["construction"] == "Change of Use":
        concrete_m3 *= 0.02  # Almost no structural
    elif r["construction"] == "Legalization":
        concrete_m3 *= 0.0   # Already built
    elif r["construction"] == "Addition":
        concrete_m3 *= 0.8   # Slightly less than full new build

    # Permit stage multiplier (pre-approvals may not proceed)
    if r["stage"] == "Small Works":
        concrete_m3 *= 0.05  # Minor works: painting, tiling, internal rearrangements
    elif r["stage"] == "Revision":
        concrete_m3 *= 0.1  # Revision = usually minor changes, already built
    elif r["stage"] == "Update":
        concrete_m3 *= 0.0  # Administrative update, no new construction

    # Cement = 300 kg per m³ of concrete = 0.3 tonnes/m³
    cement_tonnes = round(concrete_m3 * 0.3, 1)
    r["cement_tonnes"] = cement_tonnes
    r["concrete_m3"] = round(concrete_m3, 1)
    r["cement_source"] = "estimated"

    return r


# ═══════════════════════════════════════════════════════════════════════════════
#  REGEX PDF PARSER (no LLM needed)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_permit_pdf(pdf_bytes: bytes) -> dict:
    """Parse a TEE building permit PDF using regex. No LLM needed."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(p.extract_text() or "" for p in reader.pages)

    def extract(pattern, default=""):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    def extract_float(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(val)
            except ValueError:
                pass
        return None

    result = {}

    # ADA
    result["ada"] = extract(r'ΑΔΑ[:\s]*([A-ZΑ-Ω0-9]+-[A-ZΑ-Ω0-9]+)')

    # Permit type & number
    result["permit_type"] = extract(r'Τύπος Πράξης\s*(.+?)(?:\n|$)')
    result["permit_number"] = extract(r'Α/Α Πράξης\s*(\d+)')
    result["issue_date"] = extract(r'Ημ/νία έκδοσης πράξης\s*([\d/]+)')
    result["valid_until"] = extract(r'Ισχύει έως\s*([\d/]+)')

    # Project description
    result["project"] = extract(r'Περιγραφή\s*[Έέ]ργου/?[Εε]γκατάστασης\s*(.+?)(?:\n|Οδός)', "")
    if not result["project"]:
        result["project"] = extract(r'Περιγραφή\n\s*[Έέ]ργου\s*(.+?)(?:\n)')

    # Address
    result["street"] = extract(r'Οδός\s*(.+?)(?:\n|$)')
    result["city"] = extract(r'Πόλη/?Οικισμός\s*(.+?)(?:\n|$)')
    result["municipality"] = extract(r'Δήμος\s*(.+?)(?:\n|$)')
    result["municipal_unit"] = extract(r'Δημοτική Ενότητα\s*/?\s*Περιοχή\s*(.+?)(?:\n|$)')

    # Issuing authority
    result["authority"] = extract(r'(ΥΔΟΜ\s*.+?)(?:\n|$)')

    # Engineer
    result["engineer"] = extract(r'Διαχειριστής Αίτησης\s*(.+?)(?:\n|$)')
    tee_match = re.search(r'Αρ\.\s*ΤΕΕ[:\s]*(\d+)', result.get("engineer", ""))
    if not tee_match:
        tee_match = re.search(r'\(Αρ\.\s*ΤΕΕ[:\s]*(\d+)\)', result.get("engineer", ""))
    result["engineer_tee"] = tee_match.group(1) if tee_match else ""

    # Clean engineer name
    eng_name = result["engineer"]
    eng_name = re.sub(r'\(Αρ\..*?\)', '', eng_name)
    eng_name = re.sub(r',\s*ΠΤΥΧΙΟΥΧΟΣ.*', '', eng_name)
    result["engineer_name"] = eng_name.strip()

    # Owners — parse the "Στοιχεία κυρίου του έργου" table
    owners = []
    owner_section = re.search(
        r'Στοιχεία κυρίου του έργου(.+?)(?:Προγενέστερες|Στοιχεία Διαγράμματος|$)',
        text, re.DOTALL
    )
    if owner_section:
        block = owner_section.group(1)
        # Pattern: SURNAME FIRSTNAME FATHER_NAME Ιδιοκτήτης PERCENTAGE
        rows = re.findall(
            r'([A-ZΑ-Ω][a-zα-ωά-ώ]+(?:\s+[A-ZΑ-Ω][a-zα-ωά-ώ]+)*)\s+'
            r'([A-ZΑ-Ω][A-ZΑ-Ω\s]+?)\s+'
            r'([A-ZΑ-Ω][A-ZΑ-Ω]+)\s+'
            r'(?:Ιδιοκτήτης|Επικαρπωτής|Ψιλός)\s+'
            r'(\d+)',
            block
        )
        for surname, firstname, father, pct in rows:
            owners.append({
                "surname": surname.strip(),
                "first_name": firstname.strip(),
                "father_name": father.strip(),
                "pct": pct,
            })
    # Fallback: try simpler pattern
    if not owners:
        rows2 = re.findall(
            r'([Α-Ω]{2,})\s+([Α-Ω\s]{2,}?)\s+([Α-Ω]+)\s+Ιδιοκτήτης\s+(\d+)',
            text
        )
        for surname, firstname, father, pct in rows2:
            owners.append({
                "surname": surname.strip(),
                "first_name": firstname.strip(),
                "father_name": father.strip(),
                "pct": pct,
            })
    result["owners"] = owners

    # Building specs from "Στοιχεία Διαγράμματος Κάλυψης"
    result["plot_area"] = extract_float(r'Εμβαδόν οικοπέδου\s*([\d.,]+)')
    result["coverage_m2"] = extract_float(r'Εμβ\.\s*κάλυψης κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)')
    result["building_area_m2"] = extract_float(r'Εμβ\.\s*δόμησης κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)')
    result["volume_m3"] = extract_float(r'[Όό]γκος κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)')
    result["height_m"] = extract_float(r'Μέγιστο ύψος κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)')
    result["floors_actual"] = extract_float(r'Αριθμός Ορόφων.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)')

    # Coordinates
    coords = re.search(r'Συντεταγμένες\s*([\d.,\s]+)', text)
    result["coordinates"] = coords.group(1).strip()[:100] if coords else ""

    return result


def download_and_parse_permit(ada: str) -> dict:
    """Download a permit PDF from Diavgeia and parse it. No LLM needed."""
    url = f"https://diavgeia.gov.gr/doc/{ada}"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200 or "pdf" not in r.headers.get("Content-Type", ""):
        return {"error": f"HTTP {r.status_code}"}
    return parse_permit_pdf(r.content)


# ═══════════════════════════════════════════════════════════════════════════════
#  BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def process_all_permits():
    """Load all permits, classify, estimate cement, prepare for dashboard."""
    print("Loading permits...")
    df = pd.read_csv(DATA_DIR / "diavgeia_building_permits.csv")
    print(f"  {len(df)} permits loaded")

    # Filter to 2025+ only
    df["issue_date"] = pd.to_datetime(df["issue_date"])
    df = df[df["issue_date"] >= "2025-01-01"].copy()
    print(f"  {len(df)} permits from 2025 onwards")

    # Classify and estimate cement
    print("Classifying and estimating cement...")
    extra = df["subject"].apply(classify_and_estimate).apply(pd.Series)
    df = pd.concat([df, extra], axis=1)

    # Sort by cement descending
    df = df.sort_values("cement_tonnes", ascending=False).reset_index(drop=True)

    # Summary
    total_cement = df["cement_tonnes"].sum()
    print(f"\n  Total estimated cement demand: {total_cement:,.0f} tonnes")
    print(f"  Average per permit: {df['cement_tonnes'].mean():.1f} tonnes")
    print(f"  Permits with >0 cement: {len(df[df['cement_tonnes'] > 0]):,}")
    print(f"\n  By construction type:")
    for ct, grp in df.groupby("construction"):
        t = grp["cement_tonnes"].sum()
        if t > 0:
            print(f"    {ct:20s}  {len(grp):5,} permits  {t:8,.0f} tonnes")
    print(f"\n  By use:")
    for use, grp in df.groupby("use"):
        t = grp["cement_tonnes"].sum()
        if t > 0:
            print(f"    {use:20s}  {len(grp):5,} permits  {t:8,.0f} tonnes")

    # Save
    csv_path = DATA_DIR / "permits_with_cement.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  Saved → {csv_path.name}")

    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════════════════════

def generate_dashboard(df):
    """Generate the v2 dashboard."""
    print("\nGenerating dashboard...")

    # Prepare table data
    table_data = []
    for _, r in df.iterrows():
        subj = str(r["subject"])
        desc = subj.split(":", 1)[1].strip() if ":" in subj else subj
        desc = desc[:90]

        # Extract engineer info from organization (most are TEE)
        eng_match = re.search(
            r'Διαχειριστ[ήη]ς\s+Α[ιί]τησης\s*(.+?)(?:\n|$)',
            subj, re.IGNORECASE
        )

        table_data.append({
            "d": r["issue_date"].strftime("%Y-%m-%d"),
            "ada": r["ada"],
            "desc": desc,
            "stage": r.get("stage", ""),
            "con": r.get("construction", ""),
            "use": r.get("use", ""),
            "fl": int(r["floors"]) if pd.notna(r.get("floors")) and r.get("floors", 0) > 0 else 0,
            "bsmt": int(r.get("has_basement", 0)) if pd.notna(r.get("has_basement")) else 0,
            "pool": int(r.get("has_pool", 0)) if pd.notna(r.get("has_pool")) else 0,
            "cem": float(r.get("cement_tonnes", 0)) if pd.notna(r.get("cement_tonnes")) else 0,
            "area": int(r.get("est_floor_area_m2", 0)) if pd.notna(r.get("est_floor_area_m2")) and r.get("est_floor_area_m2", 0) else 0,
            "eng": str(r.get("organization_name", "")),
        })

    # KPIs
    total = len(df)
    total_cement = df["cement_tonnes"].sum()
    new_builds = len(df[df["construction"] == "New Build"])
    high_cement = len(df[df["cement_tonnes"] >= 15])
    avg_cement = df[df["cement_tonnes"] > 0]["cement_tonnes"].mean()
    date_min = df["issue_date"].min().strftime("%Y-%m-%d")
    date_max = df["issue_date"].max().strftime("%Y-%m-%d")

    # Weekly cement demand chart
    weekly = df.groupby(df["issue_date"].dt.to_period("W").astype(str)).agg(
        permits=("ada", "count"),
        cement=("cement_tonnes", "sum"),
    ).reset_index()
    w_labels = weekly["issue_date"].tolist()
    w_cement = [round(x, 1) for x in weekly["cement"].tolist()]
    w_permits = weekly["permits"].tolist()

    # Cement by use
    by_use = df.groupby("use")["cement_tonnes"].sum().sort_values(ascending=False)
    use_labels = by_use.index.tolist()
    use_values = [round(x, 1) for x in by_use.values.tolist()]

    # Cement by construction type
    by_con = df.groupby("construction")["cement_tonnes"].sum().sort_values(ascending=False)
    con_labels = by_con.index.tolist()
    con_values = [round(x, 1) for x in by_con.values.tolist()]

    # Pre-parsed detail data for the 10 permits we already extracted
    detail_json = "null"
    detail_path = DATA_DIR / "enriched_permits_with_contacts.json"
    if detail_path.exists():
        with open(detail_path) as f:
            detail_data = json.load(f)
        # Key by ADA
        detail_map = {}
        for p in detail_data:
            ada = p.get("ada", "")
            if ada:
                detail_map[ada] = p
        detail_json = json.dumps(detail_map, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Greek Construction — Cement Demand Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg:#0b0f19;--card:#111827;--card2:#1a2332;--border:#1e293b;
  --text:#e2e8f0;--muted:#94a3b8;--dim:#64748b;
  --blue:#3b82f6;--green:#10b981;--orange:#f59e0b;
  --red:#ef4444;--purple:#8b5cf6;--cyan:#06b6d4;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text)}}
.hdr{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);padding:2rem 2rem 1.5rem;border-bottom:1px solid var(--border)}}
.hdr-in{{max-width:1400px;margin:0 auto}}
.hdr h1{{font-size:1.5rem;font-weight:800}} .hdr h1 span{{color:var(--orange)}}
.hdr .sub{{color:var(--muted);font-size:0.82rem;margin-top:0.3rem}}
.hdr .sub b{{color:var(--text)}}
.ctr{{max-width:1400px;margin:0 auto;padding:1.25rem}}
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:0.75rem;margin-bottom:1.25rem}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1rem;text-align:center}}
.kpi .n{{font-size:1.5rem;font-weight:800}} .kpi .l{{font-size:0.62rem;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-top:0.15rem}}
.charts{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:1rem;margin-bottom:1.25rem}}
@media(max-width:900px){{.charts{{grid-template-columns:1fr}}}}
.ch{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.1rem}}
.ch h3{{font-size:0.72rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--dim);margin-bottom:0.8rem}}
.tbl-sec{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.1rem;overflow:hidden}}
.tbl-bar{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.75rem}}
.tbl-bar h2{{font-size:0.95rem;font-weight:700}}
.flt{{display:flex;gap:0.4rem;flex-wrap:wrap;align-items:center}}
.flt select,.flt input{{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:0.35rem 0.5rem;font-size:0.72rem;outline:none}}
.flt select:focus,.flt input:focus{{border-color:var(--blue)}}
.flt label{{font-size:0.62rem;color:var(--muted)}}
.btn{{background:var(--blue);color:#fff;border:none;border-radius:5px;padding:0.35rem 0.8rem;font-size:0.72rem;font-weight:600;cursor:pointer}}
.btn:hover{{opacity:0.9}}
.tw{{overflow-x:auto;max-height:70vh;overflow-y:auto}}
table{{width:100%;border-collapse:collapse;font-size:0.73rem;white-space:nowrap}}
thead{{position:sticky;top:0;z-index:10}}
th{{background:var(--card2);color:var(--muted);font-weight:600;text-transform:uppercase;font-size:0.62rem;letter-spacing:0.05em;padding:0.55rem 0.5rem;text-align:left;border-bottom:2px solid var(--border);cursor:pointer;user-select:none}}
th:hover{{color:var(--text)}}
td{{padding:0.5rem 0.5rem;border-bottom:1px solid rgba(30,41,59,0.5)}}
tr:hover{{background:rgba(59,130,246,0.04)}}
tr.expandable{{cursor:pointer}}
a{{color:var(--blue);text-decoration:none}} a:hover{{text-decoration:underline}}
.cem-bar{{display:inline-block;height:12px;border-radius:2px;vertical-align:middle;margin-right:4px}}
.pager{{display:flex;gap:3px;align-items:center}}
.pager button{{background:var(--bg);color:var(--muted);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:0.68rem;cursor:pointer}}
.pager button:hover{{color:var(--text);border-color:var(--blue)}}
.pager button:disabled{{opacity:0.3;cursor:default}}
.pager button.act{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.pager span{{font-size:0.68rem;color:var(--dim);padding:0 3px}}
.cnt{{font-size:0.72rem;color:var(--muted)}}
.pg-row{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-top:0.5rem}}
/* Detail card overlay */
.detail-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:100;overflow-y:auto;padding:2rem}}
.detail-overlay.open{{display:flex;justify-content:center;align-items:flex-start}}
.detail-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.75rem;max-width:900px;width:100%;position:relative}}
.detail-card .close{{position:absolute;top:1rem;right:1rem;background:none;border:none;color:var(--muted);font-size:1.2rem;cursor:pointer}}
.detail-card .close:hover{{color:var(--text)}}
.detail-card h2{{font-size:1rem;font-weight:700;margin-bottom:0.25rem}}
.detail-card .meta{{font-size:0.75rem;color:var(--muted);margin-bottom:1rem}}
.dg{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.25rem;font-size:0.78rem}}
@media(max-width:700px){{.dg{{grid-template-columns:1fr}}}}
.ds h4{{font-size:0.62rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--dim);margin-bottom:0.5rem;border-bottom:1px solid var(--border);padding-bottom:0.2rem}}
.ds .r{{display:flex;gap:0.4rem;margin-bottom:0.25rem}}
.ds .k{{color:var(--muted);min-width:65px;flex-shrink:0}}
.ds .v{{color:var(--text);font-weight:500}}
.phone-big{{color:var(--green);font-weight:700;font-size:0.9rem}}
.loading{{color:var(--dim);font-style:italic;padding:1rem;text-align:center}}
.ft{{text-align:center;padding:1.5rem;color:var(--dim);font-size:0.68rem;border-top:1px solid var(--border);margin-top:1.5rem}}
</style>
</head>
<body>
<div class="hdr"><div class="hdr-in">
  <h1>Cement Demand Intelligence <span>// Greece</span></h1>
  <div class="sub"><b>{total:,}</b> permits, <b>{date_min}</b> to <b>{date_max}</b> | Est. <b>{total_cement:,.0f} tonnes</b> cement demand | Source: Diavgeia (real-time)</div>
</div></div>
<div class="ctr">
  <div class="kpi-row">
    <div class="kpi"><div class="n" style="color:var(--orange)">{total_cement:,.0f}t</div><div class="l">Total Cement Demand</div></div>
    <div class="kpi"><div class="n" style="color:var(--text)">{total:,}</div><div class="l">Total Permits</div></div>
    <div class="kpi"><div class="n" style="color:var(--green)">{new_builds:,}</div><div class="l">New Builds</div></div>
    <div class="kpi"><div class="n" style="color:var(--red)">{high_cement:,}</div><div class="l">&ge;15t Cement</div></div>
    <div class="kpi"><div class="n" style="color:var(--cyan)">{avg_cement:.1f}t</div><div class="l">Avg per Permit</div></div>
  </div>
  <div class="charts">
    <div class="ch"><h3>Weekly Cement Demand (tonnes)</h3><canvas id="c1" height="85"></canvas></div>
    <div class="ch"><h3>Cement by Use</h3><canvas id="c2" height="130"></canvas></div>
    <div class="ch"><h3>Cement by Type</h3><canvas id="c3" height="130"></canvas></div>
  </div>
  <div class="tbl-sec">
    <div class="tbl-bar">
      <h2>Permit Register</h2>
      <div class="flt">
        <div><label>Min Cement</label><br><select id="fCem" onchange="af()"><option value="0">All</option><option value="1">&ge;1t</option><option value="5">&ge;5t</option><option value="15">&ge;15t</option><option value="30">&ge;30t</option></select></div>
        <div><label>Use</label><br><select id="fUse" onchange="af()"><option value="">All</option><option>Residential</option><option>Tourism</option><option>Commercial</option><option>Industrial</option><option>Public</option><option>Energy</option></select></div>
        <div><label>Construction</label><br><select id="fCon" onchange="af()"><option value="">All</option><option>New Build</option><option>Addition</option><option>Renovation</option><option>Change of Use</option></select></div>
        <div><label>Stage</label><br><select id="fStg" onchange="af()"><option value="">All</option><option>Full Permit</option><option>Pre-approval</option><option>Small Works</option></select></div>
        <div><label>Search</label><br><input id="fQ" type="text" placeholder="keyword..." oninput="af()" style="width:120px"></div>
        <div style="padding-top:13px"><button class="btn" onclick="xCSV()">Export CSV</button></div>
      </div>
    </div>
    <div class="pg-row"><span class="cnt" id="cnt"></span><div class="pager" id="pg"></div></div>
    <div class="tw">
      <table><thead><tr>
        <th onclick="st(0)">Date</th>
        <th onclick="st(1)">Cement (t)</th>
        <th onclick="st(2)">Use</th>
        <th onclick="st(3)">Stage</th>
        <th onclick="st(4)">Construction</th>
        <th onclick="st(5)" style="min-width:180px">Description</th>
        <th onclick="st(6)">ADA</th>
      </tr></thead><tbody id="tb"></tbody></table>
    </div>
    <div class="pg-row"><span class="cnt" id="cnt2"></span><div class="pager" id="pg2"></div></div>
  </div>
</div>
<!-- Detail overlay -->
<div class="detail-overlay" id="overlay" onclick="if(event.target===this)closeDetail()">
  <div class="detail-card" id="detailCard"></div>
</div>
<div class="ft">Cement estimation model: floor area heuristic &times; concrete intensity (0.15&ndash;0.22 m&sup3;/m&sup2;) &times; 300 kg cement/m&sup3; concrete | Data: opendata.diavgeia.gov.gr</div>
<script>
const D={json.dumps(table_data,ensure_ascii=False)};
const PRE={detail_json};
let F=[...D],sc=1,sa=false,pg=0;
const PS=50;
const maxCem=Math.max(...D.map(r=>r.cem));

function cemBar(v){{
  if(v<=0)return'<span style="color:var(--dim)">0</span>';
  const w=Math.min(Math.max(v/maxCem*80,4),80);
  const c=v>=30?'var(--red)':v>=15?'var(--orange)':v>=5?'var(--blue)':'var(--dim)';
  return'<span class="cem-bar" style="width:'+w+'px;background:'+c+'"></span><b style="color:'+c+'">'+v.toFixed(1)+'</b>';
}}

function rt(){{
  const s=pg*PS,sl=F.slice(s,s+PS);
  const h=[];
  for(const r of sl){{
    h.push('<tr class="expandable" onclick="openDetail(\\''+r.ada+'\\',this)"><td>'+r.d+'</td><td>'+cemBar(r.cem)+'</td><td>'+r.use+'</td><td>'+r.stage+'</td><td>'+r.con+'</td><td style="white-space:normal;max-width:300px">'+r.desc+'</td><td><a href="https://diavgeia.gov.gr/decision/view/'+r.ada+'" target="_blank" onclick="event.stopPropagation()">'+r.ada+'</a></td></tr>');
  }}
  document.getElementById('tb').innerHTML=h.join('');
  const t=F.length,pages=Math.ceil(t/PS);
  const info=t===0?'No matches':'Showing '+(s+1)+'\\u2013'+Math.min(s+PS,t)+' of '+t.toLocaleString();
  ['cnt','cnt2'].forEach(id=>document.getElementById(id).textContent=info);
  ['pg','pg2'].forEach(id=>{{
    const el=document.getElementById(id);
    if(pages<=1){{el.innerHTML='';return}}
    let h='<button '+(pg===0?'disabled':'')+' onclick="gp('+(pg-1)+')">Prev</button>';
    let s2=Math.max(0,pg-3),e=Math.min(pages,s2+7);if(e-s2<7)s2=Math.max(0,e-7);
    if(s2>0)h+='<button onclick="gp(0)">1</button><span>...</span>';
    for(let p=s2;p<e;p++)h+='<button class="'+(p===pg?'act':'')+'" onclick="gp('+p+')">'+(p+1)+'</button>';
    if(e<pages)h+='<span>...</span><button onclick="gp('+(pages-1)+')">'+pages+'</button>';
    h+='<button '+(pg>=pages-1?'disabled':'')+' onclick="gp('+(pg+1)+')">Next</button>';
    el.innerHTML=h;
  }});
}}
function gp(p){{pg=p;rt()}}
function af(){{
  const cm=+document.getElementById('fCem').value;
  const use=document.getElementById('fUse').value;
  const con=document.getElementById('fCon').value;
  const stg=document.getElementById('fStg').value;
  const q=document.getElementById('fQ').value.toLowerCase();
  F=D.filter(r=>{{
    if(r.cem<cm)return false;
    if(use&&r.use!==use)return false;
    if(con&&r.con!==con)return false;
    if(stg&&r.stage!==stg)return false;
    if(q&&!r.desc.toLowerCase().includes(q)&&!r.ada.toLowerCase().includes(q))return false;
    return true;
  }});
  pg=0;rt();
}}
function st(c){{
  if(sc===c)sa=!sa;else{{sc=c;sa=c===1?false:true}}
  const k=['d','cem','use','stage','con','desc','ada'][c];
  F.sort((a,b)=>{{
    let va=a[k],vb=b[k];
    if(typeof va==='number')return sa?va-vb:vb-va;
    return String(va).localeCompare(String(vb))*(sa?1:-1);
  }});
  pg=0;rt();
}}
function xCSV(){{
  const hd=['Date','Cement_t','Use','Stage','Construction','Description','ADA'];
  const rows=F.map(r=>[r.d,r.cem,r.use,r.stage,r.con,'"'+r.desc.replace(/"/g,'""')+'"',r.ada]);
  const csv=[hd.join(','),...rows.map(r=>r.join(','))].join('\\n');
  const b=new Blob(['\\uFEFF'+csv],{{type:'text/csv;charset=utf-8;'}});
  const u=URL.createObjectURL(b);
  const a=document.createElement('a');a.href=u;a.download='cement_permits_'+new Date().toISOString().slice(0,10)+'.csv';
  a.click();URL.revokeObjectURL(u);
}}

// Detail card
function openDetail(ada){{
  const ov=document.getElementById('overlay');
  const card=document.getElementById('detailCard');
  const row=D.find(r=>r.ada===ada);
  if(!row)return;

  // Check if we have pre-parsed detail
  const pre=PRE&&PRE[ada];

  let html='<button class="close" onclick="closeDetail()">&times;</button>';
  html+='<h2>'+row.desc+'</h2>';
  html+='<div class="meta"><a href="https://diavgeia.gov.gr/decision/view/'+ada+'" target="_blank">ADA: '+ada+'</a> | '+row.d+' | Est. cement: <b style="color:var(--orange)">'+row.cem.toFixed(1)+' tonnes</b> | '+row.area+' m&sup2; est. floor area</div>';

  if(pre){{
    // We have extracted PDF data
    const owners=pre.owners||[];
    let ownHtml='';
    for(const o of owners){{
      ownHtml+='<div class="r"><span class="v" style="font-weight:700">'+((o.name||o.surname||"")+" "+(o.first_name||"")).trim()+'</span></div>';
      if(o.father||o.pct)ownHtml+='<div class="r"><span class="k">Father</span><span class="v">'+(o.father||'-')+'</span><span class="k" style="margin-left:8px">Own%</span><span class="v">'+(o.pct||'-')+'</span></div>';
    }}
    const addr=pre.address||{{}};
    const specs=pre.specs||{{}};
    const eng=pre.engineer||{{}};
    const ph=pre.engineer_phone;
    const phHtml=ph?'<a class="phone-big" href="tel:+30'+ph.replace(/\\s/g,'')+'">'+ph+'</a> <span style="font-size:0.6rem;color:var(--dim)">via '+(pre.engineer_source||'')+'</span>':'<span style="color:var(--dim)">Not in directory</span>';

    html+='<div class="dg">';
    html+='<div class="ds"><h4>Owners &amp; Location</h4>'+ownHtml;
    html+='<div style="margin-top:0.6rem"><div class="r"><span class="k">Address</span><span class="v">'+[addr.street,addr.number,addr.city_village,addr.municipality].filter(Boolean).join(', ')+'</span></div>';
    html+='<div class="r"><span class="k">Plot</span><span class="v">'+(pre.plot&&pre.plot.area_m2?pre.plot.area_m2+' m&sup2;':'-')+'</span></div></div></div>';
    html+='<div class="ds"><h4>Building Specs</h4>';
    html+='<div class="r"><span class="k">Floors</span><span class="v">'+(specs.floors||'-')+'</span></div>';
    html+='<div class="r"><span class="k">Area</span><span class="v">'+(specs.building_area_m2||'-')+' m&sup2;</span></div>';
    html+='<div class="r"><span class="k">Coverage</span><span class="v">'+(specs.building_coverage_m2||'-')+' m&sup2;</span></div>';
    html+='<div class="r"><span class="k">Volume</span><span class="v">'+(specs.volume_m3||'-')+' m&sup3;</span></div>';
    html+='<div class="r"><span class="k">Height</span><span class="v">'+(specs.max_height_m||'-')+' m</span></div>';
    html+='<div class="r"><span class="k">Valid</span><span class="v">'+(pre.issue_date||'?')+' &rarr; '+(pre.valid_until||'?')+'</span></div></div>';
    html+='<div class="ds"><h4>Engineer Contact</h4>';
    html+='<div class="r"><span class="k">Name</span><span class="v">'+(eng.name||'-')+'</span></div>';
    html+='<div class="r"><span class="k">TEE#</span><span class="v">'+(eng.tee_number||'-')+'</span></div>';
    html+='<div class="r"><span class="k">Phone</span><span class="v">'+phHtml+'</span></div>';
    if(pre.engineer_address)html+='<div class="r"><span class="k">Addr</span><span class="v">'+pre.engineer_address+'</span></div>';
    html+='</div></div>';
  }} else {{
    // No pre-parsed data — show estimation basis + link to PDF
    html+='<div class="dg">';
    html+='<div class="ds"><h4>Estimation Basis</h4>';
    html+='<div class="r"><span class="k">Floors</span><span class="v">'+(row.fl||'unknown')+'</span></div>';
    html+='<div class="r"><span class="k">Basement</span><span class="v">'+(row.bsmt?'Yes':'No')+'</span></div>';
    html+='<div class="r"><span class="k">Pool</span><span class="v">'+(row.pool?'Yes':'No')+'</span></div>';
    html+='<div class="r"><span class="k">Est. area</span><span class="v">'+row.area+' m&sup2;</span></div>';
    html+='<div class="r"><span class="k">Cement</span><span class="v" style="color:var(--orange)">'+row.cem.toFixed(1)+' tonnes</span></div></div>';
    html+='<div class="ds"><h4>Permit Info</h4>';
    html+='<div class="r"><span class="k">Stage</span><span class="v">'+row.stage+'</span></div>';
    html+='<div class="r"><span class="k">Type</span><span class="v">'+row.con+'</span></div>';
    html+='<div class="r"><span class="k">Use</span><span class="v">'+row.use+'</span></div></div>';
    html+='<div class="ds"><h4>Full Details</h4>';
    html+='<p style="color:var(--muted);font-size:0.78rem">Full owner, engineer &amp; specs data available by parsing the official PDF.</p>';
    html+='<a class="btn" href="https://diavgeia.gov.gr/doc/'+ada+'" target="_blank" style="display:inline-block;margin-top:0.5rem">Download PDF</a></div>';
    html+='</div>';
  }}

  card.innerHTML=html;
  ov.classList.add('open');
}}
function closeDetail(){{document.getElementById('overlay').classList.remove('open')}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeDetail()}});

rt();
Chart.defaults.color='#94a3b8';Chart.defaults.borderColor='#1e293b';
new Chart(document.getElementById('c1'),{{type:'bar',data:{{labels:{json.dumps(w_labels)},datasets:[
  {{label:'Cement (t)',data:{json.dumps(w_cement)},backgroundColor:'rgba(245,158,11,0.6)',borderRadius:3}},
]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{font:{{size:9}},maxRotation:45}}}},y:{{beginAtZero:true,ticks:{{callback:v=>v+'t'}}}}}}}}}});
new Chart(document.getElementById('c2'),{{type:'doughnut',data:{{labels:{json.dumps(use_labels)},datasets:[{{data:{json.dumps(use_values)},backgroundColor:['#3b82f6','#f59e0b','#10b981','#8b5cf6','#06b6d4','#ef4444','#64748b'],borderWidth:0}}]}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:9}}}}}}}}}}}});
new Chart(document.getElementById('c3'),{{type:'doughnut',data:{{labels:{json.dumps(con_labels)},datasets:[{{data:{json.dumps(con_values)},backgroundColor:['#10b981','#3b82f6','#f59e0b','#8b5cf6','#06b6d4','#ef4444','#64748b','#374151'],borderWidth:0}}]}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:9}}}}}}}}}}}});
</script>
</body>
</html>"""

    out = DATA_DIR / "titan_demo.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Saved → {out} ({out.stat().st_size:,} bytes)")
    return out


if __name__ == "__main__":
    df = process_all_permits()
    path = generate_dashboard(df)
    print(f"\n  Open: file://{path.resolve()}")
