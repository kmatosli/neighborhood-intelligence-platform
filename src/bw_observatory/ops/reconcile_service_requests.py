"""Reconcile local 311 partitions against the source's current id set.

    python -m bw_observatory.ops.reconcile_service_requests             # two newest years
    python -m bw_observatory.ops.reconcile_service_requests --year 2025 --year 2026
    python -m bw_observatory.ops.reconcile_service_requests --dry-run

Marks requests the City no longer publishes as `source_removed` in Silver (kept as provenance,
excluded from every published figure) and logs the outcome. Exit codes: 0 done, 1 blocked,
2 usage, 3 another run holds the lock.
"""

from __future__ import annotations

import argparse

from bw_observatory.clients.chicago_data import ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.ingest.refresh_lock import AlreadyRunning
from bw_observatory.ingest.service_request_reconcile import ServiceRequestReconciler
from bw_observatory.logging_config import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        help="A year to reconcile (repeatable). Default: the two newest years on disk.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compare and report; mark nothing.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)
    reconciler = ServiceRequestReconciler(settings)

    try:
        result = reconciler.run(args.year, dry_run=args.dry_run)
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
    suffix = " (DRY RUN)" if result.dry_run else ""
    print(f"311 reconciliation {result.run_id} — {result.status}{suffix}")
    print(f"Elapsed time:  {result.elapsed_seconds:.1f}s")
    print()
    for y in result.years:
        print(
            f"  {y.year}: local {y.local_rows:,} vs source {y.source_rows:,} — "
            f"{y.confirmed_active:,} active, {y.newly_removed:,} newly removed, "
            f"{y.still_removed:,} still removed, {y.reappeared:,} reappeared, "
            f"{y.missing_locally:,} in source but missing locally"
        )
        if y.missing_ids_sample:
            print(f"        missing sample: {y.missing_ids_sample}")
    print()
    print(f"Reconciliation log: {reconciler.log_path}")
    return 0 if result.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
