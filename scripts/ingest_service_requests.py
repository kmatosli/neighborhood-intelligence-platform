"""Bring the 311 layers (Bronze + Silver) up to date with the City of Chicago source.

    uv run python scripts/ingest_service_requests.py --year 2024 --backfill   # fetch a year whole
    uv run python scripts/ingest_service_requests.py                          # refresh newest years
    uv run python scripts/ingest_service_requests.py --enrich-only --year 2025 # rebuild Silver only

Thin wrapper: the command lives in `bw_observatory.ops.ingest_service_requests` so a scheduler
would run exactly the same code. Withdrawn records are a separate question — see
`scripts/reconcile_service_requests.py`.
"""

from __future__ import annotations

from bw_observatory.ops.ingest_service_requests import main

if __name__ == "__main__":
    raise SystemExit(main())
