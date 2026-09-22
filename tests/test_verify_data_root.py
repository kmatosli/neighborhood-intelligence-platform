"""`ops.verify_data_root`: the pre-activation proof for a staged release root."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from test_crime_refresh import assigner, crime_record, seed_year  # tests/ is on sys.path

from bw_observatory.config import Settings
from bw_observatory.geography.assign import quality_path
from bw_observatory.ingest.crime_refresh import CrimeRefresher
from bw_observatory.ops import verify_data_root as verify_cli


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


@pytest.fixture
def refresher(settings: Settings) -> CrimeRefresher:
    return CrimeRefresher(settings, page_size=50, assigner=assigner())


def test_sound_root_passes_and_every_drift_is_named(
    refresher: CrimeRefresher, settings: Settings
) -> None:
    seed_year(refresher, 2024, [crime_record(1), crime_record(2)])
    seed_year(refresher, 2025, [crime_record(3)])
    quality_path(refresher.silver_dir).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"year": [2024, 2025]}).to_parquet(quality_path(refresher.silver_dir))

    assert verify_cli.verify(settings.data_dir, first_year=2024) == []

    # A year missing from the middle would silently shorten /api/v1/years.
    assert verify_cli.verify(settings.data_dir, first_year=2023) == ["2023: Bronze file missing"]

    # Silver drifting from Bronze is the 2024 failure class the refresh repairs; a release
    # root must not ship it.
    silver = pd.read_parquet(refresher.silver_partition(2024))
    silver[silver["id"] != "2"].to_parquet(refresher.silver_partition(2024), index=False)
    problems = verify_cli.verify(settings.data_dir, first_year=2024)
    assert problems == ["2024: 1 Bronze id(s) with no Silver row"]


def test_cli_exit_codes_follow_the_verdict(
    refresher: CrimeRefresher, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_year(refresher, 2024, [crime_record(1)])
    monkeypatch.setattr(verify_cli, "FIRST_YEAR", 2024)
    monkeypatch.setattr("sys.argv", ["verify", "--data-dir", str(settings.data_dir)])
    assert verify_cli.main() == 1  # quality file missing

    quality_path(refresher.silver_dir).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"year": [2024]}).to_parquet(quality_path(refresher.silver_dir))
    assert verify_cli.main() == 0
