"""V2-004A: invariants, concurrency, source reconciliation, freshness, scheduling."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest
from pytest_httpx import HTTPXMock
from test_crime_refresh import (  # pytest puts tests/ on sys.path
    assigner,
    crime_record,
    metadata,
    mock_api,
    seed_year,
    sha256,
    silver,
)

from bw_observatory.clients.chicago_data import ChicagoDataClient, ChicagoDataError
from bw_observatory.config import Settings
from bw_observatory.geography.assign import SOURCE_COLUMNS, quality_path
from bw_observatory.geography.models import SourceStatus
from bw_observatory.ingest import crime_refresh as refresh_module
from bw_observatory.ingest.base import STATUS_COMPLETE, STATUS_FAILED
from bw_observatory.ingest.crime_reconcile import CrimeReconciler
from bw_observatory.ingest.crime_refresh import CrimeRefresher
from bw_observatory.ingest.freshness import (
    STATUS_CURRENT,
    STATUS_NEVER_REFRESHED,
    STATUS_REFRESH_FAILED,
    STATUS_STALE,
    crime_freshness,
)
from bw_observatory.ingest.partitions import (
    bronze_schema,
    duplicate_ids_across_partitions,
    frame_to_table,
    partition_ids,
    partition_problems,
    sorted_by_id,
    stream_rewrite,
)
from bw_observatory.ingest.refresh_lock import AlreadyRunning, RefreshLock
from bw_observatory.ops import refresh_crime as refresh_cli
from bw_observatory.ops import scheduler as scheduler_module
from bw_observatory.ops.scheduler import RefreshScheduler, next_occurrence, parse_schedule
from bw_observatory.presentation.geography import load_geography_registry
from bw_observatory.presentation.overview import load_geography_rows


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


@pytest.fixture
def refresher(settings: Settings) -> CrimeRefresher:
    return CrimeRefresher(settings, page_size=50, assigner=assigner())


@pytest.fixture
def reconciler(settings: Settings) -> CrimeReconciler:
    return CrimeReconciler(settings)


def mock_ids(
    httpx_mock: HTTPXMock, ids_by_year: dict[int, list[str]], *, fail: bool = False
) -> None:
    """Answer `$select=id` requests from `ids_by_year`; anything else is a metadata reply."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("$select") == "id":
            if fail:
                return httpx.Response(503, json={"error": "down"})
            year = int(params["$where"].split("'")[1][:4])
            if "$offset" in params:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"id": i} for i in ids_by_year.get(year, [])])
        return httpx.Response(200, json=metadata())

    httpx_mock.add_callback(handler, is_reusable=True)


def sound(refresher: CrimeRefresher, year: int) -> None:
    assert partition_problems(refresher.bronze_dir, refresher.silver_dir, year) == []


# -- 1. invariants -----------------------------------------------------------------------


