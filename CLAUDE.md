# Claude Code Instructions

Read `README.md` and `docs/PROJECT_STATUS.md` before editing.

Rules:

1. Make narrow, reviewable changes.
2. Never delete working functionality to simplify a task.
3. Keep scripts thin; reusable logic belongs under `src/bw_observatory`.
4. Run Ruff, mypy, and pytest after meaningful changes.
5. Never commit secrets or downloaded source data.
6. Do not define Bronzeville as one official community area.
7. Do not infer causation from correlation.
8. Do not attribute crime to nationality or immigration status.
9. Update `docs/PROJECT_STATUS.md` after completing a feature.
10. Show `git diff` before committing.

## Execution Authority

Claude may proceed without additional approval for:

- Reading and searching project files
- Inspecting repository structure and configuration
- Running tests, type checks, and read-only diagnostics
- Inspecting APIs and local data files
- Loading and validating existing data through approved project commands
- Implementing the current approved milestone
- Fixing defects directly related to the current milestone
- Editing files required to complete the current approved feature

Claude must stop and request approval before:

- Committing, merging, rebasing, resetting, or force-pushing Git history
- Deleting or moving files or directories
- Performing destructive data or database operations
- Making schema-breaking changes
- Adding or removing major dependencies
- Redesigning the application architecture
- Changing the approved product scope
- Deploying publicly or modifying production infrastructure
- Making changes unrelated to the current milestone

Claude should not pause merely to confirm the repository, read documentation,
list files, inspect existing data, run focused tests, or perform other routine
read-only engineering work.

## Data Layer Contract

The geography-enriched Silver layer is the application system of record.

Application code, APIs, charts, reports, and resident-facing analysis should read
from validated Silver outputs rather than returning to Bronze source files.

Do not inspect, rebuild, or modify Bronze data unless a specific user-visible
defect requires it.

Known protection:

- `data/bronze/crime/2024.parquet` is currently invalid and contains one row.
- The corresponding Silver 2024 output is intact and remains usable.
- Do not run forced 2024 enrichment from the current Bronze file.
- Restore Bronze 2024 through the approved downloader before any future forced
  re-enrichment.

## Current Delivery Priority

Historical data loading and geography enrichment are complete for 2006 through
2026.

The current approved milestone is the Overview page.

Until Overview meets its acceptance criteria:

- Do not work on Trends.
- Do not work on Beat Meeting.
- Do not work on Community Change.
- Do not return to ingestion or enrichment work unless a user-visible defect
  requires it.
- Do not redesign working application structure.
- Do not refactor unrelated code.

Overview is complete only when:

- Every visible widget uses live API data.
- Every visible control works.
- No fabricated or placeholder values remain.
- Unsupported controls are removed or clearly disabled.
- Data source and data-through information are visible.
- The page remains usable on mobile and desktop.

## Feature Completion Workflow

When implementing a milestone:

1. Perform only the minimum read-only inspection needed to understand the inputs.
2. Make the required code changes.
3. Run only focused validation for the feature being implemented.
4. Report completion.
5. Stop.

Avoid repeated repository exploration once the project structure is understood.

Do not perform broad audits, repository-wide verification, or unrelated inspections while implementing a page unless a blocking defect is encountered.

