"""Validate downloaded boundary layers and build the Silver geography layer.

uv run python scripts/validate_geography.py
uv run python scripts/validate_geography.py --version 2026-07-11
"""

from __future__ import annotations

import argparse

from bw_observatory.config import Settings
from bw_observatory.geography.ingest import latest_version, read_manifest, version_dir
from bw_observatory.geography.models import NeighborhoodStatus
from bw_observatory.geography.normalize import (
    build_geography_dimension,
    build_neighborhood_boundaries,
    layer_validation_report,
    load_neighborhood_config,
    write_silver_geography,
)
from bw_observatory.logging_config import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Boundary set version (default: latest downloaded).")
    args = parser.parse_args()

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)

    reference_dir = settings.data_dir / "reference"
    version = args.version or latest_version(reference_dir)
    if version is None:
        print("ERROR: no boundary set found. Run scripts/download_geography.py first.")
        return 2

    path = version_dir(reference_dir, version)
    manifest = read_manifest(reference_dir, version)

    print(f"Boundary set version: {version}")
    print(f"Location:             {path}")
    print()

    report = layer_validation_report(path)
    print("Layer validation")
    print("-" * 100)
    for row in report.itertuples():
        print(
            f"  {row.layer:20} features={row.feature_count:<6} crs={row.crs:12} "
            f"types={row.geometry_types:14} repaired={row.repaired_geometries:<3} "
            f"dupes={row.duplicate_ids:<3} overlaps={row.unexpected_overlaps:<3} "
            f"area={row.total_area_sq_km:>9.1f} km²  {row.validation_status}"
        )
        if row.messages:
            print(f"       ! {row.messages}")

    dimension = build_geography_dimension(path, manifest)
    configs = load_neighborhood_config()
    neighborhoods = build_neighborhood_boundaries(dimension, configs)

    dimension_path, neighborhood_path = write_silver_geography(
        settings.data_dir / "silver", dimension, neighborhoods
    )

    print()
    print(f"geography_dimension:     {len(dimension):,} polygons -> {dimension_path}")
    print(f"neighborhood_boundaries: {len(neighborhoods)} rows    -> {neighborhood_path}")
    print()
    for row in neighborhoods.itertuples():
        state = "ACTIVE " if row.status == NeighborhoodStatus.ACTIVE else "BLOCKED"
        print(f"  [{state}] {row.display_name:14} {row.boundary_type:26} {row.status}")

    blocked = neighborhoods[neighborhoods["status"] != NeighborhoodStatus.ACTIVE]
    if not blocked.empty:
        print()
        print(
            "NOTE: blocked neighborhoods have no approved boundary. Their assignment is "
            "left null; no substitute geography (ward, beat, ZIP, single community area) "
            "is used."
        )

    print()
    print(
        "VINTAGE WARNING: these are CURRENT boundaries. Assigning a historical incident to "
        "a current ward, beat, or district tells you where it falls TODAY, not which ward "
        "or beat it was in at the time."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
