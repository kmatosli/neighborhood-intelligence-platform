"""Incremental crime refresh: watermark, upsert, enrichment, safety properties."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from pytest_httpx import HTTPXMock
from shapely.geometry import Polygon

from bw_observatory.clients.chicago_data import ChicagoDataClient, ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.geography.assign import GeographyAssigner, quality_path, silver_path
from bw_observatory.geography.models import INTERCHANGE_CRS, NeighborhoodStatus
from bw_observatory.ingest.base import STATUS_COMPLETE, STATUS_FAILED
from bw_observatory.ingest.bronze import ParquetBronzeWriter, records_to_frame
from bw_observatory.ingest.crime_refresh import (
    CrimeRefresher,
    NothingToRefreshFrom,
    partition_year,
    rows_differ,
)
from bw_observatory.validation.crime_schema import REQUIRED_CRIME_FIELDS

DATA_URL = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"

# One square over the real south side (see tests/test_geography.py): community area 42,
# ward 20. Points inside land in Ward 20; points elsewhere in the city do not.
SQUARE = Polygon([(-87.61, 41.78), (-87.60, 41.78), (-87.60, 41.79), (-87.61, 41.79)])
INSIDE = {"latitude": "41.785", "longitude": "-87.605"}


def metadata() -> dict[str, Any]:
    return {
        "rowsUpdatedAt": 1_700_000_000,
        "columns": [{"fieldName": name} for name in sorted(REQUIRED_CRIME_FIELDS)],
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
        "district": "003",
        "ward": "20",
        "community_area": "42",
        "year": 2024,
        "updated_on": "2024-03-08T15:00:00.000",
        **INSIDE,
    }
    record.update(overrides)
    return record


def assigner() -> GeographyAssigner:
    dimension = gpd.GeoDataFrame(
        {
            "geography_type": ["community_area", "ward"],
            "geography_id": ["42", "20"],
            "geography_name": ["WOODLAWN", "20"],
            "vintage_start": ["1920", "2023"],
        },
        geometry=[SQUARE, SQUARE],
        crs=INTERCHANGE_CRS,
    )
    neighborhoods = gpd.GeoDataFrame(
        {
            "neighborhood_id": ["woodlawn", "bronzeville"],
            "status": [NeighborhoodStatus.ACTIVE, NeighborhoodStatus.BLOCKED],
        },
        geometry=[SQUARE, None],
        crs=INTERCHANGE_CRS,
    )
    return GeographyAssigner(dimension, neighborhoods)


def mock_api(
    httpx_mock: HTTPXMock,
    changed: list[dict[str, Any]],
    *,
    counts: dict[int, int] | None = None,
    count_error: bool = False,
) -> None:
    """Metadata always answers; a `$select=count(*)` request answers from `counts` (keyed
    by year, parsed out of the `$where`); everything else is one page of changed rows."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/views/" in url:
            return httpx.Response(200, json=metadata())
        params = request.url.params
        if params.get("$select", "").startswith("count"):
            if count_error:
                return httpx.Response(500, json={"error": "boom"})
            year = int(params["$where"].split("'")[1][:4])
            return httpx.Response(200, json=[{"n": str((counts or {}).get(year, 0))}])
        if "$offset" in params:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=changed)

    httpx_mock.add_callback(handler, is_reusable=True)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


@pytest.fixture
def refresher(settings: Settings) -> CrimeRefresher:
    return CrimeRefresher(settings, page_size=50, assigner=assigner())


