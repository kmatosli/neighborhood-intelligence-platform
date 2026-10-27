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
