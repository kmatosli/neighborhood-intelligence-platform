"""Write or verify `release.json`, the explicit identity of a data release root.

    uv run python scripts/write_release_manifest.py --release-id bw-release-20261028
    uv run python scripts/write_release_manifest.py --release-id dev-local --status development
    uv run python scripts/write_release_manifest.py --verify

Thin wrapper over `bw_observatory.ops.write_release_manifest`.
"""

from __future__ import annotations

from bw_observatory.ops.write_release_manifest import main

if __name__ == "__main__":
    raise SystemExit(main())
