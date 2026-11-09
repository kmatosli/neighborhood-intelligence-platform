"""`release.json` — the explicit identity of a data release root.

A release root (`/var/data/bw-release-YYYYMMDD`, or a local development root) used to be
identified only by its directory name, which locally is just `data`. The owner approved
`release.json` (2026-10-27) as the identity contract: an archived release must describe
itself, so a figure computed from it can be traced back to exactly the inputs it read.

Two kinds of digest, on purpose:

* **Full checksums** (`silver_sha256`, the Bronze manifest's own per-year checksums) are
  computed when a release is cut and checked at release verification and deployment
  acceptance. They read hundreds of megabytes and never run per request.
* **The ledger digest** covers the three small bookkeeping files every write to a release
  touches — the Bronze manifest (rewritten by every refresh), the incremental refresh log and
  the reconciliation log (appended by every refresh or reconciliation, which is also the only
  path that changes Silver's `source_status`). Hashing them costs a few kilobytes, so the API
  can afford it on every request to prove that derived products (Gold) still describe the
  bytes beside them.

Releases are immutable once public (owner decision, 2026-10-27): nothing refreshes `current` in
place, so in a healthy deployment the ledger digest never changes after the cut.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

RELEASE_FILENAME = "release.json"
SCHEMA_VERSION = 1

STATUS_RELEASE = "release"
STATUS_DEVELOPMENT = "development"
STATUSES = frozenset({STATUS_RELEASE, STATUS_DEVELOPMENT})

# A public release is named for the day it was cut; a development root says so in its id.
_RELEASE_ID = re.compile(r"^bw-release-\d{8}$")
_DEVELOPMENT_ID = re.compile(r"^dev-[a-z0-9][a-z0-9-]*$")

CRIME_DATASET_ID = "ijzp-q8t2"
BRONZE_CRIME = Path("bronze") / "crime"
SILVER_CRIME = Path("silver") / "crime" / "crime_with_geography"
# The bookkeeping files whose digest is the cheap runtime identity of a release's inputs.
LEDGER_FILES = (
    BRONZE_CRIME / "manifest.parquet",
    BRONZE_CRIME / "incremental_refresh_log.parquet",
    BRONZE_CRIME / "reconciliation_log.parquet",
)
# Config read when deriving products; part of the identity because a changed grouping
# changes the meaning of a derived count.
CONFIG_FILES = ("crime_categories.yml", "geographies.yml")
# The first year of the City crime dataset. The last expected year is never a constant: it is
# the year of the release's `data_through`, so a 2027 release needs no source edit.
FIRST_CRIME_YEAR = 2006


def expected_crime_years(data_through: str) -> range:
    """Exactly the crime years a release must hold: 2006 through `data_through`'s year."""
    return range(FIRST_CRIME_YEAR, int(data_through[:4]) + 1)


def crime_year_problems(label: str, found: set[int], expected: range) -> list[str]:
    """Problems unless `found` is exactly `expected` (missing first, middle, last, or extra)."""
    problems: list[str] = []
    missing = sorted(set(expected) - found)
    extra = sorted(found - set(expected))
    if missing:
        problems.append(f"{label} is missing years: {', '.join(map(str, missing))}")
    if extra:
        problems.append(
            f"{label} has years outside {expected.start}-{expected.stop - 1}: "
            f"{', '.join(map(str, extra))}"
        )
    return problems


class ReleaseManifestError(RuntimeError):
    """A release root has no usable identity."""


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    status: str
    cut_at: str
    data_through: str | None
    source_watermark: str | None
    source_dataset_id: str
    source_manifest_sha256: str
    ledger_sha256: str
    silver_sha256: dict[str, str]
    builder_commit: str
    config_sha256: dict[str, str]
    schema_version: int = SCHEMA_VERSION
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ledger_digest(data_dir: Path) -> str:
    """One SHA-256 over the release's small bookkeeping files (absent ones count as absent).

    Cheap enough to compute per request: the files are a few kilobytes each.
    """
    digest = hashlib.sha256()
    for relative in LEDGER_FILES:
        path = data_dir / relative
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256_file(path).encode() if path.exists() else b"absent")
        digest.update(b"\n")
    return digest.hexdigest()


def config_digests(config_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(config_dir / name) if (config_dir / name).exists() else "absent"
        for name in CONFIG_FILES
    }


def validate_release_id(release_id: str, status: str) -> None:
    if status not in STATUSES:
        raise ReleaseManifestError(f"Unknown release status {status!r}.")
    pattern = _RELEASE_ID if status == STATUS_RELEASE else _DEVELOPMENT_ID
    if not pattern.match(release_id):
        expected = "bw-release-YYYYMMDD" if status == STATUS_RELEASE else "dev-<name>"
        raise ReleaseManifestError(
            f"Release id {release_id!r} does not match {expected} for status {status!r}."
        )


