# Contributing

## Setup

```powershell
uv sync
Copy-Item .env.example .env
uv run pytest
```

An API token is optional. Without one the Chicago Data Portal applies stricter rate
limits. If you have a token, set `CHICAGO_DATA_APP_TOKEN` in `.env` — never in code.

If `uv sync` fails with a hardlink error (`os error 396`), see
[docs/decisions/ISSUE_LOG.md](docs/decisions/ISSUE_LOG.md#onedrive-interferes-with-uv-hardlinks).

## Before every pull request

```powershell
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
```

CI runs the same four commands and will fail the PR if any of them fail.

## Code conventions

- Reusable logic belongs in `src/bw_observatory/`. Scripts under `scripts/` stay thin —
  they wire together library calls and print results, nothing more.
- Make narrow, reviewable changes. Do not delete working functionality to simplify a task.
- Type annotations are required; mypy runs in `strict` mode.

## Data and analysis rules

These are not style preferences. They exist because this project publishes claims about a
real neighborhood and real people.

- Never commit downloaded source data or API tokens. `data/` contents are gitignored.
- Preserve official source fields; do not silently rewrite what the city published.
- Bronzeville is not one official community area. Do not substitute a ward, beat, ZIP
  code, or a single community area for it. See
  [GIS_STRATEGY.md](docs/architecture/GIS_STRATEGY.md).
- Do not infer causation from correlation. Timing association is context, not cause.
- Do not attribute crime to nationality or immigration status, and do not infer either
  from crime data. See
  [EVENTS_AND_POLICY_CONTEXT.md](docs/methodology/EVENTS_AND_POLICY_CONTEXT.md).
- Every published statistic must carry its source and refresh date.

## Documentation

- Update [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) and [TODO.md](TODO.md) after
  completing a feature.
- Record decisions with lasting consequences as an ADR under
  [docs/architecture/ADR/](docs/architecture/ADR/).
- Do not document unbuilt features as if they exist. Mark planned work as planned.
