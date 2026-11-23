"""Write `release.json`, the explicit identity of a data release root.

    python -m bw_observatory.ops.write_release_manifest --release-id bw-release-20261028
    python -m bw_observatory.ops.write_release_manifest --release-id dev-local --status development
    python -m bw_observatory.ops.write_release_manifest --verify

Run on a candidate release after its refresh and reconciliation and before Gold is built and
the archive is cut; the identity records the bytes it describes, so any later write to the
root makes `--verify` (and the API's Gold check) fail. Exit codes: 0 done, 1 verification
failed, 2 usage.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bw_observatory.config import Settings
from bw_observatory.release import (
    STATUS_DEVELOPMENT,
    STATUS_RELEASE,
    ReleaseManifestError,
    build_release_manifest,
    verify_release_manifest,
    write_release_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=None, help="Release root (default BW_DATA_DIR)."
    )
    parser.add_argument("--release-id", help="bw-release-YYYYMMDD, or dev-<name> for development.")
    parser.add_argument(
        "--status", choices=[STATUS_RELEASE, STATUS_DEVELOPMENT], default=STATUS_RELEASE
    )
    parser.add_argument("--cut-at", default=None, help="ISO timestamp of the cut (default now).")
    parser.add_argument("--note", action="append", default=[], help="Provenance note (repeatable).")
    parser.add_argument("--verify", action="store_true", help="Verify the existing release.json.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    data_dir = (args.data_dir or settings.data_dir).resolve()

    if args.verify:
        problems = verify_release_manifest(data_dir, settings.config_dir)
        for problem in problems:
            print(f"FAIL: {problem}")
        print("RESULT: PASS" if not problems else "RESULT: FAIL")
        return 0 if not problems else 1

    if not args.release_id:
        print("ERROR: --release-id is required unless --verify is given.")
        return 2
    try:
        manifest = build_release_manifest(
            data_dir,
            settings.config_dir,
            args.release_id,
            args.status,
            cut_at=args.cut_at,
            notes=args.note,
        )
    except ReleaseManifestError as exc:
        print(f"ERROR: {exc}")
        return 2
    path = write_release_manifest(data_dir, manifest)
    print(f"Wrote {path}")
    print(f"  release_id     {manifest.release_id} ({manifest.status})")
    print(f"  data_through   {manifest.data_through}")
    print(f"  watermark      {manifest.source_watermark}")
    print(f"  ledger sha256  {manifest.ledger_sha256}")
    print(f"  builder commit {manifest.builder_commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
