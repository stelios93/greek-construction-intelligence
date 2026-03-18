#!/usr/bin/env python3
"""
Batch PDF Download + Parse + Geocode + Map
===========================================
1. Downloads permit PDFs from Diavgeia (permits since Jan 1 2026 with cement > 0)
2. Parses each PDF with regex (no LLM) for address, engineer, area
3. Geocodes addresses via Nominatim (cached by municipality)
4. Generates a Leaflet.js map with cement demand intensity
"""

import json
import os
import re
import time
import hashlib
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from io import BytesIO
from PyPDF2 import PdfReader

DATA_DIR = Path(__file__).parent / "data"
PDF_CACHE_DIR = DATA_DIR / "pdf_cache"
PDF_CACHE_DIR.mkdir(exist_ok=True)

GEOCODE_CACHE_FILE = DATA_DIR / "geocode_cache.json"

# ── Herakles plant locations (cement + ready-mix concrete) ──
HERACLES_PLANTS = [
    # Cement plants
    {"name": "Herakles Μιλάκι (Τσιμέντο)", "lat": 39.3600, "lng": 22.9300, "type": "Cement"},
    {"name": "Herakles Αλιβέρι (Τσιμέντο)", "lat": 38.3800, "lng": 23.9800, "type": "Cement"},
    # Ready-mix concrete — Αττική
    {"name": "Herakles Ελευσίνα", "lat": 38.0418, "lng": 23.5422, "type": "RMC"},
    {"name": "Herakles Ασπρόπυργος", "lat": 38.0597, "lng": 23.5865, "type": "RMC"},
    {"name": "Herakles Περισσός", "lat": 38.0520, "lng": 23.7538, "type": "RMC"},
    {"name": "Herakles Γέρακας", "lat": 38.0231, "lng": 23.8571, "type": "RMC"},
    {"name": "Herakles Κορωπί", "lat": 37.9012, "lng": 23.8767, "type": "RMC"},
    {"name": "Herakles Πειραιάς", "lat": 37.9435, "lng": 23.6443, "type": "RMC"},
    {"name": "Herakles Μοσχάτο", "lat": 37.9500, "lng": 23.7000, "type": "RMC"},
    {"name": "Herakles Παλλήνη", "lat": 38.0050, "lng": 23.8800, "type": "RMC"},
    # Ready-mix — Rest of Greece
    {"name": "Herakles Θεσσαλονίκη", "lat": 40.6401, "lng": 22.9444, "type": "RMC"},
    {"name": "Herakles Σίνδος", "lat": 40.6667, "lng": 22.7833, "type": "RMC"},
    {"name": "Herakles Λάρισα", "lat": 39.6372, "lng": 22.4202, "type": "RMC"},
    {"name": "Herakles Βόλος", "lat": 39.3621, "lng": 22.9420, "type": "RMC"},
    {"name": "Herakles Πάτρα", "lat": 38.2466, "lng": 21.7346, "type": "RMC"},
    {"name": "Herakles Κόρινθος", "lat": 37.9409, "lng": 22.9319, "type": "RMC"},
    {"name": "Herakles Χαλκίδα", "lat": 38.4633, "lng": 23.5981, "type": "RMC"},
    {"name": "Herakles Λαμία", "lat": 38.8990, "lng": 22.4341, "type": "RMC"},
    {"name": "Herakles Ιωάννινα", "lat": 39.6650, "lng": 20.8537, "type": "RMC"},
    {"name": "Herakles Ηράκλειο Κρήτης", "lat": 35.3387, "lng": 25.1442, "type": "RMC"},
    {"name": "Herakles Χανιά", "lat": 35.5138, "lng": 24.0180, "type": "RMC"},
    {"name": "Herakles Καβάλα", "lat": 40.9396, "lng": 24.4014, "type": "RMC"},
    {"name": "Herakles Αλεξανδρούπολη", "lat": 40.8447, "lng": 25.8744, "type": "RMC"},
]

