"""The validated Change response cache: Gold is proved on every request, and an entry is
reused only under the exact identity it was computed for."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from crime_release_fixtures import CONFIG_DIR, write_root
from fastapi.testclient import TestClient
from test_crime_change import _mix_rows, _monthly_rows

from bw_observatory.gold.crime_aggregates import (
    BUILD_FILENAME,
    COVERAGE_FILENAME,
    DAILY_COUNTS_FILENAME,
    build_crime_gold,
    gold_dir,
)
from bw_observatory.gold.revisions import PROOF_FILENAME, REVISIONS_DIR
from bw_observatory.ingest.freshness import Freshness
from bw_observatory.presentation import change
from bw_observatory.presentation.change import (
    CHANGE_CACHE,
    WINDOW_FULL_YEAR,
    WINDOW_TRAILING,
    WINDOW_YTD,
    ChangeResponseCache,
    build_change,
)
from bw_observatory.presentation.models import ChangeResponse
from bw_observatory.release import (
    STATUS_DEVELOPMENT,
    build_release_manifest,
    write_release_manifest,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    built = write_root(tmp_path / "release", [*_monthly_rows(), *_mix_rows()])
    build_crime_gold(built, CONFIG_DIR)
    return built


class Spy:
    """Counts calls to `check_gold` and to the expensive assembly, passing each through."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.checks = 0
        self.assemblies = 0
        real_check, real_assemble = change.check_gold, change.assemble_change

        def check(*args: Any, **kwargs: Any) -> Any:
            self.checks += 1
            return real_check(*args, **kwargs)

        def assemble(*args: Any, **kwargs: Any) -> ChangeResponse:
            self.assemblies += 1
            return real_assemble(*args, **kwargs)

        monkeypatch.setattr(change, "check_gold", check)
        monkeypatch.setattr(change, "assemble_change", assemble)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Spy]:
    CHANGE_CACHE.clear()
    yield Spy(monkeypatch)
    CHANGE_CACHE.clear()


def _ward(root: Path, year: int | None = 2026, window: str = WINDOW_YTD) -> ChangeResponse:
    return build_change(root, CONFIG_DIR, "ward20", year, window)


def test_an_identical_request_computes_once_and_proves_gold_every_time(
    root: Path, spy: Spy
) -> None:
    first = _ward(root)
    assert (spy.assemblies, spy.checks, CHANGE_CACHE.hits) == (1, 1, 0)
    second = _ward(root)
    assert (spy.assemblies, spy.checks, CHANGE_CACHE.hits) == (1, 2, 1)
    assert first.analysis_status == second.analysis_status == "ok"


def test_cached_and_uncached_responses_are_identical(root: Path, spy: Spy) -> None:
    computed = _ward(root)
    cached = _ward(root)
    CHANGE_CACHE.clear()
    recomputed = _ward(root)
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0  # the last one really recomputed
    assert computed.model_dump() == cached.model_dump() == recomputed.model_dump()


@pytest.mark.parametrize(
    ("geography", "year", "window"),
    [
        ("woodlawn", 2026, WINDOW_YTD),  # different geography
        ("ward20", 2025, WINDOW_YTD),  # different year
        ("ward20", None, WINDOW_YTD),  # the year as asked, not as resolved
        ("ward20", 2026, WINDOW_TRAILING),  # different window
        ("ward20", 2025, WINDOW_FULL_YEAR),
    ],
)
def test_a_different_request_does_not_reuse_the_entry(
    root: Path, spy: Spy, geography: str, year: int | None, window: str
) -> None:
    _ward(root)
    other = build_change(root, CONFIG_DIR, geography, year, window)
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0
    assert other.analysis_status in {"ok", "window_unavailable"}


def test_a_new_release_id_does_not_reuse_the_entry(root: Path, spy: Spy) -> None:
    assert _ward(root).identity.release_id == "dev-test"  # type: ignore[union-attr]
    write_release_manifest(
        root,
        build_release_manifest(root, CONFIG_DIR, "dev-second", STATUS_DEVELOPMENT, commit="test"),
    )
    # Gold still names the old release: stale, and never the cached success.
    stale = _ward(root)
    assert stale.analysis_status == "aggregates_stale" and stale.identity is None
    build_crime_gold(root, CONFIG_DIR)
    fresh = _ward(root)
    assert fresh.identity is not None and fresh.identity.release_id == "dev-second"
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0


def test_a_changed_gold_build_identity_does_not_reuse_the_entry(root: Path, spy: Spy) -> None:
    _ward(root)
    path = gold_dir(root) / BUILD_FILENAME
    build = json.loads(path.read_text("utf-8"))
    build["builder_commit"] = "a-different-builder"  # still PASS, same release: a new build
    path.write_text(json.dumps(build), "utf-8")
    assert _ward(root).analysis_status == "ok"
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0


def test_a_changed_findings_config_does_not_reuse_the_entry(
    root: Path, spy: Spy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The findings config sets the minimum counts that suppress a percentage. It is not part
    # of Gold's identity (check_gold still passes), so the cache key must carry it itself.
    altered = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, altered)
    _ward(root)
    findings = altered / "findings.yml"
    findings.write_text(findings.read_text("utf-8") + "\n# changed\n", "utf-8")
    monkeypatch.setenv("BW_CONFIG_DIR", str(altered))
    assert build_change(root, altered, "ward20", 2026, WINDOW_YTD).analysis_status == "ok"
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0


