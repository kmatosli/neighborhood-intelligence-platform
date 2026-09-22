"""Measure how Ward 20 overlaps each community area (and the tourism neighborhood layer).

uv run python scripts/measure_ward_coverage.py
uv run python scripts/measure_ward_coverage.py --version 2026-07-12 --ward 20

Prints the table that backs config/geographies.yml and docs/methodology/GEOGRAPHY.md.
Method and CRS: src/bw_observatory/geography/ward_coverage.py.
"""

from __future__ import annotations

import argparse

import geopandas as gpd

from bw_observatory.config import Settings
from bw_observatory.geography.ingest import latest_version, version_dir
from bw_observatory.geography.ward_coverage import (
    MEASUREMENT_CRS,
    community_area_coverage,
    measure_ward_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Reference boundary version (default: latest).")
    parser.add_argument("--ward", default="20")
    args = parser.parse_args()

    reference_dir = Settings().data_dir / "reference"
    version = args.version or latest_version(reference_dir)
    if version is None:
        print("No reference boundary version found. Run scripts/download_geography.py first.")
        return 1
    folder = version_dir(reference_dir, version)

    coverage = community_area_coverage(folder, args.ward)
    print(f"Ward {coverage.ward_id} — {coverage.ward_sq_mi:.3f} sq mi (planar, {MEASUREMENT_CRS})")
    print(f"Reference version {version}; sum of shares = {coverage.total_share_pct:.4f}%")
    print()
    print("| CA | Community area | Intersection (sq mi) | % of ward | % of area inside ward |")
    print("|---|---|---|---|---|")
    for row in coverage.rows.itertuples():
        print(
            f"| {row.polygon_id} | {row.polygon_name} | {row.intersection_sq_mi:.3f} | "
            f"{row.share_of_ward_pct:.2f} | {row.share_of_polygon_in_ward_pct:.2f} |"
        )

    neighborhoods = folder / "neighborhoods.geojson"
    if neighborhoods.exists():
        wards = gpd.read_file(folder / "wards_current.geojson")
        layer = gpd.read_file(neighborhoods)
        tourism = measure_ward_coverage(
            wards, layer, ward_id=args.ward, id_field="PRI_NEIGH", name_field="SEC_NEIGH"
        )
        print()
        print("Tourism neighborhood layer (secondary reference; approximate, names not official):")
        print("| Primary | Secondary | Intersection (sq mi) | % of ward | % inside ward |")
        print("|---|---|---|---|---|")
        for row in tourism.rows.itertuples():
            print(
                f"| {row.polygon_id} | {row.polygon_name} | {row.intersection_sq_mi:.3f} | "
                f"{row.share_of_ward_pct:.2f} | {row.share_of_polygon_in_ward_pct:.2f} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
