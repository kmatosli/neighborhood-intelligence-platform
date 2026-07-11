"""Reusable ingestion framework.

Two abstractions, so a second dataset does not mean a second copy of this logic:

* `BaseBronzeWriter` — where raw records land, and how a partition's progress is recorded.
* `BaseDownloader` — the orchestration every source shares: validate the schema before
  fetching anything, page through a partition, never discard records, reconcile the row
  count, mark the partition complete, log the run.

Subclasses supply only what is genuinely source-specific: how to fetch metadata, how to
fetch a page, and what validity means for their records.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_IN_PROGRESS = "in_progress"

# Catalog statuses for a dataset as a whole, distinct from a partition's status above.
DATASET_ACTIVE = "active"
DATASET_BLOCKED = "blocked"


class SchemaValidationError(RuntimeError):
    """The source schema no longer provides a column the project depends on."""


class RecordValidationError(RuntimeError):
    """A record is missing a core field. Records are never silently discarded."""


@dataclass(frozen=True)
class DatasetSpec:
    """What a dataset is, as registered in the dataset catalog."""

    dataset_id: str
    dataset_name: str
    source: str
    primary_key: str
    date_column: str
    refresh_frequency: str
    bronze_location: str


@dataclass
class PartitionResult:
    """One partition (for crime, one calendar year)."""

    partition: str
    records_downloaded: int = 0
    rows_written: int = 0
    pages: int = 0
    analytic_warnings: int = 0
    skipped: bool = False
    checksum: str = ""


@dataclass
class RunResult:
    run_id: str
    start_time: datetime
    end_time: datetime | None = None
    partitions: list[PartitionResult] = field(default_factory=list)
    warnings: int = 0
    errors: int = 0
    status: str = STATUS_IN_PROGRESS

    @property
    def records_downloaded(self) -> int:
        return sum(p.records_downloaded for p in self.partitions)

    @property
    def rows_written(self) -> int:
        return sum(p.rows_written for p in self.partitions)

    @property
    def analytic_warnings(self) -> int:
        return sum(p.analytic_warnings for p in self.partitions)

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or datetime.now(UTC)
        return (end - self.start_time).total_seconds()


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.isoformat()


class BaseBronzeWriter(ABC):
    """Raw storage for one dataset, plus its manifest and refresh log."""

    @abstractmethod
    def partition_path(self, partition: str) -> Path: ...

    @abstractmethod
    def write_partition(self, records: list[dict[str, Any]], partition: str) -> tuple[int, str]:
        """Write records verbatim. Returns (rows written, checksum)."""

    @abstractmethod
    def upsert_manifest_entry(self, entry: dict[str, Any]) -> None: ...

    @abstractmethod
    def read_manifest(self) -> pd.DataFrame: ...

    @abstractmethod
    def completed_partitions(self) -> set[str]:
        """Partitions already written in full — what `--resume` skips."""

    @abstractmethod
    def append_refresh_log(self, entry: dict[str, Any]) -> None: ...


class BaseDownloader(ABC):
    """Shared ingestion orchestration. Subclass per source dataset."""

    def __init__(
        self,
        spec: DatasetSpec,
        writer: BaseBronzeWriter,
        *,
        page_size: int,
        reference_dir: Path,
    ) -> None:
        self.spec = spec
        self.writer = writer
        self.page_size = page_size
        self.reference_dir = reference_dir

    # -- source-specific ------------------------------------------------------------

    @abstractmethod
    def fetch_metadata(self) -> dict[str, Any]:
        """Source metadata, used to validate the schema before anything is downloaded."""

    @abstractmethod
    def fetch_page(self, partition: str, offset: int, limit: int) -> list[dict[str, Any]]:
        """One page of records for a partition, ordered by a stable key."""

    @abstractmethod
    def validate_schema(self, metadata: dict[str, Any]) -> int:
        """Blocking check. Raise SchemaValidationError; return a count of warnings."""

    @abstractmethod
    def validate_records(self, records: list[dict[str, Any]], partition: str) -> int:
        """Blocking check per record. Raise RecordValidationError; return warning count."""

    @abstractmethod
    def schema_version(self, metadata: dict[str, Any]) -> str:
        """A fingerprint of the source schema, recorded in the catalog."""

    @abstractmethod
    def source_last_updated(self, metadata: dict[str, Any]) -> str: ...

    @property
    @abstractmethod
    def api_version(self) -> str: ...

    # -- logging hooks (subclasses provide their loggers) ----------------------------

    @abstractmethod
    def log_download(self, message: str, *args: Any) -> None: ...

    @abstractmethod
    def log_api(self, message: str, *args: Any) -> None: ...

    # -- shared orchestration -------------------------------------------------------

    def download_partition(self, partition: str, metadata: dict[str, Any]) -> PartitionResult:
        """Page through one partition and write it. Identical for every dataset."""
        result = PartitionResult(partition=partition)
        started = now()

        self.writer.upsert_manifest_entry(
            self._manifest_entry(
                partition,
                rows=0,
                started=started,
                completed=None,
                checksum="",
                status=STATUS_IN_PROGRESS,
                metadata=metadata,
            )
        )

        records: list[dict[str, Any]] = []
        offset = 0
        while True:
            self.log_api(
                "GET %s partition=%s offset=%d limit=%d",
                self.spec.dataset_id,
                partition,
                offset,
                self.page_size,
            )
            page = self.fetch_page(partition, offset, self.page_size)
            result.pages += 1
            self.log_api(
                "Received %d records (partition=%s offset=%d)", len(page), partition, offset
            )

            if not page:
                break

            result.analytic_warnings += self.validate_records(page, partition)
            records.extend(page)
            result.records_downloaded += len(page)
            self.log_download(
                "Partition %s: %d records downloaded so far (page %d)",
                partition,
                result.records_downloaded,
                result.pages,
            )

            if len(page) < self.page_size:
                break
            offset += self.page_size

        rows, checksum = self.writer.write_partition(records, partition)
        result.rows_written = rows
        result.checksum = checksum

        if rows != result.records_downloaded:
            # Records are never silently discarded. If these disagree, something dropped
            # data between the API and the file, and the partition is not trustworthy.
            raise RecordValidationError(
                f"Partition {partition}: downloaded {result.records_downloaded} records but "
                f"wrote {rows} rows. Refusing to mark it complete."
            )

        self.writer.upsert_manifest_entry(
            self._manifest_entry(
                partition,
                rows=rows,
                started=started,
                completed=now(),
                checksum=checksum,
                status=STATUS_COMPLETE,
                metadata=metadata,
            )
        )
        self.log_download(
            "Partition %s complete: %d rows written to %s",
            partition,
            rows,
            self.writer.partition_path(partition),
        )
        return result

    def run(
        self,
        partitions: list[str],
        *,
        resume: bool = False,
        force: bool = False,
    ) -> RunResult:
        """Download the requested partitions. A failure leaves good partitions intact."""
        from bw_observatory.ingest import catalog

        run = RunResult(run_id=str(uuid.uuid4()), start_time=now())
        self.log_download("Run %s starting for partitions %s", run.run_id, partitions)

        try:
            metadata = self.fetch_metadata()
            try:
                run.warnings += self.validate_schema(metadata)
            except SchemaValidationError:
                # The catalog must record that this dataset can no longer be trusted,
                # not just that a single run failed.
                catalog.register_dataset(
                    self.reference_dir,
                    self.spec,
                    schema_version=self.schema_version(metadata),
                    last_verified=iso(now()),
                    status=DATASET_BLOCKED,
                )
                raise

            catalog.register_dataset(
                self.reference_dir,
                self.spec,
                schema_version=self.schema_version(metadata),
                last_verified=iso(now()),
                status=DATASET_ACTIVE,
            )

            already_done = set() if force else self.writer.completed_partitions()

            for partition in partitions:
                if partition in already_done:
                    reason = "resume" if resume else "already complete"
                    self.log_download(
                        "Partition %s skipped (%s). Use --force to re-download.",
                        partition,
                        reason,
                    )
                    run.partitions.append(PartitionResult(partition=partition, skipped=True))
                    continue

                partition_result = self.download_partition(partition, metadata)
                run.partitions.append(partition_result)
                if partition_result.analytic_warnings:
                    run.warnings += 1

            run.status = STATUS_COMPLETE

        except Exception as exc:
            run.errors += 1
            run.status = STATUS_FAILED
            self.log_download("Run %s failed: %s", run.run_id, exc)
            raise
        finally:
            run.end_time = now()
            self.writer.append_refresh_log(
                {
                    "run_id": run.run_id,
                    "start_time": iso(run.start_time),
                    "end_time": iso(run.end_time),
                    "records_downloaded": run.records_downloaded,
                    "rows_written": run.rows_written,
                    "warnings": run.warnings,
                    "errors": run.errors,
                    "status": run.status,
                }
            )

        return run

    def _manifest_entry(
        self,
        partition: str,
        *,
        rows: int,
        started: datetime,
        completed: datetime | None,
        checksum: str,
        status: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "rows": rows,
            "download_started": iso(started),
            "download_completed": None if completed is None else iso(completed),
            "api_version": self.api_version,
            "dataset_last_updated": self.source_last_updated(metadata),
            "checksum": checksum,
            "status": status,
            "partition": partition,
        }
