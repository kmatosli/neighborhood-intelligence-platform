"""Build and verify the Render data release archive `bw-data-release.tar.gz`.

The API reads Parquet directly off disk at request time. That data is never in Git and never
in a build artifact, so it reaches Render as a portable archive built here. This script:

    1. copies the source data tree into a staging directory (outside the source tree),
    2. verifies staging matches the source byte-for-byte (relative path, size, SHA-256),
    3. builds `bw-data-release.tar.gz` with directories stored 0755 and files 0644,
    4. inspects the archive's stored permissions and paths without extracting,
    5. extracts into a clean temporary directory,
    6. verifies the extracted tree matches the source byte-for-byte,

and prints a report. Any failure exits non-zero and names the exact problem.

    uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz
    uv run python scripts/build_data_release.py --output <archive> --verify-only

An existing archive is never overwritten unless `--overwrite` is given, so an earlier release
(the one production currently runs) survives building the next one. A `<archive>.sha256`
sidecar (`sha256sum -c` format) is written next to the archive so the copy that lands on the
far side can be checked before anything is extracted.

The source data tree is NEVER modified. Directory permissions are normalized only inside the
staging copy and, authoritatively, in the archive metadata itself — the previous archive
stored directories 0555 (read-only), which broke extraction on Render's GNU tar.

Standard library only. No network, no credentials, no ingestion, no enrichment.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "data"
DEFAULT_ARCHIVE_PATH = REPO_ROOT / "bw-data-release.tar.gz"

# Staging and extraction live in the system temp dir, outside the source tree and outside the
# OneDrive-synced repository, so a multi-hundred-MB copy never churns Git or the sync client.
WORK_ROOT = Path(tempfile.gettempdir()) / "bw-data-release"
STAGING_DIR = WORK_ROOT / "staging"
EXTRACT_DIR = WORK_ROOT / "extract"

# The data folders the archive root should contain directly, in the order the deployment
# expects them. Only those that exist in the source are archived; absent ones are reported.
TOP_LEVEL = ("bronze", "silver", "reference", "catalog", "review", "gold")

# Bronze and Silver crime years that must both be present and complete.
REQUIRED_YEARS = range(2006, 2027)
BRONZE_CRIME = Path("bronze") / "crime"
SILVER_CRIME = Path("silver") / "crime" / "crime_with_geography"

DIR_MODE = 0o755
FILE_MODE = 0o644

# OS metadata that must never enter the archive. Real POSIX data files are kept as-is,
# including `.gitkeep` markers, so the extracted tree matches the source exactly.
JUNK_NAMES = {".DS_Store", "Thumbs.db"}


def _is_junk(name: str) -> bool:
    return name in JUNK_NAMES or name.startswith("._")


def iter_files(root: Path) -> Iterator[Path]:
    """Every non-junk file under `root`, as paths relative to `root`, sorted for determinism."""
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _is_junk(d))
        for name in filenames:
            if _is_junk(name):
                continue
            paths.append(Path(dirpath, name).relative_to(root))
    return iter(sorted(paths, key=lambda p: p.as_posix()))


def iter_dirs(root: Path) -> Iterator[Path]:
    """Every directory under `root` (including empty ones), relative to `root`, sorted."""
    paths: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _is_junk(d))
        for name in dirnames:
            paths.append(Path(dirpath, name).relative_to(root))
    return iter(sorted(paths, key=lambda p: p.as_posix()))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path) -> dict[str, tuple[int, str]]:
    """Map each relative POSIX path to (byte size, SHA-256) for every file under `root`."""
    result: dict[str, tuple[int, str]] = {}
    for rel in iter_files(root):
        full = root / rel
        result[rel.as_posix()] = (full.stat().st_size, sha256(full))
    return result


def years_present(root: Path, subdir: Path) -> set[int]:
    directory = root / subdir
    if not directory.exists():
        return set()
    years: set[int] = set()
    for entry in directory.glob("*.parquet"):
        if entry.stem.isdigit():
            years.add(int(entry.stem))
    return years


def check_years(root: Path) -> list[str]:
    """Return a list of problems if Bronze or Silver is missing any year in 2006-2026."""
    problems: list[str] = []
    for label, subdir in (("Bronze", BRONZE_CRIME), ("Silver", SILVER_CRIME)):
        found = years_present(root, subdir)
        missing = [str(y) for y in REQUIRED_YEARS if y not in found]
        if missing:
            problems.append(f"{label} is missing years: {', '.join(missing)}")
    return problems


def refuse_unsafe_target(target: Path) -> None:
    """Never let staging or extraction be, contain, or sit inside the source data tree."""
    source = SOURCE_DIR.resolve()
    resolved = target.resolve()
    if resolved == source or source in resolved.parents or resolved in source.parents:
        sys.exit(f"REFUSED: {resolved} overlaps the source data tree {source}.")


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


Inventory = dict[str, tuple[int, str]]


def compare_trees(source: Inventory, other: Inventory, other_label: str) -> list[str]:
    """Compare two inventories by path set, per-file size, and SHA-256. Return problems."""
    problems: list[str] = []
    missing = sorted(set(source) - set(other))
    extra = sorted(set(other) - set(source))
    if missing:
        problems.append(f"{other_label}: missing {len(missing)} file(s), e.g. {missing[:3]}")
    if extra:
        problems.append(f"{other_label}: {len(extra)} unexpected file(s), e.g. {extra[:3]}")
    for rel in sorted(set(source) & set(other)):
        s_size, s_hash = source[rel]
        o_size, o_hash = other[rel]
        if s_size != o_size:
            problems.append(f"{other_label}: size differs for {rel} ({s_size} vs {o_size})")
        if s_hash != o_hash:
            problems.append(f"{other_label}: SHA-256 differs for {rel}")
    return problems


def make_staging(source: Path, staging: Path) -> None:
    refuse_unsafe_target(staging)
    if staging.exists():
        shutil.rmtree(staging)
    staging.parent.mkdir(parents=True, exist_ok=True)
    # copy2 preserves file bytes and timestamps; contents are what the checksum verifies.
    shutil.copytree(source, staging, copy_function=shutil.copy2)
    normalize_permissions(staging)


def normalize_permissions(root: Path) -> None:
    """Set staging dirs 0755 and files 0644 where the OS honours it.

    On Windows this only moves the read-only bit; the archive's stored modes (set at build
    time) are the portable, authoritative source of truth for the deployment target.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            _try_chmod(Path(dirpath, name), DIR_MODE)
        for name in filenames:
            _try_chmod(Path(dirpath, name), FILE_MODE)
    _try_chmod(root, DIR_MODE)


