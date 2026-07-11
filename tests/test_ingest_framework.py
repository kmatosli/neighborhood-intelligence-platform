"""Tests for the reusable ingestion framework: the writer, the catalog, and BaseDownloader.

BaseDownloader is exercised here through a fake source with no HTTP at all — which is the
point of the refactor: a second dataset gets paging, resume, manifest, reconciliation, and
catalog registration without reimplementing any of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bw_observatory.ingest.base import (
    DATASET_ACTIVE,
    DATASET_BLOCKED,
    STATUS_COMPLETE,
    BaseDownloader,
    DatasetSpec,
    RecordValidationError,
    SchemaValidationError,
)
from bw_observatory.ingest.bronze import ParquetBronzeWriter
from bw_observatory.ingest.catalog import (
    CATALOG_COLUMNS,
    catalog_path,
    read_catalog,
    schema_fingerprint,
)

FAKE_SPEC = DatasetSpec(
    dataset_id="test-0001",
    dataset_name="Test Dataset",
    source="Test Source",
    primary_key="id",
    date_column="occurred_at",
    refresh_frequency="weekly",
    bronze_location="data/bronze/test",
)


class FakeDownloader(BaseDownloader):
    """A source with no HTTP. Supplies pages from a dict; everything else is inherited."""

    def __init__(
        self,
        tmp_path: Path,
        pages: dict[str, list[list[dict[str, Any]]]],
        *,
        page_size: int = 2,
        missing_column: bool = False,
        core_field_missing: bool = False,
    ) -> None:
        super().__init__(
            FAKE_SPEC,
            ParquetBronzeWriter(tmp_path / "bronze" / "test", partition_column="year"),
            page_size=page_size,
            reference_dir=tmp_path / "reference",
        )
        self.pages = pages
        self.missing_column = missing_column
        self.core_field_missing = core_field_missing
        self.messages: list[str] = []

    @property
    def api_version(self) -> str:
        return "test-v1"

    def fetch_metadata(self) -> dict[str, Any]:
        return {"columns": ["id", "occurred_at"], "updated": "2026-01-01"}

    def fetch_page(self, partition: str, offset: int, limit: int) -> list[dict[str, Any]]:
        pages = self.pages.get(partition, [])
        index = offset // limit
        return pages[index] if index < len(pages) else []

    def validate_schema(self, metadata: dict[str, Any]) -> int:
        if self.missing_column:
            raise SchemaValidationError("Source dataset is missing required columns: ['id']")
        return 0

    def validate_records(self, records: list[dict[str, Any]], partition: str) -> int:
        if self.core_field_missing:
            raise RecordValidationError("missing core fields")
        return sum(1 for record in records if record.get("optional") is None)

    def schema_version(self, metadata: dict[str, Any]) -> str:
        return schema_fingerprint(set(metadata["columns"]))

    def source_last_updated(self, metadata: dict[str, Any]) -> str:
        return str(metadata["updated"])

    def log_download(self, message: str, *args: Any) -> None:
        self.messages.append(message % args if args else message)

    def log_api(self, message: str, *args: Any) -> None:
        self.messages.append(message % args if args else message)


def record(n: int, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"id": str(n), "occurred_at": "2024-01-01", "optional": "x"}
    row.update(overrides)
    return row


# -- schema fingerprint ------------------------------------------------------------------


def test_schema_fingerprint_is_stable_and_order_independent() -> None:
    assert schema_fingerprint({"a", "b"}) == schema_fingerprint({"b", "a"})


def test_schema_fingerprint_changes_when_a_column_changes() -> None:
    # This is what makes a shifting schema_version in the catalog a drift signal.
    assert schema_fingerprint({"a", "b"}) != schema_fingerprint({"a", "b", "c"})


# -- the framework, driven by a non-crime source -----------------------------------------


def test_base_downloader_pages_and_writes_without_source_specific_code(tmp_path: Path) -> None:
    downloader = FakeDownloader(tmp_path, {"2024": [[record(1), record(2)], [record(3)]]})

    run = downloader.run(["2024"])

    assert run.records_downloaded == 3
    assert run.rows_written == 3
    assert run.partitions[0].pages == 2
    assert run.status == STATUS_COMPLETE
    assert (tmp_path / "bronze" / "test" / "2024.parquet").exists()


def test_base_downloader_resumes_and_forces(tmp_path: Path) -> None:
    pages = {"2024": [[record(1)]]}
    downloader = FakeDownloader(tmp_path, pages)
    downloader.run(["2024"])

    resumed = downloader.run(["2024"], resume=True)
    assert resumed.partitions[0].skipped is True
    assert resumed.rows_written == 0

    forced = downloader.run(["2024"], force=True)
    assert forced.partitions[0].skipped is False
    assert forced.rows_written == 1


def test_row_count_mismatch_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If anything drops records between the API and the file, the partition must not pass."""
    downloader = FakeDownloader(tmp_path, {"2024": [[record(1), record(2)]]})

    def short_write(records: list[dict[str, Any]], partition: str) -> tuple[int, str]:
        return len(records) - 1, "deadbeef"  # silently lose one row

    monkeypatch.setattr(downloader.writer, "write_partition", short_write)

    with pytest.raises(RecordValidationError, match="Refusing to mark it complete"):
        downloader.run(["2024"])


