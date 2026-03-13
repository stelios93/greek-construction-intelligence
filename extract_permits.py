#!/usr/bin/env python3
"""
Permit PDF Extractor
====================
Downloads building permit PDFs from Diavgeia and extracts structured info
using PyPDF2 for text extraction + GPT for structured parsing.

Extracts:
- Owner/developer name(s)
- Owner address / contact info
- Architect/engineer name + TEE registration
- Property address (street, city, municipality, region)
- Plot coordinates (from satellite map page)
- Building description (floors, surface, volume, use)
- Permit metadata (ADA, date, validity, ΥΔΟΜ office)
"""

import json
import os
import re
import time
from pathlib import Path
from io import BytesIO

import requests
from PyPDF2 import PdfReader
from openai import OpenAI

DATA_DIR = Path(__file__).parent / "data"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

EXTRACTION_PROMPT = """You are an expert at reading Greek building permit documents (Οικοδομικές Άδειες).

Extract ALL of the following fields from this permit document. Return ONLY valid JSON, no markdown.

{
  "ada": "the ADA code (ΑΔΑ)",
  "permit_type": "e.g. Οικοδομική Άδεια, Προέγκριση, Έγκριση Εργασιών Μικρής Κλίμακας",
  "permit_number": "Α/Α Πράξης number",
  "issue_date": "DD/MM/YYYY",
  "valid_until": "DD/MM/YYYY",
  "issuing_authority": "e.g. ΥΔΟΜ ΡΟΔΟΥ",

  "project_description": "full description of the work (Περιγραφή Έργου)",

  "owners": [
    {
      "surname": "",
      "first_name": "",
      "father_name": "",
      "role": "e.g. Ιδιοκτήτης (Owner)",
      "ownership_pct": "e.g. 50",
      "ownership_type": "e.g. Πλήρης κυριότητα"
    }
  ],

  "property_address": {
    "street": "",
    "number": "",
    "city_village": "",
    "municipality": "",
    "municipal_unit": "",
    "region": "",
    "postal_code": ""
  },

  "plot_details": {
    "area_m2": "",
    "kaek": "cadastral code if present",
    "coordinates": "if GPS/EGSA coordinates are present"
  },

  "building_specs": {
    "building_coverage_m2": "",
    "building_area_m2": "",
    "volume_m3": "",
    "max_height_m": "",
    "floors": "",
    "parking_spaces": "",
    "building_use": "e.g. Κατοικία, Κατάστημα, Ξενοδοχείο"
  },

  "engineer": {
    "name": "",
    "tee_number": "",
    "specialty": ""
  },

  "developer_contact": {
    "name": "owner or developer's full name - the person building",
    "phone": "if found anywhere in the document",
    "email": "if found",
    "address": "owner's personal address if different from property"
  }
}

IMPORTANT:
- Extract EXACT values from the document, do not guess
- For owners, list ALL owners found in the "Στοιχεία κυρίου του έργου" table
- The engineer is in "Διαχειριστής Αίτησης" or "ΟΜΑΔΑ ΜΕΛΕΤΗΣ ΕΡΓΟΥ"
- Property address comes from Οδός, Πόλη/Οικισμός, Δήμος fields
- Building specs from "Στοιχεία Διαγράμματος Κάλυψης" table
- If a field is not found, use null
- Return ONLY the JSON object, nothing else
"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using PyPDF2."""
    reader = PdfReader(pdf_path)
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(text_parts)


def extract_with_gpt(text: str, ada: str) -> dict:
    """Send extracted text to GPT for structured extraction."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Truncate if very long (GPT context limit)
    if len(text) > 15000:
        text = text[:15000]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Here is the text extracted from building permit {ada}:\n\n{text}"},
        ],
        temperature=0,
        max_tokens=2000,
    )

    content = response.choices[0].message.content.strip()

    # Clean up markdown fences if present
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"    Warning: GPT response not valid JSON for {ada}")
        return {"raw_response": content, "ada": ada}


def process_permit(pdf_path: str, ada: str) -> dict:
    """Full pipeline: PDF → text → GPT → structured data."""
    print(f"\n  Processing {ada}...")

    # Step 1: Extract text
    text = extract_text_from_pdf(pdf_path)
    print(f"    Extracted {len(text):,} chars from {Path(pdf_path).stat().st_size:,} byte PDF")

    # Step 2: Send to GPT
    result = extract_with_gpt(text, ada)
    print(f"    Extracted: {len(result.get('owners', []))} owners, "
          f"property at {result.get('property_address', {}).get('city_village', '?')}, "
          f"{result.get('property_address', {}).get('municipality', '?')}")

    return result


def run_batch():
    """Process all downloaded permit PDFs."""
    print("=" * 60)
    print("  PERMIT PDF EXTRACTION PIPELINE")
    print("=" * 60)

    # Find all permit PDFs
    pdfs = sorted(DATA_DIR.glob("permit_*.pdf"))
    print(f"\n  Found {len(pdfs)} permit PDFs to process")

    results = []
    for pdf_path in pdfs:
        ada = pdf_path.stem.replace("permit_", "")
        try:
            result = process_permit(str(pdf_path), ada)
            results.append(result)
        except Exception as e:
            print(f"    ERROR processing {ada}: {e}")
        time.sleep(1)  # Rate limit

    # Save results
    json_path = DATA_DIR / "extracted_permits.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(results)} extracted permits → {json_path.name}")

    # Print summary table
    print("\n" + "=" * 120)
    print(f"  {'ADA':<20} {'OWNERS':<35} {'LOCATION':<30} {'PROJECT':<35}")
    print("  " + "-" * 116)
    for r in results:
        ada = (r.get("ada") or "?")[:18]
        owners = r.get("owners", [])
        owner_str = ", ".join(
            f"{o.get('surname', '')} {o.get('first_name', '')}"
            for o in owners[:2]
        )[:33] if owners else "—"

        addr = r.get("property_address", {})
        loc = f"{addr.get('city_village', '?')}, {addr.get('municipality', '?')}"[:28]

        desc = r.get("project_description", "?")[:33]

        print(f"  {ada:<20} {owner_str:<35} {loc:<30} {desc:<35}")

    # Developer contact summary
    print("\n  DEVELOPER CONTACTS:")
    print("  " + "-" * 80)
    for r in results:
        contact = r.get("developer_contact", {})
        owners = r.get("owners", [])
        name = contact.get("name") or (
            f"{owners[0].get('surname', '')} {owners[0].get('first_name', '')}" if owners else "?"
        )
        eng = r.get("engineer", {})
        eng_name = eng.get("name", "?")
        eng_tee = eng.get("tee_number", "")

        addr = r.get("property_address", {})
        loc = f"{addr.get('street', '')} {addr.get('number', '')}, {addr.get('city_village', '')}, {addr.get('municipality', '')}"

        print(f"  Owner: {name}")
        print(f"    Property: {loc}")
        print(f"    Engineer: {eng_name} (TEE: {eng_tee})")
        print(f"    Phone: {contact.get('phone', '—')}  Email: {contact.get('email', '—')}")
        specs = r.get("building_specs", {})
        print(f"    Build: {specs.get('floors', '?')} floors, {specs.get('building_area_m2', '?')} m², {specs.get('volume_m3', '?')} m³")
        print()

    return results


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        exit(1)
    run_batch()
