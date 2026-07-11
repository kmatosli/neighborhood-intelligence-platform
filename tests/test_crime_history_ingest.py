from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest
from pytest_httpx import HTTPXMock

from bw_observatory.config import Settings
from bw_observatory.ingest import bronze
from bw_observatory.ingest.base import RecordValidationError, SchemaValidationError
from bw_observatory.ingest.crime_history import (
    CrimeDownloader,
    resolve_years,
    year_where_clause,
)
from bw_observatory.validation.crime_schema import REQUIRED_CRIME_FIELDS

METADATA_URL = "https://data.cityofchicago.org/api/views/ijzp-q8t2"
DATA_URL_PREFIX = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"


def metadata(fields: set[str] | None = None) -> dict[str, Any]:
    names = REQUIRED_CRIME_FIELDS if fields is None else fields
    return {
        "rowsUpdatedAt": 1_700_000_000,
        "columns": [{"fieldName": name} for name in sorted(names)],
    }


def crime_record(record_id: int, **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": str(record_id),
        "case_number": f"JE{record_id:06d}",
        "date": "2024-03-01T12:00:00.000",
        "block": "001XX W TEST ST",
        "iucr": "0810",
        "primary_type": "THEFT",
        "description": "OVER $500",
        "location_description": "STREET",
        "arrest": False,
        "domestic": False,
        "beat": "0132",
        "district": "001",
        "ward": "3",
        "community_area": "35",
        "year": 2024,
        "updated_on": "2024-03-08T15:00:00.000",
        "latitude": "41.8781",
        "longitude": "-87.6298",
    }
    record.update(overrides)
    return record


def mock_api(
    httpx_mock: HTTPXMock,
    pages: list[list[dict[str, Any]]],
    meta: dict[str, Any] | None = None,
) -> None:
    """Route by URL: metadata always answers; data requests consume `pages` in order.

    Needed for multi-run tests, where each run re-fetches metadata and a plain response
    queue would hand the second run's metadata request a leftover data page.
    """
    remaining = list(pages)
    payload = metadata() if meta is None else meta

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in str(request.url):
            return httpx.Response(200, json=payload)
        page = remaining.pop(0) if remaining else []
        return httpx.Response(200, json=page)

    httpx_mock.add_callback(handler, is_reusable=True)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


@pytest.fixture
def ingestor(settings: Settings) -> CrimeDownloader:
    # Small page size so paging is exercised without 50k fixture records.
    return CrimeDownloader(settings, page_size=2)


def test_year_where_clause_is_half_open() -> None:
    clause = year_where_clause(2024)
    assert "date >= '2024-01-01T00:00:00.000'" in clause
    assert "date < '2025-01-01T00:00:00.000'" in clause


def test_paging_follows_offsets_until_a_short_page(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1), crime_record(2)])  # full page -> keep going
    httpx_mock.add_response(json=[crime_record(3)])  # short page -> stop

    run = ingestor.run_years([2024])

    assert run.records_downloaded == 3
    assert run.rows_written == 3
    assert run.partitions[0].pages == 2

    data_requests = [r for r in httpx_mock.get_requests() if str(r.url).startswith(DATA_URL_PREFIX)]
    assert len(data_requests) == 2
    assert "%24offset=2" in str(data_requests[1].url)
    # Paging must be ordered by a stable key, or records shift between pages.
    assert "id+ASC" in str(data_requests[0].url) or "id%20ASC" in str(data_requests[0].url)


def test_empty_page_terminates_paging(httpx_mock: HTTPXMock, ingestor: CrimeDownloader) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1), crime_record(2)])
    httpx_mock.add_response(json=[])

    run = ingestor.run_years([2024])

    assert run.records_downloaded == 2
    assert run.rows_written == 2


def test_retry_recovers_from_a_transport_error(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
    httpx_mock.add_response(json=[crime_record(1)])

    run = ingestor.run_years([2024])

    assert run.records_downloaded == 1
    assert run.status == bronze.STATUS_COMPLETE


def test_year_partitioning_writes_one_file_per_year(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1)])  # 2023
    httpx_mock.add_response(json=[crime_record(2)])  # 2024

    ingestor.run_years([2023, 2024])

    assert (ingestor.bronze_dir / "2023.parquet").exists()
    assert (ingestor.bronze_dir / "2024.parquet").exists()


def test_manifest_records_each_year(httpx_mock: HTTPXMock, ingestor: CrimeDownloader) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1)])

    ingestor.run_years([2024])

    manifest = ingestor.writer.read_manifest()
    assert list(manifest.columns) == bronze.manifest_columns("year")

    row = manifest.iloc[0]
    assert int(row["year"]) == 2024
    assert int(row["rows"]) == 1
    assert row["status"] == bronze.STATUS_COMPLETE
    assert row["checksum"]
    assert row["download_started"]
    assert row["download_completed"]
    assert row["api_version"]
    assert row["dataset_last_updated"]


