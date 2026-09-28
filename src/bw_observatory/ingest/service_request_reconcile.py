"""Periodic reconciliation of the 311 layers against the source's current id set.

Why this exists, in the same terms as the crime reconciler:

The refresh (`ServiceRequestIngest.refresh_year`) sees every record the City inserts or edits,
because both restamp `last_modified_date`. It cannot see a record the City *withdraws* — a
withdrawn row has no timestamp left to fetch, so an incremental query can never return it. Row
counts drifting below what we hold shows that such rows exist; this module finds *which* ones,
and records the finding as provenance instead of guessing at it.

Source-truth model, identical to crime (V2-004A) on purpose — one model, two datasets:

* **Preserved history.** A record we ingested stays in Bronze verbatim and in Silver with its
  geography. Nothing is deleted, ever.
* **Current official view.** Silver carries `source_status`. A run marks an `sr_number` the
  source no longer returns as `source_removed`, with `source_removed_at` set the first time
  that was observed; `current_source_view` excludes those rows from every published figure. An
  id that reappears goes back to `active_in_source`.
* **Auditability.** `source_last_seen` is the last instant the source returned the row.
  `reconciliation_log.parquet` records, per run and year, how many rows were confirmed, newly
  removed, still removed, reappeared, and — the case that means a refresh gap — present in the
  source but absent locally. "Removed" asserts nothing about why.

The comparison window must match the ingest filter exactly. Bronze holds the records inside the
Ward 20 bounding box whose `created_date` falls in the year, so the id query applies the same
box and the same date range. Widening it would report every record elsewhere in Chicago as
missing locally; narrowing it would report records we correctly hold as withdrawn.

One caveat this does not pretend to resolve: a record whose `created_date` the City *edits*
across a year boundary leaves the window of the year we filed it under. It is counted as removed
from that year, correctly, and as missing from the other, also correctly — but the log shows two
entries rather than one move. `missing_ids_sample` is what makes that visible.
"""

from __future__ import annotations

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
from bw_observatory.geography.models import SourceStatus
from bw_observatory.ingest.base import STATUS_COMPLETE, STATUS_FAILED, iso, now
from bw_observatory.ingest.partitions import (
    BATCH_ROWS,
    conform,
    discard,
    file_columns,
    iter_batches,
    publish,
    temp_sibling,
)
from bw_observatory.ingest.refresh_lock import RefreshLock
from bw_observatory.ingest.service_requests import (
    bronze_dir,
    bronze_path,
    load_service_request_config,
    silver_path,
    source_where_clause,
    ward_bounding_box,
    years_on_disk,
)
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
#: The provenance columns a reconciled Silver partition must carry.
PROVENANCE_COLUMNS = ("source_status", "source_last_seen", "source_removed_at")
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