def seed_year(refresher: CrimeRefresher, year: int, records: list[dict[str, Any]]) -> None:
    """A year as the historical loader would have left it: Bronze, manifest, Silver."""
    writer = ParquetBronzeWriter(refresher.bronze_dir)
    rows, checksum = writer.write_partition(records, str(year))
    writer.upsert_manifest_entry(
        {
            "partition": str(year),
            "rows": rows,
            "download_started": "2026-07-11T23:00:00+00:00",
            "download_completed": "2026-07-11T23:01:00+00:00",
            "api_version": "socrata-resource-v2.1",
            "dataset_last_updated": "2026-07-11T12:11:28+00:00",
            "checksum": checksum,
            "status": STATUS_COMPLETE,
        }
    )
    enriched = refresher.assigner.enrich(records_to_frame(records), year)
    target = silver_path(refresher.silver_dir, year)
    target.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(target, index=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bronze(refresher: CrimeRefresher, year: int) -> pd.DataFrame:
    return pd.read_parquet(refresher.bronze_partition(year))


def silver(refresher: CrimeRefresher, year: int) -> pd.DataFrame:
    return pd.read_parquet(refresher.silver_partition(year))


def manifest_row(refresher: CrimeRefresher, year: int) -> pd.Series:
    manifest = refresher.writer.read_manifest()
    return manifest[manifest["year"] == year].iloc[0]


# -- helpers -------------------------------------------------------------------------


def test_partition_year_reads_the_date_not_the_year_field() -> None:
    assert partition_year("2025-01-01T00:00:00.000") == 2025
    assert partition_year(None) is None
    assert partition_year("bogus") is None


def test_rows_differ_is_na_safe() -> None:
    existing = pd.DataFrame({"a": ["1", None], "b": ["x", "y"]}, index=pd.Index(["1", "2"]))
    incoming = pd.DataFrame({"a": ["1", None], "b": ["x", "z"]}, index=pd.Index(["1", "2"]))
    assert rows_differ(existing, incoming).tolist() == [False, True]


def test_count_crimes_parses_the_aggregate(httpx_mock: HTTPXMock, settings: Settings) -> None:
    httpx_mock.add_response(json=[{"n": "42"}])
    assert ChicagoDataClient(settings).count_crimes("date >= '2024'") == 42


def test_count_crimes_rejects_a_malformed_aggregate(
    httpx_mock: HTTPXMock, settings: Settings
) -> None:
    httpx_mock.add_response(json=[{"count": "42"}])
    with pytest.raises(ChicagoDataError):
        ChicagoDataClient(settings).count_crimes()


# -- watermark -----------------------------------------------------------------------


def test_no_data_and_no_log_means_nothing_to_refresh_from(refresher: CrimeRefresher) -> None:
    with pytest.raises(NothingToRefreshFrom):
        refresher.watermark()


def test_fallback_watermark_is_the_smallest_partition_maximum(refresher: CrimeRefresher) -> None:
    # 2024 was re-downloaded later and carries newer stamps; 2023 is the partition that
    # bounds what every year is guaranteed to hold.
    seed_year(refresher, 2023, [crime_record(1, updated_on="2026-07-10T15:53:54.000")])
    seed_year(
        refresher,
        2024,
        [crime_record(2, date="2024-05-01T00:00:00.000", updated_on="2026-07-25T16:47:30.000")],
    )
    assert refresher.watermark() == "2026-07-10T15:53:54.000"


# -- upsert --------------------------------------------------------------------------


def test_refresh_inserts_updates_and_keeps_unchanged_rows(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    changed = [
        crime_record(1),  # re-fetched at the watermark, identical
        crime_record(2, arrest=True, updated_on="2024-04-01T15:00:00.000"),  # edited
        crime_record(3, updated_on="2024-04-01T15:00:00.000"),  # new
    ]
    mock_api(httpx_mock, changed, counts={2024: 3})

    result = refresher.run()

    assert result.status == STATUS_COMPLETE
    assert (result.rows_inserted, result.rows_updated, result.rows_unchanged) == (1, 1, 1)
    assert result.new_watermark == "2024-04-01T15:00:00.000"
    assert result.partitions[0].drift == 0

    frame = bronze(refresher, 2024).set_index("id")
    assert frame.index.tolist() == ["1", "2", "3"]
    assert frame.loc["2", "arrest"] == "true"  # Bronze fidelity: JSON text, not a bool
    assert frame.loc["1", "arrest"] == "false"

    enriched = silver(refresher, 2024).set_index("id")
    assert enriched.index.tolist() == ["1", "2", "3"]
    assert enriched.loc["3", "spatial_ward_current"] == "20"

    row = manifest_row(refresher, 2024)
    assert row["rows"] == 3
    assert row["checksum"] == sha256(refresher.bronze_partition(2024))

    quality = pd.read_parquet(quality_path(refresher.silver_dir))
    assert quality.loc[quality["year"] == 2024, "total_records"].item() == 3

    log = refresher.read_incremental_log()
    assert len(log) == 1
    assert log.iloc[0]["status"] == STATUS_COMPLETE
    assert log.iloc[0]["rows_inserted"] == 1
    assert json.loads(log.iloc[0]["reconciliation"])["2024"]["drift"] == 0


def test_running_twice_changes_nothing_the_second_time(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    changed = [crime_record(2, updated_on="2024-04-01T15:00:00.000")]
    mock_api(httpx_mock, changed, counts={2024: 2})

    first = refresher.run()
    before = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))

    second = refresher.run()

    assert first.rows_inserted == 1
    assert second.previous_watermark == first.new_watermark
    assert (second.rows_inserted, second.rows_updated, second.rows_unchanged) == (0, 0, 1)
    after = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))
    assert after == before
    assert manifest_row(refresher, 2024)["checksum"] == before[0]
    assert len(refresher.read_incremental_log()) == 2


