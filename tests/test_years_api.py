"""The /years endpoint must offer only years the API can actually answer.

A Silver year whose Bronze file has been truncated (e.g. the protected 1-row 2024 file) must
NOT be offered, because the resident pages join Silver to Bronze for incident attributes and
would otherwise 404 or render blank rows.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bw_observatory.api.routes import years as years_route
from bw_observatory.api.routes.years import year_is_answerable


def _write_year(root: Path, year: int, bronze_rows: int, silver_rows: int) -> None:
    bronze = root / "bronze" / "crime"
    silver = root / "silver" / "crime" / "crime_with_geography"
    bronze.mkdir(parents=True, exist_ok=True)
    silver.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": [str(i) for i in range(bronze_rows)]}).to_parquet(
        bronze / f"{year}.parquet", index=False
    )
    pd.DataFrame({"id": [str(i) for i in range(silver_rows)]}).to_parquet(
        silver / f"{year}.parquet", index=False
    )


def test_healthy_year_is_answerable(tmp_path: Path) -> None:
    _write_year(tmp_path, 2023, bronze_rows=100, silver_rows=100)
    silver = tmp_path / "silver" / "crime" / "crime_with_geography" / "2023.parquet"
    bronze = tmp_path / "bronze" / "crime" / "2023.parquet"
    assert year_is_answerable(silver, bronze) is True


def test_truncated_bronze_is_not_answerable(tmp_path: Path) -> None:
    # The 2024 pathology: Silver holds the full year, Bronze was reduced to a stub.
    _write_year(tmp_path, 2024, bronze_rows=1, silver_rows=259_191)
    silver = tmp_path / "silver" / "crime" / "crime_with_geography" / "2024.parquet"
    bronze = tmp_path / "bronze" / "crime" / "2024.parquet"
    assert year_is_answerable(silver, bronze) is False


def test_missing_bronze_is_not_answerable(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "crime" / "crime_with_geography" / "2019.parquet"
    silver.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": ["1"]}).to_parquet(silver, index=False)
    bronze = tmp_path / "bronze" / "crime" / "2019.parquet"
    assert year_is_answerable(silver, bronze) is False


def test_endpoint_excludes_the_truncated_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_year(tmp_path, 2023, bronze_rows=100, silver_rows=100)
    _write_year(tmp_path, 2024, bronze_rows=1, silver_rows=100)  # truncated Bronze
    _write_year(tmp_path, 2025, bronze_rows=100, silver_rows=100)

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(years_route.router)
    client = TestClient(app)

    payload = client.get("/api/v1/years").json()
    assert payload["years"] == [2023, 2025]  # 2024 is withheld
    assert payload["latest"] == 2025


def test_self_healing_when_bronze_is_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Restoring the Bronze file brings the year back with no code change.
    _write_year(tmp_path, 2024, bronze_rows=1, silver_rows=100)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(years_route.router)
    client = TestClient(app)
    assert client.get("/api/v1/years").json()["years"] == []

    _write_year(tmp_path, 2024, bronze_rows=100, silver_rows=100)  # restored
    assert client.get("/api/v1/years").json()["years"] == [2024]
