# Security and Responsible Use

This document covers both conventional security and the analytical limits that protect the
people this project is about. Both are enforced.

## Secrets

- **No secrets in Git.** No API tokens, credentials, or keys in source, config, tests, or
  commit history.
- **Tokens come from environment variables.** `CHICAGO_DATA_APP_TOKEN` is read from the
  environment via `.env`, which is gitignored. `.env.example` documents the variable names
  with empty values.
- The Chicago app token is a rate-limit key, not an authorization secret — it still must
  not be committed.

## Data handling

- **Downloaded source data is ignored by Git.** `data/**` JSON, CSV, GeoJSON, Parquet, and
  DuckDB files are gitignored; only `.gitkeep` files are tracked. Re-derive data by running
  ingestion, never by committing it.
- **Preserve source provenance.** Every stored record retains its source dataset ID and
  refresh timestamp so any published number can be traced to the official record it came
  from.
- Logs must not contain full API tokens or raw personal detail.

## Analytical limits

These are hard constraints on what may be built, not guidance.

- **No person-level profiling.** The project analyzes places, times, and categories — not
  individuals. No dossiers, no individual histories.
- **No suspect identification.** Nothing in this project may be used to name, rank, or
  score a person as a suspect, or to support a watch-list of any kind.
- **No nationality-based risk analysis.** Crime data may not be used to attribute crime to
  a nationality, ethnicity, or immigration status, and neither may be inferred from crime
  data. See
  [EVENTS_AND_POLICY_CONTEXT.md](../methodology/EVENTS_AND_POLICY_CONTEXT.md).
- **Exact addresses are not displayed.** Chicago publishes block-level locations; the
  project does not attempt to de-blur them or reconstruct precise addresses.

## Application surface

- **No public unrestricted refresh endpoint.** Ingestion is not triggerable by anonymous
  users. The public API is read-only over the Gold layer.
- Refreshes run on a schedule or an authenticated internal trigger only.
- A failed refresh must never erase valid existing data.

## Status

Secrets handling and data gitignoring are **in place today**. The application-surface rules
apply to the API and web application, which are **not built** — they are constraints on
future work.
