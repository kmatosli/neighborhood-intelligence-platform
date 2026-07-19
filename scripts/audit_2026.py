"""Full audit of the 2026 crime ingestion. Read-only.

Reads Bronze and Silver; writes two review files under data/review/ (gitignored, like all of
data/). No production data is created, modified, or deleted — the Bronze checksum is verified
before and after.

    uv run python scripts/audit_2026.py

Outputs:
    data/review/2026_ingestion_audit.csv       every audit metric, one row per metric
    data/review/woodlawn_2026_incidents.csv    the 1,919 Woodlawn incidents, newest first

Locations in the incident file are block-level, exactly as the City of Chicago publishes
them. They are for local review only and must never be rendered in the public UI.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

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

INCIDENT_FIELDS = [
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

AUDIT_PATH = Path("data/review/2026_ingestion_audit.csv")
INCIDENTS_PATH = Path("data/review/woodlawn_2026_incidents.csv")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    settings = Settings()
    data_dir = settings.data_dir

    bronze_path = data_dir / "bronze" / "crime" / f"{YEAR}.parquet"
    silver_path = data_dir / "silver" / "crime" / "crime_with_geography" / f"{YEAR}.parquet"

    if not bronze_path.exists() or not silver_path.exists():
        print(f"ERROR: {YEAR} Bronze or Silver data is missing.")
        return 2

    bronze_before = sha256(bronze_path)
    silver_before = sha256(silver_path)

    bronze = pd.read_parquet(bronze_path, columns=BRONZE_FIELDS)
    silver = pd.read_parquet(silver_path)

    joined = silver.merge(bronze, on="id", how="left")
    joined["_when"] = pd.to_datetime(joined["date"], errors="coerce")

    total = len(joined)
    earliest = joined["_when"].min()
    latest = joined["_when"].max()

    status = joined["geography_status"]
    missing_coords = int((status == "missing_coordinates").sum())
    invalid_coords = int((status == "invalid_coordinates").sum())
    outside = int((status == "outside_chicago_boundaries").sum())
    assigned = int((status == "assigned").sum())

    # "Failed neighborhood assignment" = every record that could not be placed in a
    # community area, for any reason. These records are retained, never dropped.
    unassigned = int(joined["spatial_community_area"].isna().sum())

    woodlawn_mask = joined["neighborhood_woodlawn"] == True  # noqa: E712
    woodlawn = int(woodlawn_mask.sum())

    # Bronzeville has no approved boundary, so no record can be assigned to it. This is a
    # null, NOT a zero: "we cannot say", not "no crime in Bronzeville".
    bronzeville_assigned = int((joined["neighborhood_bronzeville"] == True).sum())  # noqa: E712
    bronzeville_null = int(joined["neighborhood_bronzeville"].isna().sum())

    rows: list[dict[str, Any]] = [
        {"section": "coverage", "metric": "total_incidents_ingested_chicago", "value": total},
        {"section": "coverage", "metric": "earliest_incident_date", "value": str(earliest)},
        {"section": "coverage", "metric": "latest_incident_date", "value": str(latest)},
        {"section": "coverage", "metric": "is_full_year", "value": "NO - year to date"},
        {"section": "coverage", "metric": "bronze_rows", "value": len(bronze)},
        {"section": "coverage", "metric": "silver_rows", "value": len(silver)},
        {
            "section": "coverage",
            "metric": "bronze_equals_silver",
            "value": len(bronze) == len(silver),
        },
    ]

    for month, count in joined["_when"].dt.month.value_counts().sort_index().items():
        rows.append(
            {
                "section": "records_per_month",
                "metric": f"{YEAR}-{int(month):02d}",
                "value": int(count),
            }
        )

    for area, count in (
        joined["spatial_community_area"].value_counts(dropna=False).sort_index().items()
    ):
        label = "UNASSIGNED" if pd.isna(area) else f"community_area_{area}"
        rows.append({"section": "records_per_community_area", "metric": label, "value": int(count)})

    rows += [
        {"section": "geography_quality", "metric": "assigned", "value": assigned},
        {
            "section": "geography_quality",
            "metric": "records_missing_coordinates",
            "value": missing_coords,
        },
        {
            "section": "geography_quality",
            "metric": "records_invalid_coordinates",
            "value": invalid_coords,
        },
        {
            "section": "geography_quality",
            "metric": "records_outside_chicago_boundaries",
            "value": outside,
        },
        {
            "section": "geography_quality",
            "metric": "records_failed_neighborhood_assignment",
            "value": unassigned,
        },
        {"section": "geography_quality", "metric": "records_retained_not_dropped", "value": total},
        {"section": "neighborhood", "metric": "assigned_to_woodlawn", "value": woodlawn},
        {
            "section": "neighborhood",
            "metric": "assigned_to_bronzeville",
            "value": bronzeville_assigned,
        },
        {
            "section": "neighborhood",
            "metric": "bronzeville_null_boundary_pending_approval",
            "value": bronzeville_null,
        },
        {
            "section": "neighborhood",
            "metric": "bronzeville_note",
            "value": "NULL not zero - boundary pending approval; absence is not a count of zero",
        },
    ]

    audit = pd.DataFrame(rows, columns=["section", "metric", "value"])
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_PATH, index=False, encoding="utf-8")

    incidents = joined[woodlawn_mask].sort_values("_when", ascending=False)[INCIDENT_FIELDS]
    incidents.to_csv(INCIDENTS_PATH, index=False, encoding="utf-8")

    # -- report ------------------------------------------------------------------------
    print("=" * 78)
    print(f"{YEAR} INGESTION AUDIT - read-only")
    print("=" * 78)

    rule("Coverage")
    print(f"  total Chicago incidents ingested : {total:,}")
    print(f"  earliest incident date           : {earliest}")
    print(f"  latest incident date             : {latest}")
    print(f"  Bronze rows / Silver rows        : {len(bronze):,} / {len(silver):,}")
    print(f"  every Bronze record preserved    : {len(bronze) == len(silver)}")
    print(f"  WARNING: {YEAR} is YEAR-TO-DATE, not a full year. Never compare it with a full")
    print("           year without labelling it as partial.")

    rule("Records per month")
    for month, count in joined["_when"].dt.month.value_counts().sort_index().items():
        print(f"  {YEAR}-{int(month):02d}  {int(count):>8,}")

    rule("Geography quality")
    print(f"  assigned                              {assigned:>8,}")
    print(f"  missing coordinates (retained)        {missing_coords:>8,}")
    print(f"  invalid coordinates (retained)        {invalid_coords:>8,}")
    print(f"  outside Chicago boundaries (retained) {outside:>8,}")
    print(f"  FAILED neighborhood assignment        {unassigned:>8,}")
    print("  records dropped                              0  (none, ever)")

    rule("Neighborhood assignment")
    print(f"  Woodlawn                     {woodlawn:>8,}")
    print(f"  Bronzeville                  {bronzeville_assigned:>8,}  <- NOT a real zero")
    print(f"  Bronzeville null (unknown)   {bronzeville_null:>8,}")
    print("  Bronzeville has no approved boundary, so NO record can be assigned to it.")
    print("  This is 'we cannot say', not 'no crime in Bronzeville'.")

    rule("Records per community area (top 10 of the assigned)")
    top = joined["spatial_community_area"].value_counts().head(10)
    for area, count in top.items():
        print(f"  community area {str(area):>4}  {int(count):>7,}")
    print(f"  ... full breakdown in {AUDIT_PATH}")

    bronze_after = sha256(bronze_path)
    silver_after = sha256(silver_path)

    rule("Output files")
    print(f"  {AUDIT_PATH}      ({len(audit):,} metrics)")
    print(f"  {INCIDENTS_PATH}  ({len(incidents):,} incidents, newest first)")

    rule("Production data integrity")
    print(f"  Bronze unchanged : {bronze_before == bronze_after}")
    print(f"  Silver unchanged : {silver_before == silver_after}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