def test_refresh_log_appends_one_row_per_run(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1)])
    ingestor.run_years([2024])

    log = pd.read_parquet(ingestor.bronze_dir / bronze.REFRESH_LOG_FILENAME)
    assert list(log.columns) == bronze.REFRESH_LOG_COLUMNS
    assert len(log) == 1
    assert log.iloc[0]["status"] == bronze.STATUS_COMPLETE
    assert int(log.iloc[0]["rows_written"]) == 1


def test_resume_skips_completed_years(httpx_mock: HTTPXMock, ingestor: CrimeDownloader) -> None:
    mock_api(httpx_mock, pages=[[crime_record(1)]])
    ingestor.run_years([2024])

    before = len(httpx_mock.get_requests())

    second = ingestor.run_years([2024], resume=True)

    assert second.partitions[0].skipped is True
    assert second.rows_written == 0
    # Only the metadata request; the year itself was not re-fetched.
    new_requests = httpx_mock.get_requests()[before:]
    assert not [r for r in new_requests if str(r.url).startswith(DATA_URL_PREFIX)]


def test_resume_selects_only_incomplete_years(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1)])
    ingestor.run_years([2023])

    remaining = resolve_years(
        start_year=2023,
        end_year=2025,
        resume=True,
        bronze_dir=ingestor.bronze_dir,
        current_year=2026,
    )

    assert remaining == [2024, 2025]


def test_force_redownloads_a_complete_year(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    mock_api(
        httpx_mock,
        pages=[
            [crime_record(1)],  # first run: one short page
            [crime_record(1), crime_record(2)],  # forced re-run: full page...
            [],  # ...then exhausted
        ],
    )
    ingestor.run_years([2024])

    forced = ingestor.run_years([2024], force=True)

    assert forced.partitions[0].skipped is False
    assert forced.rows_written == 2


def test_missing_required_column_blocks_before_any_download(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata(REQUIRED_CRIME_FIELDS - {"latitude"}))

    with pytest.raises(SchemaValidationError, match="latitude"):
        ingestor.run_years([2024])

    # Nothing was fetched and nothing was written.
    assert not [r for r in httpx_mock.get_requests() if str(r.url).startswith(DATA_URL_PREFIX)]
    assert not (ingestor.bronze_dir / "2024.parquet").exists()


def test_failed_run_is_recorded_in_the_refresh_log(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata(REQUIRED_CRIME_FIELDS - {"latitude"}))

    with pytest.raises(SchemaValidationError):
        ingestor.run_years([2024])

    log = pd.read_parquet(ingestor.bronze_dir / bronze.REFRESH_LOG_FILENAME)
    assert log.iloc[0]["status"] == bronze.STATUS_FAILED
    assert int(log.iloc[0]["errors"]) == 1


def test_record_missing_a_core_field_blocks_the_year(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    broken = crime_record(2)
    del broken["id"]

    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1), broken])

    with pytest.raises(RecordValidationError, match="core fields"):
        ingestor.run_years([2024])


def test_records_without_coordinates_are_kept_and_warned(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    no_coords = crime_record(2)
    del no_coords["latitude"]
    del no_coords["longitude"]

    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1), no_coords])
    httpx_mock.add_response(json=[])

    run = ingestor.run_years([2024])

    assert run.analytic_warnings == 1
    assert run.warnings >= 1
    # Kept, not discarded.
    assert run.rows_written == 2

    frame = pd.read_parquet(ingestor.bronze_dir / "2024.parquet")
    assert len(frame) == 2
    assert frame["latitude"].isna().sum() == 1


def test_bronze_preserves_source_fields_verbatim(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata())
    httpx_mock.add_response(json=[crime_record(1)])

    ingestor.run_years([2024])
    frame = pd.read_parquet(ingestor.bronze_dir / "2024.parquet")
    row = frame.iloc[0]

    # Geography fields are preserved exactly as published, for later GIS assignment.
    # A leading-zero beat must not be coerced into an integer.
    assert row["beat"] == "0132"
    assert row["district"] == "001"
    assert row["ward"] == "3"
    assert row["community_area"] == "35"
    assert row["latitude"] == "41.8781"
    assert row["longitude"] == "-87.6298"
    # Booleans and numbers survive losslessly in their JSON form.
    assert row["arrest"] == "false"
    assert row["year"] == "2024"


def test_unknown_source_column_warns_but_does_not_block(
    httpx_mock: HTTPXMock, ingestor: CrimeDownloader
) -> None:
    httpx_mock.add_response(url=METADATA_URL, json=metadata(REQUIRED_CRIME_FIELDS | {"brand_new"}))
    httpx_mock.add_response(json=[crime_record(1, brand_new="kept")])

    run = ingestor.run_years([2024])

    assert run.status == bronze.STATUS_COMPLETE
    assert run.warnings >= 1

    frame = pd.read_parquet(ingestor.bronze_dir / "2024.parquet")
    assert frame.iloc[0]["brand_new"] == "kept"


def test_resolve_years_rejects_years_before_2006() -> None:
    with pytest.raises(ValueError, match="2006"):
        resolve_years(year=2005, current_year=2026)


def test_resolve_years_defaults_to_full_range() -> None:
    assert resolve_years(current_year=2008) == [2006, 2007, 2008]
