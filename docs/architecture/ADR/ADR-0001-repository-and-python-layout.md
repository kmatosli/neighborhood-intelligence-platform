# ADR-0001 — Repository and Python layout

**Status.** Accepted
**Date.** 2026-07-11

## Context

The project needs a layout that supports a library of reusable ingestion and validation
logic, thin operational scripts, and a future web application, while keeping quality gates
enforceable in CI.

An early defect made the choice concrete. The package lived under `src/` but `pyproject.toml`
declared no build backend, so `uv` treated the project as virtual and never installed
`bw_observatory` into the environment. Tests still passed, because pytest was configured
with `pythonpath = ["src"]` — which put the source tree on the path for the *test process
only*. Every other process failed: `scripts/check_crime_api.py` died with
`ModuleNotFoundError`. The test configuration was masking a broken install.

## Decision

- Keep the **`src/` layout**: importable code lives in `src/bw_observatory/`.
- Declare **hatchling** as the build backend, with
  `[tool.hatch.build.targets.wheel] packages = ["src/bw_observatory"]` (needed because the
  distribution name, `bronzeville-woodlawn-observatory`, differs from the package name).
- **Install the project into the environment** on `uv sync`.
- **Remove `pythonpath = ["src"]` from the pytest config**, so tests import the package
  exactly the way scripts and the future application do.
- Never work around import failures with `sys.path` manipulation or a manually set
  `PYTHONPATH`.
- Keep scripts in `scripts/` thin: wiring and printing only, with reusable logic in the
  package.
- CI enforces Ruff, Ruff format, mypy (`strict`), and pytest.

## Consequences

- A broken install now fails the test suite instead of hiding behind it. A subprocess test
  (`tests/test_package_install.py`) imports the package in a clean interpreter to guard the
  regression.
- Scripts, tests, cron jobs, and the future API all resolve imports identically.
- `uv sync` builds the project, so a build backend must stay installable — this surfaced a
  OneDrive hardlink issue on the primary dev machine (see
  [ISSUE_LOG.md](../../decisions/ISSUE_LOG.md#onedrive-interferes-with-uv-hardlinks)).
- Contributors must run `uv sync` before scripts will work. This is expected and documented
  in [CONTRIBUTING.md](../../../CONTRIBUTING.md).

## Alternatives considered

**Flat layout (package at the repository root).** Importable without installation, so the
original bug could not occur. Rejected: it makes it easy to accidentally import from the
working directory rather than the installed package, blurs what actually ships, and mixes
scripts, tests, and library code at the top level.

**Keep `src/` and keep `pythonpath = ["src"]`, without installing.** The status quo that
caused the bug. Rejected: tests would keep passing while every non-pytest process fails.

**`sys.path` manipulation in scripts, or a checked-in `PYTHONPATH`.** Rejected: it makes
each entry point responsible for import plumbing, breaks silently when a script is moved,
and papers over the actual packaging defect.
