"""Bring the 311 layers (Bronze + Silver) up to date with the City of Chicago source.

    python -m bw_observatory.ops.ingest_service_requests --year 2024 --year 2025 --backfill
    python -m bw_observatory.ops.ingest_service_requests              # refresh the newest years
    python -m bw_observatory.ops.ingest_service_requests --enrich-only --year 2025

Two modes, because they answer different questions:

* `--backfill` fetches a year whole. Used once per new year, and again only if a partition has
  to be rebuilt from the source.
* the default refreshes: it fetches only records whose `last_modified_date` is newer than the
  watermark already stored, and upserts them by `sr_number`. This is the normal freshness path.

Silver is rebuilt from the Bronze partition after either mode, so the enrichment, the geography
and the exclusion reasons always describe the Bronze rows actually on disk. Reconciliation is a
separate command (`reconcile_service_requests`) because it answers a question a refresh cannot:
which records the City has *withdrawn*.

Exit codes: 0 done, 1 blocked by the source, 2 usage or missing input, 3 another run holds
the lock.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from bw_observatory.clients.chicago_data import ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.geography.service_requests import (
    enrich_service_requests,
    load_reference_layers,
)
from bw_observatory.ingest.refresh_lock import AlreadyRunning, RefreshLock
from bw_observatory.ingest.service_requests import (
    ServiceRequestIngest,
    bronze_dir,
    bronze_path,
    load_service_request_config,
    silver_path,
    write_parquet_atomic,
    years_on_disk,
)
from bw_observatory.logging_config import configure_logging

#: How many of the newest years a bare refresh covers. Older years are edited rarely, and a
#: named `--year` still reaches them.
DEFAULT_RECENT_YEARS = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        help="A year to process (repeatable). Default: the two newest years already on disk.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Fetch each year whole instead of only what changed since the watermark.",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Rebuild Silver from the Bronze already on disk. Makes no source requests.",
    )
    parser.add_argument(
        "--reference-version",
        default="2026-07-12",
        help="Boundary layer version to place points against.",
    )
    return parser


def enrich_year(data_dir: Path, year: int, reference_version: str) -> int:
    """Rebuild one Silver partition from its Bronze partition. Returns the row count."""
    source = bronze_path(data_dir, year)
    if not source.exists():
        raise FileNotFoundError(f"311 {year}: no Bronze partition at {source}")
    config = load_service_request_config()
    layers = load_reference_layers(data_dir, reference_version)
    bronze = pd.read_parquet(source)
    # The ingest instant travels into Silver so an unreconciled row can say when it was last
    # known to exist, rather than implying an observation that never happened.
    ingested = bronze["ingested_at"].dropna().max() if "ingested_at" in bronze.columns else None
    silver = enrich_service_requests(
        bronze,
        year,
        config,
        layers,
        ingested_at=str(ingested) if pd.notna(ingested) else None,
    )
    write_parquet_atomic(silver, silver_path(data_dir, year))
    return len(silver)


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    years = args.year or years_on_disk(settings.data_dir)[-DEFAULT_RECENT_YEARS:]
    if not years:
        print("ERROR: no years on disk and none named. Pass --year with --backfill.")
        return 2

    ingest = ServiceRequestIngest(settings, reference_version=args.reference_version)
    started = datetime.now(UTC)
    try:
        # One writer at a time, sharing the crime pipeline's lock file convention.
        with RefreshLock(bronze_dir(settings.data_dir)):
            for year in years:
                if args.enrich_only:
                    fetched = written = None
                elif args.backfill:
                    records = ingest.fetch_year(year)
                    result = ingest.write_bronze(year, records)
                    fetched, written = result.rows_fetched, result.rows_written
                else:
                    result = ingest.refresh_year(year)
                    fetched, written = result.rows_fetched, result.rows_written
                rows = enrich_year(settings.data_dir, year, args.reference_version)
                if fetched is None:
                    print(f"  {year}: Silver rebuilt from Bronze — {rows:,} rows")
                else:
                    print(
                        f"  {year}: fetched {fetched:,}, Bronze now {written:,} rows, "
                        f"Silver {rows:,} rows"
                    )
    except AlreadyRunning as exc:
        print(f"SKIPPED: a refresh or reconciliation is already running — {exc}")
        return 3
    except ChicagoDataError as exc:
        print(f"BLOCKING: Chicago API error: {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 2

    print()
    print(f"Elapsed time: {(datetime.now(UTC) - started).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