class ServiceRequestReconciler:
    """Compares the 311 id set we hold against the one the source currently publishes."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: ChicagoDataClient | None = None,
        reference_version: str = "2026-07-12",
    ) -> None:
        self.settings = settings
        self.config = load_service_request_config()
        self.client = client or ChicagoDataClient(settings)
        self.reference_version = reference_version
        self.log = download_logger()
        self.api_log = api_logger()

    @property
    def id_column(self) -> str:
        return self.config.id_column

    @property
    def log_path(self) -> Path:
        return bronze_dir(self.settings.data_dir) / RECONCILIATION_LOG_FILENAME

    def read_log(self) -> pd.DataFrame:
        if not self.log_path.exists():
            return pd.DataFrame(columns=RECONCILIATION_LOG_COLUMNS)
        return pd.read_parquet(self.log_path)

    def default_years(self, recent: int = DEFAULT_RECENT_YEARS) -> list[int]:
        """The newest `recent` years. Withdrawals concentrate in the years still being edited,
        and a year costs a few id-only requests, so this stays cheap enough to run monthly."""
        return years_on_disk(self.settings.data_dir)[-recent:]

    # -- source ids ---------------------------------------------------------------------

    def source_ids(self, year: int) -> set[str]:
        """Every id the source currently returns for the year, inside the ingest bounding box.

        Ids alone are a fraction of the row payload, so a year is a handful of requests rather
        than a re-download. The order is explicit because Socrata promises none without it, and
        paging an unordered query can repeat or skip rows.
        """
        box = ward_bounding_box(self.settings.data_dir, self.reference_version)
        where = source_where_clause(box, year=year)
        ids: set[str] = set()
        offset = 0
        while True:
            self.api_log.info("GET 311 ids year=%d offset=%d limit=%d", year, offset, PAGE_SIZE)
            page = self.client.get_records(
                self.config.dataset_id,
                limit=PAGE_SIZE,
                offset=offset,
                where=where,
                order=self.id_column,
                select=self.id_column,
            )
            ids.update(str(row[self.id_column]) for row in page if row.get(self.id_column))
            if len(page) < PAGE_SIZE:
                return ids
            offset += PAGE_SIZE

    # -- run ----------------------------------------------------------------------------

    def run(self, years: list[int] | None = None, *, dry_run: bool = False) -> ReconciliationResult:
        # One writer at a time. The lock is the Bronze directory's, shared with the refresh, so
        # a reconciliation can never interleave with an upsert of the same partition.
        with RefreshLock(bronze_dir(self.settings.data_dir)):
            return self._run_locked(years, dry_run=dry_run)

    def _run_locked(self, years: list[int] | None, *, dry_run: bool) -> ReconciliationResult:
        result = ReconciliationResult(run_id=str(uuid.uuid4()), start_time=now(), dry_run=dry_run)
        targets = years if years is not None else self.default_years()
        self.log.info(
            "311 reconciliation %s starting for %s%s",
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
            self.log.error("311 reconciliation %s failed: %s", result.run_id, result.error)
            raise
        finally:
            result.end_time = now()
        return result

    def _local_ids(self, path: Path) -> set[str]:
        ids: set[str] = set()
        for batch in iter_batches(path, [self.id_column]):
            ids.update(str(v) for v in batch.column(self.id_column).to_pylist())
        return ids

    def _already_removed(self, silver_file: Path) -> set[str]:
        """What Silver said before this run. Two columns are read, never the whole year."""
        if "source_status" not in file_columns(silver_file):
            return set()
        removed: set[str] = set()
        for batch in iter_batches(silver_file, [self.id_column, "source_status"]):
            flags = pc.fill_null(
                pc.equal(batch.column("source_status"), SourceStatus.REMOVED), False
            )
            removed.update(str(v) for v in batch.column(self.id_column).filter(flags).to_pylist())
        return removed

    def _reconcile_year(self, year: int, *, dry_run: bool, seen_at: str) -> YearReconciliation:
        outcome = YearReconciliation(year=year)
        bronze_file = bronze_path(self.settings.data_dir, year)
        silver_file = silver_path(self.settings.data_dir, year)
        if not bronze_file.exists() or not silver_file.exists():
            raise FileNotFoundError(f"311 {year}: Bronze or Silver partition missing")

        local = self._local_ids(bronze_file)
        source = self.source_ids(year)
        outcome.local_rows = len(local)
        outcome.source_rows = len(source)

        removed_now = local - source
        missing = source - local
        outcome.missing_locally = len(missing)
        outcome.missing_ids_sample = sorted(missing)[:10]

        was_removed = self._already_removed(silver_file)
        outcome.newly_removed = len(removed_now - was_removed)
        outcome.still_removed = len(removed_now & was_removed)
        outcome.reappeared = len(was_removed - removed_now)
        outcome.confirmed_active = len(local - removed_now)

        self.log.info(
            "Reconcile 311 %d: local %d vs source %d — %d confirmed active, %d newly removed, "
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
                "Reconcile 311 %d: %d id(s) exist in the source but not locally (sample %s). "
                "Run the refresh for this year to fetch them.",
                year,
                len(missing),
                outcome.missing_ids_sample,
            )
        if dry_run:
            return outcome

        self._rewrite_provenance(silver_file, removed_now, seen_at=seen_at)
        return outcome

    def _rewrite_provenance(self, silver_file: Path, removed: set[str], *, seen_at: str) -> None:
        """Rewrite only the provenance columns, batch by batch. Every other column passes
        through untouched, and the old file stays intact until the swap."""
        existing = pq.read_schema(silver_file)
        legacy = existing.empty_table().to_pandas()
        for column in PROVENANCE_COLUMNS:
            if column not in legacy.columns:
                legacy[column] = pd.Series(dtype="string")
        schema = pa.Schema.from_pandas(legacy.iloc[0:0], preserve_index=False)
        defaults = {"source_status": SourceStatus.ACTIVE, "source_last_seen": ""}

        staged = {silver_file: temp_sibling(silver_file)}
        try:
            with pq.ParquetWriter(staged[silver_file], schema) as writer:
                for batch in iter_batches(silver_file):
                    table = conform(pa.Table.from_batches([batch]), schema, defaults)
                    table = conform(self._adapt(table, removed, seen_at), schema)
                    if len(table):
                        writer.write_table(table, row_group_size=BATCH_ROWS)
        except Exception:
            discard(staged)
            raise
        publish(staged)

    def _adapt(self, table: pa.Table, removed: set[str], seen_at: str) -> pa.Table:
        """Set `source_status`, `source_last_seen` and `source_removed_at` for one batch."""
        text = table.schema.field("source_status").type
        removed_value = pa.scalar(SourceStatus.REMOVED, type=text)
        active_value = pa.scalar(SourceStatus.ACTIVE, type=text)
        seen_value = pa.scalar(seen_at, type=text)
        null_value = pa.scalar(None, type=text)

        ids = table.column(self.id_column)
        if removed:
            is_removed = pc.is_in(ids, value_set=pa.array(sorted(removed), type=ids.type))
        else:
            is_removed = pa.array([False] * len(table), type=pa.bool_())
        was = pc.fill_null(pc.equal(table.column("source_status"), removed_value), False)
        # The first observation of a withdrawal is the provenance that matters; keep it rather
        # than restamping it on every later run.
        removed_at = pc.if_else(
            is_removed,
            pc.if_else(was, table.column("source_removed_at"), seen_value),
            null_value,
        )
        # A row the source still returns was seen now. A withdrawn row keeps the last instant it
        # was actually seen, which would otherwise be overwritten with a lie.
        last_seen = pc.if_else(is_removed, table.column("source_last_seen"), seen_value)
        status = pc.if_else(is_removed, removed_value, active_value)

        names = table.column_names
        table = table.set_column(names.index("source_status"), "source_status", status)
        table = table.set_column(names.index("source_last_seen"), "source_last_seen", last_seen)
        return table.set_column(names.index("source_removed_at"), "source_removed_at", removed_at)

    def _append_log(
        self,
        result: ReconciliationResult,
        outcome: YearReconciliation,
        started: datetime,
        status: str,
        error: str,
    ) -> None:
        ended = now()
        row: dict[str, Any] = {
            "run_id": result.run_id,
            "year": outcome.year,
            "start_time": iso(started),
            "end_time": iso(ended),
            "local_rows": outcome.local_rows,
            "source_rows": outcome.source_rows,
            "confirmed_active": outcome.confirmed_active,
            "newly_removed": outcome.newly_removed,
            "still_removed": outcome.still_removed,
            "reappeared": outcome.reappeared,
            "missing_locally": outcome.missing_locally,
            "duration_seconds": round((ended - started).total_seconds(), 3),
            "dry_run": result.dry_run,
            "status": status,
            "error": error,
        }
        existing = self.read_log()
        updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
        staged = {self.log_path: temp_sibling(self.log_path)}
        try:
            updated[RECONCILIATION_LOG_COLUMNS].to_parquet(staged[self.log_path], index=False)
        except Exception:
            discard(staged)
            raise
        publish(staged)