def _try_chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except (PermissionError, NotImplementedError, OSError):
        pass


def build_archive(staging: Path, archive: Path) -> None:
    """Write the archive with directories 0755 and files 0644, folders at the root directly.

    Uses GNU format, which Python's tarfile writes without pax/SCHILY extended headers, so no
    macOS/BSD metadata enters the archive. Every entry's mode, ownership, and name are set
    explicitly rather than inherited from the (Windows) filesystem.
    """
    if archive.exists():
        archive.unlink()

    def entry(name: str, template: tarfile.TarInfo | None = None) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        if template is not None:
            info.mtime = int(template.mtime)
        return info

    with tarfile.open(archive, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        # Directories first, each stored 0755 so the far side can write into them.
        for rel in iter_dirs(staging):
            info = entry(rel.as_posix() + "/")
            info.type = tarfile.DIRTYPE
            info.mode = DIR_MODE
            info.mtime = int((staging / rel).stat().st_mtime)
            tar.addfile(info)
        # Regular files, each stored 0644.
        for rel in iter_files(staging):
            full = staging / rel
            info = entry(rel.as_posix())
            info.type = tarfile.REGTYPE
            info.mode = FILE_MODE
            info.size = full.stat().st_size
            info.mtime = int(full.stat().st_mtime)
            with full.open("rb") as handle:
                tar.addfile(info, handle)


def inspect_archive(archive: Path) -> tuple[list[str], set[int], set[int]]:
    """Check stored permissions and paths without extracting. Return (problems, bronze, silver)."""
    problems: list[str] = []
    bronze: set[int] = set()
    silver: set[int] = set()
    bronze_prefix = BRONZE_CRIME.as_posix() + "/"
    silver_prefix = SILVER_CRIME.as_posix() + "/"

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()

    if not members:
        return (["archive is empty"], bronze, silver)

    for member in members:
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            problems.append(f"unsafe path in archive: {name}")
        if _is_junk(Path(name).name):
            problems.append(f"junk metadata in archive: {name}")
        if member.isdir():
            if member.mode != DIR_MODE:
                problems.append(f"directory not 0755: {name} is {oct(member.mode)}")
        elif member.isreg():
            if member.mode != FILE_MODE:
                problems.append(f"file not 0644: {name} is {oct(member.mode)}")
            stem = Path(name).stem
            if name.startswith(bronze_prefix) and stem.isdigit():
                bronze.add(int(stem))
            elif name.startswith(silver_prefix) and stem.isdigit():
                silver.add(int(stem))
        else:
            problems.append(f"unexpected entry type in archive: {name} (type {member.type!r})")

    # No unnecessary enclosing directory: every top-level component is an expected data folder.
    top_level = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
    for unexpected in sorted(top_level - set(TOP_LEVEL)):
        problems.append(f"unexpected top-level entry in archive: {unexpected}/")

    for year in REQUIRED_YEARS:
        if year not in bronze:
            problems.append(f"Bronze year missing from archive: {year}")
        if year not in silver:
            problems.append(f"Silver year missing from archive: {year}")

    return (problems, bronze, silver)


def extract_archive(archive: Path, extract: Path) -> None:
    refuse_unsafe_target(extract)
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(extract)


def check_writable_dirs(extract: Path) -> list[str]:
    """Every extracted directory must be writable by its owner (the 0555 bug's symptom)."""
    problems: list[str] = []
    for rel in iter_dirs(extract):
        mode = (extract / rel).stat().st_mode
        if not mode & 0o200:
            problems.append(f"extracted directory not owner-writable: {rel}")
    return problems


def fail(report_lines: list[str], problems: list[str]) -> None:
    print("\n".join(report_lines))
    print("\nRESULT: FAILED")
    for problem in problems:
        print(f"  - {problem}")
    sys.exit(1)


def write_sha256_sidecar(archive: Path) -> Path:
    """`<archive>.sha256` in `sha256sum -c` format, so the far side can verify the transfer."""
    sidecar = archive.with_name(archive.name + ".sha256")
    sidecar.write_text(sha256(archive) + "  " + archive.name + chr(10), encoding="utf-8")
    return sidecar


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify a data release archive")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="skip staging and build; inspect, extract, and checksum-verify the existing archive",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARCHIVE_PATH,
        help=f"archive path to build or verify (default: {DEFAULT_ARCHIVE_PATH.name})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --output to replace an archive that already exists (off by default, so a "
        "previous release is never clobbered by accident)",
    )
    args = parser.parse_args()
    archive_path: Path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    if not args.verify_only and archive_path.exists() and not args.overwrite:
        sys.exit(
            f"Refusing to overwrite existing archive {archive_path}. Pass --output with a new "
            "name (recommended: one archive per release) or --overwrite."
        )

    report: list[str] = []

    def log(line: str = "") -> None:
        report.append(line)
        print(line, flush=True)

    if not SOURCE_DIR.exists():
        sys.exit(f"Source data directory not found: {SOURCE_DIR}")

    log(f"Source data directory : {SOURCE_DIR}")
    log("Building source inventory (SHA-256 per file)…")
    source_inv = inventory(SOURCE_DIR)
    source_bytes = sum(size for size, _ in source_inv.values())
    log(f"Source files          : {len(source_inv)}")
    log(f"Source total size      : {human(source_bytes)} ({source_bytes:,} bytes)")

    year_problems = check_years(SOURCE_DIR)
    if year_problems:
        fail(report, year_problems)
    log(f"Bronze years           : {min(REQUIRED_YEARS)}-{max(REQUIRED_YEARS)} complete")
    log(f"Silver years           : {min(REQUIRED_YEARS)}-{max(REQUIRED_YEARS)} complete")

    if not args.verify_only:
        # Phase: disk space. Need staging + archive + extraction + overhead.
        needed = source_bytes * 2 + source_bytes // 2 + 300 * 1024 * 1024
        available = min(free_bytes(WORK_ROOT), free_bytes(archive_path))
        log(f"Disk free (min)        : {human(available)} (need ~{human(needed)})")
        if available < needed:
            shortfall = f"insufficient disk space: need ~{human(needed)}, have {human(available)}"
            fail(report, [shortfall])

        # Phase: staging copy.
        log(f"Staging copy           : {STAGING_DIR}")
        make_staging(SOURCE_DIR, STAGING_DIR)

        # Phase: verify staging vs source.
        staging_inv = inventory(STAGING_DIR)
        staging_problems = compare_trees(source_inv, staging_inv, "staging")
        if staging_problems:
            fail(report, staging_problems)
        log("Source vs staging      : PASS (paths, sizes, SHA-256 all match)")

        # Phase: build archive.
        log(f"Building archive       : {archive_path}")
        build_archive(STAGING_DIR, archive_path)

    if not archive_path.exists():
        sys.exit(f"Archive not found: {archive_path}. Run without --verify-only first.")

    # Phase: inspect archive.
    archive_problems, arc_bronze, arc_silver = inspect_archive(archive_path)
    if archive_problems:
        fail(report, archive_problems)
    log("Archive permissions    : PASS (dirs 0755, files 0644, no unsafe paths, no junk)")
    log(f"Archive Bronze years   : {min(arc_bronze)}-{max(arc_bronze)} present")
    log(f"Archive Silver years   : {min(arc_silver)}-{max(arc_silver)} present")

    # Phase: extract and verify.
    log(f"Extraction dir         : {EXTRACT_DIR}")
    extract_archive(archive_path, EXTRACT_DIR)
    extract_inv = inventory(EXTRACT_DIR)
    extract_problems = compare_trees(source_inv, extract_inv, "extracted")
    extract_problems += check_writable_dirs(EXTRACT_DIR)
    if extract_problems:
        fail(report, extract_problems)
    log("Source vs extracted    : PASS (paths, sizes, SHA-256 all match)")
    log("Extracted dirs writable: PASS")

    archive_size = archive_path.stat().st_size
    sidecar = write_sha256_sidecar(archive_path)
    log("")
    log(f"Archive path           : {archive_path}")
    log(f"Archive size           : {human(archive_size)} ({archive_size:,} bytes)")
    digest = sidecar.read_text(encoding="utf-8").split()[0]
    log(f"Archive SHA-256        : {digest}  ({sidecar.name})")
    log("")
    log(f"RESULT: PASS — verified {archive_path.name} is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
