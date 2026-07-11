"""Bronze storage: raw records, the manifest, and the refresh log.

Fidelity rule (see docs/methodology/DATA_GOVERNANCE.md): the Bronze layer stores what the
API returned, unmodified. Every field is written as a **string**, JSON-serializing anything
the API did not already send as a string (booleans, numbers, nested objects).

Storing strings is what preserves the data, not what alters it. Letting a dataframe infer
types would silently rewrite the source: `beat` "0132" becomes the integer 132, `id` values
beyond float precision get rounded, and a column that is all-null in one year picks a
different type than in the next. Serializing to text is lossless and reversible; type
casting happens in Silver, where it can be inspected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from bw_observatory.ingest.base import (
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    BaseBronzeWriter,
)

__all__ = [
    "MANIFEST_FILENAME",
    "REFRESH_LOG_COLUMNS",
    "REFRESH_LOG_FILENAME",
    "STATUS_COMPLETE",
    "STATUS_FAILED",
    "STATUS_IN_PROGRESS",
    "ParquetBronzeWriter",
    "file_checksum",
    "manifest_columns",
    "records_to_frame",
    "serialize_record",
]

MANIFEST_FILENAME = "manifest.parquet"
REFRESH_LOG_FILENAME = "refresh_log.parquet"

REFRESH_LOG_COLUMNS = [
    "run_id",
    "start_time",
    "end_time",
    "records_downloaded",
    "rows_written",
    "warnings",
    "errors",
    "status",
]


def manifest_columns(partition_column: str = "year") -> list[str]:
    return [
        partition_column,
        "rows",
        "download_started",
        "download_completed",
        "api_version",
        "dataset_last_updated",
        "checksum",
        "status",
    ]


def _serialize_value(value: Any) -> str | None:
    """Render one API value as text without losing information.

    Strings pass through untouched. Everything else is JSON-encoded, so `True` becomes
    "true" and a nested object becomes its JSON form. `None` stays `None` — a missing
    value is recorded as missing, never filled in.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def serialize_record(record: dict[str, Any]) -> dict[str, str | None]:
    return {key: _serialize_value(value) for key, value in record.items()}


def records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a string-typed frame preserving every field any record returned.

    Column order follows first appearance across the batch, so a field that only shows up
    on later records is still kept rather than dropped.
    """
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)

    rows = [serialize_record(record) for record in records]
    frame = pd.DataFrame(rows, columns=columns, dtype="string")
    return frame.reindex(columns=columns)


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class ParquetBronzeWriter(BaseBronzeWriter):
    """One Parquet file per partition, plus `manifest.parquet` and `refresh_log.parquet`.

    `partition_column` is what the partition is called on disk — "year" for crime. Keeping
    it configurable lets a monthly or quarterly dataset reuse this writer unchanged.
    """

    def __init__(self, bronze_dir: Path, partition_column: str = "year") -> None:
        self.bronze_dir = bronze_dir
        self.partition_column = partition_column
        self.manifest_columns = manifest_columns(partition_column)

    # -- paths ----------------------------------------------------------------------

    def partition_path(self, partition: str) -> Path:
        return self.bronze_dir / f"{partition}.parquet"

    @property
    def manifest_path(self) -> Path:
        return self.bronze_dir / MANIFEST_FILENAME

    @property
    def refresh_log_path(self) -> Path:
        return self.bronze_dir / REFRESH_LOG_FILENAME

    # -- records --------------------------------------------------------------------

    def write_partition(self, records: list[dict[str, Any]], partition: str) -> tuple[int, str]:
        path = self.partition_path(partition)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = records_to_frame(records)
        frame.to_parquet(path, index=False)
        return len(frame), file_checksum(path)

    # -- manifest -------------------------------------------------------------------

    def _read(self, path: Path, columns: list[str]) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=columns)
        return pd.read_parquet(path)

    def read_manifest(self) -> pd.DataFrame:
        return self._read(self.manifest_path, self.manifest_columns)

    def _to_row(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Translate the framework's generic `partition` into this writer's column."""
        row = dict(entry)
        partition = row.pop("partition")
        row[self.partition_column] = self._coerce_partition(partition)
        return {column: row.get(column) for column in self.manifest_columns}

    @staticmethod
    def _coerce_partition(partition: str) -> Any:
        # Keep the manifest's partition column numeric when the partition is a year, so
        # sorting and comparison behave. Anything else stays a string.
        return int(partition) if partition.isdigit() else partition

    def upsert_manifest_entry(self, entry: dict[str, Any]) -> None:
        """Insert or replace the manifest row for a partition. One row per partition."""
        manifest = self.read_manifest()
        row = self._to_row(entry)

        if not manifest.empty:
            manifest = manifest[manifest[self.partition_column] != row[self.partition_column]]

        updated = pd.concat([manifest, pd.DataFrame([row], columns=self.manifest_columns)])
        updated = updated.sort_values(self.partition_column).reset_index(drop=True)

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        updated.to_parquet(self.manifest_path, index=False)

    def completed_partitions(self) -> set[str]:
        manifest = self.read_manifest()
        if manifest.empty:
            return set()
        complete = manifest[manifest["status"] == STATUS_COMPLETE]
        return {str(value) for value in complete[self.partition_column]}

    # -- refresh log ----------------------------------------------------------------

    def append_refresh_log(self, entry: dict[str, Any]) -> None:
        existing = self._read(self.refresh_log_path, REFRESH_LOG_COLUMNS)
        updated = pd.concat([existing, pd.DataFrame([entry], columns=REFRESH_LOG_COLUMNS)])

        self.refresh_log_path.parent.mkdir(parents=True, exist_ok=True)
        updated.reset_index(drop=True).to_parquet(self.refresh_log_path, index=False)
