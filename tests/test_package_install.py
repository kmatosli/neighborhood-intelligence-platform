"""Guards that the package is installed into the environment, not merely on sys.path."""

import subprocess
import sys

import bw_observatory


def test_version_is_exposed() -> None:
    assert bw_observatory.__version__ == "0.1.0"


def test_importable_in_a_clean_interpreter() -> None:
    # Run outside pytest's process so no test-time sys.path setup can satisfy the import.
    # This fails if `uv sync` stops installing the project package.
    result = subprocess.run(
        [sys.executable, "-c", "import bw_observatory; print(bw_observatory.__version__)"],
        capture_output=True,
        text=True,
        cwd=sys.prefix,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"
