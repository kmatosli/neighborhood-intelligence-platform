"""Build the Gold crime aggregates for a release root, and optionally its revision events.

    python -m bw_observatory.ops.build_crime_gold
    python -m bw_observatory.ops.build_crime_gold --data-dir <root> --prior <previous release root>

The root must already carry `release.json`. The build fails — and publishes nothing new —
unless every Gold total reconciles exactly to Silver. With `--prior`, the incident-level
revision events between the two releases are built into this root's Gold and proved by the
per-cell invariant. Exit codes: 0 PASS, 1 build failed, 2 usage.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bw_observatory.config import Settings
from bw_observatory.gold.crime_aggregates import GoldBuildError, build_crime_gold
from bw_observatory.gold.revisions import RevisionBuildError, build_revision_events
from bw_observatory.release import builder_commit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=None, help="Release root (default BW_DATA_DIR)."
    )
    parser.add_argument(
        "--prior", type=Path, default=None, help="Previous release root to compare."
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    data_dir = (args.data_dir or settings.data_dir).resolve()
    try:
        build = build_crime_gold(data_dir, settings.config_dir, commit=builder_commit())
    except GoldBuildError as exc:
        print(f"FAIL: {exc}")
        return 1
    span = f"{build.years[0]}–{build.years[-1]}"
    print(f"Gold PASS for {build.release_id}: {build.rows:,} rows, years {span}")
    print(f"  geographies {', '.join(build.geographies)}")
    print(f"  data_through {build.data_through}")

    if args.prior is not None:
        try:
            proof = build_revision_events(args.prior.resolve(), data_dir)
        except RevisionBuildError as exc:
            print(f"FAIL (revisions): {exc}")
            return 1
        print(
            f"Revisions PASS {proof.prior_release_id} → {proof.current_release_id}: "
            f"{proof.events:,} changed incidents of {proof.ids_compared:,} compared; "
            f"{proof.cells_checked:,} cells satisfy current − prior = entries − exits"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
