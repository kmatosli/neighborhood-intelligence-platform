"""Is the crime data current? Answered from the refresh bookkeeping, not by opening data.

Three states the product owner needs to tell apart without reading Parquet files:

* **current** — the last refresh succeeded recently and the newest incident date is as
  recent as the source allows;
* **stale** — no successful refresh within `STALE_AFTER_HOURS`, or the newest incident
  date has fallen further behind than the source's publication lag explains;
* **refresh_failed** — the most recent real run failed and nothing has succeeded since
  (the API keeps serving the last known-good data, so this is a warning, not an outage).

The staleness threshold is deliberately not "today": the City withholds roughly the most
recent seven days (`SOURCE_LAG_DAYS`), and a daily batch can land a day late, so data
through eleven days ago is normal and data through twelve is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from bw_observatory.ingest.base import STATUS_COMPLETE, STATUS_FAILED
from bw_observatory.ingest.crime_refresh import INCREMENTAL_LOG_FILENAME
from bw_observatory.ingest.partitions import column_max
from bw_observatory.ingest.refresh_lock import RefreshLock

STATUS_CURRENT = "current"
STATUS_STALE = "stale"
STATUS_REFRESH_FAILED = "refresh_failed"
STATUS_NEVER_REFRESHED = "never_refreshed"

# One daily run may be missed (a deploy at the wrong moment) before the data counts as stale.
STALE_AFTER_HOURS = 48
# "2001 to present, minus the most recent seven days" — the source's own description.
SOURCE_LAG_DAYS = 7
# Batches occasionally land a day or so late; beyond this the pipeline is the problem.
DATA_THROUGH_GRACE_DAYS = 4

RECONCILIATION_LOG_FILENAME = "reconciliation_log.parquet"


@dataclass
class Freshness:
    status: str
    reasons: list[str] = field(default_factory=list)
    refresh_running: bool = False
    last_successful_refresh: str | None = None
    hours_since_success: float | None = None
    last_run_status: str | None = None
    last_run_started: str | None = None
    last_run_error: str | None = None
    source_watermark: str | None = None
    data_through: str | None = None
    days_behind: int | None = None
    stale_after_hours: int = STALE_AFTER_HOURS
    source_lag_days: int = SOURCE_LAG_DAYS
    rows_fetched: int | None = None
    rows_inserted: int | None = None
    rows_updated: int | None = None
    rows_unchanged: int | None = None
    rows_missing_geography: int | None = None
    duration_seconds: float | None = None
    reconciliation_drift: dict[str, int] = field(default_factory=dict)
    last_reconciliation: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _parse(moment: str | None) -> datetime | None:
    if not moment:
        return None
    try:
        parsed = datetime.fromisoformat(str(moment))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _newest_year(bronze_dir: Path) -> int | None:
    years = [int(p.stem) for p in bronze_dir.glob("*.parquet") if p.stem.isdigit()]
    return max(years) if years else None


def crime_freshness(data_dir: Path, now: datetime | None = None) -> Freshness:
    moment = now or datetime.now(UTC)
    bronze_dir = data_dir / "bronze" / "crime"
    freshness = Freshness(status=STATUS_NEVER_REFRESHED)

    # -- data through: the newest incident date on disk (one column of one file) --------
    newest = _newest_year(bronze_dir)
    if newest is not None:
        through = column_max(bronze_dir / f"{newest}.parquet", "date")
        if through:
            freshness.data_through = through[:10]
            through_day = _parse(through[:10])
            if through_day is not None:
                freshness.days_behind = (moment - through_day).days

    # -- last refresh run -----------------------------------------------------------------
    log_path = bronze_dir / INCREMENTAL_LOG_FILENAME
    real_runs = pd.DataFrame()
    if log_path.exists():
        log = pd.read_parquet(log_path)
        if not log.empty:
            real_runs = log[~log["dry_run"].astype(bool)]
    if not real_runs.empty:
        last = real_runs.iloc[-1]
        freshness.last_run_status = str(last["status"])
        freshness.last_run_started = str(last["start_time"])
        freshness.last_run_error = str(last["error"]) or None
        done = real_runs[real_runs["status"] == STATUS_COMPLETE]
        if not done.empty:
            success = done.iloc[-1]
            freshness.last_successful_refresh = str(success["end_time"])
            freshness.source_watermark = str(success["new_watermark"])
            freshness.rows_fetched = int(success["rows_fetched"])
            freshness.rows_inserted = int(success["rows_inserted"])
            freshness.rows_updated = int(success["rows_updated"])
            freshness.rows_unchanged = int(success["rows_unchanged"])
            freshness.rows_missing_geography = int(success["rows_missing_geography"])
            if "duration_seconds" in success.index and pd.notna(success["duration_seconds"]):
                freshness.duration_seconds = float(success["duration_seconds"])
            try:
                figures = json.loads(str(success["reconciliation"]) or "{}")
                freshness.reconciliation_drift = {
                    year: int(v["drift"])
                    for year, v in figures.items()
                    if v.get("drift") is not None
                }
            except (ValueError, TypeError, KeyError):
                freshness.reconciliation_drift = {}
    else:
        # Before any refresh has run, the historical download is the last "refresh".
        manifest_path = bronze_dir / "manifest.parquet"
        if manifest_path.exists():
            manifest = pd.read_parquet(manifest_path)
            completed = manifest["download_completed"].dropna()
            if not completed.empty:
                freshness.last_successful_refresh = str(completed.max())

    # -- last reconciliation ----------------------------------------------------------------
    reconcile_path = bronze_dir / RECONCILIATION_LOG_FILENAME
    if reconcile_path.exists():
        rlog = pd.read_parquet(reconcile_path)
        rlog = rlog[~rlog["dry_run"].astype(bool)] if not rlog.empty else rlog
        if not rlog.empty:
            latest_run = rlog[rlog["run_id"] == rlog.iloc[-1]["run_id"]]
            freshness.last_reconciliation = {
                "end_time": str(latest_run["end_time"].max()),
                "years": [int(y) for y in latest_run["year"]],
                "status": STATUS_FAILED
                if (latest_run["status"] == STATUS_FAILED).any()
                else STATUS_COMPLETE,
                "newly_removed": int(latest_run["newly_removed"].sum()),
                "still_removed": int(latest_run["still_removed"].sum()),
                "reappeared": int(latest_run["reappeared"].sum()),
                "missing_locally": int(latest_run["missing_locally"].sum()),
            }

    # -- running now? ---------------------------------------------------------------------
    lock = RefreshLock(bronze_dir)
    owner = lock.owner()
    freshness.refresh_running = owner is not None and not lock.is_stale(owner, moment)

    # -- verdict ------------------------------------------------------------------------
    success_at = _parse(freshness.last_successful_refresh)
    if success_at is not None:
        freshness.hours_since_success = round((moment - success_at).total_seconds() / 3600, 1)

    last_started = _parse(freshness.last_run_started)
    failed_since_success = freshness.last_run_status == STATUS_FAILED and (
        success_at is None or (last_started is not None and last_started > success_at)
    )
    if failed_since_success:
        freshness.status = STATUS_REFRESH_FAILED
        freshness.reasons.append(
            f"the last refresh failed: {freshness.last_run_error or 'no error recorded'}"
        )
    elif success_at is None:
        freshness.status = STATUS_NEVER_REFRESHED
        freshness.reasons.append("no refresh has ever completed and no download is recorded")
    else:
        freshness.status = STATUS_CURRENT
        if moment - success_at > timedelta(hours=STALE_AFTER_HOURS):
            freshness.status = STATUS_STALE
            freshness.reasons.append(
                f"no successful refresh for {freshness.hours_since_success} h "
                f"(threshold {STALE_AFTER_HOURS} h)"
            )
        if (
            freshness.days_behind is not None
            and freshness.days_behind > SOURCE_LAG_DAYS + DATA_THROUGH_GRACE_DAYS
        ):
            freshness.status = STATUS_STALE
            freshness.reasons.append(
                f"newest incident date is {freshness.days_behind} days old; the source lag "
                f"explains at most {SOURCE_LAG_DAYS + DATA_THROUGH_GRACE_DAYS}"
            )
    return freshness
