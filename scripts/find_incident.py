"""Search local Bronze + Silver data for a known incident. Read-only.

A local operator tool for validating that the pipeline found and classified a specific real
incident. It opens the Parquet files read-only, writes nothing, and modifies nothing.

    uv run python scripts/find_incident.py --year 2026 --date 2026-03-14 --days 3 \
        --block "63RD" --type BATTERY

    uv run python scripts/find_incident.py --case JH123456
    uv run python scripts/find_incident.py --year 2026 --beat 0313 --date 2026-03-14

WHAT IT WILL NOT DO
-------------------
* It never fabricates a match. If nothing matches, it says nothing matched.
* It never picks a "best" match. Every candidate is reported, with the ambiguity explained.
* It prints the block-level location exactly as the city published it (e.g. "063XX S
  BLACKSTONE AVE"). Chicago already redacts the house number. This output is for local
  verification only — block text must never be rendered in the public UI, which shows
  neighborhood-level figures only (docs/architecture/SECURITY.md).

Every filter is optional; supplying more of them narrows the candidate set. Filters are
matched against the data as published, and each match is reported with the field that
matched, so a coincidence is visible as a coincidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from bw_observatory.config import Settings

BRONZE_COLUMNS = [
    "id",
    "case_number",
    "date",
    "block",
    "iucr",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "updated_on",
    "latitude",
    "longitude",
]

SILVER_COLUMNS = [
    "id",
    "spatial_community_area",
    "spatial_beat_current",
    "spatial_district_current",
    "spatial_ward_current",
    "census_tract",
    "neighborhood_woodlawn",
    "neighborhood_bronzeville",
    "geography_status",
    "community_area_mismatch",
    "beat_mismatch",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year", type=int, help="Year to search (defaults to every enriched year)."
    )
    parser.add_argument("--case", help="Case number (RD number), e.g. JH123456. Exact match.")
    parser.add_argument("--date", help="Approximate incident date, YYYY-MM-DD.")
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Window around --date, in days (default 3). Widen it if the date is uncertain.",
    )
    parser.add_argument(
        "--block", help="Substring of the block as published, e.g. '63RD' or 'BLACKSTONE'."
    )
    parser.add_argument("--type", dest="crime_type", help="primary_type substring, e.g. BATTERY.")
    parser.add_argument("--beat", help="Police beat, e.g. 0313.")
    parser.add_argument("--district", help="Police district, e.g. 003.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum candidates to print.")
    return parser


def bronze_years(data_dir: Path) -> list[int]:
    directory = data_dir / "bronze" / "crime"
    return sorted(int(p.stem) for p in directory.glob("*.parquet") if p.stem.isdigit())


def load_year(data_dir: Path, year: int) -> pd.DataFrame:
    """Bronze attributes joined to Silver geography, where the year has been enriched."""
    bronze = data_dir / "bronze" / "crime" / f"{year}.parquet"
    if not bronze.exists():
        return pd.DataFrame()

    frame = pd.read_parquet(bronze, columns=BRONZE_COLUMNS)
    frame["source_year"] = year

    silver = data_dir / "silver" / "crime" / "crime_with_geography" / f"{year}.parquet"
    if silver.exists():
        enriched = pd.read_parquet(silver, columns=SILVER_COLUMNS)
        frame = frame.merge(enriched, on="id", how="left")
        frame["enriched"] = True
    else:
        # The year exists in Bronze but has no spatial assignment yet. Say so; do not guess.
        for column in SILVER_COLUMNS:
            if column != "id":
                frame[column] = pd.NA
        frame["enriched"] = False

    return frame


def apply_filters(frame: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, list[str]]:
    applied: list[str] = []

    if args.case:
        frame = frame[frame["case_number"].astype("string").str.upper() == args.case.upper()]
        applied.append(f"case_number == {args.case.upper()}")

    if args.date:
        target = pd.Timestamp(args.date)
        window = pd.Timedelta(days=args.days)
        moment = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame[
            (moment >= target - window) & (moment <= target + window + pd.Timedelta(days=1))
        ]
        applied.append(f"date within {args.days} day(s) of {target.date()}")

    if args.block:
        frame = frame[
            frame["block"].astype("string").str.upper().str.contains(args.block.upper(), na=False)
        ]
        applied.append(f"block contains '{args.block.upper()}'")

    if args.crime_type:
        frame = frame[
            frame["primary_type"]
            .astype("string")
            .str.upper()
            .str.contains(args.crime_type.upper(), na=False)
        ]
        applied.append(f"primary_type contains '{args.crime_type.upper()}'")

    if args.beat:
        frame = frame[frame["beat"].astype("string").str.lstrip("0") == args.beat.lstrip("0")]
        applied.append(f"beat == {args.beat}")

    if args.district:
        frame = frame[
            frame["district"].astype("string").str.lstrip("0") == args.district.lstrip("0")
        ]
        applied.append(f"district == {args.district}")

    return frame, applied


def describe(record: dict[str, Any], index: int) -> None:
    def value(key: str, default: str = "not published") -> str:
        raw = record.get(key)
        return default if raw is None or pd.isna(raw) else str(raw)

    print(f"\n--- CANDIDATE {index} " + "-" * 56)
    print(f"  incident id       {value('id')}")
    print(f"  case number       {value('case_number')}")
    print(f"  date              {value('date')}")
    print(f"  primary type      {value('primary_type')}")
    print(f"  description       {value('description')}")
    print(f"  location type     {value('location_description')}")
    print(f"  block (published) {value('block')}   <- block level; not an exact address")
    print(f"  arrest            {value('arrest')}   (an arrest is not a conviction)")
    print(f"  domestic          {value('domestic')}")
    print(f"  last updated      {value('updated_on')}")

    print("  -- geography as the city reported it --")
    print(
        f"     beat {value('beat')} | district {value('district')} | ward {value('ward')} "
        f"| community area {value('community_area')}"
    )

    if record.get("enriched"):
        print("  -- geography derived by point-in-polygon (this project) --")
        print(
            f"     beat {value('spatial_beat_current')} "
            f"| district {value('spatial_district_current')} "
            f"| ward {value('spatial_ward_current')} "
            f"| community area {value('spatial_community_area')}"
        )
        print(f"     census tract      {value('census_tract')}")
        print(f"     Woodlawn          {value('neighborhood_woodlawn')}")
        bronzeville = value("neighborhood_bronzeville", "null - boundary pending approval")
        print(f"     Bronzeville       {bronzeville}")
        print(f"     geography status  {value('geography_status')}")

        mismatches = [
            name
            for name, key in (
                ("community area", "community_area_mismatch"),
                ("beat", "beat_mismatch"),
            )
            if record.get(key) is True
        ]
        if mismatches:
            print(
                f"     NOTE: source and spatial {', '.join(mismatches)} disagree for this record."
            )
    else:
        print("  -- geography NOT derived: this year has not been enriched yet --")


def main() -> int:
    args = build_parser().parse_args()

    if not any([args.case, args.date, args.block, args.crime_type, args.beat, args.district]):
        print(
            "ERROR: supply at least one filter "
            "(--case, --date, --block, --type, --beat, --district)."
        )
        return 2

    settings = Settings()
    data_dir = settings.data_dir

    years = [args.year] if args.year else bronze_years(data_dir)
    if not years:
        print("ERROR: no Bronze crime data found.")
        return 2

    frames = [load_year(data_dir, year) for year in years]
    frames = [f for f in frames if not f.empty]
    if not frames:
        print(f"ERROR: no Bronze data for {years}.")
        return 2

    combined = pd.concat(frames, ignore_index=True)
    candidates, applied = apply_filters(combined, args)

    print("=" * 74)
    print("INCIDENT SEARCH - read-only. No data was modified.")
    print("=" * 74)
    print(f"Years searched:   {years}")
    print(f"Records searched: {len(combined):,}")
    print("Filters applied:")
    for rule in applied:
        print(f"  - {rule}")

    count = len(candidates)
    print(f"\nCANDIDATES FOUND: {count}")

    if count == 0:
        print(
            "\nNo record matches these filters. That is the result — no closest match is\n"
            "offered, because the nearest record is not evidence of anything.\n"
            "\nIf you expected a match, consider:\n"
            "  * widening --days (the reported date may differ from the incident date)\n"
            "  * dropping --type (the city's classification may not match your expectation)\n"
            "  * a shorter --block fragment (street naming varies: '63RD' vs 'E 63RD ST')\n"
            "  * the ~7-day publication lag, and that records are revised after publication\n"
            "  * the incident may never have been reported to CPD, or may be withheld"
        )
        return 1

    ordered = candidates.sort_values("date")
    for index, (_, row) in enumerate(ordered.head(args.limit).iterrows(), start=1):
        describe(dict(row), index)

    if count > args.limit:
        print(f"\n({count - args.limit} further candidates not shown; raise --limit.)")

    if count > 1:
        print("\n" + "=" * 74)
        print("AMBIGUITY: more than one record matches.")
        print("=" * 74)
        print(
            "These filters cannot distinguish between the candidates above. The crime data\n"
            "contains no names, so no record can be tied to a specific person from this data\n"
            "alone. Narrow the search with a case number if you have one - it is the only\n"
            "field that identifies a single report."
        )
        types = ordered["primary_type"].astype("string").value_counts().to_dict()
        print(f"\nCandidate crime types: {types}")

    print("\nReminder: block-level locations above are for local verification only and must")
    print("not be rendered in the public UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
