"""Assign Bronze crime records to official geographies (Silver enrichment).

    uv run python scripts/enrich_crime_geography.py --year 2024
    uv run python scripts/enrich_crime_geography.py --start-year 2006 --end-year 2026 --resume

Bronze is read-only. Every Bronze record survives into Silver, including records with no
coordinates.
"""

from __future__ import annotations

import argparse

from bw_observatory.config import Settings
from bw_observatory.geography.assign import (
    GeographyAssigner,
    completed_years,
    enrich_year,
    quality_path,
)
from bw_observatory.geography.normalize import read_neighborhoods, read_silver_geography
from bw_observatory.ingest.crime_history import FIRST_YEAR, resolve_years
from bw_observatory.logging_config import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="Enrich a single calendar year.")
    parser.add_argument("--start-year", type=int, help=f"First year (default {FIRST_YEAR}).")
    parser.add_argument("--end-year", type=int, help="Last year (default: current year).")
    parser.add_argument("--resume", action="store_true", help="Skip years already enriched.")
    parser.add_argument("--force", action="store_true", help="Re-enrich completed years.")
    args = parser.parse_args()

    if args.year is not None and (args.start_year is not None or args.end_year is not None):
        print("ERROR: --year cannot be combined with --start-year or --end-year.")
        return 2

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    bronze_dir = settings.data_dir / "bronze" / "crime"
    silver_dir = settings.data_dir / "silver"

    try:
        dimension = read_silver_geography(silver_dir)
        neighborhoods = read_neighborhoods(silver_dir)
    except FileNotFoundError:
        print("ERROR: no Silver geography layer. Run scripts/validate_geography.py first.")
        return 2

    try:
        years = resolve_years(
            year=args.year,
            start_year=args.start_year,
            end_year=args.end_year,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    done = set() if args.force else completed_years(silver_dir)
    available = {year for year in years if (bronze_dir / f"{year}.parquet").exists()}
    missing = sorted(set(years) - available)

    todo = sorted(available - done) if (args.resume or not args.force) else sorted(available)
    skipped = sorted(available & done) if not args.force else []

    assigner = GeographyAssigner(dimension, neighborhoods)

    if missing:
        print(f"NOTE: no Bronze data for {missing}; those years were not enriched.")
    if not todo:
        print("Nothing to enrich — every requested year is already complete.")
        return 0

    rows = [enrich_year(assigner, bronze_dir, silver_dir, year) for year in todo]

    print()
    print(f"Years enriched: {todo}")
    if skipped:
        print(f"Years skipped:  {skipped}")
    print(f"Boundary vintage: {assigner.vintage}")
    print()

    for row in rows:
        print(f"--- {row['year']} ---")
        print(f"  Total Bronze records:        {row['total_records']:,}")
        print(f"  With coordinates:            {row['records_with_coordinates']:,}")
        print(f"  Without coordinates:         {row['records_without_coordinates']:,} (kept)")
        print(f"  Assigned to community area:  {row['records_assigned_to_community_area']:,}")
        print(f"  Assigned to ward:            {row['records_assigned_to_ward']:,}")
        print(f"  Assigned to beat:            {row['records_assigned_to_beat']:,}")
        print(f"  Assigned to district:        {row['records_assigned_to_district']:,}")
        print(f"  Assigned to census tract:    {row['records_assigned_to_census_tract']:,}")
        print(f"  Woodlawn:                    {row['records_woodlawn']:,}")
        print(f"  Bronzeville:                 {row['bronzeville_status']}")
        print(f"  Invalid coordinates:         {row['invalid_coordinates']:,}")
        print(f"  Outside Chicago boundaries:  {row['outside_chicago_boundaries']:,}")
        print(f"  Ambiguous overlaps:          {row['ambiguous_overlaps']:,}")
        print(
            f"  Source-vs-spatial mismatch:  ward={row['ward_mismatches']:,} "
            f"beat={row['beat_mismatches']:,} district={row['district_mismatches']:,} "
            f"community_area={row['community_area_mismatches']:,}"
        )

    print()
    print(f"Quality report: {quality_path(silver_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
