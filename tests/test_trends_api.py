"""GET /api/v1/trends/{geography_id}/change: identity, refusals and stale-Gold behaviour."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from crime_release_fixtures import CONFIG_DIR, write_root
from fastapi.testclient import TestClient
from test_crime_change import _mix_rows, _monthly_rows

from bw_observatory.gold.crime_aggregates import build_crime_gold
from bw_observatory.presentation.change import WINDOW_YTD, build_change


@pytest.fixture
def root(tmp_path: Path) -> Path:
    built = write_root(tmp_path / "release", [*_monthly_rows(), *_mix_rows()])
    build_crime_gold(built, CONFIG_DIR)
    return built


@pytest.fixture
def client(root: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from bw_observatory.api.app import app

    monkeypatch.setenv("BW_DATA_DIR", str(root))
    return TestClient(app)


def test_change_endpoint_serves_ward_and_a_portion(client: TestClient) -> None:
    for geo in ("ward20", "englewood"):
        response = client.get(f"/api/v1/trends/{geo}/change", params={"year": 2026})
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis_status"] == "ok"
        assert payload["identity"]["geography_id"] == geo
        assert payload["decomposition"]["reconciles"] is True


def test_unsupported_geographies_are_refused_not_zero(client: TestClient) -> None:
    assert client.get("/api/v1/trends/bronzeville/change").status_code == 404
    assert client.get("/api/v1/trends/back-of-the-yards/change").status_code == 404
    assert client.get("/api/v1/trends/ward20/change", params={"window": "5y"}).status_code == 422


def test_stale_gold_serves_no_figures(client: TestClient, root: Path) -> None:
    log = root / "bronze" / "crime" / "reconciliation_log.parquet"
    pd.DataFrame([{"run_id": "late", "year": 2025}]).to_parquet(log, index=False)
    payload = client.get("/api/v1/trends/ward20/change").json()
    assert payload["analysis_status"] == "aggregates_stale"
    for key in ("identity", "window", "decomposition", "composition", "history", "sensitivity"):
        assert payload[key] is None
    assert payload["trend"] == []


def test_a_config_change_makes_gold_stale(root: Path, tmp_path: Path) -> None:
    import shutil

    altered = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, altered)
    path = altered / "crime_categories.yml"
    path.write_text(path.read_text("utf-8") + "\n# changed\n", "utf-8")
    response = build_change(root, altered, "ward20", 2026, WINDOW_YTD)
    assert response.analysis_status == "aggregates_stale" and response.decomposition is None