def builder_commit(repo_root: Path | None = None) -> str:
    """The code version that cut the release; `unknown` outside a git checkout."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else "unknown"


def _newest_bronze_year(data_dir: Path) -> int | None:
    years = [int(p.stem) for p in (data_dir / BRONZE_CRIME).glob("*.parquet") if p.stem.isdigit()]
    return max(years) if years else None


def _data_through(data_dir: Path) -> str | None:
    newest = _newest_bronze_year(data_dir)
    if newest is None:
        return None
    table = pq.read_table(data_dir / BRONZE_CRIME / f"{newest}.parquet", columns=["date"])
    value = pc.max(table["date"]).as_py()
    return str(value)[:10] if value else None


def _source_watermark(data_dir: Path) -> str | None:
    log = data_dir / BRONZE_CRIME / "incremental_refresh_log.parquet"
    if not log.exists():
        return None
    runs = pq.read_table(log, columns=["new_watermark", "status", "dry_run"]).to_pandas()
    done = runs[(runs["status"] == "complete") & ~runs["dry_run"].astype(bool)]
    return None if done.empty else str(done.iloc[-1]["new_watermark"])


def build_release_manifest(
    data_dir: Path,
    config_dir: Path,
    release_id: str,
    status: str,
    *,
    cut_at: str | None = None,
    commit: str | None = None,
    notes: list[str] | None = None,
) -> ReleaseManifest:
    """Describe `data_dir` completely. Reads every Silver partition once (build time only)."""
    validate_release_id(release_id, status)
    manifest_path = data_dir / BRONZE_CRIME / "manifest.parquet"
    if not manifest_path.exists():
        raise ReleaseManifestError(f"No Bronze crime manifest under {data_dir}.")
    silver_dir = data_dir / SILVER_CRIME
    silver = {
        path.stem: sha256_file(path)
        for path in sorted(silver_dir.glob("*.parquet"))
        if path.stem.isdigit()
    }
    if not silver:
        raise ReleaseManifestError(f"No Silver crime partitions under {silver_dir}.")
    return ReleaseManifest(
        release_id=release_id,
        status=status,
        cut_at=cut_at or datetime.now(UTC).isoformat(timespec="seconds"),
        data_through=_data_through(data_dir),
        source_watermark=_source_watermark(data_dir),
        source_dataset_id=CRIME_DATASET_ID,
        source_manifest_sha256=sha256_file(manifest_path),
        ledger_sha256=ledger_digest(data_dir),
        silver_sha256=silver,
        builder_commit=commit or builder_commit(),
        config_sha256=config_digests(config_dir),
        notes=list(notes or []),
    )


def write_release_manifest(data_dir: Path, manifest: ReleaseManifest) -> Path:
    target = data_dir / RELEASE_FILENAME
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
    temp.replace(target)
    return target


def read_release_manifest(data_dir: Path) -> ReleaseManifest:
    path = data_dir / RELEASE_FILENAME
    if not path.exists():
        raise ReleaseManifestError(f"{path} does not exist; this root has no release identity.")
    try:
        payload = json.loads(path.read_text("utf-8"))
        manifest = ReleaseManifest(**payload)
    except (ValueError, TypeError) as exc:
        raise ReleaseManifestError(f"{path} is not a valid release manifest: {exc}") from exc
    validate_release_id(manifest.release_id, manifest.status)
    return manifest


def verify_release_manifest(data_dir: Path, config_dir: Path) -> list[str]:
    """Full verification (release verification / deployment acceptance). Empty = sound."""
    try:
        manifest = read_release_manifest(data_dir)
    except ReleaseManifestError as exc:
        return [str(exc)]
    problems: list[str] = []
    if sha256_file(data_dir / BRONZE_CRIME / "manifest.parquet") != (
        manifest.source_manifest_sha256
    ):
        problems.append("Bronze manifest differs from the one recorded at the cut.")
    if ledger_digest(data_dir) != manifest.ledger_sha256:
        problems.append("Release ledger differs from the one recorded at the cut.")
    silver_dir = data_dir / SILVER_CRIME
    on_disk = {p.stem for p in silver_dir.glob("*.parquet") if p.stem.isdigit()}
    if on_disk != set(manifest.silver_sha256):
        problems.append(
            f"Silver partitions {sorted(on_disk)} differ from those recorded "
            f"{sorted(manifest.silver_sha256)}."
        )
    for year, recorded in sorted(manifest.silver_sha256.items()):
        path = silver_dir / f"{year}.parquet"
        if path.exists() and sha256_file(path) != recorded:
            problems.append(f"Silver {year} checksum differs from the one recorded at the cut.")
    # Config differing from the cut is not a data fault (config ships with the code); Gold's own
    # build record is what must match the live config (gold.crime_aggregates.check_gold).
    return problems
