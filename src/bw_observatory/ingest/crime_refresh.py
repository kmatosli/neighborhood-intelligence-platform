"""Incremental refresh of the crime layers — Bronze and Silver together.

The historical loader (`crime_history.py`) downloads a whole calendar year at a time. That
is the right tool for the first load and for a deliberate rebuild, but it is the wrong tool
for keeping the data current: every run re-pulls hundreds of thousands of rows to pick up a
few thousand changes, and the current year still ends wherever the last full pull ended.

This module fetches only what changed. The watermark is the source's `updated_on` column
(verified 2026-09-14 on `ijzp-q8t2`): the portal stamps it in one daily batch on every row
it inserts *or* modifies, and it is never null. Filtering on `date` alone would miss the
edits the city makes to existing incidents weeks after the fact — arrest status, IUCR
reclassification, relocated coordinates — which is roughly a fifth of the current year.

What one run does, in order, per affected year:

1. upsert the fetched rows by `id` into that year's Bronze partition, keyed on the year of
   the record's `date` (a record whose date moved across a year boundary is removed from
   the partition it used to sit in);
2. rewrite the manifest row — rows, checksum, timestamps — so the API's
   `bronze_integrity_verified` keeps telling the truth about the new file;
3. point-in-polygon enrich *only the fetched rows* with the same `GeographyAssigner` the
   full enrichment uses, upsert them into the Silver partition, and recompute the year's
   quality row from the whole partition;
4. reconcile the partition's row count with the source, because a watermark on
   `updated_on` cannot see deletions.

Safety properties the design leans on:

* a year's Bronze and Silver files are both staged as temp siblings and then swapped in
  back to back with `os.replace`, so a crash never leaves a half-written Parquet in place
  and the window in which the two layers disagree is milliseconds, not minutes;
* after every publish the partition invariants are proved (`partitions.partition_problems`)
  — unique ids, identical id sets on both layers, manifest checksum matching the file — and
  a run that cannot prove them fails;
* the watermark only advances when a run finishes, so an interrupted run is re-done from
  the same point — the upsert makes that harmless;
* one writer at a time (`refresh_lock.RefreshLock`): a second refresh exits with "already
  running" instead of interleaving partition writes;
* nothing historical is deleted: rows are replaced by `id` or left alone;
* Bronze is handled as Arrow tables, never as whole pandas frames, so the largest year fits
  comfortably beside the API on a 512 MB instance;
* `--dry-run` fetches, classifies, and reports; the only thing it writes is its own row in
  the refresh log, flagged `dry_run`, which the watermark ignores.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from bw_observatory.clients.chicago_data import ChicagoDataClient
from bw_observatory.config import Settings
from bw_observatory.geography.assign import (
    GeographyAssigner,
    bronze_downloaded_at,
    silver_path,
    upsert_quality_row,
)
from bw_observatory.geography.models import GeographyStatus, SourceStatus
from bw_observatory.geography.normalize import read_neighborhoods, read_silver_geography
from bw_observatory.ingest.base import (
    DATASET_ACTIVE,
    DATASET_BLOCKED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    SchemaValidationError,
    iso,
    now,
)
from bw_observatory.ingest.bronze import file_checksum, records_to_frame
from bw_observatory.ingest.catalog import register_dataset
from bw_observatory.ingest.crime_history import (
    FIRST_YEAR,
    PAGE_ORDER,
    PAGE_SIZE,
    CrimeDownloader,
    dataset_last_updated,
    year_where_clause,
)
from bw_observatory.ingest.partitions import (
    bronze_schema,
    column_max,
    discard,
    file_columns,
    frame_schema,
    frame_to_table,
    ids_present,
    partition_ids,
    partition_problems,
    publish,
    quality_row_from_file,
    row_count,
    rows_for_ids,
    sorted_by_id,
    stream_rewrite,
    temp_sibling,
    write_parquet_atomic,
)
from bw_observatory.ingest.refresh_lock import RefreshLock

INCREMENTAL_LOG_FILENAME = "incremental_refresh_log.parquet"

# One row per run, successful or not. Richer than the year-download refresh log because a
# refresh has to answer "what changed?" rather than "what was downloaded?".
INCREMENTAL_LOG_COLUMNS = [
    "run_id",
    "dataset_id",
    "start_time",
    "end_time",
    "previous_watermark",
    "new_watermark",
    "rows_fetched",
    "rows_inserted",
    "rows_updated",
    "rows_unchanged",
    "rows_out_of_range",
    "rows_moved_partition",
    "rows_missing_geography",
    "rows_silver_backfilled",
    "rows_silver_orphans",
    "partitions_touched",
    "final_bronze_rows",
    "reconciliation",
    "duration_seconds",
    "dry_run",
    "status",
    "error",
]

WATERMARK_COLUMN = "updated_on"


@dataclass
class PartitionRefresh:
    """What one run did to one calendar year."""

    year: int
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    moved_out: int = 0
    missing_geography: int = 0
    # Repairs to a Silver partition that had drifted from Bronze before this run.
    silver_backfilled: int = 0
    silver_orphans: int = 0
    local_rows: int = 0
    source_rows: int | None = None
    moved_ids: list[str] = field(default_factory=list)

    @property
    def drift(self) -> int | None:
        """Source minus local. Non-zero means rows exist the watermark cannot see."""
        return None if self.source_rows is None else self.source_rows - self.local_rows


@dataclass
class RefreshResult:
    run_id: str
    start_time: datetime
    previous_watermark: str
    dry_run: bool
    end_time: datetime | None = None
    new_watermark: str = ""
    rows_fetched: int = 0
    rows_out_of_range: int = 0
    partitions: list[PartitionRefresh] = field(default_factory=list)
    final_bronze_rows: int = 0
    warnings: int = 0
    status: str = STATUS_COMPLETE
    error: str = ""

    @property
    def rows_inserted(self) -> int:
        return sum(p.inserted for p in self.partitions)

    @property
    def rows_updated(self) -> int:
        return sum(p.updated for p in self.partitions)

    @property
    def rows_unchanged(self) -> int:
        return sum(p.unchanged for p in self.partitions)

    @property
    def rows_moved_partition(self) -> int:
        return sum(p.moved_out for p in self.partitions)

    @property
    def rows_missing_geography(self) -> int:
        return sum(p.missing_geography for p in self.partitions)

    @property
    def rows_silver_backfilled(self) -> int:
        return sum(p.silver_backfilled for p in self.partitions)

    @property
    def rows_silver_orphans(self) -> int:
        return sum(p.silver_orphans for p in self.partitions)

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or now()
        return (end - self.start_time).total_seconds()


class NothingToRefreshFrom(RuntimeError):
    """There is no Bronze crime data and no prior refresh, so no watermark exists.

    The first load is the historical downloader's job; a refresh only moves forward.
    """


def partition_year(date_value: Any) -> int | None:
    """The calendar year a record's `date` places it in, or None if it cannot be placed."""
    if not isinstance(date_value, str) or len(date_value) < 4 or not date_value[:4].isdigit():
        return None
    return int(date_value[:4])


