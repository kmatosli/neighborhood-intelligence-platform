from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from bw_observatory.config import Settings
from bw_observatory.presentation.overview import bronze_path, silver_path


def test_default_dataset_id() -> None:
    settings = Settings(_env_file=None)
    assert settings.chicago_crime_dataset_id == "ijzp-q8t2"


def test_dataset_id_override(monkeypatch) -> None:
    monkeypatch.setenv("CHICAGO_CRIME_DATASET_ID", "example-id")
    settings = Settings(_env_file=None)
    assert settings.chicago_crime_dataset_id == "example-id"


# -- release pointer -----------------------------------------------------------------------
#
# In production BW_DATA_DIR is `/var/data/current`, a symlink a release switch renames over.
# Settings must pin the root it was built with, so one request (or one refresh run) reads
# every file from the same release even if the pointer moves underneath it.


def test_data_dir_is_pinned_to_its_resolved_target(tmp_path: Path, monkeypatch) -> None:
    release = tmp_path / "releases" / "a"
    release.mkdir(parents=True)
    indirect = tmp_path / "releases" / "b" / ".." / "a"

    assert Settings(_env_file=None, data_dir=indirect).data_dir == release.resolve()

    monkeypatch.setenv("BW_DATA_DIR", str(indirect))
    assert Settings(_env_file=None).data_dir == release.resolve()

    # A root that does not exist yet (fresh tmp dirs in tests) must still be accepted.
    missing = tmp_path / "not-yet"
    assert Settings(_env_file=None, data_dir=missing).data_dir == missing.resolve()


def _release(root: Path, name: str) -> Path:
    """A minimal release root whose Bronze and Silver both carry the release's name."""
    bronze = root / "releases" / name / "bronze" / "crime"
    silver = root / "releases" / name / "silver" / "crime" / "crime_with_geography"
    bronze.mkdir(parents=True)
    silver.mkdir(parents=True)
    pd.DataFrame({"id": ["1"], "release": [name]}).to_parquet(bronze / "2024.parquet")
    pd.DataFrame({"id": ["1"], "release": [name]}).to_parquet(silver / "2024.parquet")
    return root / "releases" / name


def _point(link: Path, target: Path) -> None:
    """The production switch: create the new link beside the old one, rename over it."""
    staged = link.with_name(link.name + ".next")
    os.symlink(target, staged, target_is_directory=True)
    os.replace(staged, link)


def test_request_reads_one_release_even_if_the_pointer_moves(tmp_path: Path) -> None:
    release_a = _release(tmp_path, "a")
    release_b = _release(tmp_path, "b")
    current = tmp_path / "current"
    try:
        os.symlink(release_a, current, target_is_directory=True)
    except OSError as error:  # Windows without the symlink privilege; runs on Linux/CI
        pytest.skip(f"symlinks unavailable here: {error}")

    settings = Settings(_env_file=None, data_dir=current)  # what a request does first
    _point(current, release_b)  # the switch lands mid-request
    assert Path(os.readlink(current)) == release_b

    bronze = pd.read_parquet(bronze_path(settings.data_dir, 2024))
    silver = pd.read_parquet(silver_path(settings.data_dir, 2024))
    assert bronze["release"].item() == "a"
    assert silver["release"].item() == "a"
    assert settings.data_dir == release_a.resolve()

    # A request that starts after the switch sees the new release, no restart involved.
    assert Settings(_env_file=None, data_dir=current).data_dir == release_b.resolve()
