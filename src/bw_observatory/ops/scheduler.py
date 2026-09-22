"""In-process daily scheduler for the crime refresh, hosted by the API service.

Why it lives inside the API process: on Render a persistent disk is reachable **only** by
the one service it is attached to, at runtime — not by a cron job, not by a one-off job, not
by a second service (render.com/docs/disks). The API owns the disk, so the API process is the
only place a scheduled refresh can run without duplicating the production dataset or paying
for infrastructure that could not reach it anyway.

Why a subprocess rather than a thread doing the work: the refresh is the tested CLI
(`python -m bw_observatory.ops.refresh_crime`) run exactly as a person would run it, so
there is one implementation; its memory is returned to the OS when it exits; and a crash or
hang inside it cannot take the API down (a timeout kills it, the lock is released, the API
keeps serving the last known-good data).

Off by default. `BW_REFRESH_SCHEDULE=16:30` (UTC, HH:MM) turns it on — the source posts one
batch a day around 15:45 UTC, so half past four picks it up the same day. On the first day
of each month (`BW_RECONCILE_DAY`) the reconciliation runs after the refresh. If the process
starts and the last successful refresh is more than a day old, one catch-up run happens
shortly after start, so a deploy at the wrong moment does not cost a day.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from bw_observatory.config import REPO_ROOT, Settings
from bw_observatory.ingest.freshness import crime_freshness
from bw_observatory.logging_config import download_logger

REFRESH_MODULE = "bw_observatory.ops.refresh_crime"
RECONCILE_MODULE = "bw_observatory.ops.reconcile_crime"
CATCH_UP_DELAY_SECONDS = 120
CATCH_UP_AFTER = timedelta(hours=24)


def parse_schedule(value: str | None) -> time | None:
    """'HH:MM' (UTC) → time, or None when scheduling is off or the value is malformed."""
    if not value:
        return None
    try:
        hour, minute = (int(part) for part in value.strip().split(":"))
        return time(hour=hour, minute=minute, tzinfo=UTC)
    except (TypeError, ValueError):
        download_logger().error(
            "BW_REFRESH_SCHEDULE=%r is not HH:MM; the scheduler stays off.", value
        )
        return None


def next_occurrence(at: time, after: datetime) -> datetime:
    candidate = datetime.combine(after.date(), at.replace(tzinfo=UTC))
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


@dataclass
class RunOutcome:
    module: str
    started: datetime
    finished: datetime
    returncode: int | None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_module(module: str, *, cwd: Path, timeout_seconds: int) -> RunOutcome:
    """Run one of the CLIs as a child process of this interpreter.

    Output goes to the child's own log files and to our stdout (which Render captures), so
    a failure is diagnosable from the service logs alone.
    """
    started = datetime.now(UTC)
    log = download_logger()
    log.info("Scheduler: starting %s", module)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", module],
            cwd=cwd,
            timeout=timeout_seconds,
            check=False,
        )
        outcome = RunOutcome(module, started, datetime.now(UTC), completed.returncode)
    except subprocess.TimeoutExpired:
        outcome = RunOutcome(module, started, datetime.now(UTC), None, timed_out=True)
        log.error("Scheduler: %s exceeded %d s and was killed", module, timeout_seconds)
    log.info(
        "Scheduler: %s finished with code %s after %.0f s",
        module,
        outcome.returncode,
        (outcome.finished - outcome.started).total_seconds(),
    )
    return outcome


class RefreshScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.at = parse_schedule(settings.refresh_schedule)
        self.reconcile_day = settings.reconcile_day_of_month
        self.timeout_seconds = settings.refresh_timeout_seconds
        self.cwd = REPO_ROOT
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.log = download_logger()
        self.history: list[RunOutcome] = []

    @property
    def enabled(self) -> bool:
        return self.at is not None

    # -- lifecycle ------------------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="crime-refresh", daemon=True)
        self._thread.start()
        self.log.info(
            "Scheduler: daily crime refresh at %s UTC; reconciliation on day %d of the month",
            self.at.strftime("%H:%M") if self.at else "?",
            self.reconcile_day,
        )

    def stop(self) -> None:
        self._stop.set()

    # -- loop -----------------------------------------------------------------------------

    def _loop(self) -> None:
        assert self.at is not None
        if self._overdue():
            self.log.info(
                "Scheduler: last successful refresh is older than %s; catching up in %d s",
                CATCH_UP_AFTER,
                CATCH_UP_DELAY_SECONDS,
            )
            if self._stop.wait(CATCH_UP_DELAY_SECONDS):
                return
            self.run_once()
        while not self._stop.is_set():
            due = next_occurrence(self.at, datetime.now(UTC))
            wait = (due - datetime.now(UTC)).total_seconds()
            if self._stop.wait(max(wait, 0)):
                return
            self.run_once()

    def _overdue(self) -> bool:
        freshness = crime_freshness(self.settings.data_dir)
        if freshness.hours_since_success is None:
            return True
        return freshness.hours_since_success > CATCH_UP_AFTER.total_seconds() / 3600

    def run_once(self, *, when: datetime | None = None) -> list[RunOutcome]:
        """One scheduled tick: the refresh, then reconciliation on its day of the month."""
        moment = when or datetime.now(UTC)
        outcomes = [run_module(REFRESH_MODULE, cwd=self.cwd, timeout_seconds=self.timeout_seconds)]
        if moment.day == self.reconcile_day:
            outcomes.append(
                run_module(RECONCILE_MODULE, cwd=self.cwd, timeout_seconds=self.timeout_seconds)
            )
        self.history.extend(outcomes)
        return outcomes
