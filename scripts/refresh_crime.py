"""Bring the crime layers (Bronze + Silver) up to date with the City of Chicago source.

    uv run python scripts/refresh_crime.py             # fetch and apply what changed
    uv run python scripts/refresh_crime.py --dry-run   # report what would change, write nothing
    uv run python scripts/refresh_crime.py --since 2026-07-10T15:53:54.000   # override watermark

Incremental: only records whose source `updated_on` is at or after the last watermark are
fetched, upserted by `id`, and re-enriched. Safe to run repeatedly. The historical loader
(`download_crime_history.py`) remains the tool for a first load or a deliberate rebuild.
"""

from __future__ import annotations

import argparse

from bw_observatory.clients.chicago_data import ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.ingest.base import RecordValidationError, SchemaValidationError
from bw_observatory.ingest.crime_history import FIRST_YEAR
from bw_observatory.ingest.crime_refresh import CrimeRefresher, NothingToRefreshFrom
from bw_observatory.logging_config import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and classify changes, print the report, write nothing.",
    )
    parser.add_argument(
        "--since",
        help="Start from this source `updated_on` timestamp instead of the stored watermark.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    refresher = CrimeRefresher(settings)

    try:
        result = refresher.run(dry_run=args.dry_run, since=args.since)
    except NothingToRefreshFrom as exc:
        print(f"ERROR: {exc}")
        return 2
    except SchemaValidationError as exc:
        print(f"BLOCKING: {exc}")
        print("Existing Bronze and Silver data were left untouched.")
        return 1
    except RecordValidationError as exc:
        print(f"BLOCKING: {exc}")
        return 1
    except ChicagoDataError as exc:
        print(f"BLOCKING: Chicago API error: {exc}")
        return 1

    print()
    print(f"Refresh {result.run_id} — {result.status}{' (DRY RUN)' if result.dry_run else ''}")
    print(f"Previous watermark:  {result.previous_watermark}")
    print(f"New watermark:       {result.new_watermark}")
    print(f"Rows fetched:        {result.rows_fetched:,}")
    print(f"Rows inserted:       {result.rows_inserted:,}")
    print(f"Rows updated:        {result.rows_updated:,}")
    print(f"Rows unchanged:      {result.rows_unchanged:,}")
    print(f"Rows moved (year):   {result.rows_moved_partition:,}")
    print(f"Rows before {FIRST_YEAR}:    {result.rows_out_of_range:,} (skipped; not held)")
    print(f"Changed rows lacking geography: {result.rows_missing_geography:,}")
    if result.rows_silver_backfilled or result.rows_silver_orphans:
        print(
            f"Silver repaired:     {result.rows_silver_backfilled:,} Bronze record(s) lacked a "
            f"Silver row (enriched); {result.rows_silver_orphans:,} Silver row(s) lacked a "
            "Bronze record (dropped)"
        )
    print(f"Final Bronze rows:   {result.final_bronze_rows:,}")
    print(f"Elapsed time:        {result.elapsed_seconds:.1f}s")
    print(f"Warnings:            {result.warnings}")

    if result.partitions:
        print()
        print("Per year (local rows vs source rows; drift = source - local):")
        for p in result.partitions:
            drift = "n/a" if p.drift is None else f"{p.drift:+d}"
            print(
                f"  {p.year}: +{p.inserted:,} inserted, {p.updated:,} updated, "
                f"{p.unchanged:,} unchanged, {p.moved_out:,} moved in; "
                f"local {p.local_rows:,} vs source {p.source_rows:,} (drift {drift})"
            )

    print()
    print(f"Refresh log:         {refresher.incremental_log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
