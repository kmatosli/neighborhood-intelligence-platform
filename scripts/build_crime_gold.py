"""Build the Gold crime aggregates (and, with --prior, revision events) for a release root.

    uv run python scripts/build_crime_gold.py
    uv run python scripts/build_crime_gold.py --data-dir <root> --prior <previous release root>

Thin wrapper over `bw_observatory.ops.build_crime_gold`.
"""

from __future__ import annotations

from bw_observatory.ops.build_crime_gold import main

if __name__ == "__main__":
    raise SystemExit(main())
