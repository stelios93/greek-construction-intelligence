#!/usr/bin/env python3
"""
Refresh all data: re-fetch from Diavgeia, re-estimate cement, re-parse PDFs, regenerate dashboard.
"""
import sys
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pipeline import DiavgeiaPermitScraper
from titan_v2 import classify_and_estimate
from batch_extract_map import (
    batch_download_and_parse, batch_geocode_unique, generate_map_dashboard,
    DATA_DIR
)

def main():
    print("=" * 70)
    print("  FULL DATA REFRESH — " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 70)

    # ── Step 1: Re-fetch from Diavgeia API ──
    print("\n[1/5] Fetching permits from Diavgeia API...")
    scraper = DiavgeiaPermitScraper()
    from_date = datetime(2026, 1, 1)
    to_date = datetime.now()
    scraper.run(from_date=from_date, to_date=to_date, max_pages=50)

    df = scraper.to_dataframe()
    csv_path = DATA_DIR / "diavgeia_building_permits.csv"
    df.to_csv(csv_path, index=False)
    print(f"  Saved {len(df)} permits → {csv_path.name}")

    # ── Step 2: Re-run cement estimation ──
    print("\n[2/5] Running cement estimation...")
    df = pd.read_csv(csv_path)
    results = df["subject"].apply(classify_and_estimate).apply(pd.Series)
    for col in results.columns:
        df[col] = results[col]
    df.rename(columns={"cement_tonnes": "cement_tonnes", "est_floor_area": "est_floor_area_m2"}, inplace=True)
    if "est_floor_area" in df.columns:
        df.rename(columns={"est_floor_area": "est_floor_area_m2"}, inplace=True)

    cement_csv = DATA_DIR / "permits_with_cement.csv"
    df.to_csv(cement_csv, index=False)
    total_cem = df["cement_tonnes"].sum()
    print(f"  Saved {len(df)} permits with cement estimates → {cement_csv.name}")
    print(f"  Total cement: {total_cem:,.0f}t across {len(df)} permits")

    # ── Step 3: Download & parse new PDFs ──
    print("\n[3/5] Downloading & parsing new permit PDFs...")
    df["issue_date"] = pd.to_datetime(df["issue_date"])
    mask = (df["issue_date"] >= "2026-01-01") & (df["cement_tonnes"] > 0)
    target = df[mask].copy()
    ada_list = target["ada"].tolist()

    parsed_path = DATA_DIR / "parsed_permits.json"
    if parsed_path.exists():
        with open(parsed_path) as f:
            parsed = json.load(f)
        print(f"  Loaded {len(parsed)} cached parsed permits")
        parsed_adas = {p["ada"] for p in parsed}
        missing = [a for a in ada_list if a not in parsed_adas]
        if missing:
            print(f"  Downloading {len(missing)} new permits...")
            new_parsed = batch_download_and_parse(missing, max_workers=10)
            parsed.extend(new_parsed)
            # Save updated parsed data
            with open(parsed_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
        else:
            print("  All permits already cached")
    else:
        parsed = batch_download_and_parse(ada_list, max_workers=10)
        with open(parsed_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)

    print(f"  Total parsed permits: {len(parsed)}")

    # ── Step 4: Geocode ──
    print("\n[4/5] Geocoding municipalities...")
    geocode_cache = batch_geocode_unique(parsed)

    # ── Step 5: Generate dashboard ──
    print("\n[5/5] Generating dashboard...")
    output_path = DATA_DIR / "titan_demo.html"
    generate_map_dashboard(df[df["issue_date"] >= "2026-01-01"], parsed, output_path)

    print(f"\n{'=' * 70}")
    print(f"  DONE — {len(df)} total permits, {len(parsed)} parsed, {total_cem:,.0f}t cement")
    print(f"  Dashboard: {output_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
