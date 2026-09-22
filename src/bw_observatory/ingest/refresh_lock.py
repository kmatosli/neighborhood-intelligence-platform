"""One writer at a time for the crime layers.

The refresh and the reconciliation both rewrite Bronze/Silver year files. Two of them running
at once — a scheduled run overlapping a manual one, or a run overlapping its own stalled
predecessor — could interleave partition writes and publish a year whose Silver came from a
different Bronze than its manifest describes. The lock makes the second writer exit with a
clear "already running" instead.

Implementation: an `O_EXCL` lock file in the Bronze directory holding the owner's pid, host
and start time. A lock is stale, and is taken over, when its owner process is gone or it is
older than `stale_after` (a refresh that has run for six hours is not running; it is stuck).
"""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any

LOCK_FILENAME = "refresh.lock"
DEFAULT_STALE_AFTER = timedelta(hours=6)


class AlreadyRunning(RuntimeError):
    """Another refresh or reconciliation holds the lock."""

    def __init__(self, owner: dict[str, Any]) -> None:
        self.owner = owner
        super().__init__(
            f"another run holds the lock (pid {owner.get('pid')} on {owner.get('host')}, "
            f"started {owner.get('started')})"
        )


def pid_alive(pid: int) -> bool:
    """Best-effort liveness check that never signals the process.

    `os.kill(pid, 0)` is the POSIX idiom; on Windows `os.kill` with any other signal would
    terminate the process, so a query-only handle is opened instead.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class RefreshLock:
    def __init__(self, directory: Path, *, stale_after: timedelta = DEFAULT_STALE_AFTER) -> None:
        self.path = directory / LOCK_FILENAME
        self.stale_after = stale_after
        self._held = False

    # -- inspection ---------------------------------------------------------------------

    def owner(self) -> dict[str, Any] | None:
        """Who holds the lock, or None. Unreadable content counts as an anonymous holder."""
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"pid": None, "host": None, "started": None}
        return payload if isinstance(payload, dict) else {"pid": None}

    def is_stale(self, owner: dict[str, Any], now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        started = owner.get("started")
        if isinstance(started, str):
            try:
                if moment - datetime.fromisoformat(started) > self.stale_after:
                    return True
            except ValueError:
                return True
        else:
            return True
        pid = owner.get("pid")
        host = owner.get("host")
        # A pid can only be checked on the machine that owns it.
        if isinstance(pid, int) and host == socket.gethostname():
            return not pid_alive(pid)
        return False

    # -- acquisition --------------------------------------------------------------------

    def acquire(self) -> None:
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "started": datetime.now(UTC).isoformat(),
            }
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                owner = self.owner()
                if owner is not None and not self.is_stale(owner):
                    raise AlreadyRunning(owner) from None
                # Stale: take it over. If the holder vanished between the checks the
                # unlink simply fails and the retry creates the file.
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            self._held = True
            return
        raise AlreadyRunning(self.owner() or {})

    def release(self) -> None:
        if self._held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._held = False

    def __enter__(self) -> RefreshLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
