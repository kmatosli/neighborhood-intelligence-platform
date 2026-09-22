"""Describe candidate public datasets for the Ward 20 equity audit (read-only, metadata only).

uv run python scripts/audit_source_readiness.py                    # the standard V2-003 list
uv run python scripts/audit_source_readiness.py v6vf-nfxy eejr-xtfb  # specific dataset ids
uv run python scripts/audit_source_readiness.py --json out.json

Prints one row per dataset (name, updated, rows, date range, geographic fields, how it could
be clipped to the current Ward 20 footprint). Nothing is downloaded beyond metadata and
aggregate counts. Logic: src/bw_observatory/audit/source_readiness.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from bw_observatory.audit.source_readiness import describe_dataset

# The candidate sources reviewed in V2-003 (2026-09-14). Cook County ids carry their domain.
STANDARD_SOURCES: list[tuple[str, str]] = [
    ("data.cityofchicago.org", "ijzp-q8t2"),  # Crimes - 2001 to present (canonical, ingested)
    ("data.cityofchicago.org", "v6vf-nfxy"),  # 311 Service Requests (2018-12 onward)
    ("data.cityofchicago.org", "7as2-ds3y"),  # 311 Pot Holes - Historical (legacy system)
    ("data.cityofchicago.org", "fpsv-qjg3"),  # TIF Projections 2025-2034
    ("data.cityofchicago.org", "72uz-ikdv"),  # TIF Annual Report - Projects
    ("data.cityofchicago.org", "mex4-ppfc"),  # TIF Funded RDA and IGA Projects
    ("data.cityofchicago.org", "etqr-sz5x"),  # SBIF financial incentive projects
    ("data.cityofchicago.org", "eejr-xtfb"),  # TIF district boundaries (current)
    ("data.cityofchicago.org", "nm3d-wkdd"),  # TIF Investment Committee decisions
    ("data.cityofchicago.org", "t68z-cikk"),  # ACS 5-year by community area
    ("data.cityofchicago.org", "kn9c-c2s2"),  # Census socioeconomic indicators by CA (2008-12)
    ("data.cityofchicago.org", "aksk-kvfp"),  # City-Owned Land Inventory
    ("data.cityofchicago.org", "kc9i-wq85"),  # Vacant and Abandoned Buildings - Violations
    ("data.cityofchicago.org", "22u3-xenr"),  # Building Violations
    ("data.cityofchicago.org", "ydr8-5enu"),  # Building Permits
    ("data.cityofchicago.org", "6imu-meau"),  # Street Center Lines
    ("data.cityofchicago.org", "cmr6-dn8c"),  # Special Service Areas boundaries
    ("datacatalog.cookcountyil.gov", "pabr-t5kh"),  # Assessor - Parcel Universe (current year)
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Dataset ids (Chicago portal) to describe.")
    parser.add_argument("--json", type=Path, help="Write full results as JSON to this path.")
    args = parser.parse_args()

    sources = [("data.cityofchicago.org", i) for i in args.ids] if args.ids else STANDARD_SOURCES
    results = []
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for domain, dataset_id in sources:
            r = describe_dataset(dataset_id, domain=domain, client=client)
            results.append(r.as_dict())
            rows = "?" if r.row_count is None else f"{r.row_count:,}"
            span = (
                f"{r.date_range.get('min', '')[:10]}..{r.date_range.get('max', '')[:10]}"
                if r.date_range
                else "-"
            )
            geo = "coords" if r.has_coordinates else ("geom" if r.has_geometry else "-")
            print(
                f"{dataset_id:10} {r.name[:52]:52} rows={rows:>11} "
                f"updated={r.rows_updated_at[:10]:10} "
                f"span={span:23} geo={geo:6} ward={'y' if r.has_ward_field else '-'} "
                f"ca={'y' if r.has_community_area_field else '-'}"
                + (f"  ERROR {r.error}" if r.error else "")
            )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