# -- catalog ------------------------------------------------------------------------------


def test_successful_run_registers_the_dataset_as_active(tmp_path: Path) -> None:
    downloader = FakeDownloader(tmp_path, {"2024": [[record(1)]]})
    downloader.run(["2024"])

    catalog = read_catalog(tmp_path / "reference")

    assert catalog_path(tmp_path / "reference").name == "dataset_catalog.parquet"
    assert list(catalog.columns) == CATALOG_COLUMNS
    assert len(catalog) == 1

    row = catalog.iloc[0]
    assert row["dataset_id"] == "test-0001"
    assert row["dataset_name"] == "Test Dataset"
    assert row["source"] == "Test Source"
    assert row["primary_key"] == "id"
    assert row["date_column"] == "occurred_at"
    assert row["refresh_frequency"] == "weekly"
    assert row["bronze_location"] == "data/bronze/test"
    assert row["schema_version"]
    assert row["last_verified"]
    assert row["status"] == DATASET_ACTIVE


def test_schema_failure_marks_the_dataset_blocked_in_the_catalog(tmp_path: Path) -> None:
    downloader = FakeDownloader(tmp_path, {"2024": [[record(1)]]}, missing_column=True)

    with pytest.raises(SchemaValidationError):
        downloader.run(["2024"])

    catalog = read_catalog(tmp_path / "reference")
    # The dataset is untrustworthy, not merely one run — downstream must be able to see that.
    assert catalog.iloc[0]["status"] == DATASET_BLOCKED


def test_catalog_keeps_one_row_per_dataset(tmp_path: Path) -> None:
    downloader = FakeDownloader(tmp_path, {"2024": [[record(1)]]})
    downloader.run(["2024"])
    first = read_catalog(tmp_path / "reference").iloc[0]["last_verified"]

    downloader.run(["2024"], force=True)
    catalog = read_catalog(tmp_path / "reference")

    assert len(catalog) == 1
    assert catalog.iloc[0]["last_verified"] >= first


# -- writer -------------------------------------------------------------------------------


def test_writer_preserves_values_verbatim(tmp_path: Path) -> None:
    writer = ParquetBronzeWriter(tmp_path / "bronze")
    rows, checksum = writer.write_partition(
        [{"id": "1", "beat": "0132", "arrest": False, "nested": {"a": 1}}], "2024"
    )

    assert rows == 1
    assert checksum

    import pandas as pd

    frame = pd.read_parquet(writer.partition_path("2024"))
    assert frame.iloc[0]["beat"] == "0132"  # leading zero survives
    assert frame.iloc[0]["arrest"] == "false"
    assert frame.iloc[0]["nested"] == '{"a": 1}'


def test_writer_partition_column_is_configurable(tmp_path: Path) -> None:
    writer = ParquetBronzeWriter(tmp_path / "bronze", partition_column="month")
    writer.write_partition([{"id": "1"}], "2024-01")
    writer.upsert_manifest_entry(
        {
            "partition": "2024-01",
            "rows": 1,
            "download_started": "t0",
            "download_completed": "t1",
            "api_version": "v",
            "dataset_last_updated": "u",
            "checksum": "c",
            "status": STATUS_COMPLETE,
        }
    )

    manifest = writer.read_manifest()
    assert "month" in manifest.columns
    assert manifest.iloc[0]["month"] == "2024-01"
    assert writer.completed_partitions() == {"2024-01"}
