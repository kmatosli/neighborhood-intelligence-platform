"""Download historical Chicago crime data into the Bronze layer.

python scripts/download_crime_history.py --year 2024
python scripts/download_crime_history.py --start-year 2006 --end-year 2012
python scripts/download_crime_history.py --resume
"""

from __future__ import annotations

import argparse

from bw_observatory.clients.chicago_data import ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.ingest.base import RecordValidationError, SchemaValidationError
from bw_observatory.ingest.crime_history import (
    FIRST_YEAR,
    CrimeDownloader,
    resolve_years,
)
from bw_observatory.logging_config import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="Download a single calendar year.")
    parser.add_argument("--start-year", type=int, help=f"First year (default {FIRST_YEAR}).")
    parser.add_argument("--end-year", type=int, help="Last year (default: current year).")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip years already marked complete in the manifest.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download years even if the manifest marks them complete.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.year is not None and (args.start_year is not None or args.end_year is not None):
        print("ERROR: --year cannot be combined with --start-year or --end-year.")
        return 2

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    downloader = CrimeDownloader(settings)

    try:
        years = resolve_years(
            year=args.year,
            start_year=args.start_year,
            end_year=args.end_year,
            resume=args.resume,
            bronze_dir=downloader.bronze_dir,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if not years:
        print("Nothing to download — every requested year is already complete.")
        return 0

    try:
        run = downloader.run_years(years, resume=args.resume, force=args.force)
    except SchemaValidationError as exc:
        print(f"BLOCKING: {exc}")
        print("Existing Bronze data was left untouched.")
        return 1
    except RecordValidationError as exc:
        print(f"BLOCKING: {exc}")
        return 1
    except ChicagoDataError as exc:
        print(f"BLOCKING: Chicago API error: {exc}")
        return 1

    downloaded = [int(p.partition) for p in run.partitions if not p.skipped]
    skipped = [int(p.partition) for p in run.partitions if p.skipped]

    print()
    print(f"Run {run.run_id} — {run.status}")
    print(f"Years downloaded:    {downloaded}")
    if skipped:
        print(f"Years skipped:       {skipped}")
    print(f"Records downloaded:  {run.records_downloaded:,}")
    print(f"Rows written:        {run.rows_written:,}")
    print(f"Elapsed time:        {run.elapsed_seconds:.1f}s")
    print(f"Warnings:            {run.warnings}")
    print(f"Errors:              {run.errors}")

    if run.analytic_warnings:
        print(
            f"WARNING: {run.analytic_warnings:,} record(s) have no latitude/longitude. "
            "They are preserved in Bronze and excluded from later spatial analysis."
        )

    print(f"Bronze directory:    {downloader.bronze_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
