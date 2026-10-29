"""`scripts/build_data_release.py`: the checksum sidecar that proves a transfer on Render."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_data_release.py"


def load_script() -> ModuleType:  # scripts/ is not a package; import it by path
    spec = importlib.util.spec_from_file_location("build_data_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sidecar_is_lf_terminated_sha256sum_format(tmp_path: Path) -> None:
    archive = tmp_path / "bw-data-release-2026-09-21.tar.gz"
    archive.write_bytes(b"not really a tarball\n" * 100)

    sidecar = load_script().write_sha256_sidecar(archive)
    raw = sidecar.read_bytes()

    # `sha256sum -c` parses "<hex>  <name>\n"; a CRLF (what Windows text mode writes) makes
    # it look for a file whose name ends in "\r", which is the failure this guards against.
    assert sidecar.name == archive.name + ".sha256"
    assert b"\r" not in raw
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    match = re.fullmatch(rb"([0-9a-f]{64})  (\S+)\n", raw)
    assert match is not None, raw
    assert match.group(1).decode() == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert match.group(2).decode() == archive.name


def test_sidecar_passes_sha256sum_check(tmp_path: Path) -> None:
    sha256sum = shutil.which("sha256sum")
    if sha256sum is None:
        pytest.skip("sha256sum not on PATH")
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"payload")
    sidecar = load_script().write_sha256_sidecar(archive)

    result = subprocess.run(
        [sha256sum, "-c", sidecar.name], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "release.tar.gz: OK" in result.stdout


def test_a_new_archive_requires_release_identity_and_matching_gold(tmp_path: Path) -> None:
    import json

    check = load_script().check_release_identity
    assert any("release.json is missing" in p for p in check(tmp_path))

    (tmp_path / "release.json").write_text(
        json.dumps({"release_id": "dev-x", "status": "development", "ledger_sha256": "a"}),
        "utf-8",
    )
    problems = check(tmp_path)
    assert any("only a 'release' root" in p for p in problems)
    assert any("_build.json is missing" in p for p in problems)

    (tmp_path / "release.json").write_text(
        json.dumps(
            {"release_id": "bw-release-20261028", "status": "release", "ledger_sha256": "a"}
        ),
        "utf-8",
    )
    gold = tmp_path / "gold" / "crime"
    gold.mkdir(parents=True)
    build = {"status": "PASS", "release_id": "bw-release-20261028", "input_ledger_sha256": "a"}
    (gold / "_build.json").write_text(json.dumps(build), "utf-8")
    assert check(tmp_path) == []

    (gold / "_build.json").write_text(
        json.dumps({**build, "release_id": "bw-release-20260921"}), "utf-8"
    )
    assert any("Gold was built for" in p for p in check(tmp_path))


def test_a_new_archive_requires_silver_to_match_release_json(tmp_path: Path) -> None:
    import pandas as pd
    from crime_release_fixtures import row, write_root

    root = write_root(tmp_path / "release", [row("a", "2025-03-01", "THEFT")])
    check = load_script().check_release_contents
    assert check(root) == []

    # A Silver rewrite that touches no ledger file: only the full checksums can see it.
    silver = root / "silver" / "crime" / "crime_with_geography" / "2025.parquet"
    frame = pd.read_parquet(silver)
    frame.loc[0, "spatial_ward_current"] = "5"
    frame.to_parquet(silver, index=False)
    assert any("Silver 2025 checksum" in p for p in check(root))


def _year_root(tmp_path: Path, last: str) -> Path:
    from crime_release_fixtures import row, write_root

    return write_root(
        tmp_path / "release", [row("a", "2025-03-01", "THEFT"), row("b", last, "THEFT")]
    )


def test_a_new_archive_requires_exactly_2006_to_the_data_through_year(tmp_path: Path) -> None:
    script = load_script()
    root = _year_root(tmp_path, "2026-09-06")
    assert script.expected_years(root) == range(2006, 2027)
    assert script.check_years(root, range(2006, 2027)) == []
    later = _year_root(tmp_path / "later", "2027-01-15")
    assert script.expected_years(later) == range(2006, 2028)  # 2027 needs no source edit
    assert script.check_years(later, range(2006, 2028)) == []
    assert script.expected_years(tmp_path / "no-release-json") is None


@pytest.mark.parametrize(
    ("layer", "year", "message"),
    [
        ("bronze", 2006, "Bronze is missing years: 2006"),
        ("silver", 2015, "Silver is missing years: 2015"),
        ("silver", 2026, "Silver is missing years: 2026"),
        ("silver", 2027, "Silver has years outside 2006-2026: 2027"),
    ],
)
def test_a_new_archive_refuses_a_missing_or_extra_year(
    tmp_path: Path, layer: str, year: int, message: str
) -> None:
    script = load_script()
    root = _year_root(tmp_path, "2026-09-06")
    subdir = script.BRONZE_CRIME if layer == "bronze" else script.SILVER_CRIME
    target = root / subdir / f"{year}.parquet"
    if target.exists():
        target.unlink()
    else:  # a year after data_through
        target.write_bytes((root / subdir / "2025.parquet").read_bytes())
    expected = script.expected_years(root)
    assert expected == range(2006, 2027)
    assert message in script.check_years(root, expected)