def test_record_whose_date_crossed_a_year_is_moved_not_duplicated(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(9, date="2024-12-31T23:00:00.000")])
    seed_year(refresher, 2025, [crime_record(5, date="2025-06-01T00:00:00.000")])
    corrected = crime_record(
        9, date="2025-01-01T00:30:00.000", updated_on="2025-02-01T15:00:00.000"
    )
    mock_api(httpx_mock, [corrected], counts={2024: 1, 2025: 2})

    result = refresher.run()

    assert result.rows_moved_partition == 1
    assert bronze(refresher, 2024)["id"].tolist() == ["1"]
    assert bronze(refresher, 2025)["id"].tolist() == ["5", "9"]
    assert silver(refresher, 2024)["id"].tolist() == ["1"]
    assert silver(refresher, 2025)["id"].tolist() == ["5", "9"]
    for year in (2024, 2025):
        assert manifest_row(refresher, year)["checksum"] == sha256(refresher.bronze_partition(year))
    assert [p.drift for p in result.partitions] == [0]


def test_records_before_the_project_window_are_skipped(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    ancient = crime_record(
        7, date="2003-05-05T00:00:00.000", year=2003, updated_on="2024-04-01T15:00:00.000"
    )
    mock_api(httpx_mock, [ancient], counts={})

    result = refresher.run()

    assert result.rows_out_of_range == 1
    assert result.partitions == []
    assert not refresher.bronze_partition(2003).exists()


def test_changed_rows_without_coordinates_are_kept_and_counted(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    no_location = crime_record(2, updated_on="2024-04-01T15:00:00.000")
    del no_location["latitude"], no_location["longitude"]
    mock_api(httpx_mock, [no_location], counts={2024: 2})

    result = refresher.run()

    assert result.rows_missing_geography == 1
    enriched = silver(refresher, 2024).set_index("id")
    assert enriched.loc["2", "geography_status"] == "missing_coordinates"
    assert pd.isna(enriched.loc["2", "spatial_ward_current"])


# -- safety --------------------------------------------------------------------------


def test_dry_run_writes_only_its_log_row(httpx_mock: HTTPXMock, refresher: CrimeRefresher) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    before = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))
    mock_api(httpx_mock, [crime_record(2, updated_on="2024-04-01T15:00:00.000")], counts={2024: 2})

    result = refresher.run(dry_run=True)

    assert result.rows_inserted == 1
    after = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))
    assert after == before
    log = refresher.read_incremental_log()
    assert bool(log.iloc[0]["dry_run"]) is True
    # A dry run never advances the watermark the next real run starts from.
    assert refresher.watermark() == "2024-03-08T15:00:00.000"


def test_failed_run_is_logged_and_leaves_the_watermark_alone(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    before = sha256(refresher.bronze_partition(2024))
    mock_api(
        httpx_mock,
        [crime_record(2, updated_on="2024-04-01T15:00:00.000")],
        count_error=True,
    )

    with pytest.raises(ChicagoDataError):
        refresher.run()

    log = refresher.read_incremental_log()
    assert log.iloc[0]["status"] == STATUS_FAILED
    assert "ChicagoDataError" in log.iloc[0]["error"]
    assert sha256(refresher.bronze_partition(2024)) == before
    assert refresher.watermark() == "2024-03-08T15:00:00.000"


def test_explicit_since_overrides_the_stored_watermark(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    mock_api(httpx_mock, [], counts={})

    result = refresher.run(since="2020-01-01T00:00:00.000")

    assert result.previous_watermark == "2020-01-01T00:00:00.000"
    assert result.rows_fetched == 0
    # Nothing came back, so the watermark is carried forward unchanged.
    assert result.new_watermark == "2020-01-01T00:00:00.000"
    requested = [str(r.url) for r in httpx_mock.get_requests() if "resource/" in str(r.url)]
    assert any("updated_on+%3E%3D+%272020-01-01" in url for url in requested)


def test_silver_that_fell_out_of_step_with_bronze_is_healed(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    # As found on 2024 (2026-09-14): Bronze re-downloaded, Silver never re-enriched — a
    # Bronze record with no Silver row, and a Silver row whose record the source deleted.
    seed_year(refresher, 2024, [crime_record(1), crime_record(8)])
    stale = pd.read_parquet(refresher.silver_partition(2024))
    stale = stale[stale["id"] != "8"]
    orphan = stale[stale["id"] == "1"].assign(id="999")
    pd.concat([stale, orphan]).to_parquet(refresher.silver_partition(2024), index=False)
    mock_api(httpx_mock, [crime_record(2, updated_on="2024-04-01T15:00:00.000")], counts={2024: 3})

    result = refresher.run()

    assert (result.rows_silver_backfilled, result.rows_silver_orphans) == (1, 1)
    # Surviving rows keep their place; new and re-enriched rows are appended in id order.
    assert bronze(refresher, 2024)["id"].tolist() == ["1", "8", "2"]
    enriched = silver(refresher, 2024).set_index("id")
    assert enriched.index.tolist() == ["1", "2", "8"]
    assert enriched.loc["8", "spatial_ward_current"] == "20"
    assert refresher.read_incremental_log().iloc[0]["rows_silver_backfilled"] == 1
