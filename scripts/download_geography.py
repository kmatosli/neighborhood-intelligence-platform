"""Download official Chicago boundary layers into versioned reference storage.

uv run python scripts/download_geography.py
uv run python scripts/download_geography.py --version 2026-07-11 --force
"""

from __future__ import annotations

import argparse

from bw_observatory.config import Settings
from bw_observatory.geography.ingest import (
    default_version,
    download_boundaries,
    version_dir,
)
from bw_observatory.geography.models import ValidationStatus
from bw_observatory.logging_config import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Boundary set version (default: today, UTC).")
    parser.add_argument("--force", action="store_true", help="Re-download existing layers.")
    args = parser.parse_args()

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    version = args.version or default_version()
    reference_dir = settings.data_dir / "reference"

    manifest = download_boundaries(reference_dir, version=version, force=args.force)

    print()
    print(f"Boundary set version: {version}")
    print(f"Location:             {version_dir(reference_dir, version)}")
    print()
    for row in manifest.itertuples():
        marker = "OK " if row.validation_status != ValidationStatus.UNRESOLVED else "FAIL"
        print(
            f"  [{marker}] {row.layer:20} {row.dataset_id:16} "
            f"features={row.feature_count:<6} vintage={row.vintage_start or '-':12} "
            f"role={row.role}"
        )

    unresolved = manifest[manifest["validation_status"] == ValidationStatus.UNRESOLVED]
    if not unresolved.empty:
        print()
        print(
            f"WARNING: {len(unresolved)} layer(s) could not be retrieved: "
            f"{list(unresolved['layer'])}"
        )
        print("They are recorded as source_unresolved. No boundary was invented for them.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