def test_a_changed_category_config_serves_stale_not_the_cached_success(
    root: Path, spy: Spy, tmp_path: Path
) -> None:
    _ward(root)
    altered = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, altered)
    path = altered / "crime_categories.yml"
    path.write_text(path.read_text("utf-8") + "\n# changed\n", "utf-8")
    response = build_change(root, altered, "ward20", 2026, WINDOW_YTD)
    assert response.analysis_status == "aggregates_stale" and response.decomposition is None
    assert spy.assemblies == 1 and CHANGE_CACHE.hits == 0


def test_a_different_release_root_does_not_reuse_the_entry(
    root: Path, spy: Spy, tmp_path: Path
) -> None:
    _ward(root)
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)  # identical contents, different root
    assert _ward(copy).analysis_status == "ok"
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0


def test_a_new_revision_comparison_does_not_reuse_the_entry(root: Path, spy: Spy) -> None:
    _ward(root)
    folder = gold_dir(root) / REVISIONS_DIR / "dev-older__dev-test"
    folder.mkdir(parents=True)
    (folder / PROOF_FILENAME).write_text(json.dumps({"status": "FAIL"}), "utf-8")
    assert _ward(root).analysis_status == "ok"
    assert spy.assemblies == 2 and CHANGE_CACHE.hits == 0


def test_stale_gold_never_returns_the_cached_success(root: Path, spy: Spy) -> None:
    assert _ward(root).analysis_status == "ok"
    log = root / "bronze" / "crime" / "reconciliation_log.parquet"
    pd.DataFrame([{"run_id": "late", "year": 2025}]).to_parquet(log, index=False)
    response = _ward(root)
    assert response.analysis_status == "aggregates_stale"
    assert response.identity is None and response.decomposition is None
    assert spy.checks == 2 and spy.assemblies == 1 and CHANGE_CACHE.hits == 0


def test_failed_gold_never_returns_the_cached_success(root: Path, spy: Spy) -> None:
    assert _ward(root).analysis_status == "ok"
    path = gold_dir(root) / BUILD_FILENAME
    build = json.loads(path.read_text("utf-8"))
    build["status"] = "FAIL"
    path.write_text(json.dumps(build), "utf-8")
    response = _ward(root)
    assert response.analysis_status == "aggregates_stale" and response.identity is None
    assert CHANGE_CACHE.hits == 0


@pytest.mark.parametrize("missing", [BUILD_FILENAME, DAILY_COUNTS_FILENAME, COVERAGE_FILENAME])
def test_missing_gold_never_returns_the_cached_success(
    root: Path, spy: Spy, missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bw_observatory.api.app import app

    monkeypatch.setenv("BW_DATA_DIR", str(root))
    client = TestClient(app, raise_server_exceptions=False)
    url = "/api/v1/trends/ward20/change"
    assert client.get(url, params={"year": 2026}).json()["analysis_status"] == "ok"
    (gold_dir(root) / missing).unlink()
    response = client.get(url, params={"year": 2026})
    assert response.status_code == 200  # an answer, not a 500
    payload = response.json()
    assert payload["analysis_status"] == "aggregates_unavailable"
    for key in ("identity", "window", "decomposition", "composition", "history", "sensitivity"):
        assert payload[key] is None
    assert payload["trend"] == [] and payload["revisions"] is None
    assert spy.checks == 2 and spy.assemblies == 1 and CHANGE_CACHE.hits == 0


def test_freshness_is_read_live_on_a_cache_hit(
    root: Path, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _ward(root)
    assert first.identity is not None
    monkeypatch.setattr(change, "crime_freshness", lambda _: Freshness(status="live-sentinel"))
    second = _ward(root)
    assert CHANGE_CACHE.hits == 1
    assert second.identity is not None and second.identity.freshness_status == "live-sentinel"
    # The cached entry itself is untouched.
    assert first.identity.freshness_status != "live-sentinel"
    assert second.model_dump(exclude={"identity"}) == first.model_dump(exclude={"identity"})


def test_the_cache_is_bounded_and_evicts_the_least_recently_used() -> None:
    cache = ChangeResponseCache(2)
    a, b, c = (ChangeResponse(analysis_status=s) for s in ("a", "b", "c"))
    cache.put(("a",), a)
    cache.put(("b",), b)
    assert cache.get(("a",)) is a  # a is now the most recently used
    cache.put(("c",), c)
    assert len(cache) == 2
    assert cache.get(("b",)) is None and cache.get(("a",)) is a and cache.get(("c",)) is c


def test_the_endpoint_serves_a_repeat_from_the_cache(
    root: Path, spy: Spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bw_observatory.api.app import app

    monkeypatch.setenv("BW_DATA_DIR", str(root))
    client = TestClient(app)
    first = client.get("/api/v1/trends/ward20/change", params={"year": 2026})
    second = client.get("/api/v1/trends/ward20/change", params={"year": 2026})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (spy.checks, spy.assemblies, CHANGE_CACHE.hits) == (2, 1, 1)
