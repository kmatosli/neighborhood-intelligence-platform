"""Reconcile local crime partitions against the source's current id set.

    uv run python scripts/reconcile_crime.py             # two newest years + any drifted year
    uv run python scripts/reconcile_crime.py --year 2025 --year 2026
    uv run python scripts/reconcile_crime.py --dry-run

Thin wrapper over `bw_observatory.ops.reconcile_crime`, which the scheduler also runs.
"""

from __future__ import annotations

from bw_observatory.ops.reconcile_crime import main

if __name__ == "__main__":
    raise SystemExit(main())