def test_streamed_rewrite_keeps_bronze_readable_as_string_frame(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    existing = pd.DataFrame([crime_record(1), crime_record(2)]).astype("string")
    schema = bronze_schema(list(existing.columns))
    stream_rewrite(None, first, schema=schema, drop=set(), append=frame_to_table(existing, schema))

    incoming = pd.DataFrame([crime_record(2, arrest=True, new_column="x")]).astype("string")
    wider = bronze_schema([*existing.columns, "new_column"])
    second = tmp_path / "second.parquet"
    written = stream_rewrite(
        first,
        second,
        schema=wider,
        drop={"2"},
        append=sorted_by_id(frame_to_table(incoming, wider)),
    )

    assert written == ["1", "2"]
    frame = pd.read_parquet(second)
    assert frame["id"].tolist() == ["1", "2"]
    assert str(frame["arrest"].dtype) == "string"
    assert frame.loc[1, "arrest"] == "True"
    assert pd.isna(frame.loc[0, "new_column"]) and frame.loc[1, "new_column"] == "x"
    assert pq.ParquetFile(second).metadata.num_row_groups >= 1


def test_partition_problems_names_every_kind_of_drift(
    refresher: CrimeRefresher,
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    sound(refresher, 2024)

    stale = pd.read_parquet(refresher.silver_partition(2024))
    broken = pd.concat([stale[stale["id"] != "2"], stale[stale["id"] == "1"].assign(id="9")])
    broken = pd.concat([broken, broken[broken["id"] == "1"]])
    broken.to_parquet(refresher.silver_partition(2024), index=False)
    bronze_frame = pd.read_parquet(refresher.bronze_partition(2024))
    pd.concat([bronze_frame, bronze_frame.iloc[[0]]]).to_parquet(
        refresher.bronze_partition(2024), index=False
    )

    problems = partition_problems(refresher.bronze_dir, refresher.silver_dir, 2024)
    joined = " | ".join(problems)
    assert "duplicate Bronze id" in joined
    assert "duplicate Silver id" in joined
    assert "Bronze id(s) with no Silver row" in joined
    assert "orphan Silver row" in joined
    assert "checksum does not match" in joined
    assert "manifest says" in joined


def test_refresh_leaves_every_touched_year_sound(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(9, date="2024-12-31T23:00:00.000")])
    seed_year(refresher, 2025, [crime_record(5, date="2025-06-01T00:00:00.000")])
    # 2025 as a pre-V2-004A partition: no provenance columns yet.
    legacy = pd.read_parquet(refresher.silver_partition(2025)).drop(columns=SOURCE_COLUMNS)
    legacy.to_parquet(refresher.silver_partition(2025), index=False)
    changed = [
        crime_record(2, updated_on="2025-02-01T15:00:00.000"),
        crime_record(9, date="2025-01-01T00:30:00.000", updated_on="2025-02-01T15:00:00.000"),
    ]
    mock_api(httpx_mock, changed, counts={2024: 2, 2025: 2})

    result = refresher.run()

    assert result.status == STATUS_COMPLETE
    for year in (2024, 2025):
        sound(refresher, year)
    assert duplicate_ids_across_partitions(refresher.bronze_dir, [2024, 2025]) == {}
    enriched = silver(refresher, 2025).set_index("id")
    assert set(SOURCE_COLUMNS) <= set(enriched.columns)
    assert enriched.loc["9", "source_status"] == SourceStatus.ACTIVE
    assert enriched.loc["9", "source_last_seen"] == result.start_time.isoformat()
    # A legacy row untouched by the refresh gets the download as its last-seen evidence.
    assert enriched.loc["5", "source_status"] == SourceStatus.ACTIVE
    assert enriched.loc["5", "source_last_seen"] == "2026-07-11T23:01:00+00:00"


def test_refresh_refuses_to_publish_an_unsound_partition(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    mock_api(httpx_mock, [crime_record(2, updated_on="2024-04-01T15:00:00.000")], counts={2024: 2})
    monkeypatch.setattr(refresh_module, "partition_problems", lambda *a: ["2024: forced"])

    with pytest.raises(RuntimeError, match="invariants violated"):
        refresher.run()

    log = refresher.read_incremental_log()
    assert log.iloc[0]["status"] == STATUS_FAILED
    assert (log["status"] == STATUS_COMPLETE).sum() == 0  # no watermark was recorded


# -- 2. interrupted publish ---------------------------------------------------------------


def test_failure_while_staging_touches_no_live_file(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    before = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))
    manifest_before = sha256(refresher.writer.manifest_path)
    mock_api(httpx_mock, [crime_record(2, updated_on="2024-04-01T15:00:00.000")], counts={2024: 2})

    real_stream = refresh_module.stream_rewrite
    calls: list[Path] = []

    def flaky_stream(source: Path | None, target: Path, **kwargs: Any) -> list[str]:
        calls.append(target)
        if len(calls) == 2:
            raise OSError("disk full while staging Silver")
        return real_stream(source, target, **kwargs)

    monkeypatch.setattr(refresh_module, "stream_rewrite", flaky_stream)

    with pytest.raises(OSError):
        refresher.run()

    after = sha256(refresher.bronze_partition(2024)), sha256(refresher.silver_partition(2024))
    assert after == before
    assert sha256(refresher.writer.manifest_path) == manifest_before
    assert list(refresher.bronze_dir.glob("*.tmp")) == []
    assert not RefreshLock(refresher.bronze_dir).path.exists()
    sound(refresher, 2024)


# -- 3. concurrency -----------------------------------------------------------------------


def test_second_writer_is_refused_while_the_first_holds_the_lock(tmp_path: Path) -> None:
    first = RefreshLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(AlreadyRunning) as excinfo:
            RefreshLock(tmp_path).acquire()
        assert excinfo.value.owner["pid"] == os.getpid()
    finally:
        first.release()
    assert not first.path.exists()
    RefreshLock(tmp_path).acquire()  # free again


def test_stale_lock_from_a_dead_process_is_taken_over(tmp_path: Path) -> None:
    lock = RefreshLock(tmp_path)
    lock.path.write_text(
        json.dumps(
            {
                "pid": 2**22 + 12345,  # not a live pid on any sane machine
                "host": __import__("socket").gethostname(),
                "started": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    lock.acquire()
    assert json.loads(lock.path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    lock.release()


def test_lock_older_than_the_stale_window_is_taken_over(tmp_path: Path) -> None:
    lock = RefreshLock(tmp_path, stale_after=timedelta(hours=1))
    lock.path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": "some-other-host",
                "started": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    lock.acquire()
    lock.release()


def test_refresh_and_reconcile_share_the_lock(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    held = RefreshLock(refresher.bronze_dir)
    held.acquire()
    try:
        with pytest.raises(AlreadyRunning):
            refresher.run()
        with pytest.raises(AlreadyRunning):
            reconciler.run([2024])
    finally:
        held.release()
    assert not refresher.incremental_log_path.exists()


def test_cli_exits_3_when_a_run_is_already_active(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BW_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("BW_LOG_DIR", str(settings.log_dir))
    held = RefreshLock(settings.data_dir / "bronze" / "crime")
    held.acquire()
    try:
        monkeypatch.setattr(sys, "argv", ["refresh_crime", "--dry-run"])
        assert refresh_cli.main() == 3
    finally:
        held.release()
    assert "already running" in capsys.readouterr().out


# -- 4. reconciliation ---------------------------------------------------------------------


def test_reconciliation_marks_source_removed_ids_and_keeps_them(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2), crime_record(3)])
    mock_ids(httpx_mock, {2024: ["1", "3"]})

    result = reconciler.run([2024])

    outcome = result.years[0]
    assert (outcome.local_rows, outcome.source_rows) == (3, 2)
    assert (outcome.confirmed_active, outcome.newly_removed, outcome.missing_locally) == (
        2,
        1,
        0,
    )
    enriched = silver(refresher, 2024).set_index("id")
    assert enriched.loc["2", "source_status"] == SourceStatus.REMOVED
    assert enriched.loc["2", "source_removed_at"] is not pd.NA
    assert enriched.loc["1", "source_status"] == SourceStatus.ACTIVE
    assert pd.isna(enriched.loc["1", "source_removed_at"])
    # Preserved: Bronze untouched, Silver row still present, partition still sound.
    assert partition_ids(refresher.bronze_partition(2024)) == {"1", "2", "3"}
    sound(refresher, 2024)
    log = reconciler.read_log()
    assert log.iloc[0]["newly_removed"] == 1 and log.iloc[0]["status"] == STATUS_COMPLETE


def test_current_view_excludes_source_removed_rows(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    ward20 = load_geography_registry().get("ward20")
    assert load_geography_rows(refresher.settings.data_dir, 2024, ward20)["id"].tolist() == [
        "1",
        "2",
    ]

    mock_ids(httpx_mock, {2024: ["1"]})
    reconciler.run([2024])

    rows = load_geography_rows(refresher.settings.data_dir, 2024, ward20)
    assert rows["id"].tolist() == ["1"]


def test_first_removal_time_is_kept_and_reappearance_restores_the_row(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    mock_ids(httpx_mock, {2024: ["1"]})
    reconciler.run([2024])
    first = silver(refresher, 2024).set_index("id").loc["2", "source_removed_at"]

    second = reconciler.run([2024])
    assert second.years[0].still_removed == 1 and second.years[0].newly_removed == 0
    assert silver(refresher, 2024).set_index("id").loc["2", "source_removed_at"] == first

    httpx_mock.reset()
    mock_ids(httpx_mock, {2024: ["1", "2"]})
    third = reconciler.run([2024])
    assert third.years[0].reappeared == 1
    enriched = silver(refresher, 2024).set_index("id")
    assert enriched.loc["2", "source_status"] == SourceStatus.ACTIVE
    assert pd.isna(enriched.loc["2", "source_removed_at"])


def test_reconciliation_reports_ids_missing_locally_without_inventing_them(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    mock_ids(httpx_mock, {2024: ["1", "77"]})

    result = reconciler.run([2024])

    assert result.years[0].missing_locally == 1
    assert result.years[0].missing_ids_sample == ["77"]
    assert partition_ids(refresher.bronze_partition(2024)) == {"1"}


def test_reconciliation_dry_run_marks_nothing(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    before = sha256(refresher.silver_partition(2024))
    mock_ids(httpx_mock, {2024: ["1"]})

    result = reconciler.run([2024], dry_run=True)

    assert result.years[0].newly_removed == 1
    assert sha256(refresher.silver_partition(2024)) == before
    assert bool(reconciler.read_log().iloc[0]["dry_run"]) is True


def test_failed_reconciliation_is_logged_and_changes_nothing(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    before = sha256(refresher.silver_partition(2024))
    mock_ids(httpx_mock, {}, fail=True)

    with pytest.raises(ChicagoDataError):
        reconciler.run([2024])

    assert sha256(refresher.silver_partition(2024)) == before
    log = reconciler.read_log()
    assert log.iloc[0]["status"] == STATUS_FAILED and "ChicagoDataError" in log.iloc[0]["error"]
    assert not RefreshLock(refresher.bronze_dir).path.exists()


def test_default_reconciliation_years_follow_the_refresh_drift(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    for year in (2022, 2023, 2024, 2025):
        seed_year(refresher, year, [crime_record(year, date=f"{year}-03-01T12:00:00.000")])
    assert reconciler.default_years() == [2024, 2025]

    # A refresh that touches 2022 and finds the source one row short flags it.
    changed = [
        crime_record(3, date="2022-05-01T00:00:00.000", updated_on="2024-04-01T15:00:00.000")
    ]
    mock_api(httpx_mock, changed, counts={2022: 1})
    refresher.run()
    assert reconciler.default_years() == [2022, 2024, 2025]


def test_list_crime_ids_pages_by_offset(httpx_mock: HTTPXMock, settings: Settings) -> None:
    httpx_mock.add_response(json=[{"id": "1"}, {"id": "2"}])
    ids = ChicagoDataClient(settings).list_crime_ids(where="x", limit=2, offset=4)
    assert ids == ["1", "2"]
    request = httpx_mock.get_requests()[0]
    assert request.url.params["$select"] == "id" and request.url.params["$offset"] == "4"


# -- 5. freshness -------------------------------------------------------------------------


def log_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_id": "r",
        "dataset_id": "ijzp-q8t2",
        "start_time": "2026-09-14T16:30:00+00:00",
        "end_time": "2026-09-14T16:45:00+00:00",
        "previous_watermark": "a",
        "new_watermark": "2026-09-13T15:54:07.000",
        "rows_fetched": 10,
        "rows_inserted": 5,
        "rows_updated": 3,
        "rows_unchanged": 2,
        "rows_out_of_range": 0,
        "rows_moved_partition": 0,
        "rows_missing_geography": 1,
        "rows_silver_backfilled": 0,
        "rows_silver_orphans": 0,
        "partitions_touched": "2026",
        "final_bronze_rows": 100,
        "reconciliation": json.dumps({"2026": {"local": 10, "source": 8, "drift": -2}}),
        "duration_seconds": 900.0,
        "dry_run": False,
        "status": STATUS_COMPLETE,
        "error": "",
    }
    row.update(overrides)
    return row


def write_log(refresher: CrimeRefresher, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_parquet(refresher.incremental_log_path, index=False)


def test_freshness_is_current_after_a_recent_success(refresher: CrimeRefresher) -> None:
    seed_year(refresher, 2026, [crime_record(1, date="2026-09-06T00:00:00.000")])
    write_log(refresher, [log_row()])
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)

    fresh = crime_freshness(refresher.settings.data_dir, now)

    assert fresh.status == STATUS_CURRENT and fresh.reasons == []
    assert fresh.data_through == "2026-09-06" and fresh.days_behind == 9
    assert fresh.source_watermark == "2026-09-13T15:54:07.000"
    assert fresh.reconciliation_drift == {"2026": -2}
    assert fresh.rows_inserted == 5 and fresh.duration_seconds == 900.0


def test_freshness_is_stale_when_no_refresh_has_succeeded_for_two_days(
    refresher: CrimeRefresher,
) -> None:
    seed_year(refresher, 2026, [crime_record(1, date="2026-09-06T00:00:00.000")])
    write_log(refresher, [log_row()])
    fresh = crime_freshness(refresher.settings.data_dir, datetime(2026, 9, 17, 12, tzinfo=UTC))
    assert fresh.status == STATUS_STALE
    assert any("no successful refresh" in reason for reason in fresh.reasons)


def test_freshness_tolerates_the_source_lag_but_not_more(refresher: CrimeRefresher) -> None:
    seed_year(refresher, 2026, [crime_record(1, date="2026-09-01T00:00:00.000")])
    write_log(refresher, [log_row(end_time="2026-09-15T16:45:00+00:00")])
    # 11 days behind: within lag + grace.
    ok = crime_freshness(refresher.settings.data_dir, datetime(2026, 9, 12, 12, tzinfo=UTC))
    assert ok.status == STATUS_CURRENT
    # 12 days behind with a fresh run: the pipeline, not the source, is behind.
    late = crime_freshness(refresher.settings.data_dir, datetime(2026, 9, 13, 12, tzinfo=UTC))
    assert late.status == STATUS_STALE
    assert any("newest incident date" in reason for reason in late.reasons)


def test_freshness_reports_a_failure_newer_than_the_last_success(
    refresher: CrimeRefresher,
) -> None:
    seed_year(refresher, 2026, [crime_record(1, date="2026-09-06T00:00:00.000")])
    write_log(
        refresher,
        [
            log_row(),
            log_row(
                start_time="2026-09-15T16:30:00+00:00",
                end_time="2026-09-15T16:31:00+00:00",
                status=STATUS_FAILED,
                error="ChicagoDataError: 503",
            ),
        ],
    )
    fresh = crime_freshness(refresher.settings.data_dir, datetime(2026, 9, 15, 17, tzinfo=UTC))
    assert fresh.status == STATUS_REFRESH_FAILED
    assert fresh.last_run_error == "ChicagoDataError: 503"
    assert fresh.last_successful_refresh == "2026-09-14T16:45:00+00:00"


def test_freshness_before_any_refresh_falls_back_to_the_download(
    refresher: CrimeRefresher,
) -> None:
    seed_year(refresher, 2026, [crime_record(1, date="2026-07-03T00:00:00.000")])
    fresh = crime_freshness(refresher.settings.data_dir, datetime(2026, 7, 12, tzinfo=UTC))
    assert fresh.status == STATUS_CURRENT
    assert fresh.last_successful_refresh == "2026-07-11T23:01:00+00:00"
    assert crime_freshness(tmp_data := refresher.settings.data_dir / "nothing").status == (
        STATUS_NEVER_REFRESHED
    )
    assert not tmp_data.exists()


def test_freshness_sees_a_running_refresh(refresher: CrimeRefresher) -> None:
    seed_year(refresher, 2026, [crime_record(1)])
    lock = RefreshLock(refresher.bronze_dir)
    lock.acquire()
    try:
        assert crime_freshness(refresher.settings.data_dir).refresh_running is True
    finally:
        lock.release()
    assert crime_freshness(refresher.settings.data_dir).refresh_running is False


def test_freshness_endpoint_is_read_only_and_reports_status(
    refresher: CrimeRefresher, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from bw_observatory.api.app import app

    seed_year(refresher, 2026, [crime_record(1, date="2026-09-06T00:00:00.000")])
    write_log(refresher, [log_row()])
    monkeypatch.setenv("BW_DATA_DIR", str(refresher.settings.data_dir))
    response = TestClient(app).get("/api/v1/freshness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {STATUS_CURRENT, STATUS_STALE}
    assert payload["data_through"] == "2026-09-06"
    assert TestClient(app).post("/api/v1/freshness").status_code == 405


# -- 6. scheduler -------------------------------------------------------------------------


def test_schedule_parsing_and_next_occurrence() -> None:
    assert parse_schedule(None) is None
    assert parse_schedule("nonsense") is None
    at = parse_schedule("16:30")
    assert at is not None
    before = datetime(2026, 9, 14, 10, tzinfo=UTC)
    after = datetime(2026, 9, 14, 17, tzinfo=UTC)
    assert next_occurrence(at, before) == datetime(2026, 9, 14, 16, 30, tzinfo=UTC)
    assert next_occurrence(at, after) == datetime(2026, 9, 15, 16, 30, tzinfo=UTC)


def test_scheduler_is_off_unless_configured(settings: Settings) -> None:
    scheduler = RefreshScheduler(settings)
    assert scheduler.enabled is False
    scheduler.start()
    assert scheduler._thread is None


def test_scheduler_runs_the_refresh_cli_and_reconciles_on_its_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        refresh_schedule="16:30",
        reconcile_day_of_month=1,
    )
    launched: list[str] = []

    def fake_run(module: str, *, cwd: Path, timeout_seconds: int) -> scheduler_module.RunOutcome:
        launched.append(module)
        moment = datetime.now(UTC)
        return scheduler_module.RunOutcome(module, moment, moment, 0)

    monkeypatch.setattr(scheduler_module, "run_module", fake_run)
    scheduler = RefreshScheduler(settings)
    assert scheduler.enabled

    scheduler.run_once(when=datetime(2026, 9, 14, tzinfo=UTC))
    assert launched == [scheduler_module.REFRESH_MODULE]
    scheduler.run_once(when=datetime(2026, 10, 1, tzinfo=UTC))
    assert launched[1:] == [scheduler_module.REFRESH_MODULE, scheduler_module.RECONCILE_MODULE]


def test_scheduler_subprocess_uses_this_interpreter_and_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    class Completed:
        returncode = 0

    def fake_subprocess(cmd: list[str], **kwargs: Any) -> Completed:
        calls.append({"cmd": cmd, **kwargs})
        return Completed()

    monkeypatch.setattr(scheduler_module.subprocess, "run", fake_subprocess)
    outcome = scheduler_module.run_module(
        "bw_observatory.ops.refresh_crime", cwd=tmp_path, timeout_seconds=7
    )
    assert outcome.ok
    assert calls[0]["cmd"] == [sys.executable, "-m", "bw_observatory.ops.refresh_crime"]
    assert calls[0]["timeout"] == 7


def test_quality_report_still_written_after_reconciliation(
    httpx_mock: HTTPXMock, refresher: CrimeRefresher, reconciler: CrimeReconciler
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    mock_api(httpx_mock, [crime_record(2, updated_on="2024-04-01T15:00:00.000")], counts={2024: 2})
    refresher.run()
    quality = pd.read_parquet(quality_path(refresher.silver_dir))
    assert quality.loc[quality["year"] == 2024, "total_records"].item() == 2


def test_repack_rewrites_in_small_row_groups_without_changing_content(
    refresher: CrimeRefresher, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bw_observatory.ingest import partitions
    from bw_observatory.ops.repack_crime import repack_year

    monkeypatch.setattr(partitions, "BATCH_ROWS", 2)
    records = [crime_record(i) for i in range(1, 8)]
    seed_year(refresher, 2024, records)
    before_bronze = pd.read_parquet(refresher.bronze_partition(2024))
    before_silver = pd.read_parquet(refresher.silver_partition(2024))

    problems = repack_year(refresher.settings, 2024)

    assert problems == []
    assert pq.ParquetFile(refresher.bronze_partition(2024)).metadata.num_row_groups == 4
    pd.testing.assert_frame_equal(pd.read_parquet(refresher.bronze_partition(2024)), before_bronze)
    pd.testing.assert_frame_equal(pd.read_parquet(refresher.silver_partition(2024)), before_silver)
    sound(refresher, 2024)