# ── Municipality → Περιφερειακή Ενότητα ──
MUNICIPALITY_TO_PE = {
    # Αττική - Κεντρικός Τομέας
    "ΑΘΗΝΑΙΩΝ": "ΠΕ Αθηνών", "ΑΘΗΝΩΝ": "ΠΕ Αθηνών", "ΖΩΓΡΑΦΟΥ": "ΠΕ Αθηνών",
    "ΔΑΦΝΗΣ-ΥΜΗΤΤΟΥ": "ΠΕ Αθηνών", "ΒΥΡΩΝΟΣ": "ΠΕ Αθηνών", "ΗΛΙΟΥΠΟΛΕΩΣ": "ΠΕ Αθηνών",
    "ΓΑΛΑΤΣΙΟΥ": "ΠΕ Αθηνών", "ΦΙΛΑΔΕΛΦΕΙΑΣ-ΧΑΛΚΗΔΟΝΟΣ": "ΠΕ Αθηνών",
    # Αττική - Νότιος Τομέας
    "ΠΑΛΑΙΟΥ ΦΑΛΗΡΟΥ": "ΠΕ Νοτίου Τομέα Αθηνών", "ΓΛΥΦΑΔΑΣ": "ΠΕ Νοτίου Τομέα Αθηνών",
    "ΑΛΙΜΟΥ": "ΠΕ Νοτίου Τομέα Αθηνών", "ΚΑΛΛΙΘΕΑΣ": "ΠΕ Νοτίου Τομέα Αθηνών",
    "ΜΟΣΧΑΤΟΥ-ΤΑΥΡΟΥ": "ΠΕ Νοτίου Τομέα Αθηνών", "ΝΕΑΣ ΣΜΥΡΝΗΣ": "ΠΕ Νοτίου Τομέα Αθηνών",
    "ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ": "ΠΕ Νοτίου Τομέα Αθηνών", "ΒΑΡΗΣ-ΒΟΥΛΑΣ-ΒΟΥΛΙΑΓΜΕΝΗΣ": "ΠΕ Νοτίου Τομέα Αθηνών",
    "ΕΛΛΗΝΙΚΟΥ-ΑΡΓΥΡΟΥΠΟΛΗΣ": "ΠΕ Νοτίου Τομέα Αθηνών",
    # Αττική - Δυτικός Τομέας
    "ΠΕΡΙΣΤΕΡΙΟΥ": "ΠΕ Δυτικού Τομέα Αθηνών", "ΙΛΙΟΥ": "ΠΕ Δυτικού Τομέα Αθηνών",
    "ΧΑΙΔΑΡΙΟΥ": "ΠΕ Δυτικού Τομέα Αθηνών", "ΑΙΓΑΛΕΩ": "ΠΕ Δυτικού Τομέα Αθηνών",
    "ΠΕΤΡΟΥΠΟΛΕΩΣ": "ΠΕ Δυτικού Τομέα Αθηνών", "ΑΓΙΑΣ ΒΑΡΒΑΡΑΣ": "ΠΕ Δυτικού Τομέα Αθηνών",
    "ΑΓΙΩΝ ΑΝΑΡΓΥΡΩΝ-ΚΑΜΑΤΕΡΟΥ": "ΠΕ Δυτικού Τομέα Αθηνών",
    # Αττική - Βόρειος Τομέας
    "ΧΑΛΑΝΔΡΙΟΥ": "ΠΕ Βορείου Τομέα Αθηνών", "ΑΜΑΡΟΥΣΙΟΥ": "ΠΕ Βορείου Τομέα Αθηνών",
    "ΚΗΦΙΣΙΑΣ": "ΠΕ Βορείου Τομέα Αθηνών", "ΠΕΝΤΕΛΗΣ": "ΠΕ Βορείου Τομέα Αθηνών",
    "ΝΕΑΣ ΙΩΝΙΑΣ": "ΠΕ Βορείου Τομέα Αθηνών", "ΜΕΤΑΜΟΡΦΩΣΕΩΣ": "ΠΕ Βορείου Τομέα Αθηνών",
    "ΑΓΙΑΣ ΠΑΡΑΣΚΕΥΗΣ": "ΠΕ Βορείου Τομέα Αθηνών", "ΠΑΠΑΓΟΥ-ΧΟΛΑΡΓΟΥ": "ΠΕ Βορείου Τομέα Αθηνών",
    "ΒΡΙΛΗΣΣΙΩΝ": "ΠΕ Βορείου Τομέα Αθηνών", "ΛΥΚΟΒΡΥΣΗΣ-ΠΕΥΚΗΣ": "ΠΕ Βορείου Τομέα Αθηνών",
    "ΦΙΛΟΘΕΗΣ-ΨΥΧΙΚΟΥ": "ΠΕ Βορείου Τομέα Αθηνών",
    # ΠΕ Πειραιώς
    "ΠΕΙΡΑΙΩΣ": "ΠΕ Πειραιώς", "ΝΙΚΑΙΑΣ-ΑΓΙΟΥ ΙΩΑΝΝΗ ΡΕΝΤΗ": "ΠΕ Πειραιώς",
    "ΚΕΡΑΤΣΙΝΙΟΥ-ΔΡΑΠΕΤΣΩΝΑΣ": "ΠΕ Πειραιώς", "ΚΟΡΥΔΑΛΛΟΥ": "ΠΕ Πειραιώς",
    "ΠΕΡΑΜΑΤΟΣ": "ΠΕ Πειραιώς",
    # ΠΕ Ανατολικής Αττικής
    "ΠΑΛΛΗΝΗΣ": "ΠΕ Ανατολικής Αττικής", "ΚΡΩΠΙΑΣ": "ΠΕ Ανατολικής Αττικής",
    "ΜΑΡΚΟΠΟΥΛΟΥ": "ΠΕ Ανατολικής Αττικής", "ΛΑΥΡΕΩΤΙΚΗΣ": "ΠΕ Ανατολικής Αττικής",
    "ΣΠΑΤΩΝ-ΑΡΤΕΜΙΔΟΣ": "ΠΕ Ανατολικής Αττικής", "ΜΑΡΑΘΩΝΟΣ": "ΠΕ Ανατολικής Αττικής",
    "ΡΑΦΗΝΑΣ-ΠΙΚΕΡΜΙΟΥ": "ΠΕ Ανατολικής Αττικής", "ΔΙΟΝΥΣΟΥ": "ΠΕ Ανατολικής Αττικής",
    "ΩΡΩΠΟΥ": "ΠΕ Ανατολικής Αττικής",
    # ΠΕ Δυτικής Αττικής
    "ΕΛΕΥΣΙΝΟΣ": "ΠΕ Δυτικής Αττικής", "ΑΣΠΡΟΠΥΡΓΟΥ": "ΠΕ Δυτικής Αττικής",
    "ΜΑΝΔΡΑΣ-ΕΙΔΥΛΛΙΑΣ": "ΠΕ Δυτικής Αττικής", "ΜΕΓΑΡΕΩΝ": "ΠΕ Δυτικής Αττικής",
    # ΠΕ Θεσσαλονίκης
    "ΘΕΣΣΑΛΟΝΙΚΗΣ": "ΠΕ Θεσσαλονίκης", "ΚΑΛΑΜΑΡΙΑΣ": "ΠΕ Θεσσαλονίκης",
    "ΠΑΥΛΟΥ ΜΕΛΑ": "ΠΕ Θεσσαλονίκης", "ΚΟΡΔΕΛΙΟΥ-ΕΥΟΣΜΟΥ": "ΠΕ Θεσσαλονίκης",
    "ΝΕΑΠΟΛΕΩΣ-ΣΥΚΕΩΝ": "ΠΕ Θεσσαλονίκης", "ΑΜΠΕΛΟΚΗΠΩΝ-ΜΕΝΕΜΕΝΗΣ": "ΠΕ Θεσσαλονίκης",
    "ΘΕΡΜΗΣ": "ΠΕ Θεσσαλονίκης", "ΔΕΛΤΑ": "ΠΕ Θεσσαλονίκης",
    "ΩΡΑΙΟΚΑΣΤΡΟΥ": "ΠΕ Θεσσαλονίκης", "ΧΟΡΤΙΑΤΗ": "ΠΕ Θεσσαλονίκης",
    "ΠΥΛΑΙΑΣ-ΧΟΡΤΙΑΤΗ": "ΠΕ Θεσσαλονίκης",
    # ΠΕ Χαλκιδικής
    "ΠΟΛΥΓΥΡΟΥ": "ΠΕ Χαλκιδικής", "ΚΑΣΣΑΝΔΡΑΣ": "ΠΕ Χαλκιδικής", "ΣΙΘΩΝΙΑΣ": "ΠΕ Χαλκιδικής",
    "ΑΡΙΣΤΟΤΕΛΗ": "ΠΕ Χαλκιδικής",
    # ΠΕ Κιλκίς
    "ΚΙΛΚΙΣ": "ΠΕ Κιλκίς",
    # ΠΕ Πέλλας
    "ΕΔΕΣΣΗΣ": "ΠΕ Πέλλας", "ΑΛΕΞΑΝΔΡΕΙΑΣ": "ΠΕ Ημαθίας",
    # ΠΕ Ημαθίας
    "ΒΕΡΟΙΑΣ": "ΠΕ Ημαθίας", "ΝΑΟΥΣΑΣ": "ΠΕ Ημαθίας",
    # ΠΕ Πιερίας
    "ΚΑΤΕΡΙΝΗΣ": "ΠΕ Πιερίας",
    # ΠΕ Σερρών
    "ΣΕΡΡΩΝ": "ΠΕ Σερρών",
    # ΠΕ Λάρισας
    "ΛΑΡΙΣΑΙΩΝ": "ΠΕ Λάρισας", "ΛΑΡΙΣΑΣ": "ΠΕ Λάρισας", "ΤΥΡΝΑΒΟΥ": "ΠΕ Λάρισας",
    # ΠΕ Μαγνησίας
    "ΒΟΛΟΥ": "ΠΕ Μαγνησίας", "ΝΕΑΣ ΙΩΝΙΑΣ ΜΑΓΝΗΣΙΑΣ": "ΠΕ Μαγνησίας",
    "ΑΛΜΥΡΟΥ": "ΠΕ Μαγνησίας", "ΖΑΓΟΡΑΣ-ΜΟΥΡΕΣΙΟΥ": "ΠΕ Μαγνησίας",
    # ΠΕ Τρικάλων
    "ΤΡΙΚΚΑΙΩΝ": "ΠΕ Τρικάλων", "ΤΡΙΚΑΛΩΝ": "ΠΕ Τρικάλων",
    # ΠΕ Καρδίτσας
    "ΚΑΡΔΙΤΣΗΣ": "ΠΕ Καρδίτσας",
    # ΠΕ Φθιώτιδας
    "ΛΑΜΙΕΩΝ": "ΠΕ Φθιώτιδας", "ΛΑΜΙΑΣ": "ΠΕ Φθιώτιδας",
    # ΠΕ Εύβοιας
    "ΧΑΛΚΙΔΕΩΝ": "ΠΕ Εύβοιας", "ΧΑΛΚΙΔΑΣ": "ΠΕ Εύβοιας",
    "ΙΣΤΙΑΙΑΣ-ΑΙΔΗΨΟΥ": "ΠΕ Εύβοιας", "ΚΑΡΥΣΤΟΥ": "ΠΕ Εύβοιας",
    # ΠΕ Βοιωτίας
    "ΘΗΒΑΙΩΝ": "ΠΕ Βοιωτίας", "ΛΕΒΑΔΕΩΝ": "ΠΕ Βοιωτίας", "ΟΡΧΟΜΕΝΟΥ": "ΠΕ Βοιωτίας",
    # ΠΕ Φωκίδας
    "ΑΜΦΙΣΣΗΣ": "ΠΕ Φωκίδας", "ΔΕΛΦΩΝ": "ΠΕ Φωκίδας",
    # ΠΕ Κορινθίας
    "ΚΟΡΙΝΘΙΩΝ": "ΠΕ Κορινθίας", "ΛΟΥΤΡΑΚΙΟΥ-ΠΕΡΑΧΩΡΑΣ": "ΠΕ Κορινθίας",
    # ΠΕ Αχαΐας
    "ΠΑΤΡΕΩΝ": "ΠΕ Αχαΐας", "ΑΙΓΙΑΛΕΙΑΣ": "ΠΕ Αχαΐας",
    # ΠΕ Αιτωλοακαρνανίας
    "ΑΓΡΙΝΙΟΥ": "ΠΕ Αιτωλοακαρνανίας", "ΜΕΣΟΛΟΓΓΙΟΥ": "ΠΕ Αιτωλοακαρνανίας",
    "ΝΑΥΠΑΚΤΙΑΣ": "ΠΕ Αιτωλοακαρνανίας",
    # ΠΕ Αρκαδίας
    "ΤΡΙΠΟΛΗΣ": "ΠΕ Αρκαδίας",
    # ΠΕ Μεσσηνίας
    "ΚΑΛΑΜΑΤΑΣ": "ΠΕ Μεσσηνίας",
    # ΠΕ Λακωνίας
    "ΣΠΑΡΤΗΣ": "ΠΕ Λακωνίας",
    # ΠΕ Αργολίδας
    "ΝΑΥΠΛΙΕΩΝ": "ΠΕ Αργολίδας", "ΑΡΓΟΥΣ-ΜΥΚΗΝΩΝ": "ΠΕ Αργολίδας",
    # ΠΕ Ιωαννίνων
    "ΙΩΑΝΝΙΤΩΝ": "ΠΕ Ιωαννίνων",
    # ΠΕ Καβάλας
    "ΚΑΒΑΛΑΣ": "ΠΕ Καβάλας",
    # ΠΕ Δράμας
    "ΔΡΑΜΑΣ": "ΠΕ Δράμας",
    # ΠΕ Ξάνθης
    "ΞΑΝΘΗΣ": "ΠΕ Ξάνθης",
    # ΠΕ Ροδόπης
    "ΚΟΜΟΤΗΝΗΣ": "ΠΕ Ροδόπης",
    # ΠΕ Έβρου
    "ΑΛΕΞΑΝΔΡΟΥΠΟΛΗΣ": "ΠΕ Έβρου",
    # ΠΕ Ηρακλείου
    "ΗΡΑΚΛΕΙΟΥ": "ΠΕ Ηρακλείου",
    # ΠΕ Χανίων
    "ΧΑΝΙΩΝ": "ΠΕ Χανίων",
    # ΠΕ Ρεθύμνης
    "ΡΕΘΥΜΝΗΣ": "ΠΕ Ρεθύμνης",
    # ΠΕ Λασιθίου
    "ΑΓΙΟΥ ΝΙΚΟΛΑΟΥ": "ΠΕ Λασιθίου",
    # Νησιά
    "ΡΟΔΟΥ": "ΠΕ Ρόδου", "ΜΥΤΙΛΗΝΗΣ": "ΠΕ Λέσβου", "ΧΙΟΥ": "ΠΕ Χίου",
    "ΣΑΜΟΥ": "ΠΕ Σάμου", "ΚΕΡΚΥΡΑΣ": "ΠΕ Κέρκυρας", "ΖΑΚΥΝΘΟΥ": "ΠΕ Ζακύνθου",
    "ΚΕΦΑΛΛΗΝΙΑΣ": "ΠΕ Κεφαλονιάς", "ΛΕΥΚΑΔΑΣ": "ΠΕ Λευκάδας",
    "ΣΥΡΟΥ-ΕΡΜΟΥΠΟΛΗΣ": "ΠΕ Σύρου", "ΜΥΚΟΝΟΥ": "ΠΕ Μυκόνου", "ΝΑΞΟΥ": "ΠΕ Νάξου",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  PDF PARSER (regex, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_permit_pdf(pdf_bytes: bytes) -> dict:
    """Parse a TEE building permit PDF using regex."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return {}
    text = "\n".join(p.extract_text() or "" for p in reader.pages)

    if len(text) < 50:
        return {}

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

    # Address
    result["street"] = extract(r'Οδός\s*(.+?)(?:\n|$)')
    result["number"] = extract(r'Αριθμός\s*(.+?)(?:\n|$)')
    result["city"] = extract(r'Πόλη/?Οικισμός\s*(.+?)(?:\n|$)')
    result["municipality"] = extract(r'Δήμος\s*(.+?)(?:\n|$)')
    result["municipal_unit"] = extract(r'Δημοτική Ενότητα\s*/?\s*Περιοχή\s*(.+?)(?:\n|$)')
    result["region"] = extract(r'Περιφέρεια\s*(.+?)(?:\n|$)')
    result["postal_code"] = extract(r'Τ\.?\s*Κ\.?\s*(\d{3}\s*\d{2})')

    # Issuing authority (contains location)
    result["authority"] = extract(r'(ΥΔΟΜ\s*.+?)(?:\n|$)')
    if not result["authority"]:
        result["authority"] = extract(r'(Υ\.ΔΟΜ\..+?)(?:\n|$)')

    # Engineer
    result["engineer"] = extract(r'Διαχειριστής Αίτησης\s*(.+?)(?:\n|$)')
    tee_match = re.search(r'Αρ\.?\s*ΤΕΕ[:\s]*(\d+)', result.get("engineer", "") + " " + text[:2000])
    result["engineer_tee"] = tee_match.group(1) if tee_match else ""

    # Clean engineer name
    eng_name = result["engineer"]
    eng_name = re.sub(r'\(Αρ\..*?\)', '', eng_name)
    eng_name = re.sub(r',\s*(?:ΠΤΥΧΙΟΥΧΟΣ|ΔΙΠΛΩΜΑΤΟΥΧΟΣ).*', '', eng_name, flags=re.IGNORECASE)
    eng_name = re.sub(r'\s+', ' ', eng_name)
    result["engineer_name"] = eng_name.strip()

    # Building specs
    result["plot_area"] = extract_float(r'Εμβαδόν οικοπέδου\s*([\d.,]+)')
    result["building_area_m2"] = extract_float(
        r'Εμβ\.\s*δόμησης κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)'
    )
    if not result["building_area_m2"]:
        result["building_area_m2"] = extract_float(r'Συνολική δόμηση\s*([\d.,]+)')
    result["volume_m3"] = extract_float(
        r'[Όό]γκος κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)'
    )
    result["coverage_m2"] = extract_float(
        r'Εμβ\.\s*κάλυψης κτιρίου.*?(?:ΣΥΝΟΛΟ|ΠΡΑΓΜΑΤΟΠΟΙΟ\s*ΥΜΕΝΑ)\s*([\d.,]+)'
    )

    # Project description
    result["project"] = extract(r'Περιγραφή\s*[Έέ]ργου/?[Εε]γκατάστασης\s*(.+?)(?:\n|Οδός)', "")
    if not result["project"]:
        result["project"] = extract(r'Περιγραφή\n\s*[Έέ]ργου\s*(.+?)(?:\n)')

    # Owners (simplified - just get first owner name)
    owner_match = re.search(
        r'Στοιχεία κυρίου.+?([Α-Ω][α-ωά-ώ]+(?:ΟΥ|ΗΣ|ΑΣ)?)\s+([Α-Ω]{2,})',
        text, re.DOTALL
    )
    if owner_match:
        result["owner"] = f"{owner_match.group(1)} {owner_match.group(2)}"
    else:
        result["owner"] = ""

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD + PARSE
# ═══════════════════════════════════════════════════════════════════════════════

def download_pdf(ada: str, session: requests.Session) -> bytes | None:
    """Download a permit PDF from Diavgeia, with disk cache."""
    safe_name = ada.replace("/", "_")
    cache_path = PDF_CACHE_DIR / f"{safe_name}.pdf"

    if cache_path.exists() and cache_path.stat().st_size > 100:
        return cache_path.read_bytes()

    url = f"https://diavgeia.gov.gr/doc/{ada}"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 500:
            cache_path.write_bytes(resp.content)
            return resp.content
    except Exception:
        pass
    return None


def process_one(ada: str, session: requests.Session) -> dict | None:
    """Download and parse one permit PDF."""
    pdf_bytes = download_pdf(ada, session)
    if not pdf_bytes:
        return None

    parsed = parse_permit_pdf(pdf_bytes)
    if not parsed:
        return None

    parsed["ada"] = ada
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
#  GEOCODING (Nominatim, cached)
# ═══════════════════════════════════════════════════════════════════════════════

def load_geocode_cache() -> dict:
    if GEOCODE_CACHE_FILE.exists():
        return json.loads(GEOCODE_CACHE_FILE.read_text())
    return {}


def save_geocode_cache(cache: dict):
    GEOCODE_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


# Pre-built lookup for major Greek municipalities → approximate center coords
# This avoids hitting Nominatim for common locations
GREEK_MUNICIPALITY_COORDS = {
    "ΑΘΗΝΑΙΩΝ": (37.9838, 23.7275), "ΑΘΗΝΩΝ": (37.9838, 23.7275), "ΑΘΗΝΑ": (37.9838, 23.7275),
    "ΘΕΣΣΑΛΟΝΙΚΗΣ": (40.6401, 22.9444), "ΘΕΣΣΑΛΟΝΙΚΗ": (40.6401, 22.9444),
    "ΠΑΤΡΕΩΝ": (38.2466, 21.7346), "ΠΑΤΡΑ": (38.2466, 21.7346),
    "ΗΡΑΚΛΕΙΟΥ": (35.3387, 25.1442), "ΗΡΑΚΛΕΙΟ": (35.3387, 25.1442),
    "ΛΑΡΙΣΑΙΩΝ": (39.6372, 22.4202), "ΛΑΡΙΣΑ": (39.6372, 22.4202),
    "ΒΟΛΟΥ": (39.3621, 22.9420), "ΒΟΛΟΣ": (39.3621, 22.9420),
    "ΙΩΑΝΝΙΤΩΝ": (39.6650, 20.8537), "ΙΩΑΝΝΙΝΑ": (39.6650, 20.8537),
    "ΧΑΝΙΩΝ": (35.5138, 24.0180), "ΧΑΝΙΑ": (35.5138, 24.0180),
    "ΡΟΔΟΥ": (36.4341, 28.2176), "ΡΟΔΟΣ": (36.4341, 28.2176),
    "ΚΑΛΑΜΑΤΑΣ": (37.0388, 22.1142), "ΚΑΛΑΜΑΤΑ": (37.0388, 22.1142),
    "ΚΕΡΚΥΡΑΣ": (39.6243, 19.9217), "ΚΕΡΚΥΡΑ": (39.6243, 19.9217),
    "ΤΡΙΚΚΑΙΩΝ": (39.5554, 21.7688), "ΤΡΙΚΑΛΑ": (39.5554, 21.7688),
    "ΚΟΜΟΤΗΝΗΣ": (41.1222, 25.4064), "ΚΟΜΟΤΗΝΗ": (41.1222, 25.4064),
    "ΣΕΡΡΩΝ": (41.0856, 23.5484), "ΣΕΡΡΕΣ": (41.0856, 23.5484),
    "ΔΡΑΜΑΣ": (41.1510, 24.1472), "ΔΡΑΜΑ": (41.1510, 24.1472),
    "ΚΑΒΑΛΑΣ": (40.9396, 24.4014), "ΚΑΒΑΛΑ": (40.9396, 24.4014),
    "ΞΑΝΘΗΣ": (41.1350, 24.8880), "ΞΑΝΘΗ": (41.1350, 24.8880),
    "ΑΛΕΞΑΝΔΡΟΥΠΟΛΗΣ": (40.8447, 25.8744), "ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ": (40.8447, 25.8744),
    "ΚΟΖΑΝΗΣ": (40.3005, 21.7887), "ΚΟΖΑΝΗ": (40.3005, 21.7887),
    "ΚΑΣΤΟΡΙΑΣ": (40.5168, 21.2684), "ΚΑΣΤΟΡΙΑ": (40.5168, 21.2684),
    "ΦΛΩΡΙΝΑΣ": (40.7841, 21.4098), "ΦΛΩΡΙΝΑ": (40.7841, 21.4098),
    "ΓΡΕΒΕΝΩΝ": (40.0834, 21.4273), "ΓΡΕΒΕΝΑ": (40.0834, 21.4273),
    "ΚΑΤΕΡΙΝΗΣ": (40.2727, 22.5024), "ΚΑΤΕΡΙΝΗ": (40.2727, 22.5024),
    "ΒΕΡΟΙΑΣ": (40.5235, 22.2031), "ΒΕΡΟΙΑ": (40.5235, 22.2031),
    "ΕΔΕΣΣΑΣ": (40.8026, 22.0447), "ΕΔΕΣΣΑ": (40.8026, 22.0447),
    "ΠΕΛΛΑΣ": (40.7584, 22.4432),
    "ΚΙΛΚΙΣ": (40.9938, 22.8741), "ΚΙΛΚΙΣ": (40.9938, 22.8741),
    "ΧΑΛΚΙΔΕΩΝ": (38.4633, 23.5981), "ΧΑΛΚΙΔΑ": (38.4633, 23.5981),
    "ΛΑΜΙΕΩΝ": (38.8990, 22.4341), "ΛΑΜΙΑ": (38.8990, 22.4341),
    "ΑΜΦΙΣΣΑΣ": (38.5257, 22.3789), "ΑΜΦΙΣΣΑ": (38.5257, 22.3789),
    "ΛΕΒΑΔΕΩΝ": (38.4360, 22.8770), "ΛΙΒΑΔΕΙΑ": (38.4360, 22.8770),
    "ΘΗΒΑΙΩΝ": (38.3265, 23.3177), "ΘΗΒΑ": (38.3265, 23.3177),
    "ΤΡΙΠΟΛΗΣ": (37.5115, 22.3725), "ΤΡΙΠΟΛΗ": (37.5115, 22.3725),
    "ΣΠΑΡΤΗΣ": (37.0736, 22.4297), "ΣΠΑΡΤΗ": (37.0736, 22.4297),
    "ΚΟΡΙΝΘΙΩΝ": (37.9409, 22.9319), "ΚΟΡΙΝΘΟΣ": (37.9409, 22.9319),
    "ΑΡΓΟΥΣ-ΜΥΚΗΝΩΝ": (37.6316, 22.7291), "ΑΡΓΟΣ": (37.6316, 22.7291),
    "ΝΑΥΠΑΚΤΙΑΣ": (38.3934, 21.8290), "ΝΑΥΠΑΚΤΟΣ": (38.3934, 21.8290),
    "ΑΓΡΙΝΙΟΥ": (38.6213, 21.4074), "ΑΓΡΙΝΙΟ": (38.6213, 21.4074),
    "ΜΕΣΟΛΟΓΓΙΟΥ": (38.3703, 21.4312), "ΜΕΣΟΛΟΓΓΙ": (38.3703, 21.4312),
    "ΖΑΚΥΝΘΟΥ": (37.7873, 20.9001), "ΖΑΚΥΝΘΟΣ": (37.7873, 20.9001),
    "ΛΕΥΚΑΔΑΣ": (38.8336, 20.7069), "ΛΕΥΚΑΔΑ": (38.8336, 20.7069),
    "ΚΕΦΑΛΛΗΝΙΑΣ": (38.1751, 20.4893), "ΚΕΦΑΛΟΝΙΑ": (38.1751, 20.4893),
    "ΜΥΤΙΛΗΝΗΣ": (39.1099, 26.5517), "ΜΥΤΙΛΗΝΗ": (39.1099, 26.5517),
    "ΧΙΟΥ": (38.3675, 26.1359), "ΧΙΟΣ": (38.3675, 26.1359),
    "ΣΑΜΟΥ": (37.7577, 26.9774), "ΣΑΜΟΣ": (37.7577, 26.9774),
    "ΣΥΡΟΥ-ΕΡΜΟΥΠΟΛΗΣ": (37.4445, 24.9419), "ΣΥΡΟΣ": (37.4445, 24.9419), "ΕΡΜΟΥΠΟΛΗ": (37.4445, 24.9419),
    "ΜΥΚΟΝΟΥ": (37.4467, 25.3289), "ΜΥΚΟΝΟΣ": (37.4467, 25.3289),
    "ΝΑΞΟΥ": (37.1036, 25.3762), "ΝΑΞΟΣ": (37.1036, 25.3762),
    "ΠΑΡΟΥ": (37.0853, 25.1527), "ΠΑΡΟΣ": (37.0853, 25.1527),
    "ΘΗΡΑΣ": (36.3932, 25.4615), "ΣΑΝΤΟΡΙΝΗ": (36.3932, 25.4615),
    "ΤΗΝΟΥ": (37.5386, 25.1633), "ΤΗΝΟΣ": (37.5386, 25.1633),
    "ΑΝΔΡΟΥ": (37.8358, 24.9351), "ΑΝΔΡΟΣ": (37.8358, 24.9351),
    "ΚΩ": (36.8943, 26.9417), "ΚΩΣ": (36.8943, 26.9417),
    "ΚΑΛΥΜΝΙΩΝ": (36.9543, 26.9854), "ΚΑΛΥΜΝΟΣ": (36.9543, 26.9854),
    "ΡΕΘΥΜΝΗΣ": (35.3693, 24.4736), "ΡΕΘΥΜΝΟ": (35.3693, 24.4736),
    "ΑΓΙΟΥ ΝΙΚΟΛΑΟΥ": (35.1910, 25.7165),
    "ΣΗΤΕΙΑΣ": (35.2060, 26.1023), "ΣΗΤΕΙΑ": (35.2060, 26.1023),
    "ΙΕΡΑΠΕΤΡΑΣ": (35.0085, 25.7350), "ΙΕΡΑΠΕΤΡΑ": (35.0085, 25.7350),
    # Attica municipalities
    "ΠΕΙΡΑΙΩΣ": (37.9475, 23.6431), "ΠΕΙΡΑΙΑΣ": (37.9475, 23.6431), "ΠΕΙΡΑΙΑ": (37.9475, 23.6431),
    "ΓΛΥΦΑΔΑΣ": (37.8600, 23.7530), "ΓΛΥΦΑΔΑ": (37.8600, 23.7530),
    "ΒΟΥΛΑΣ-ΒΑΡΗΣ-ΒΟΥΛΙΑΓΜΕΝΗΣ": (37.8280, 23.7800),
    "ΑΛΙΜΟΥ": (37.9097, 23.7136), "ΑΛΙΜΟΣ": (37.9097, 23.7136),
    "ΕΛΛΗΝΙΚΟΥ-ΑΡΓΥΡΟΥΠΟΛΗΣ": (37.8939, 23.7467),
    "ΚΑΛΛΙΘΕΑΣ": (37.9564, 23.7022), "ΚΑΛΛΙΘΕΑ": (37.9564, 23.7022),
    "ΝΕΑΣ ΣΜΥΡΝΗΣ": (37.9433, 23.7131), "ΝΕΑ ΣΜΥΡΝΗ": (37.9433, 23.7131),
    "ΠΑΛΑΙΟΥ ΦΑΛΗΡΟΥ": (37.9290, 23.7000), "ΠΑΛΑΙΟ ΦΑΛΗΡΟ": (37.9290, 23.7000),
    "ΜΟΣΧΑΤΟΥ-ΤΑΥΡΟΥ": (37.9570, 23.6790),
    "ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ": (37.9350, 23.7340), "ΑΓΙΟΣ ΔΗΜΗΤΡΙΟΣ": (37.9350, 23.7340),
    "ΔΑΦΝΗΣ-ΥΜΗΤΤΟΥ": (37.9500, 23.7400),
    "ΒΥΡΩΝΟΣ": (37.9600, 23.7600), "ΒΥΡΩΝΑΣ": (37.9600, 23.7600),
    "ΗΛΙΟΥΠΟΛΗΣ": (37.9310, 23.7530), "ΗΛΙΟΥΠΟΛΗ": (37.9310, 23.7530),
    "ΖΩΓΡΑΦΟΥ": (37.9760, 23.7690),
    "ΚΑΙΣΑΡΙΑΝΗΣ": (37.9660, 23.7600), "ΚΑΙΣΑΡΙΑΝΗ": (37.9660, 23.7600),
    "ΧΟΛΑΡΓΟΥ-ΠΑΠΑΓΟΥ": (37.9930, 23.7900),
    "ΑΓΙΑΣ ΠΑΡΑΣΚΕΥΗΣ": (38.0100, 23.8200), "ΑΓΙΑ ΠΑΡΑΣΚΕΥΗ": (38.0100, 23.8200),
    "ΧΑΛΑΝΔΡΙΟΥ": (38.0214, 23.7982), "ΧΑΛΑΝΔΡΙ": (38.0214, 23.7982),
    "ΒΡΙΛΗΣΣΙΩΝ": (38.0340, 23.8290), "ΒΡΙΛΗΣΣΙΑ": (38.0340, 23.8290),
    "ΦΙΛΟΘΕΗΣ-ΨΥΧΙΚΟΥ": (38.0100, 23.7750),
    "ΑΜΑΡΟΥΣΙΟΥ": (38.0494, 23.8061), "ΜΑΡΟΥΣΙ": (38.0494, 23.8061),
    "ΚΗΦΙΣΙΑΣ": (38.0732, 23.8110), "ΚΗΦΙΣΙΑ": (38.0732, 23.8110),
    "ΠΕΝΤΕΛΗΣ": (38.0530, 23.8550),
    "ΗΡΑΚΛΕΙΟΥ": (38.0530, 23.7650), "ΝΕΟΥ ΗΡΑΚΛΕΙΟΥ": (38.0530, 23.7650),
    "ΜΕΤΑΜΟΡΦΩΣΗΣ": (38.0650, 23.7560), "ΜΕΤΑΜΟΡΦΩΣΗ": (38.0650, 23.7560),
    "ΛΥΚΟΒΡΥΣΗΣ-ΠΕΥΚΗΣ": (38.0700, 23.7800),
    "ΑΓΙΩΝ ΑΝΑΡΓΥΡΩΝ-ΚΑΜΑΤΕΡΟΥ": (38.0380, 23.7200),
    "ΙΛΙΟΥ": (38.0220, 23.7040), "ΙΛΙΟΝ": (38.0220, 23.7040),
    "ΠΕΤΡΟΥΠΟΛΗΣ": (38.0380, 23.6880), "ΠΕΤΡΟΥΠΟΛΗ": (38.0380, 23.6880),
    "ΠΕΡΙΣΤΕΡΙΟΥ": (38.0160, 23.6870), "ΠΕΡΙΣΤΕΡΙ": (38.0160, 23.6870),
    "ΑΙΓΑΛΕΩ": (37.9940, 23.6810), "ΑΙΓΑΛΕΟ": (37.9940, 23.6810),
    "ΧΑΙΔΑΡΙΟΥ": (38.0100, 23.6600), "ΧΑΙΔΑΡΙ": (38.0100, 23.6600),
    "ΝΙΚΑΙΑΣ-ΑΓΙΟΥ ΙΩΑΝΝΗ ΡΕΝΤΗ": (37.9700, 23.6500), "ΝΙΚΑΙΑ": (37.9700, 23.6500),
    "ΚΕΡΑΤΣΙΝΙΟΥ-ΔΡΑΠΕΤΣΩΝΑΣ": (37.9600, 23.6200), "ΚΕΡΑΤΣΙΝΙ": (37.9600, 23.6200),
    "ΠΕΡΑΜΑΤΟΣ": (37.9600, 23.5700), "ΠΕΡΑΜΑ": (37.9600, 23.5700),
    "ΣΑΛΑΜΙΝΟΣ": (37.9470, 23.4960), "ΣΑΛΑΜΙΝΑ": (37.9470, 23.4960),
    "ΚΡΩΠΙΑΣ": (37.8450, 23.8550), "ΚΡΩΠΙΑ": (37.8450, 23.8550),
    "ΜΑΡΚΟΠΟΥΛΟΥ": (37.8850, 23.9200), "ΜΑΡΚΟΠΟΥΛΟ": (37.8850, 23.9200),
    "ΣΠΑΤΩΝ-ΑΡΤΕΜΙΔΟΣ": (37.9500, 23.9600),
    "ΠΑΛΛΗΝΗΣ": (37.9900, 23.8800), "ΠΑΛΛΗΝΗ": (37.9900, 23.8800),
    "ΡΑΦΗΝΑΣ-ΠΙΚΕΡΜΙΟΥ": (38.0200, 23.9400), "ΡΑΦΗΝΑ": (38.0200, 23.9400),
    "ΔΙΟΝΥΣΟΥ": (38.1070, 23.8700),
    "ΩΡΩΠΟΥ": (38.2950, 23.7500), "ΩΡΩΠΟΣ": (38.2950, 23.7500),
    "ΜΑΡΑΘΩΝΟΣ": (38.1530, 23.9600), "ΜΑΡΑΘΩΝΑΣ": (38.1530, 23.9600),
    "ΑΧΑΡΝΩΝ": (38.0800, 23.7300), "ΑΧΑΡΝΕΣ": (38.0800, 23.7300),
    "ΦΥΛΗΣ": (38.0870, 23.6530),
    "ΑΣΠΡΟΠΥΡΓΟΥ": (38.0620, 23.5850), "ΑΣΠΡΟΠΥΡΓΟΣ": (38.0620, 23.5850),
    "ΕΛΕΥΣΙΝΑΣ": (38.0420, 23.5370), "ΕΛΕΥΣΙΝΑ": (38.0420, 23.5370),
    "ΜΑΝΔΡΑΣ-ΕΙΔΥΛΛΙΑΣ": (38.0700, 23.5050),
    "ΜΕΓΑΡΕΩΝ": (37.9950, 23.3450), "ΜΕΓΑΡΑ": (37.9950, 23.3450),
    "ΣΑΡΩΝΙΚΟΥ": (37.7700, 23.8000),
    "ΛΑΥΡΕΩΤΙΚΗΣ": (37.7100, 24.0500), "ΛΑΥΡΙΟ": (37.7100, 24.0500),
    # More cities
    "ΠΡΕΒΕΖΑΣ": (38.9506, 20.7517), "ΠΡΕΒΕΖΑ": (38.9506, 20.7517),
    "ΑΡΤΑΣ": (39.1574, 20.9854), "ΑΡΤΑ": (39.1574, 20.9854),
    "ΚΑΡΔΙΤΣΑΣ": (39.3652, 21.9216), "ΚΑΡΔΙΤΣΑ": (39.3652, 21.9216),
    "ΠΥΡΓΟΥ": (37.6707, 21.4389), "ΠΥΡΓΟΣ": (37.6707, 21.4389),
    "ΧΑΛΚΙΔΙΚΗΣ": (40.3200, 23.5100),
    "ΘΕΡΜΑΙΚΟΥ": (40.4600, 22.8700),
    "ΘΕΡΜΗΣ": (40.5400, 23.0200),
    "ΠΥΛΑΙΑΣ-ΧΟΡΤΙΑΤΗ": (40.5800, 23.0300),
    "ΚΑΛΑΜΑΡΙΑΣ": (40.5800, 22.9500), "ΚΑΛΑΜΑΡΙΑ": (40.5800, 22.9500),
    "ΠΑΥΛΟΥ ΜΕΛΑ": (40.6700, 22.9100),
    "ΝΕΑΠΟΛΗΣ-ΣΥΚΕΩΝ": (40.6600, 22.9300),
    "ΑΜΠΕΛΟΚΗΠΩΝ-ΜΕΝΕΜΕΝΗΣ": (40.6500, 22.8900),
    "ΚΟΡΔΕΛΙΟΥ-ΕΥΟΣΜΟΥ": (40.6700, 22.8800),
    "ΔΕΛΤΑ": (40.5700, 22.7300),
    "ΩΡΑΙΟΚΑΣΤΡΟΥ": (40.6400, 22.8400), "ΩΡΑΙΟΚΑΣΤΡΟ": (40.6400, 22.8400),
    "ΛΑΓΚΑΔΑ": (40.7500, 23.0700),
    "ΒΟΛΒΗΣ": (40.6800, 23.4600),
    "ΝΕΑΣ ΠΡΟΠΟΝΤΙΔΑΣ": (40.3000, 23.3000),
    "ΚΑΣΣΑΝΔΡΑΣ": (40.0500, 23.4200),
    "ΣΙΘΩΝΙΑΣ": (40.1500, 23.7700),
    "ΑΡΙΣΤΟΤΕΛΗ": (40.3700, 23.8700),
    "ΠΟΛΥΓΥΡΟΥ": (40.3700, 23.4400), "ΠΟΛΥΓΥΡΟΣ": (40.3700, 23.4400),
}


def clean_municipality(raw: str) -> str:
    """Clean municipality name from PDF extraction artifacts."""
    m = raw.strip().replace(':', '').strip()
    if 'Οδός' in m:
        m = m.split('Οδός')[0].strip()
    return m


def geocode_municipality(municipality: str, city: str, geocode_cache: dict) -> tuple | None:
    """Geocode a Greek municipality/city. Uses local lookup first, then cache."""
    municipality = clean_municipality(municipality) if municipality else ""
    city = clean_municipality(city) if city else ""

    if not municipality and not city:
        return None

    # Normalize
    muni_upper = municipality.upper().strip()
    city_upper = city.upper().strip()

    # Cache key
    cache_key = f"{muni_upper}|{city_upper}"
    if cache_key in geocode_cache:
        val = geocode_cache[cache_key]
        return (val["lat"], val["lng"]) if val else None

    # Try local lookup first
    for name in [muni_upper, city_upper]:
        if name in GREEK_MUNICIPALITY_COORDS:
            lat, lng = GREEK_MUNICIPALITY_COORDS[name]
            geocode_cache[cache_key] = {"lat": lat, "lng": lng}
            return (lat, lng)
        # Try partial match
        for key, coords in GREEK_MUNICIPALITY_COORDS.items():
            if key in name or name in key:
                geocode_cache[cache_key] = {"lat": coords[0], "lng": coords[1]}
                return coords

    geocode_cache[cache_key] = None
    return None


def batch_geocode_unique(parsed_data: list) -> dict:
    """Pre-geocode all unique municipalities via Nominatim, then return cache."""
    geocode_cache = load_geocode_cache()

    # Collect unique municipality names
    unique_munis = set()
    for p in parsed_data:
        m = clean_municipality(p.get("municipality", ""))
        c = clean_municipality(p.get("city", ""))
        if m:
            unique_munis.add(m)

    # First pass: resolve from local lookup
    unresolved = []
    for muni in unique_munis:
        muni_upper = muni.upper()
        cache_key = f"{muni_upper}|"
        if cache_key in geocode_cache:
            continue
        found = False
        for name in [muni_upper]:
            if name in GREEK_MUNICIPALITY_COORDS:
                geocode_cache[cache_key] = {"lat": GREEK_MUNICIPALITY_COORDS[name][0], "lng": GREEK_MUNICIPALITY_COORDS[name][1]}
                found = True
                break
            for key, coords in GREEK_MUNICIPALITY_COORDS.items():
                if key in name or name in key:
                    geocode_cache[cache_key] = {"lat": coords[0], "lng": coords[1]}
                    found = True
                    break
            if found:
                break
        if not found:
            unresolved.append(muni)

    print(f"    Local lookup resolved {len(unique_munis) - len(unresolved)}/{len(unique_munis)} municipalities")
    print(f"    Geocoding {len(unresolved)} via Nominatim...")

    # Nominatim for unresolved
    for i, muni in enumerate(unresolved):
        cache_key = f"{muni.upper()}|"
        query = f"Δήμος {muni}, Greece"
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "gr"},
                headers={"User-Agent": "GreekConstructionPipeline/1.0"},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                result = resp.json()[0]
                lat, lng = float(result["lat"]), float(result["lon"])
                geocode_cache[cache_key] = {"lat": lat, "lng": lng}
                print(f"      [{i+1}/{len(unresolved)}] {muni} → ({lat:.4f}, {lng:.4f})")
            else:
                geocode_cache[cache_key] = None
                print(f"      [{i+1}/{len(unresolved)}] {muni} → NOT FOUND")
            time.sleep(1.1)
        except Exception as e:
            geocode_cache[cache_key] = None
            print(f"      [{i+1}/{len(unresolved)}] {muni} → ERROR: {e}")
            time.sleep(1.1)

    save_geocode_cache(geocode_cache)
    return geocode_cache


# ═══════════════════════════════════════════════════════════════════════════════
#  BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def batch_download_and_parse(ada_list: list, max_workers: int = 10) -> list:
    """Download and parse PDFs in parallel."""
    results = []
    session = requests.Session()
    session.headers["User-Agent"] = "GreekConstructionPipeline/1.0"

    total = len(ada_list)
    done = 0
    failed = 0

    print(f"\n  Downloading & parsing {total} PDFs ({max_workers} parallel)...")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_one, ada, session): ada for ada in ada_list}

        for future in as_completed(futures):
            done += 1
            ada = futures[future]
            try:
                result = future.result()
                if result and (result.get("municipality") or result.get("city")):
                    results.append(result)
                else:
                    failed += 1
            except Exception:
                failed += 1

            if done % 100 == 0 or done == total:
                print(f"    {done}/{total}  ({len(results)} parsed, {failed} failed)")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  MAP GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_map_dashboard(df: pd.DataFrame, parsed_data: list, output_path: Path):
    """Generate an interactive Leaflet map with cement demand markers."""

    # Merge parsed PDF data with permit data
    parsed_lookup = {p["ada"]: p for p in parsed_data}

    geocode_cache = load_geocode_cache()
    markers = []
    geocoded = 0
    skipped = 0

    print(f"\n  Geocoding {len(df)} permits...")

    for _, row in df.iterrows():
        ada = row["ada"]
        parsed = parsed_lookup.get(ada, {})
        municipality = parsed.get("municipality", "")
        city = parsed.get("city", "")

        if not municipality and not city:
            skipped += 1
            continue

        coords = geocode_municipality(municipality, city, geocode_cache)
        if not coords:
            skipped += 1
            continue

        lat, lng = coords
        # Add small random jitter so overlapping markers don't stack
        import random
        lat += random.uniform(-0.005, 0.005)
        lng += random.uniform(-0.005, 0.005)

        cement = float(row.get("cement_tonnes", 0))
        area = parsed.get("building_area_m2") or row.get("est_floor_area_m2", 0)
        area = float(area) if area else 0

        concrete = float(row.get("concrete_m3", 0)) if pd.notna(row.get("concrete_m3")) else round(cement / 0.3, 1)
        markers.append({
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "ada": ada,
            "cem": round(cement, 1),
            "m3": round(concrete, 1),
            "area": round(area, 0),
            "desc": str(row.get("subject", ""))[:120],
            "date": str(row.get("issue_date", ""))[:10],
            "use": str(row.get("use", "")),
            "con": str(row.get("construction", "")),
            "stage": str(row.get("stage", "")),
            "muni": municipality,
            "city": city,
            "eng": parsed.get("engineer_name", ""),
            "tee": parsed.get("engineer_tee", ""),
            "street": parsed.get("street", ""),
        })
        geocoded += 1

    save_geocode_cache(geocode_cache)
    print(f"    Geocoded: {geocoded}, Skipped: {skipped}")

    # Also build the updated table data with engineer info from PDFs
    table_data = []
    for _, row in df.iterrows():
        ada = row["ada"]
        parsed = parsed_lookup.get(ada, {})
        eng_name = parsed.get("engineer_name", "")
        eng_tee = parsed.get("engineer_tee", "")
        muni = parsed.get("municipality", "")
        city = parsed.get("city", "")
        pdf_area = parsed.get("building_area_m2")

        table_data.append({
            "ada": ada,
            "date": str(row.get("issue_date", ""))[:10],
            "sub": str(row.get("subject", ""))[:100],
            "cem": float(row.get("cement_tonnes", 0)) if pd.notna(row.get("cement_tonnes")) else 0,
            "use": str(row.get("use", "")),
            "con": str(row.get("construction", "")),
            "stage": str(row.get("stage", "")),
            "fl": int(row["floors"]) if pd.notna(row.get("floors")) and row.get("floors", 0) > 0 else 0,
            "area": int(pdf_area) if pdf_area else (int(row.get("est_floor_area_m2", 0)) if pd.notna(row.get("est_floor_area_m2")) and row.get("est_floor_area_m2", 0) else 0),
            "eng": eng_name,
            "tee": eng_tee,
            "muni": muni,
            "city": city,
            "street": parsed.get("street", ""),
            "m3": round(float(row.get("concrete_m3", 0)), 1) if pd.notna(row.get("concrete_m3")) else 0,
            "pe": MUNICIPALITY_TO_PE.get(muni.upper().strip() if muni else "", ""),
        })

    # Sort by cement desc
    markers.sort(key=lambda x: -x["cem"])
    table_data.sort(key=lambda x: -x["cem"])

    # KPIs
    total = len(df)
    total_cement = df["cement_tonnes"].sum()
    total_concrete = round(df["concrete_m3"].sum()) if "concrete_m3" in df.columns else round(total_cement / 0.3)
    geocoded_cement = sum(m["cem"] for m in markers)
    new_builds = len(df[df["construction"] == "New Build"])
    with_engineer = sum(1 for t in table_data if t["eng"])

    # Date range for slider
    all_dates = sorted({t["date"] for t in table_data if t["date"] and t["date"] != "NaT"})
    date_min = all_dates[0] if all_dates else "2026-01-01"
    date_max = all_dates[-1] if all_dates else "2026-12-31"

    markers_json = json.dumps(markers, ensure_ascii=False)
    table_json = json.dumps(table_data, ensure_ascii=False)
    plants_json = json.dumps(HERACLES_PLANTS, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Greek Construction — Cement Demand Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>
  :root {{
    --bg: #0a0e17; --card: #111827; --card2: #1a2234; --border: #1e293b;
    --text: #e2e8f0; --dim: #64748b; --muted: #94a3b8;
    --blue: #3b82f6; --green: #22c55e; --orange: #f59e0b; --red: #ef4444;
    --cyan: #06b6d4; --purple: #a855f7;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, system-ui, sans-serif; font-size: 0.82rem; }}

  .header {{
    padding: 1.5rem 2rem 1rem;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{ font-size: 1.5rem; font-weight: 800; }}
  .header h1 span {{ color: var(--cyan); }}
  .header .sub {{ color: var(--muted); font-size: 0.78rem; margin-top: 0.3rem; }}

  .kpi-row {{
    display: flex; gap: 1rem; padding: 1rem 2rem; flex-wrap: wrap;
  }}
  .kpi {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 1rem 1.5rem; flex: 1; min-width: 140px; text-align: center;
  }}
  .kpi .val {{ font-size: 1.4rem; font-weight: 800; }}
  .kpi .lbl {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--dim); margin-top: 0.3rem; }}

  .tabs {{
    display: flex; gap: 0; padding: 0 2rem; border-bottom: 1px solid var(--border);
  }}
  .tab {{
    padding: 0.75rem 1.5rem; cursor: pointer; border-bottom: 2px solid transparent;
    color: var(--muted); font-weight: 600; font-size: 0.82rem; transition: all 0.2s;
  }}
  .tab:hover {{ color: var(--text); }}
  .tab.active {{ color: var(--cyan); border-bottom-color: var(--cyan); }}

  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* Map */
  #map {{ height: calc(100vh - 340px); min-height: 500px; }}
  .map-container {{
    margin: 1rem 2rem; border-radius: 10px; overflow: hidden;
    border: 1px solid var(--border);
  }}
  .map-controls {{
    padding: 0.75rem 2rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;
  }}
  .map-controls label {{ color: var(--muted); font-size: 0.75rem; }}
  .map-controls select, .map-controls input {{
    background: var(--card2); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 0.4rem 0.6rem; font-size: 0.78rem;
  }}
  .legend {{
    display: flex; gap: 1rem; align-items: center; margin-left: auto;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 0.3rem; font-size: 0.7rem; color: var(--muted); }}
  .legend-dot {{
    width: 12px; height: 12px; border-radius: 50%; display: inline-block;
  }}

  /* Table */
  .table-wrap {{
    margin: 1rem 2rem; background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
  }}
  .table-header {{
    padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;
  }}
  .filters {{ display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }}
  .filters label {{ color: var(--muted); font-size: 0.7rem; }}
  .filters select, .filters input {{
    background: var(--card2); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 0.35rem 0.5rem; font-size: 0.75rem;
  }}
  .btn {{
    background: var(--blue); color: white; border: none; border-radius: 6px;
    padding: 0.45rem 1rem; font-size: 0.75rem; font-weight: 600; cursor: pointer;
  }}
  .btn:hover {{ filter: brightness(1.15); }}
  .btn-red {{ background: var(--red); }}

  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left; padding: 0.6rem 0.75rem; font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim);
    border-bottom: 1px solid var(--border); cursor: pointer; white-space: nowrap;
  }}
  th:hover {{ color: var(--text); }}
  td {{
    padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(30,41,59,0.5);
    font-size: 0.78rem; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  tr:hover {{ background: rgba(59,130,246,0.06); }}
  tr {{ cursor: pointer; }}

  .cem-bar {{
    height: 6px; border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 6px;
  }}

  .pager {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.75rem 1.25rem; font-size: 0.75rem; color: var(--muted);
  }}
  .pager button {{
    background: var(--card2); color: var(--text); border: 1px solid var(--border);
    border-radius: 4px; padding: 0.3rem 0.7rem; font-size: 0.72rem; cursor: pointer;
    margin: 0 2px;
  }}
  .pager button:hover {{ border-color: var(--blue); }}
  .pager button:disabled {{ opacity: 0.3; cursor: default; }}
  .pager button.active {{ background: var(--blue); border-color: var(--blue); }}

  /* Overlay */
  .overlay {{
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center;
    padding: 2rem;
  }}
  .overlay.show {{ display: flex; }}
  .overlay-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    max-width: 700px; width: 100%; max-height: 80vh; overflow-y: auto; padding: 1.5rem;
    position: relative;
  }}
  .overlay-card .close {{
    position: absolute; top: 0.75rem; right: 1rem; font-size: 1.5rem;
    color: var(--dim); cursor: pointer; background: none; border: none;
  }}
  .overlay-card h2 {{ font-size: 0.95rem; margin-bottom: 0.75rem; padding-right: 2rem; }}
  .overlay-card .meta {{ color: var(--muted); font-size: 0.75rem; margin-bottom: 1rem; }}
  .overlay-card .meta a {{ color: var(--blue); }}
  .detail-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: 0.78rem;
  }}
  @media (max-width: 600px) {{ .detail-grid {{ grid-template-columns: 1fr; }} }}
  .detail-section h4 {{
    font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--dim); margin-bottom: 0.5rem; border-bottom: 1px solid var(--border);
    padding-bottom: 0.25rem;
  }}
  .detail-row {{ display: flex; gap: 0.5rem; margin-bottom: 0.25rem; }}
  .detail-row .dl {{ color: var(--muted); min-width: 80px; flex-shrink: 0; }}
  .detail-row .dv {{ color: var(--text); font-weight: 500; }}

  .footer {{
    text-align: center; padding: 1rem; color: var(--dim); font-size: 0.65rem;
    border-top: 1px solid var(--border);
  }}

  /* Territories tab */
  .territory-wrap {{ margin: 1rem 2rem; }}
  .territory-header {{ display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1.25rem; background: var(--card); border: 1px solid var(--border); border-radius: 10px 10px 0 0; }}
  .territory-header h3 {{ font-size: 0.9rem; font-weight: 700; }}
  .territory-table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-top: none; border-radius: 0 0 10px 10px; overflow: hidden; }}
  .territory-table th {{ padding: 0.6rem 0.75rem; background: var(--card2); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); border-bottom: 1px solid var(--border); text-align: left; }}
  .territory-table td {{ padding: 0.55rem 0.75rem; border-bottom: 1px solid rgba(30,41,59,0.4); font-size: 0.78rem; }}
  .territory-table tr:hover {{ background: rgba(59,130,246,0.05); }}
  .mgr-input {{ background: var(--card2); border: 1px solid var(--border); color: var(--text); border-radius: 5px; padding: 0.25rem 0.5rem; font-size: 0.75rem; width: 140px; }}
  .mgr-input:focus {{ border-color: var(--cyan); outline: none; }}
  .pe-bar {{ height: 8px; border-radius: 4px; background: var(--cyan); display: inline-block; }}

  /* Formula config panel */
  #formulaPanel {{
    display: none; position: fixed; top: 0; right: 0; width: 360px; height: 100%;
    background: var(--card); border-left: 1px solid var(--border); z-index: 900;
    overflow-y: auto; padding: 1.5rem; box-shadow: -10px 0 30px rgba(0,0,0,0.5);
  }}
  #formulaPanel.open {{ display: block; }}
  #formulaPanel h3 {{ font-size: 0.9rem; color: var(--cyan); margin-bottom: 1rem; }}
  .fp-section {{ background: var(--card2); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
  .fp-section h4 {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); margin-bottom: 0.75rem; }}
  .fp-row {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-size: 0.78rem; }}
  .fp-row label {{ min-width: 110px; color: var(--muted); }}
  .fp-row input[type=range] {{ flex: 1; accent-color: var(--cyan); cursor: pointer; }}
  .fp-row .fp-val {{ min-width: 45px; text-align: right; font-weight: 700; color: var(--cyan); font-size: 0.75rem; }}
  .fp-close {{ position: absolute; top: 1rem; right: 1rem; background: none; border: none; color: var(--dim); font-size: 1.3rem; cursor: pointer; }}
  .fp-close:hover {{ color: var(--text); }}
  .fp-note {{ font-size: 0.7rem; color: var(--dim); line-height: 1.5; margin-bottom: 0.5rem; }}

  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

  /* Date range slider */
  .date-filter {{
    padding: 0.85rem 2rem; background: var(--card); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
  }}
  .date-filter .lbl {{ color: var(--muted); font-size: 0.72rem; white-space: nowrap; }}
  .date-filter .date-val {{
    color: var(--cyan); font-weight: 700; font-size: 0.78rem; min-width: 80px; text-align: center;
  }}
  .slider-wrap {{
    position: relative; flex: 1; min-width: 200px; height: 28px; display: flex; align-items: center;
  }}
  .slider-wrap input[type=range] {{
    position: absolute; width: 100%; height: 4px; background: transparent;
    pointer-events: none; appearance: none; -webkit-appearance: none; outline: none;
  }}
  .slider-wrap input[type=range]::-webkit-slider-thumb {{
    appearance: none; -webkit-appearance: none; width: 16px; height: 16px;
    border-radius: 50%; background: var(--cyan); border: 2px solid var(--bg);
    pointer-events: all; cursor: pointer; box-shadow: 0 0 4px rgba(6,182,212,0.5);
  }}
  .slider-wrap input[type=range]::-moz-range-thumb {{
    width: 16px; height: 16px; border-radius: 50%; background: var(--cyan);
    border: 2px solid var(--bg); pointer-events: all; cursor: pointer;
  }}
  .slider-track {{
    position: absolute; width: 100%; height: 4px; border-radius: 2px;
    background: var(--border);
  }}
  .slider-range {{
    position: absolute; height: 4px; border-radius: 2px; background: var(--cyan);
  }}
  .date-filter .reset-btn {{
    background: none; border: 1px solid var(--border); color: var(--dim);
    border-radius: 5px; padding: 0.25rem 0.6rem; font-size: 0.7rem; cursor: pointer;
    white-space: nowrap;
  }}
  .date-filter .reset-btn:hover {{ border-color: var(--cyan); color: var(--cyan); }}
</style>
</head>
<body>

<div class="header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem">
  <div>
    <h1>Cement Demand Intelligence // <span>Greece</span></h1>
    <div class="sub">
      {total:,} άδειες | Est. <strong>{total_concrete:,.0f} m³ μπετόν</strong> (<strong>{total_cement:,.0f}t</strong> τσιμέντο) |
      {geocoded:,} στο χάρτη | {with_engineer:,} με μηχανικό | Πηγή: Diavgeia
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:0.75rem">
    <button id="refreshBtn" class="btn" onclick="startRefresh()" style="background:var(--green);padding:0.6rem 1.25rem;font-size:0.82rem;white-space:nowrap">
      Refresh Data
    </button>
  </div>
</div>

<!-- Refresh Modal -->
<div class="overlay" id="refreshOverlay" onclick="if(event.target===this)closeRefresh()">
  <div class="overlay-card" style="max-width:550px">
    <button class="close" onclick="closeRefresh()">&times;</button>
    <h2 id="refreshTitle" style="font-size:1rem">Checking for new permits...</h2>
    <div id="refreshEstimate" style="margin:1rem 0;font-size:0.85rem;color:var(--muted)"></div>
    <div id="refreshProgress" style="display:none">
      <div style="background:var(--card2);border-radius:6px;height:8px;overflow:hidden;margin:1rem 0">
        <div id="refreshBar" style="height:100%;background:var(--green);width:0%;transition:width 0.5s ease;border-radius:6px"></div>
      </div>
      <div id="refreshLog" style="font-family:monospace;font-size:0.72rem;color:var(--muted);max-height:180px;overflow-y:auto;background:var(--card2);border-radius:6px;padding:0.75rem;margin-top:0.75rem"></div>
    </div>
    <div id="refreshActions" style="margin-top:1rem;display:flex;gap:0.75rem">
      <button id="refreshConfirmBtn" class="btn" style="background:var(--green)" onclick="confirmRefresh()" disabled>Loading estimate...</button>
      <button class="btn" style="background:var(--card2);border:1px solid var(--border)" onclick="closeRefresh()">Cancel</button>
    </div>
  </div>
</div>

<div class="kpi-row">
  <div class="kpi"><div class="val" style="color:var(--cyan)">{total_concrete:,.0f} m³</div><div class="lbl">Σύνολο Μπετόν</div></div>
  <div class="kpi"><div class="val" style="color:var(--orange)">{total_cement:,.0f}t</div><div class="lbl">Τσιμέντο (εκτ.)</div></div>
  <div class="kpi"><div class="val" style="color:var(--text)">{total:,}</div><div class="lbl">Άδειες</div></div>
  <div class="kpi"><div class="val" style="color:var(--green)">{new_builds}</div><div class="lbl">Ανεγέρσεις</div></div>
  <div class="kpi"><div class="val" style="color:var(--purple)">{with_engineer:,}</div><div class="lbl">Με Μηχανικό</div></div>
</div>

<div class="date-filter">
  <span class="lbl">Date range</span>
  <span class="date-val" id="dateFromLabel">{date_min}</span>
  <div class="slider-wrap">
    <div class="slider-track"></div>
    <div class="slider-range" id="sliderRange"></div>
    <input type="range" id="sliderFrom" min="0" max="100" value="0" oninput="onSlider()">
    <input type="range" id="sliderTo"   min="0" max="100" value="100" oninput="onSlider()">
  </div>
  <span class="date-val" id="dateToLabel">{date_max}</span>
  <button class="reset-btn" onclick="resetDateFilter()">Reset</button>
  <span id="dateFilterCount" style="color:var(--dim);font-size:0.72rem"></span>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('map')">Map</div>
  <div class="tab" onclick="switchTab('table')">Permit Register</div>
  <div class="tab" onclick="switchTab('territories')">Territories</div>
</div>

<!-- MAP TAB -->
<div id="tab-map" class="tab-content active">
  <div class="map-controls">
    <label>Color by:</label>
    <select id="mapColor" onchange="updateMap()">
      <option value="cement">Cement (t)</option>
      <option value="use">Building Use</option>
    </select>
    <label>Min Cement:</label>
    <select id="mapMinCem" onchange="updateMap()">
      <option value="0">All</option>
      <option value="1">≥1t</option>
      <option value="5" selected>≥5t</option>
      <option value="15">≥15t</option>
      <option value="30">≥30t</option>
    </select>
    <label>View:</label>
    <select id="mapView" onchange="changeView()">
      <option value="greece">All Greece</option>
      <option value="attica">Attica</option>
      <option value="thessaloniki">Thessaloniki</option>
      <option value="crete">Crete</option>
    </select>
    <label style="margin-left:0.5rem">
      <input type="checkbox" id="heatToggle" onchange="toggleHeat()"> Heatmap
    </label>
    <label style="margin-left:0.5rem">
      <input type="checkbox" id="plantsToggle" onchange="togglePlants()" checked> Herakles Plants
    </label>
    <label style="margin-left:0.5rem">
      <input type="checkbox" id="circlesToggle" onchange="toggleCircles()"> 60km Zones
    </label>
    <button class="btn" onclick="toggleFormulaPanel()" style="font-size:0.72rem;background:var(--card2);border:1px solid var(--border);color:var(--muted)">Formula Config</button>
    <div class="legend">
      <div class="legend-item"><span class="legend-dot" style="background:var(--red)"></span> ≥30t</div>
      <div class="legend-item"><span class="legend-dot" style="background:var(--orange)"></span> ≥15t</div>
      <div class="legend-item"><span class="legend-dot" style="background:var(--blue)"></span> ≥5t</div>
      <div class="legend-item"><span class="legend-dot" style="background:var(--cyan)"></span> ≥1t</div>
      <div class="legend-item"><span class="legend-dot" style="background:var(--dim)"></span> <1t</div>
    </div>
  </div>
  <div class="map-container">
    <div id="map"></div>
  </div>
</div>

<!-- TABLE TAB -->
<div id="tab-table" class="tab-content">
  <div class="table-wrap">
    <div class="table-header">
      <div class="filters">
        <div><label>Min Cement</label><select id="fCem" onchange="filterTable()">
          <option value="0">All</option><option value="1">≥1t</option><option value="5">≥5t</option>
          <option value="15">≥15t</option><option value="30">≥30t</option>
        </select></div>
        <div><label>Use</label><select id="fUse" onchange="filterTable()">
          <option value="">All</option><option>Residential</option><option>Tourism</option>
          <option>Commercial</option><option>Industrial</option><option>Public</option>
        </select></div>
        <div><label>Construction</label><select id="fCon" onchange="filterTable()">
          <option value="">All</option><option>New Build</option><option>Addition</option>
          <option>Renovation</option><option>Change of Use</option>
        </select></div>
        <div><label>Search</label><input id="fSearch" placeholder="keyword..." oninput="filterTable()"></div>
        <button class="btn" onclick="exportCSV()">Export CSV</button>
      </div>
    </div>
    <div id="pagerTop" class="pager"></div>
    <table>
      <thead><tr>
        <th onclick="sortTable('date')">Date</th>
        <th onclick="sortTable('cem')">Cement (t)</th>
        <th onclick="sortTable('use')">Use</th>
        <th onclick="sortTable('stage')">Stage</th>
        <th onclick="sortTable('con')">Construction</th>
        <th onclick="sortTable('eng')">Engineer</th>
        <th onclick="sortTable('muni')">Location</th>
        <th onclick="sortTable('ada')">ADA</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div id="pagerBot" class="pager"></div>
  </div>
</div>

<!-- Territories Tab -->
<div id="tab-territories" class="tab-content">
  <div class="territory-wrap">
    <div class="territory-header">
      <h3>Διαχείριση Εδαφών — Περιφερειακές Ενότητες</h3>
      <div style="font-size:0.72rem;color:var(--dim)">Κλικ για ανάθεση Υπεύθυνου Πωλήσεων · Αποθηκεύεται αυτόματα</div>
    </div>
    <table class="territory-table">
      <thead><tr>
        <th>Περιφερειακή Ενότητα</th>
        <th>Άδειες</th>
        <th>Μπετόν (m³)</th>
        <th>Ανεγέρσεις</th>
        <th>Μπετόν / Άδεια</th>
        <th style="min-width:160px">Υπεύθυνος Πωλήσεων</th>
      </tr></thead>
      <tbody id="territoryTbody"></tbody>
    </table>
  </div>
</div>

<!-- Formula Config Panel -->
<div id="formulaPanel">
  <button class="fp-close" onclick="toggleFormulaPanel()">&times;</button>
  <h3>Formula Configuration — Μπετόν</h3>
  <div class="fp-note">Ρυθμίστε τις παραμέτρους εκτίμησης όγκου μπετόν. Οι αλλαγές εφαρμόζονται άμεσα στα δεδομένα.</div>

  <div class="fp-section">
    <h4>Ένταση Σκυροδέματος (m³ / m² δαπέδου)</h4>
    <div class="fp-row"><label>Κατοικία</label><input type="range" id="fpRes" min="5" max="35" value="15" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvRes">0.15</span></div>
    <div class="fp-row"><label>Τουρισμός</label><input type="range" id="fpTou" min="5" max="35" value="18" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvTou">0.18</span></div>
    <div class="fp-row"><label>Εμπορικό</label><input type="range" id="fpCom" min="5" max="35" value="20" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvCom">0.20</span></div>
    <div class="fp-row"><label>Βιομηχανικό</label><input type="range" id="fpInd" min="5" max="35" value="22" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvInd">0.22</span></div>
    <div class="fp-row"><label>Δημόσιο</label><input type="range" id="fpPub" min="5" max="35" value="20" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvPub">0.20</span></div>
    <div class="fp-row"><label>Άλλο</label><input type="range" id="fpOth" min="5" max="35" value="16" step="1" oninput="recomputeFormula()"><span class="fp-val" id="fvOth">0.16</span></div>
  </div>

  <div class="fp-section">
    <h4>Πολλαπλασιαστές</h4>
    <div class="fp-row"><label>Υπόγειο (+%)</label><input type="range" id="fpBsmt" min="10" max="80" value="40" step="5" oninput="recomputeFormula()"><span class="fp-val" id="fvBsmt">+40%</span></div>
    <div class="fp-row"><label>Τσιμέντο/Μπετόν</label><input type="range" id="fpCemRatio" min="200" max="400" value="300" step="10" oninput="recomputeFormula()"><span class="fp-val" id="fvCemRatio">300 kg/m³</span></div>
  </div>

  <div class="fp-section">
    <h4>Εκτιμώμενοι Σύνολοι</h4>
    <div style="font-size:0.82rem">
      <div style="display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid var(--border)"><span style="color:var(--muted)">Σύνολο Μπετόν</span><span id="fpTotalM3" style="color:var(--cyan);font-weight:700">—</span></div>
      <div style="display:flex;justify-content:space-between;padding:0.3rem 0"><span style="color:var(--muted)">Σύνολο Τσιμέντο</span><span id="fpTotalCem" style="color:var(--orange);font-weight:700">—</span></div>
    </div>
  </div>
  <button class="btn" style="width:100%;margin-top:0.5rem;font-size:0.78rem" onclick="resetFormula()">Reset Defaults</button>
</div>

<!-- Detail Overlay -->
<div class="overlay" id="overlay" onclick="if(event.target===this)closeOverlay()">
  <div class="overlay-card" id="overlayCard"></div>
</div>

<div class="footer">
  Cement estimation: floor area heuristic × concrete intensity (0.15–0.22 m³/m²) × 300 kg cement/m³ |
  Addresses extracted from official PDF permits via regex | Data: opendata.diavgeia.gov.gr
</div>

<script>
const MARKERS = {markers_json};
const TABLE = {table_json};
const HERACLES_PLANTS = {plants_json};

// ── Map ──
let map, markerLayer, heatLayer;
const views = {{
  greece: [38.5, 24.0, 6],
  attica: [37.98, 23.73, 11],
  thessaloniki: [40.63, 22.94, 11],
  crete: [35.24, 24.90, 9],
}};

let plantLayer, circleLayer;

function initMap() {{
  map = L.map('map', {{ zoomControl: true }}).setView([38.5, 24.0], 6);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 18,
  }}).addTo(map);
  markerLayer = L.layerGroup().addTo(map);
  plantLayer = L.layerGroup().addTo(map);
  circleLayer = L.layerGroup();

  for (const pl of HERACLES_PLANTS) {{
    const isCement = pl.type === 'Cement';
    const color = isCement ? '#ef4444' : '#f59e0b';
    const icon = L.divIcon({{
      html: '<div style="background:' + color + ';border:2px solid #fff;width:' + (isCement?14:10) + 'px;height:' + (isCement?14:10) + 'px;border-radius:' + (isCement?'2px':'50%') + ';box-shadow:0 0 6px rgba(0,0,0,0.5)"></div>',
      iconSize: [isCement?14:10, isCement?14:10],
      iconAnchor: [isCement?7:5, isCement?7:5],
      className: ''
    }});
    L.marker([pl.lat, pl.lng], {{icon}}).addTo(plantLayer)
      .bindPopup('<div style="font-size:12px;font-weight:700;color:#e2e8f0;background:#1a2234;padding:0.4rem 0.6rem;border-radius:6px">' + pl.name + '<br><span style="color:#f59e0b;font-size:10px">' + pl.type + '</span></div>');
  }}

  updateMap();
}}

function togglePlants() {{
  if (document.getElementById('plantsToggle').checked) {{
    plantLayer.addTo(map);
  }} else {{
    map.removeLayer(plantLayer);
  }}
}}

function toggleCircles() {{
  if (document.getElementById('circlesToggle').checked) {{
    circleLayer.clearLayers();
    for (const pl of HERACLES_PLANTS) {{
      L.circle([pl.lat, pl.lng], {{
        radius: 60000,
        color: pl.type === 'Cement' ? '#ef4444' : '#f59e0b',
        fillColor: pl.type === 'Cement' ? '#ef4444' : '#f59e0b',
        fillOpacity: 0.04,
        weight: 1,
        dashArray: '4 4',
      }}).addTo(circleLayer);
    }}
    circleLayer.addTo(map);
  }} else {{
    map.removeLayer(circleLayer);
  }}
}}

function cemColor(cem) {{
  if (cem >= 30) return '#ef4444';
  if (cem >= 15) return '#f59e0b';
  if (cem >= 5) return '#3b82f6';
  if (cem >= 1) return '#06b6d4';
  return '#64748b';
}}

const useColors = {{
  Residential: '#3b82f6', Tourism: '#06b6d4', Commercial: '#f59e0b',
  Industrial: '#a855f7', Public: '#ef4444', Other: '#64748b', Energy: '#22c55e',
}};

function updateMap() {{
  const minCem = parseFloat(document.getElementById('mapMinCem').value);
  const colorBy = document.getElementById('mapColor').value;
  markerLayer.clearLayers();

  const filtered = MARKERS.filter(m => m.cem >= minCem && (!dateFrom || (m.date >= dateFrom && m.date <= dateTo)));

  for (const m of filtered) {{
    const color = colorBy === 'use' ? (useColors[m.use] || '#64748b') : cemColor(m.cem);
    const radius = Math.max(4, Math.min(20, Math.sqrt(m.cem) * 2.5));

    const circle = L.circleMarker([m.lat, m.lng], {{
      radius: radius,
      fillColor: color,
      color: color,
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.5,
    }});

    circle.bindPopup(`
      <div style="font-size:12px;max-width:300px">
        <strong>${{m.desc}}</strong><br>
        <span style="color:#f59e0b;font-weight:700">${{m.cem}}t cement</span> | ${{m.area ? m.area + ' m²' : '—'}}<br>
        ${{m.muni}}${{m.city ? ', ' + m.city : ''}} ${{m.street ? '— ' + m.street : ''}}<br>
        ${{m.eng ? 'Eng: ' + m.eng + (m.tee ? ' (TEE ' + m.tee + ')' : '') : ''}}<br>
        <small>${{m.date}} | ${{m.use}} | ${{m.con}}</small><br>
        <a href="https://diavgeia.gov.gr/decision/view/${{m.ada}}" target="_blank" style="color:#3b82f6">${{m.ada}}</a>
      </div>
    `);
    circle.addTo(markerLayer);
  }}

  // Update heat layer if active
  if (document.getElementById('heatToggle').checked) {{
    if (heatLayer) map.removeLayer(heatLayer);
    const heatData = filtered.map(m => [m.lat, m.lng, m.cem]);
    heatLayer = L.heatLayer(heatData, {{
      radius: 25, blur: 20, maxZoom: 12, max: 50,
      gradient: {{0.2: '#06b6d4', 0.4: '#3b82f6', 0.6: '#f59e0b', 0.8: '#ef4444', 1: '#ff0000'}}
    }}).addTo(map);
  }}
}}

function changeView() {{
  const v = document.getElementById('mapView').value;
  const [lat, lng, zoom] = views[v];
  map.setView([lat, lng], zoom);
}}

function toggleHeat() {{
  if (!document.getElementById('heatToggle').checked && heatLayer) {{
    map.removeLayer(heatLayer);
    heatLayer = null;
  }} else {{
    updateMap();
  }}
}}

// ── Tabs ──
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach((t, i) => {{
    t.classList.toggle('active',
      (name==='map'&&i===0)||(name==='table'&&i===1)||(name==='territories'&&i===2));
  }});
  ['map','table','territories'].forEach(n => {{
    document.getElementById('tab-'+n).classList.toggle('active', name===n);
  }});
  if (name === 'map') setTimeout(() => map.invalidateSize(), 100);
  if (name === 'territories' && !territoriesRendered) renderTerritories();
}}

// ── Date slider ──
const ALL_DATES = [...new Set([...MARKERS.map(m => m.date), ...TABLE.map(t => t.date)])]
  .filter(d => d && /^\d{{4}}-\d{{2}}-\d{{2}}$/.test(d)).sort();
const DATE_MIN = ALL_DATES[0] || '{date_min}';
const DATE_MAX = ALL_DATES[ALL_DATES.length - 1] || '{date_max}';

// null means "no filter active" — show everything
let dateFrom = null, dateTo = null;

function dateAtPct(pct) {{
  const idx = Math.round((pct / 100) * (ALL_DATES.length - 1));
  return ALL_DATES[Math.min(Math.max(idx, 0), ALL_DATES.length - 1)];
}}

function onSlider() {{
  let lo = parseFloat(document.getElementById('sliderFrom').value);
  let hi = parseFloat(document.getElementById('sliderTo').value);
  if (lo > hi) {{ lo = hi; document.getElementById('sliderFrom').value = lo; }}
  dateFrom = dateAtPct(lo);
  dateTo   = dateAtPct(hi);
  document.getElementById('dateFromLabel').textContent = dateFrom || DATE_MIN;
  document.getElementById('dateToLabel').textContent   = dateTo   || DATE_MAX;
  const range = document.getElementById('sliderRange');
  range.style.left  = lo + '%';
  range.style.width = (hi - lo) + '%';
  filterTable();
  updateMap();
  const count = TABLE.filter(r => !dateFrom || (r.date >= dateFrom && r.date <= dateTo)).length;
  document.getElementById('dateFilterCount').textContent = count.toLocaleString() + ' permits';
}}

function resetDateFilter() {{
  dateFrom = null; dateTo = null;
  document.getElementById('sliderFrom').value = 0;
  document.getElementById('sliderTo').value   = 100;
  document.getElementById('dateFromLabel').textContent = DATE_MIN;
  document.getElementById('dateToLabel').textContent   = DATE_MAX;
  const range = document.getElementById('sliderRange');
  range.style.left = '0%'; range.style.width = '100%';
  document.getElementById('dateFilterCount').textContent = TABLE.length.toLocaleString() + ' permits';
  filterTable();
  updateMap();
}}

// ── Table ──
let filtered = [...TABLE];
let sortCol = 'cem', sortDir = -1, page = 0;
const PAGE_SIZE = 50;

function filterTable() {{
  const minCem = parseFloat(document.getElementById('fCem').value);
  const use = document.getElementById('fUse').value;
  const con = document.getElementById('fCon').value;
  const search = document.getElementById('fSearch').value.toUpperCase();

  filtered = TABLE.filter(r =>
    r.cem >= minCem &&
    (!use || r.use === use) &&
    (!con || r.con === con) &&
    (!dateFrom || (r.date >= dateFrom && r.date <= dateTo)) &&
    (!search || r.sub.toUpperCase().includes(search) || r.ada.toUpperCase().includes(search) ||
     r.eng.toUpperCase().includes(search) || r.muni.toUpperCase().includes(search))
  );
  page = 0;
  doSort();
}}

function sortTable(col) {{
  if (sortCol === col) sortDir *= -1;
  else {{ sortCol = col; sortDir = (col === 'cem' || col === 'area') ? -1 : 1; }}
  doSort();
}}

function doSort() {{
  filtered.sort((a, b) => {{
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'number') return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  }});
  renderTable();
}}

function renderTable() {{
  const start = page * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  const maxCem = Math.max(...filtered.map(r => r.cem), 1);

  const rows = slice.map(r => {{
    const barW = Math.max(0, Math.min(100, (r.cem / maxCem) * 100));
    const barColor = r.cem >= 30 ? 'var(--red)' : r.cem >= 15 ? 'var(--orange)' : r.cem >= 5 ? 'var(--blue)' : 'var(--cyan)';
    const engDisplay = r.eng ? (r.eng + (r.tee ? ' <span style="color:var(--dim);font-size:0.68rem">(TEE ' + r.tee + ')</span>' : '')) : '<span style="color:var(--dim)">—</span>';
    const locDisplay = r.muni || r.city || '<span style="color:var(--dim)">—</span>';

    return '<tr onclick="showDetail(\\'' + r.ada.replace(/'/g, "\\\\'") + '\\')">' +
      '<td>' + r.date + '</td>' +
      '<td><span class="cem-bar" style="width:' + barW + '%;background:' + barColor + '"></span>' + r.cem.toFixed(1) + '</td>' +
      '<td>' + r.use + '</td>' +
      '<td>' + r.stage + '</td>' +
      '<td>' + r.con + '</td>' +
      '<td>' + engDisplay + '</td>' +
      '<td>' + locDisplay + '</td>' +
      '<td><a href="https://diavgeia.gov.gr/decision/view/' + r.ada + '" target="_blank" onclick="event.stopPropagation()" style="color:var(--blue);text-decoration:none">' + r.ada + '</a></td>' +
      '</tr>';
  }}).join('');

  document.getElementById('tbody').innerHTML = rows;

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pagerHtml = '<div>Showing ' + (start + 1) + '–' + Math.min(start + PAGE_SIZE, filtered.length) + ' of ' + filtered.length.toLocaleString() + '</div>' +
    '<div>' + buildPager(totalPages) + '</div>';
  document.getElementById('pagerTop').innerHTML = pagerHtml;
  document.getElementById('pagerBot').innerHTML = pagerHtml;
}}

function buildPager(totalPages) {{
  let btns = '<button ' + (page === 0 ? 'disabled' : 'onclick="goPage(' + (page - 1) + ')"') + '>Prev</button>';
  const show = [];
  for (let i = 0; i < Math.min(7, totalPages); i++) show.push(i);
  if (totalPages > 8) {{ show.push(-1); show.push(totalPages - 1); }}
  for (const i of show) {{
    if (i === -1) {{ btns += '<span style="color:var(--dim)">...</span>'; continue; }}
    btns += '<button class="' + (i === page ? 'active' : '') + '" onclick="goPage(' + i + ')">' + (i + 1) + '</button>';
  }}
  btns += '<button ' + (page >= totalPages - 1 ? 'disabled' : 'onclick="goPage(' + (page + 1) + ')"') + '>Next</button>';
  return btns;
}}

function goPage(p) {{ page = p; renderTable(); }}

// ── Detail Overlay ──
function showDetail(ada) {{
  const r = TABLE.find(t => t.ada === ada);
  if (!r) return;
  const m = MARKERS.find(x => x.ada === ada);

  let html = '<button class="close" onclick="closeOverlay()">×</button>';
  html += '<h2>' + r.sub + '</h2>';
  html += '<div class="meta"><a href="https://diavgeia.gov.gr/decision/view/' + r.ada + '" target="_blank">ADA: ' + r.ada + '</a>';
  html += ' | ' + r.date + ' | Est. cement: <strong style="color:var(--orange)">' + r.cem.toFixed(1) + ' tonnes</strong>';
  if (r.area) html += ' | ' + r.area + ' m²';
  html += '</div>';

  html += '<div class="detail-grid">';

  // Location
  html += '<div class="detail-section"><h4>Location</h4>';
  if (r.street) html += '<div class="detail-row"><span class="dl">Street</span><span class="dv">' + r.street + '</span></div>';
  if (r.city) html += '<div class="detail-row"><span class="dl">City</span><span class="dv">' + r.city + '</span></div>';
  if (r.muni) html += '<div class="detail-row"><span class="dl">Municipality</span><span class="dv">' + r.muni + '</span></div>';
  html += '<div class="detail-row"><span class="dl">Use</span><span class="dv">' + r.use + '</span></div>';
  html += '<div class="detail-row"><span class="dl">Stage</span><span class="dv">' + r.stage + '</span></div>';
  html += '<div class="detail-row"><span class="dl">Type</span><span class="dv">' + r.con + '</span></div>';
  html += '</div>';

  // Engineer
  html += '<div class="detail-section"><h4>Engineer / Contact</h4>';
  if (r.eng) {{
    html += '<div class="detail-row"><span class="dl">Name</span><span class="dv">' + r.eng + '</span></div>';
    if (r.tee) html += '<div class="detail-row"><span class="dl">TEE #</span><span class="dv">' + r.tee + '</span></div>';
    const searchQ = encodeURIComponent('"' + r.eng + '" μηχανικός τηλέφωνο' + (r.muni ? ' ' + r.muni : ''));
    html += '<div style="margin-top:0.75rem">';
    html += '<a href="https://www.google.com/search?q=' + searchQ + '" target="_blank" class="btn" ' +
      'style="font-size:0.72rem;display:inline-flex;align-items:center;gap:0.35rem;background:var(--green);text-decoration:none">' +
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81 19.79 19.79 0 01.22 1.18 2 2 0 012.18 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.91 7.91a16 16 0 006.29 6.29l1.28-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>' +
      'Find Contact</a>';
    html += '</div>';
  }} else {{
    html += '<div style="color:var(--dim)">Parse PDF for engineer data</div>';
  }}
  html += '<div style="margin-top:0.5rem"><a href="https://diavgeia.gov.gr/doc/' + r.ada + '" target="_blank" class="btn" style="font-size:0.72rem;display:inline-block">Download PDF</a></div>';
  html += '</div>';

  html += '</div>';

  document.getElementById('overlayCard').innerHTML = html;
  document.getElementById('overlay').classList.add('show');
}}

function closeOverlay() {{ document.getElementById('overlay').classList.remove('show'); }}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeOverlay(); }});

// ── CSV Export ──
function exportCSV() {{
  const header = 'Date,Cement_t,Use,Stage,Construction,Engineer,TEE,Municipality,City,Street,Area_m2,ADA\\n';
  const rows = filtered.map(r =>
    [r.date, r.cem, r.use, r.stage, r.con,
     '"' + r.eng.replace(/"/g, '""') + '"', r.tee,
     '"' + r.muni.replace(/"/g, '""') + '"',
     '"' + r.city.replace(/"/g, '""') + '"',
     '"' + r.street.replace(/"/g, '""') + '"',
     r.area, r.ada].join(',')
  ).join('\\n');
  const blob = new Blob([header + rows], {{type: 'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'cement_demand_permits.csv';
  a.click();
}}

// ── Refresh ──
const REFRESH_API = 'http://localhost:8787';
let refreshPollTimer = null;

function startRefresh() {{
  document.getElementById('refreshOverlay').classList.add('show');
  document.getElementById('refreshTitle').textContent = 'Checking for new permits...';
  document.getElementById('refreshEstimate').innerHTML = '<span style="color:var(--dim)">Probing Diavgeia API...</span>';
  document.getElementById('refreshProgress').style.display = 'none';
  document.getElementById('refreshConfirmBtn').disabled = true;
  document.getElementById('refreshConfirmBtn').textContent = 'Loading estimate...';

  fetch(REFRESH_API + '/api/estimate')
    .then(r => r.json())
    .then(est => {{
      if (est.error) {{
        document.getElementById('refreshTitle').textContent = 'Could not reach refresh server';
        document.getElementById('refreshEstimate').innerHTML =
          '<div style="color:var(--red);margin-bottom:0.75rem">Start the refresh server first:</div>' +
          '<code style="background:var(--card2);padding:0.5rem 0.75rem;border-radius:6px;display:block;color:var(--cyan)">python incremental_refresh.py</code>';
        return;
      }}
      document.getElementById('refreshTitle').textContent =
        est.estimated_new_permits === 0 ? 'Data is up to date' : est.estimated_new_permits + ' new permits found';

      let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem 1.5rem;margin-bottom:1rem">';
      html += '<div>Existing permits</div><div style="color:var(--text);font-weight:600">' + est.existing_permits.toLocaleString() + '</div>';
      html += '<div>Last scraped</div><div style="color:var(--text);font-weight:600">' + est.last_scrape_date + '</div>';
      html += '<div>Estimated new</div><div style="color:var(--green);font-weight:600">' + est.estimated_new_permits.toLocaleString() + '</div>';
      html += '<div>Parsed PDFs cached</div><div style="color:var(--text);font-weight:600">' + est.existing_parsed.toLocaleString() + '</div>';
      html += '</div>';

      if (est.estimated_new_permits > 0) {{
        html += '<div style="background:var(--card2);border-radius:8px;padding:0.75rem;margin-bottom:0.5rem">';
        html += '<div style="font-weight:600;margin-bottom:0.5rem;color:var(--cyan)">Estimated time: ~' + est.estimated_minutes + ' min</div>';
        html += '<div style="font-size:0.72rem;color:var(--dim)">';
        html += 'API scrape: ~' + est.breakdown.api_scrape_secs + 's · ';
        html += 'PDF download: ~' + est.breakdown.pdf_download_secs + 's · ';
        html += 'Geocode: ~' + est.breakdown.geocode_secs + 's · ';
        html += 'Dashboard: ~' + est.breakdown.dashboard_secs + 's';
        html += '</div></div>';
      }}

      document.getElementById('refreshEstimate').innerHTML = html;
      const btn = document.getElementById('refreshConfirmBtn');
      if (est.estimated_new_permits > 0) {{
        btn.disabled = false;
        btn.textContent = 'Start Refresh (' + est.estimated_new_permits + ' new)';
      }} else {{
        btn.disabled = false;
        btn.textContent = 'Force Refresh';
      }}
    }})
    .catch(err => {{
      document.getElementById('refreshTitle').textContent = 'Refresh server not running';
      document.getElementById('refreshEstimate').innerHTML =
        '<div style="color:var(--red);margin-bottom:0.75rem">Start the refresh server:</div>' +
        '<code style="background:var(--card2);padding:0.5rem 0.75rem;border-radius:6px;display:block;color:var(--cyan)">python incremental_refresh.py</code>' +
        '<div style="margin-top:0.75rem;color:var(--dim);font-size:0.75rem">Then open <strong>http://localhost:8787</strong> in your browser.</div>';
    }});
}}

function confirmRefresh() {{
  document.getElementById('refreshConfirmBtn').disabled = true;
  document.getElementById('refreshConfirmBtn').textContent = 'Running...';
  document.getElementById('refreshProgress').style.display = 'block';
  document.getElementById('refreshLog').innerHTML = '';
  document.getElementById('refreshBar').style.width = '0%';

  fetch(REFRESH_API + '/api/refresh', {{ method: 'POST' }})
    .then(r => r.json())
    .then(data => {{
      if (data.error) {{
        document.getElementById('refreshLog').innerHTML += '<div style="color:var(--red)">' + data.error + '</div>';
        return;
      }}
      // Start polling for progress
      refreshPollTimer = setInterval(pollRefreshStatus, 1500);
    }})
    .catch(err => {{
      document.getElementById('refreshLog').innerHTML += '<div style="color:var(--red)">Failed to start: ' + err + '</div>';
    }});
}}

function pollRefreshStatus() {{
  fetch(REFRESH_API + '/api/status')
    .then(r => r.json())
    .then(status => {{
      const log = document.getElementById('refreshLog');
      log.innerHTML = status.progress.map(p =>
        '<div>' + p.time + ' [' + p.step + '] ' + p.message + '</div>'
      ).join('');
      log.scrollTop = log.scrollHeight;

      // Update progress bar
      const lastPct = status.progress.length > 0 ? status.progress[status.progress.length - 1].pct : 0;
      if (lastPct > 0) {{
        document.getElementById('refreshBar').style.width = lastPct + '%';
      }}

      if (!status.running) {{
        clearInterval(refreshPollTimer);
        if (status.result && status.result.success) {{
          document.getElementById('refreshTitle').textContent = 'Refresh Complete!';
          document.getElementById('refreshBar').style.width = '100%';
          document.getElementById('refreshBar').style.background = 'var(--green)';
          const btn = document.getElementById('refreshConfirmBtn');
          btn.textContent = 'Reload Dashboard';
          btn.disabled = false;
          btn.onclick = () => window.location.reload();
          btn.style.background = 'var(--cyan)';
        }} else if (status.error) {{
          document.getElementById('refreshTitle').textContent = 'Refresh Failed';
          document.getElementById('refreshBar').style.background = 'var(--red)';
        }}
      }}
    }})
    .catch(() => {{}});
}}

function closeRefresh() {{
  document.getElementById('refreshOverlay').classList.remove('show');
  if (refreshPollTimer) clearInterval(refreshPollTimer);
}}

// ── Formula Config ──
function toggleFormulaPanel() {{
  document.getElementById('formulaPanel').classList.toggle('open');
  recomputeFormula();
}}

function recomputeFormula() {{
  const getV = id => parseFloat(document.getElementById(id).value);
  const intensities = {{
    Residential: getV('fpRes') / 100,
    Tourism: getV('fpTou') / 100,
    Commercial: getV('fpCom') / 100,
    Industrial: getV('fpInd') / 100,
    Public: getV('fpPub') / 100,
  }};
  const bsmtPct = getV('fpBsmt') / 100;
  const cemRatio = getV('fpCemRatio');

  document.getElementById('fvRes').textContent = (getV('fpRes')/100).toFixed(2);
  document.getElementById('fvTou').textContent = (getV('fpTou')/100).toFixed(2);
  document.getElementById('fvCom').textContent = (getV('fpCom')/100).toFixed(2);
  document.getElementById('fvInd').textContent = (getV('fpInd')/100).toFixed(2);
  document.getElementById('fvPub').textContent = (getV('fpPub')/100).toFixed(2);
  document.getElementById('fvOth').textContent = (getV('fpOth')/100).toFixed(2);
  document.getElementById('fvBsmt').textContent = '+' + getV('fpBsmt') + '%';
  document.getElementById('fvCemRatio').textContent = cemRatio + ' kg/m³';

  let totalM3 = 0;
  for (const r of TABLE) {{
    if (r.m3 && r.m3 > 0) {{ totalM3 += r.m3; continue; }}
    const intens = intensities[r.use] || (getV('fpOth')/100);
    totalM3 += (r.area || 0) * intens * (1 + bsmtPct);
  }}
  const totalCem = totalM3 * cemRatio / 1000;
  document.getElementById('fpTotalM3').textContent = Math.round(totalM3).toLocaleString() + ' m³';
  document.getElementById('fpTotalCem').textContent = Math.round(totalCem).toLocaleString() + ' t';
}}

function resetFormula() {{
  document.getElementById('fpRes').value = 15;
  document.getElementById('fpTou').value = 18;
  document.getElementById('fpCom').value = 20;
  document.getElementById('fpInd').value = 22;
  document.getElementById('fpPub').value = 20;
  document.getElementById('fpOth').value = 16;
  document.getElementById('fpBsmt').value = 40;
  document.getElementById('fpCemRatio').value = 300;
  recomputeFormula();
}}

// ── Territories ──
let territoriesRendered = false;
const TERRITORY_MANAGERS = JSON.parse(localStorage.getItem('territoryManagers') || '{{}}');

function saveTerritoryManagers() {{
  localStorage.setItem('territoryManagers', JSON.stringify(TERRITORY_MANAGERS));
}}

function saveMgr(input) {{
  const pe = input.dataset.pe;
  TERRITORY_MANAGERS[pe] = input.value;
  saveTerritoryManagers();
}}

function renderTerritories() {{
  territoriesRendered = true;

  // Aggregate by PE
  const peStats = {{}};
  for (const r of TABLE) {{
    const pe = r.pe || '(Άγνωστη ΠΕ)';
    if (!peStats[pe]) peStats[pe] = {{ permits: 0, m3: 0, newBuilds: 0 }};
    peStats[pe].permits++;
    peStats[pe].m3 += r.m3 || 0;
    if (r.con === 'New Build') peStats[pe].newBuilds++;
  }}

  const sorted = Object.entries(peStats).sort((a, b) => b[1].m3 - a[1].m3);
  const maxM3 = sorted.length > 0 ? sorted[0][1].m3 : 1;

  const rows = sorted.map(([pe, s]) => {{
    const barPct = Math.round((s.m3 / maxM3) * 100);
    const perPermit = s.permits > 0 ? (s.m3 / s.permits).toFixed(1) : '—';
    const mgr = TERRITORY_MANAGERS[pe] || '';
    return '<tr>' +
      '<td><strong>' + pe + '</strong></td>' +
      '<td>' + s.permits.toLocaleString() + '</td>' +
      '<td><span class="pe-bar" style="width:' + barPct + 'px;max-width:120px"></span> ' + Math.round(s.m3).toLocaleString() + '</td>' +
      '<td>' + s.newBuilds.toLocaleString() + '</td>' +
      '<td>' + perPermit + '</td>' +
      '<td><input class="mgr-input" value="' + mgr.replace(/"/g, '&quot;') + '" placeholder="π.χ. Γ. Παπαδόπουλος" data-pe="' + pe.replace(/"/g, '&quot;') + '" onchange="saveMgr(this)"></td>' +
      '</tr>';
  }}).join('');

  document.getElementById('territoryTbody').innerHTML = rows;
}}

// ── Init ──
initMap();
setTimeout(() => map.invalidateSize(), 100);
filterTable();
// Init slider labels/track display without filtering
document.getElementById('dateFromLabel').textContent = DATE_MIN;
document.getElementById('dateToLabel').textContent   = DATE_MAX;
document.getElementById('sliderRange').style.left  = '0%';
document.getElementById('sliderRange').style.width = '100%';
document.getElementById('dateFilterCount').textContent = TABLE.length.toLocaleString() + ' permits';
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"\n  Dashboard saved → {output_path} ({output_path.stat().st_size:,} bytes)")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  BATCH PDF EXTRACTION + MAP GENERATION")
    print("=" * 70)

    # Load permits
    df = pd.read_csv(DATA_DIR / "permits_with_cement.csv")
    df["issue_date"] = pd.to_datetime(df["issue_date"])

    # Filter: since Jan 1 2026, with cement > 0
    mask = (df["issue_date"] >= "2026-01-01") & (df["cement_tonnes"] > 0)
    target = df[mask].copy()
    print(f"\n  Target permits: {len(target)} (since 2026-01-01, cement > 0)")

    # Get ADA list
    ada_list = target["ada"].tolist()

    # Check for cached parsed data
    parsed_path = DATA_DIR / "parsed_permits.json"
    if parsed_path.exists():
        with open(parsed_path) as f:
            parsed = json.load(f)
        print(f"  Loaded {len(parsed)} cached parsed permits")
        # Download only missing ones
        parsed_adas = {p["ada"] for p in parsed}
        missing = [a for a in ada_list if a not in parsed_adas]
        if missing:
            print(f"  Downloading {len(missing)} new permits...")
            new_parsed = batch_download_and_parse(missing, max_workers=10)
            parsed.extend(new_parsed)
    else:
        # Batch download and parse
        parsed = batch_download_and_parse(ada_list, max_workers=10)

    print(f"\n  Successfully parsed: {len(parsed)} permits with address data")

    # Save parsed data
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    print(f"  Saved → {parsed_path.name}")

    # Pre-geocode unique municipalities (Nominatim for unknowns)
    print("\n  Geocoding municipalities...")
    geocode_cache = batch_geocode_unique(parsed)

    # Generate map dashboard (use full dataset for table, parsed for map)
    output_path = DATA_DIR / "titan_demo.html"
    generate_map_dashboard(df[df["issue_date"] >= "2026-01-01"], parsed, output_path)

    print(f"\n  Open: file://{output_path}")


if __name__ == "__main__":
    main()
