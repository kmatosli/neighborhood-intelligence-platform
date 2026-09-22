"""Periodic reconciliation of the crime layers against the source's current id set.

The daily refresh (`crime_refresh.py`) sees every record the City inserts or edits, because
each of those carries a fresh `updated_on`. It cannot see a record the City *removes* — a
removed row has no timestamp to fetch. The refresh's per-year row-count comparison shows
that such rows exist (a negative "drift"); this module finds *which* rows, and records the
finding as provenance instead of guessing at it.

Source-truth model (V2-004A):

* **Preserved history.** A record we ingested stays in Bronze verbatim and in Silver with
  its geography. Nothing is deleted.
* **Current official view.** Silver carries `source_status`. A reconciliation run marks an
  id the source no longer returns as `source_removed`, with `source_removed_at` set the
  first time that was observed; the API's `current_source_view` excludes those rows from
  every published figure. An id that reappears goes back to `active_in_source`.
* **Auditability.** `source_last_seen` is the last instant the source returned the row;
  `reconciliation_log.parquet` records, per run and year, how many rows were confirmed,
  newly removed, still removed, reappeared, and — the case that means a refresh gap —
  present in the source but absent locally. "Removed" asserts nothing about why.

Cadence: the refresh's drift figure decides. By default a run covers the two newest years
(where removals concentrate: 149 and 42 of them in the first two months observed, against
single digits in older years) plus any year whose last refresh reported non-zero drift. A
year costs a few id-only requests, so this is cheap enough to run monthly, and it never
re-downloads a year.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bw_observatory.clients.chicago_data import ChicagoDataClient
from bw_observatory.config import Settings
from bw_observatory.geography.assign import SOURCE_COLUMNS, bronze_downloaded_at, silver_path
from bw_observatory.geography.models import SourceStatus
from bw_observatory.ingest.base import STATUS_COMPLETE, STATUS_FAILED, iso, now
from bw_observatory.ingest.bronze import write_frame_atomic
from bw_observatory.ingest.crime_history import year_where_clause
from bw_observatory.ingest.crime_refresh import INCREMENTAL_LOG_FILENAME
from bw_observatory.ingest.partitions import (
    discard,
    file_columns,
    frame_schema,
    iter_batches,
    partition_ids,
    partition_problems,
    publish,
    stream_rewrite,
    temp_sibling,
)
from bw_observatory.ingest.refresh_lock import RefreshLock
from bw_observatory.logging_config import api_logger, download_logger

RECONCILIATION_LOG_FILENAME = "reconciliation_log.parquet"
RECONCILIATION_LOG_COLUMNS = [
    "run_id",
    "year",
    "start_time",
    "end_time",
    "local_rows",
    "source_rows",
    "confirmed_active",
    "newly_removed",
    "still_removed",
    "reappeared",
    "missing_locally",
    "duration_seconds",
    "dry_run",
    "status",
    "error",
]
PAGE_SIZE = 50_000
DEFAULT_RECENT_YEARS = 2


@dataclass
class YearReconciliation:
    year: int
    local_rows: int = 0
    source_rows: int = 0
    confirmed_active: int = 0
    newly_removed: int = 0
    still_removed: int = 0
    reappeared: int = 0
    missing_locally: int = 0
    missing_ids_sample: list[str] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    run_id: str
    start_time: datetime
    dry_run: bool
    years: list[YearReconciliation] = field(default_factory=list)
    end_time: datetime | None = None
    status: str = STATUS_COMPLETE
    error: str = ""

    @property
    def elapsed_seconds(self) -> float:
        return ((self.end_time or now()) - self.start_time).total_seconds()


class CrimeReconciler:
    def __init__(self, settings: Settings, client: ChicagoDataClient | None = None) -> None:
        self.settings = settings
        self.client = client or ChicagoDataClient(settings)
        self.bronze_dir = settings.data_dir / "bronze" / "crime"
        self.silver_dir = settings.data_dir / "silver"
        self.log = download_logger()
        self.api_log = api_logger()

    @property
    def log_path(self) -> Path:
        return self.bronze_dir / RECONCILIATION_LOG_FILENAME

    def read_log(self) -> pd.DataFrame:
        if not self.log_path.exists():
            return pd.DataFrame(columns=RECONCILIATION_LOG_COLUMNS)
        return pd.read_parquet(self.log_path)

    def bronze_years(self) -> list[int]:
        return sorted(
            int(path.stem) for path in self.bronze_dir.glob("*.parquet") if path.stem.isdigit()
        )

    # -- which years --------------------------------------------------------------------

    def default_years(self, recent: int = DEFAULT_RECENT_YEARS) -> list[int]:
        """The newest `recent` years plus any year the last refresh saw drift in."""
        years = self.bronze_years()
        chosen = set(years[-recent:])
        log_path = self.bronze_dir / INCREMENTAL_LOG_FILENAME
        if log_path.exists():
            log = pd.read_parquet(log_path)
            done = log[(log["status"] == STATUS_COMPLETE) & (~log["dry_run"].astype(bool))]
            if not done.empty:
                latest = json.loads(str(done.iloc[-1]["reconciliation"]) or "{}")
                for year, figures in latest.items():
                    drift = figures.get("drift")
                    if drift not in (None, 0) and int(year) in years:
                        chosen.add(int(year))
        return sorted(chosen)

    # -- source ids ---------------------------------------------------------------------

    def source_ids(self, year: int) -> set[str]:
        where = year_where_clause(year)
        ids: set[str] = set()
        offset = 0
        while True:
            self.api_log.info("GET ids year=%d offset=%d limit=%d", year, offset, PAGE_SIZE)
            page = self.client.list_crime_ids(where=where, limit=PAGE_SIZE, offset=offset)
            ids.update(page)
            if len(page) < PAGE_SIZE:
                return ids
            offset += PAGE_SIZE

    # -- run ----------------------------------------------------------------------------

    def run(self, years: list[int] | None = None, *, dry_run: bool = False) -> ReconciliationResult:
        with RefreshLock(self.bronze_dir):
            return self._run_locked(years, dry_run=dry_run)

    def _run_locked(self, years: list[int] | None, *, dry_run: bool) -> ReconciliationResult:
        result = ReconciliationResult(run_id=str(uuid.uuid4()), start_time=now(), dry_run=dry_run)
        targets = years if years is not None else self.default_years()
        self.log.info(
            "Reconciliation %s starting for %s%s",
            result.run_id,
            targets,
            " (dry run)" if dry_run else "",
        )
        try:
            for year in targets:
                started = now()
                try:
                    outcome = self._reconcile_year(year, dry_run=dry_run, seen_at=iso(started))
                    result.years.append(outcome)
                    self._append_log(result, outcome, started, STATUS_COMPLETE, "")
                except Exception as exc:
                    self._append_log(
                        result,
                        YearReconciliation(year=year),
                        started,
                        STATUS_FAILED,
                        f"{type(exc).__name__}: {exc}",
                    )
                    raise
            result.status = STATUS_COMPLETE
        except Exception as exc:
            result.status = STATUS_FAILED
            result.error = f"{type(exc).__name__}: {exc}"
            self.log.error("Reconciliation %s failed: %s", result.run_id, result.error)
            raise
        finally:
            result.end_time = now()
        return result

    def _reconcile_year(self, year: int, *, dry_run: bool, seen_at: str) -> YearReconciliation:
        outcome = YearReconciliation(year=year)
        bronze_file = self.bronze_dir / f"{year}.parquet"
        silver_file = silver_path(self.silver_dir, year)
        if not bronze_file.exists() or not silver_file.exists():
            raise FileNotFoundError(f"{year}: Bronze or Silver partition missing")

        local = partition_ids(bronze_file)
        source = self.source_ids(year)
        outcome.local_rows = len(local)
        outcome.source_rows = len(source)

        removed_now = local - source
        missing = source - local
        outcome.missing_locally = len(missing)
        outcome.missing_ids_sample = sorted(missing)[:10]

        # What Silver said before this run — only two columns are read.
        was_removed: set[str] = set()
        if "source_status" in file_columns(silver_file):
            for batch in iter_batches(silver_file, ["id", "source_status"]):
                flags = pc.fill_null(
                    pc.equal(batch.column("source_status"), SourceStatus.REMOVED), False
                )
                was_removed.update(str(v) for v in batch.column("id").filter(flags).to_pylist())

        outcome.newly_removed = len(removed_now - was_removed)
        outcome.still_removed = len(removed_now & was_removed)
        outcome.reappeared = len(was_removed - removed_now)
        outcome.confirmed_active = len(local - removed_now)

        self.log.info(
            "Reconcile %d: local %d vs source %d — %d confirmed active, %d newly removed, "
            "%d still removed, %d reappeared, %d in source but missing locally%s",
            year,
            outcome.local_rows,
            outcome.source_rows,
            outcome.confirmed_active,
            outcome.newly_removed,
            outcome.still_removed,
            outcome.reappeared,
            outcome.missing_locally,
            " (dry run — nothing written)" if dry_run else "",
        )
        if missing:
            self.log.warning(
                "Reconcile %d: %d id(s) exist in the source but not locally (sample %s). "
                "Run the refresh with --since before this year's watermark to fetch them.",
                year,
                len(missing),
                outcome.missing_ids_sample,
            )
        if dry_run:
            return outcome

        # Rewrite the provenance columns batch by batch; every other column passes through.
        existing_schema = pq.read_schema(silver_file)
        legacy = existing_schema.empty_table().to_pandas()
        for column in SOURCE_COLUMNS:
            if column not in legacy.columns:
                legacy[column] = pd.Series(dtype="string")
        schema = frame_schema(legacy)
        defaults = {
            "source_status": SourceStatus.ACTIVE,
            "source_last_seen": bronze_downloaded_at(self.bronze_dir, year) or "",
        }

        def adapt(table: pa.Table) -> pa.Table:
            # Scalars take the column's own type so the writer sees an unchanged schema.
            text = table.schema.field("source_status").type
            removed_value = pa.scalar(SourceStatus.REMOVED, type=text)
            active_value = pa.scalar(SourceStatus.ACTIVE, type=text)
            seen_value = pa.scalar(seen_at, type=text)
            null_value = pa.scalar(None, type=text)
            ids = table.column("id")
            if removed_now:
                is_removed = pc.is_in(ids, value_set=pa.array(sorted(removed_now), type=ids.type))
            else:
                is_removed = pa.array([False] * len(table), type=pa.bool_())
            was = pc.fill_null(pc.equal(table.column("source_status"), removed_value), False)
            # First observation of a removal is the provenance that matters; keep it.
            removed_at = pc.if_else(
                is_removed,
                pc.if_else(was, table.column("source_removed_at"), seen_value),
                null_value,
            )
            last_seen = pc.if_else(is_removed, table.column("source_last_seen"), seen_value)
            status = pc.if_else(is_removed, removed_value, active_value)
            names = table.column_names
            table = table.set_column(names.index("source_status"), "source_status", status)
            table = table.set_column(
                names.index("source_removed_at"), "source_removed_at", removed_at
            )
            table = table.set_column(names.index("source_last_seen"), "source_last_seen", last_seen)
            return table

        staged = {silver_file: temp_sibling(silver_file)}
        try:
            stream_rewrite(
                silver_file,
                staged[silver_file],
                schema=schema,
                drop=set(),
                append=None,
                defaults=defaults,
                adapt=adapt,
            )
        except BaseException:
            discard(staged)
            raise
        publish(staged)
        problems = partition_problems(self.bronze_dir, self.silver_dir, year)
        if problems:
            raise RuntimeError(
                "partition invariants violated after reconcile: " + "; ".join(problems)
            )
        return outcome

    def _append_log(
        self,
        result: ReconciliationResult,
        outcome: YearReconciliation,
        started: datetime,
        status: str,
        error: str,
    ) -> None:
        finished = now()
        row: dict[str, Any] = {
            "run_id": result.run_id,
            "year": outcome.year,
            "start_time": iso(started),
            "end_time": iso(finished),
            "local_rows": outcome.local_rows,
            "source_rows": outcome.source_rows,
            "confirmed_active": outcome.confirmed_active,
            "newly_removed": outcome.newly_removed,
            "still_removed": outcome.still_removed,
            "reappeared": outcome.reappeared,
            "missing_locally": outcome.missing_locally,
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "dry_run": result.dry_run,
            "status": status,
            "error": error,
        }
        existing = self.read_log()
        updated = pd.concat([existing, pd.DataFrame([row], columns=RECONCILIATION_LOG_COLUMNS)])
        write_frame_atomic(updated.reset_index(drop=True), self.log_path)
