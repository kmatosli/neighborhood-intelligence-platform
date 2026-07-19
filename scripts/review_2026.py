"""Read-only review of the 2026 crime data, plus a reviewable Woodlawn CSV.

Reads Bronze and Silver, writes ONE new file under data/review/ (which is gitignored along
with the rest of data/). Bronze and Silver are opened read-only and are never modified.

    uv run python scripts/review_2026.py

The CSV contains only fields the City of Chicago already publishes. Locations are
block-level, as published — Chicago redacts the house number. Nothing here may be rendered
in the public UI, which shows neighborhood-level figures only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from bw_observatory.config import Settings

YEAR = 2026

BRONZE_FIELDS = [
    "id",
    "case_number",
    "date",
    "block",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "latitude",
    "longitude",
]

CSV_FIELDS = [
    "date",
    "block",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "latitude",
    "longitude",
    "neighborhood_woodlawn",
    "geography_status",
]

REVIEW_PATH = Path("data/review/woodlawn_2026_incidents.csv")


def rule(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    settings = Settings()
    data_dir = settings.data_dir

    bronze_path = data_dir / "bronze" / "crime" / f"{YEAR}.parquet"
    silver_path = data_dir / "silver" / "crime" / "crime_with_geography" / f"{YEAR}.parquet"

    if not bronze_path.exists():
        print(f"ERROR: no Bronze data for {YEAR}.")
        return 2
    if not silver_path.exists():
        print(f"ERROR: {YEAR} has not been enriched. Run enrich_crime_geography.py --year {YEAR}.")
        return 2

    before = hashlib.sha256(bronze_path.read_bytes()).hexdigest()

    bronze = pd.read_parquet(bronze_path, columns=BRONZE_FIELDS)
    silver = pd.read_parquet(silver_path)

    # Silver carries the spatial assignment; Bronze carries the incident's own fields.
    joined = silver.merge(bronze, on="id", how="left")
    joined["_when"] = pd.to_datetime(joined["date"], errors="coerce")

    print("=" * 78)
    print(f"{YEAR} CRIME DATA REVIEW - read-only")
    print("=" * 78)
    print(f"Bronze: {bronze_path}")
    print(f"Silver: {silver_path}")

    rule("Coverage")
    print(f"  earliest {YEAR} incident : {joined['_when'].min()}")
    print(f"  latest   {YEAR} incident : {joined['_when'].max()}")
    print(f"  total {YEAR} records     : {len(joined):,}")
    print(f"  NOTE: {YEAR} is YEAR-TO-DATE. It is not a full year and must never be compared")
    print("        with a full year without saying so.")

    woodlawn = joined[joined["neighborhood_woodlawn"] == True].copy()  # noqa: E712
    print(f"  Woodlawn records        : {len(woodlawn):,}")
    print(f"  Woodlawn latest incident: {woodlawn['_when'].max()}")

    rule("Records with missing coordinates (citywide, retained not dropped)")
    status = joined["geography_status"].value_counts()
    for name, count in status.items():
        print(f"  {str(name):30} {count:>8,}")

    rule(f"Counts by month - citywide {YEAR}")
    for month, count in joined["_when"].dt.month.value_counts().sort_index().items():
        print(f"  {int(month):02d}  {count:>8,}")

    rule(f"Counts by month - Woodlawn {YEAR}")
    for month, count in woodlawn["_when"].dt.month.value_counts().sort_index().items():
        print(f"  {int(month):02d}  {count:>8,}")

    rule(f"Counts by primary_type - Woodlawn {YEAR}")
    for name, count in woodlawn["primary_type"].value_counts().items():
        print(f"  {str(name):32} {count:>6,}")

    rule(f"Counts by police beat - Woodlawn {YEAR} (source-reported)")
    for name, count in woodlawn["beat"].value_counts().sort_index().items():
        print(f"  beat {str(name):8} {count:>6,}")

    rule(f"Counts by police district - Woodlawn {YEAR} (source-reported)")
    for name, count in woodlawn["district"].value_counts().sort_index().items():
        print(f"  district {str(name):6} {count:>6,}")

    rule(f"Counts by ward - Woodlawn {YEAR} (source-reported)")
    for name, count in woodlawn["ward"].value_counts().sort_index().items():
        print(f"  ward {str(name):8} {count:>6,}")

    # -- the reviewable file -----------------------------------------------------------
    review = woodlawn.sort_values("_when", ascending=False)[CSV_FIELDS]

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(REVIEW_PATH, index=False, encoding="utf-8")

    after = hashlib.sha256(bronze_path.read_bytes()).hexdigest()

    rule("Review file")
    print(f"  path : {REVIEW_PATH}")
    print(f"  rows : {len(review):,}  (Woodlawn only, newest first)")
    print(f"  cols : {', '.join(CSV_FIELDS)}")
    print(f"  Bronze unchanged: {before == after}")
    print("  Locations are block-level as published by the city. No names. No derived or")
    print("  invented fields. This file is local review only - never render it in the UI.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