def _id_order(ids: pd.Series) -> pd.Series:
    """Sort key matching the historical loader's `id ASC` page order (ids are numeric)."""
    return pd.to_numeric(ids, errors="coerce")


def rows_differ(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.Series:
    """Per-row: does the incoming version differ from the stored one? NA-safe.

    Both frames are indexed by `id`, restricted to the shared ids, and compared over the
    union of their columns, so a column that is new in the source counts as a change.
    """
    columns = sorted(set(existing.columns) | set(incoming.columns))
    left = existing.reindex(columns=columns).astype("string")
    right = incoming.reindex(index=left.index, columns=columns).astype("string")
    same = (left == right) | (left.isna() & right.isna())
    return ~same.all(axis=1)


class CrimeRefresher:
    """Bring the crime layers up to the source's latest `updated_on`."""

    def __init__(
        self,
        settings: Settings,
        client: ChicagoDataClient | None = None,
        *,
        page_size: int = PAGE_SIZE,
        assigner: GeographyAssigner | None = None,
    ) -> None:
        self.settings = settings
        # The historical downloader already owns the client, the validators, and the
        # Bronze writer. Reusing it keeps one definition of "a valid crime record".
        self.downloader = CrimeDownloader(settings, client, page_size=page_size)
        self.client = self.downloader.client
        self.writer = self.downloader.writer
        self.bronze_dir = self.downloader.bronze_dir
        self.silver_dir = settings.data_dir / "silver"
        self.reference_dir = settings.data_dir / "reference"
        self.log = self.downloader.log
        self._assigner = assigner

    # -- paths ----------------------------------------------------------------------

    @property
    def incremental_log_path(self) -> Path:
        return self.bronze_dir / INCREMENTAL_LOG_FILENAME

    def bronze_partition(self, year: int) -> Path:
        return self.writer.partition_path(str(year))

    def silver_partition(self, year: int) -> Path:
        return silver_path(self.silver_dir, year)

    def bronze_years(self) -> list[int]:
        return sorted(
            int(path.stem) for path in self.bronze_dir.glob("*.parquet") if path.stem.isdigit()
        )

    # -- geography ------------------------------------------------------------------

    @property
    def assigner(self) -> GeographyAssigner:
        # Loaded lazily: the boundary layers are the slow part, and a dry run that finds
        # nothing to do should not pay for them.
        if self._assigner is None:
            self._assigner = GeographyAssigner(
                read_silver_geography(self.silver_dir), read_neighborhoods(self.silver_dir)
            )
        return self._assigner

    # -- watermark ------------------------------------------------------------------

    def read_incremental_log(self) -> pd.DataFrame:
        if not self.incremental_log_path.exists():
            return pd.DataFrame(columns=INCREMENTAL_LOG_COLUMNS)
        return pd.read_parquet(self.incremental_log_path)

    def watermark(self) -> str:
        """Where the last successful refresh left off.

        With no prior refresh, the watermark is derived from what the historical loader
        left behind: for each year partition, the newest `updated_on` it holds, and then
        the **smallest** of those. A partition downloaded at time T contains every row the
        source had stamped up to that partition's own maximum, so the smallest maximum is
        the latest instant every partition is guaranteed complete to. Taking the largest
        instead would skip changes in whichever years were downloaded earlier — the 2024
        partition alone was re-pulled two weeks after the rest, and that gap is invisible
        unless the watermark is the minimum.
        """
        log = self.read_incremental_log()
        if not log.empty:
            successful = log[(log["status"] == STATUS_COMPLETE) & (~log["dry_run"].astype(bool))]
            if not successful.empty:
                return str(successful.iloc[-1]["new_watermark"])

        per_partition: list[str] = []
        for year in self.bronze_years():
            latest = column_max(self.bronze_partition(year), WATERMARK_COLUMN)
            if latest:
                per_partition.append(latest)
        if not per_partition:
            raise NothingToRefreshFrom(
                f"No Bronze crime data under {self.bronze_dir} and no prior refresh. "
                "Run scripts/download_crime_history.py first."
            )
        return min(per_partition)

    # -- fetch ----------------------------------------------------------------------

    def fetch_changed(self, since: str) -> tuple[list[dict[str, Any]], int]:
        """Every record whose `updated_on` is at or after the watermark.

        `>=` rather than `>`: the portal stamps a whole batch with one timestamp, so the
        rows sharing the watermark are re-fetched each run and classified unchanged. That
        costs a few hundred rows and guarantees a batch is never half-seen.
        """
        where = f"{WATERMARK_COLUMN} >= '{since}'"
        records: list[dict[str, Any]] = []
        warnings = 0
        offset = 0
        while True:
            self.downloader.log_api(
                "GET %s refresh since=%s offset=%d limit=%d",
                self.downloader.spec.dataset_id,
                since,
                offset,
                self.downloader.page_size,
            )
            page = self.client.get_crimes(
                limit=self.downloader.page_size, where=where, order=PAGE_ORDER, offset=offset
            )
            if not page:
                break
            warnings += self.downloader.validate_records(page, f"refresh>={since}")
            records.extend(page)
            self.log.info("Refresh: %d changed records fetched so far", len(records))
            if len(page) < self.downloader.page_size:
                break
            offset += self.downloader.page_size
        return records, warnings

    # -- run ------------------------------------------------------------------------

    def run(self, *, dry_run: bool = False, since: str | None = None) -> RefreshResult:
        """One refresh. Raises `AlreadyRunning` if another writer holds the lock."""
        with RefreshLock(self.bronze_dir):
            return self._run_locked(dry_run=dry_run, since=since)

    def _run_locked(self, *, dry_run: bool, since: str | None) -> RefreshResult:
        metadata = self.client.get_metadata()
        try:
            schema_warnings = self.downloader.validate_schema(metadata)
        except SchemaValidationError:
            register_dataset(
                self.reference_dir,
                self.downloader.spec,
                schema_version=self.downloader.schema_version(metadata),
                last_verified=iso(now()),
                status=DATASET_BLOCKED,
            )
            raise
        register_dataset(
            self.reference_dir,
            self.downloader.spec,
            schema_version=self.downloader.schema_version(metadata),
            last_verified=iso(now()),
            status=DATASET_ACTIVE,
        )

        previous = since if since is not None else self.watermark()
        result = RefreshResult(
            run_id=str(uuid.uuid4()),
            start_time=now(),
            previous_watermark=previous,
            dry_run=dry_run,
            new_watermark=previous,
            warnings=schema_warnings,
        )
        self.log.info(
            "Refresh %s starting from watermark %s%s",
            result.run_id,
            previous,
            " (dry run)" if dry_run else "",
        )

        try:
            records, record_warnings = self.fetch_changed(previous)
            result.warnings += record_warnings
            result.rows_fetched = len(records)
            self._apply(records, metadata, result, dry_run=dry_run)
            if not dry_run:
                self._verify_moves(result)
            result.status = STATUS_COMPLETE
        except Exception as exc:
            result.status = STATUS_FAILED
            result.error = f"{type(exc).__name__}: {exc}"
            self.log.error("Refresh %s failed: %s", result.run_id, result.error)
            raise
        finally:
            result.end_time = now()
            result.final_bronze_rows = self._count_bronze_rows()
            self._append_log(result)

        return result

    # -- apply ----------------------------------------------------------------------

    def _apply(
        self,
        records: list[dict[str, Any]],
        metadata: dict[str, Any],
        result: RefreshResult,
        *,
        dry_run: bool,
    ) -> None:
        if not records:
            self.log.info("Refresh: source has nothing newer than %s", result.previous_watermark)
            return

        fetched = records_to_frame(records)
        # A record can appear twice if the portal's daily batch lands mid-page. Keep the
        # later copy; it is the one the source now holds.
        fetched = fetched.drop_duplicates(subset="id", keep="last")
        result.new_watermark = max(
            result.previous_watermark, str(fetched[WATERMARK_COLUMN].dropna().max())
        )

        years = fetched["date"].map(partition_year)
        in_range = years.notna() & (years >= FIRST_YEAR)
        result.rows_out_of_range = int((~in_range).sum())
        if result.rows_out_of_range:
            self.log.info(
                "Refresh: %d changed record(s) fall before %d and are not held by this "
                "project; skipped.",
                result.rows_out_of_range,
                FIRST_YEAR,
            )
        fetched = fetched[in_range]
        years = years[in_range].astype(int)

        # Where every fetched id currently lives, so a record whose date crossed a year
        # boundary is moved rather than duplicated.
        current_home = self._locate_ids(set(fetched["id"]))

        seen_at = iso(result.start_time)
        for year in sorted(years.unique()):
            incoming = fetched[years == year].set_index("id")
            partition = PartitionRefresh(year=int(year))
            self._refresh_partition(partition, incoming, current_home, metadata, dry_run, seen_at)
            result.partitions.append(partition)

    def _locate_ids(self, ids: set[str]) -> dict[str, int]:
        """Which year file currently holds each id. An id found in two files (a move that
        was interrupted before the old copy was removed) resolves to the later year, and
        the refresh of that year removes the stale copy."""
        home: dict[str, int] = {}
        for year in self.bronze_years():
            for record_id in ids_present(self.bronze_partition(year), ids):
                home[str(record_id)] = year
        return home

    def _verify_moves(self, result: RefreshResult) -> None:
        """A moved id must now live in exactly one year file."""
        moved = {record_id for p in result.partitions for record_id in p.moved_ids}
        if not moved:
            return
        homes: dict[str, list[int]] = {}
        for year in self.bronze_years():
            for record_id in ids_present(self.bronze_partition(year), moved):
                homes.setdefault(str(record_id), []).append(year)
        duplicated = {k: v for k, v in homes.items() if len(v) > 1}
        if duplicated:
            raise RuntimeError(f"ids present in more than one year after refresh: {duplicated}")

    def _refresh_partition(
        self,
        partition: PartitionRefresh,
        incoming: pd.DataFrame,
        current_home: dict[str, int],
        metadata: dict[str, Any],
        dry_run: bool,
        seen_at: str,
    ) -> None:
        year = partition.year
        bronze_file = self.bronze_partition(year)
        bronze_exists = bronze_file.exists()
        existing_ids = partition_ids(bronze_file) if bronze_exists else set()

        incoming_ids = set(map(str, incoming.index))
        shared_ids = incoming_ids & existing_ids
        shared = pd.Index(sorted(shared_ids))
        if shared_ids:
            changed = rows_differ(rows_for_ids(bronze_file, shared_ids), incoming.loc[shared])
        else:
            changed = pd.Series(False, index=shared, dtype=bool)
        partition.unchanged = int((~changed).sum())
        partition.updated = int(changed.sum())
        partition.inserted = len(incoming) - len(shared)

        # Ids that used to live in a different year: they leave that year's files.
        moved_from: dict[int, list[str]] = {}
        for record_id in incoming.index:
            old_year = current_home.get(str(record_id))
            if old_year is not None and old_year != year:
                moved_from.setdefault(old_year, []).append(str(record_id))
        partition.moved_ids = [i for ids in moved_from.values() for i in ids]
        partition.moved_out = len(partition.moved_ids)

        # Only rows that are new or changed need to be re-enriched. Unchanged rows keep the
        # Silver assignment they already have.
        to_write = set(incoming_ids - shared_ids) | set(changed[changed].index.astype(str))

        # Column order follows the existing file, then anything new the source now sends.
        columns = list(
            dict.fromkeys(
                [*(file_columns(bronze_file) if bronze_exists else []), "id", *incoming.columns]
            )
        )
        bronze_schema_ = bronze_schema(columns)
        merged_ids = existing_ids | incoming_ids
        partition.local_rows = len(merged_ids)

        partition.source_rows = self.client.count_crimes(year_where_clause(year))

        self.log.info(
            "Refresh %d: %d inserted, %d updated, %d unchanged, %d moved in from other years; "
            "local %d vs source %d%s",
            year,
            partition.inserted,
            partition.updated,
            partition.unchanged,
            partition.moved_out,
            partition.local_rows,
            partition.source_rows,
            " (dry run — nothing written)" if dry_run else "",
        )

        # Silver is read before anything is decided so a partition whose Silver fell out
        # of step with Bronze (a year re-downloaded without being re-enriched) is healed
        # here: every Bronze id with no Silver row is enriched alongside the changed rows,
        # and a Silver row with no Bronze record is dropped on the way through.
        silver_file = self.silver_partition(year)
        silver_exists = silver_file.exists()
        silver_ids = partition_ids(silver_file) if silver_exists else set()
        to_enrich = to_write | (merged_ids - silver_ids)
        orphans = silver_ids - merged_ids
        partition.silver_backfilled = len(to_enrich) - len(to_write)
        partition.silver_orphans = len(orphans)
        if partition.silver_backfilled or partition.silver_orphans:
            self.log.warning(
                "Refresh %d: Silver was out of step with Bronze — %d Bronze record(s) had no "
                "Silver row and are being enriched; %d Silver row(s) had no Bronze record and "
                "are being dropped.",
                year,
                partition.silver_backfilled,
                partition.silver_orphans,
            )

        # Enrichment runs in dry-run too, so the report can say how many changed rows have
        # no usable geography before anything is committed. Rows come from the fetched
        # batch when they are in it and from the Bronze file (only those rows) otherwise.
        from_incoming = incoming.loc[sorted(to_enrich & incoming_ids)]
        from_file = (
            rows_for_ids(bronze_file, to_enrich - incoming_ids)
            if bronze_exists and (to_enrich - incoming_ids)
            else None
        )
        changed_bronze = (
            pd.concat([from_incoming, from_file]) if from_file is not None else from_incoming
        )
        changed_bronze = changed_bronze.reset_index().astype("string")
        enriched = self.assigner.enrich(changed_bronze, year, seen_at=seen_at)
        partition.missing_geography = int(
            (enriched["geography_status"] != GeographyStatus.ASSIGNED).sum()
        )

        if dry_run:
            return
        if not to_enrich and not orphans and not moved_from:
            # Every fetched row was already held verbatim: nothing to write, and the files
            # (and their checksums) stay byte-for-byte what they were.
            self.log.info("Refresh %d: nothing to write", year)
            return

        # Stage both layers as streams — the old file minus the replaced rows, then the new
        # rows — and publish them back to back; the manifest and quality rows follow at
        # once. Anything that fails before `publish` touches no live file.
        started = now()
        silver_schema = frame_schema(enriched)
        silver_defaults = {
            "source_status": SourceStatus.ACTIVE,
            "source_last_seen": bronze_downloaded_at(self.bronze_dir, year) or "",
        }
        staged: dict[Path, Path] = {}
        try:
            staged[bronze_file] = temp_sibling(bronze_file)
            written_bronze = stream_rewrite(
                bronze_file if bronze_exists else None,
                staged[bronze_file],
                schema=bronze_schema_,
                drop=incoming_ids,
                append=sorted_by_id(frame_to_table(incoming.reset_index(), bronze_schema_)),
            )
            staged[silver_file] = temp_sibling(silver_file)
            written_silver = stream_rewrite(
                silver_file if silver_exists else None,
                staged[silver_file],
                schema=silver_schema,
                drop=to_enrich | orphans,
                append=sorted_by_id(frame_to_table(enriched, silver_schema)),
                defaults=silver_defaults,
            )
            if (
                len(written_bronze) != partition.local_rows
                or len(set(written_bronze)) != len(written_bronze)
                or set(written_bronze) != set(written_silver)
                or len(written_silver) != len(written_bronze)
            ):
                raise RuntimeError(
                    f"{year}: staged Bronze holds {len(written_bronze)} rows and Silver "
                    f"{len(written_silver)}, expected {partition.local_rows} identical ids. "
                    "Refusing to publish a partition that drops or duplicates records."
                )
        except BaseException:
            discard(staged)
            raise
        publish(staged)
        self.writer.upsert_manifest_entry(
            {
                "partition": str(year),
                "rows": partition.local_rows,
                "download_started": iso(started),
                "download_completed": iso(now()),
                "api_version": self.downloader.api_version,
                "dataset_last_updated": dataset_last_updated(metadata),
                "checksum": file_checksum(bronze_file),
                "status": STATUS_COMPLETE,
            }
        )
        upsert_quality_row(
            self.silver_dir,
            quality_row_from_file(silver_file, year, self.assigner.bronzeville_available),
        )

        # Records that moved into this year leave the year they came from.
        for old_year, ids in moved_from.items():
            self._remove_ids(old_year, ids, metadata)

        self._assert_sound(year)

    def _assert_sound(self, year: int) -> None:
        problems = partition_problems(self.bronze_dir, self.silver_dir, year)
        if problems:
            raise RuntimeError(
                "partition invariants violated after publish: " + "; ".join(problems)
            )

    def _remove_ids(self, year: int, ids: list[str], metadata: dict[str, Any]) -> None:
        bronze_file = self.bronze_partition(year)
        silver_file = self.silver_partition(year)
        staged: dict[Path, Path] = {}
        try:
            staged[bronze_file] = temp_sibling(bronze_file)
            written = stream_rewrite(
                bronze_file,
                staged[bronze_file],
                schema=bronze_schema(file_columns(bronze_file)),
                drop=set(ids),
                append=None,
            )
            if silver_file.exists():
                staged[silver_file] = temp_sibling(silver_file)
                stream_rewrite(
                    silver_file,
                    staged[silver_file],
                    schema=pq.read_schema(silver_file),
                    drop=set(ids),
                    append=None,
                )
        except BaseException:
            discard(staged)
            raise
        publish(staged)
        self.writer.upsert_manifest_entry(
            {
                "partition": str(year),
                "rows": len(written),
                "download_started": iso(now()),
                "download_completed": iso(now()),
                "api_version": self.downloader.api_version,
                "dataset_last_updated": dataset_last_updated(metadata),
                "checksum": file_checksum(bronze_file),
                "status": STATUS_COMPLETE,
            }
        )
        if silver_file.exists():
            upsert_quality_row(
                self.silver_dir,
                quality_row_from_file(silver_file, year, self.assigner.bronzeville_available),
            )
        self.log.info("Refresh %d: %d record(s) moved to another year", year, len(ids))
        self._assert_sound(year)

    # -- bookkeeping ----------------------------------------------------------------

    def _count_bronze_rows(self) -> int:
        return sum(row_count(self.bronze_partition(year)) for year in self.bronze_years())

    def _append_log(self, result: RefreshResult) -> None:
        reconciliation = {
            str(p.year): {"local": p.local_rows, "source": p.source_rows, "drift": p.drift}
            for p in result.partitions
        }
        row = {
            "run_id": result.run_id,
            "dataset_id": self.downloader.spec.dataset_id,
            "start_time": iso(result.start_time),
            "end_time": iso(result.end_time or now()),
            "previous_watermark": result.previous_watermark,
            "new_watermark": result.new_watermark,
            "rows_fetched": result.rows_fetched,
            "rows_inserted": result.rows_inserted,
            "rows_updated": result.rows_updated,
            "rows_unchanged": result.rows_unchanged,
            "rows_out_of_range": result.rows_out_of_range,
            "rows_moved_partition": result.rows_moved_partition,
            "rows_missing_geography": result.rows_missing_geography,
            "rows_silver_backfilled": result.rows_silver_backfilled,
            "rows_silver_orphans": result.rows_silver_orphans,
            "partitions_touched": ",".join(str(p.year) for p in result.partitions),
            "final_bronze_rows": result.final_bronze_rows,
            "reconciliation": json.dumps(reconciliation),
            "duration_seconds": round(result.elapsed_seconds, 1),
            "dry_run": result.dry_run,
            "status": result.status,
            "error": result.error,
        }
        existing = self.read_incremental_log()
        updated = pd.concat([existing, pd.DataFrame([row], columns=INCREMENTAL_LOG_COLUMNS)])
        write_parquet_atomic(updated.reset_index(drop=True), self.incremental_log_path)
