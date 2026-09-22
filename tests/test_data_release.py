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
