"""Bring the crime layers (Bronze + Silver) up to date with the City of Chicago source.

    uv run python scripts/refresh_crime.py             # fetch and apply what changed
    uv run python scripts/refresh_crime.py --dry-run   # report what would change, write nothing
    uv run python scripts/refresh_crime.py --since 2026-07-10T15:53:54.000   # override watermark

Thin wrapper: the command lives in `bw_observatory.ops.refresh_crime` so the scheduler runs
exactly the same code. This is the normal freshness path; the whole-year downloader is not.
"""

from __future__ import annotations

from bw_observatory.ops.refresh_crime import main

if __name__ == "__main__":
    raise SystemExit(main())
