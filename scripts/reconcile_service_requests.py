"""Reconcile local 311 partitions against the source's current id set.

    uv run python scripts/reconcile_service_requests.py              # the two newest years
    uv run python scripts/reconcile_service_requests.py --year 2025 --year 2026
    uv run python scripts/reconcile_service_requests.py --dry-run

Thin wrapper over `bw_observatory.ops.reconcile_service_requests`. Records the City no longer
publishes are marked `source_removed` in Silver and kept; nothing is ever deleted.
"""

from __future__ import annotations

from bw_observatory.ops.reconcile_service_requests import main

if __name__ == "__main__":
    raise SystemExit(main())
