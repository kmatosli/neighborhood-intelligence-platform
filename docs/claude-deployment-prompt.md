# Claude Code Task: Build a Verified Render Data Release

## Objective

Create a reliable, fully verified deployment package for the Bronzeville-Woodlawn Observatory / Neighborhood Intelligence Platform.

The immediate problem is packaging. Do not change or rebuild the data.

## Environment

The user is working in:

- Windows 11
- VS Code
- Claude Code
- PowerShell

Use PowerShell syntax for all user-facing commands unless another shell is strictly required.

Follow the repository's `CLAUDE.md` instructions.

Work autonomously. Do not ask permission for routine, non-destructive steps. Continue until the task is complete or a listed stop condition occurs.

## Non-Negotiable Data Protections

Do not:

- modify, regenerate, truncate, transform, or download data
- run ingestion
- run geography enrichment
- delete the original data directory
- overwrite the original data directory
- modify source Parquet, GeoJSON, manifest, refresh-log, or reference files
- upload anything
- change Render
- deploy anything

Preserve every source data file byte-for-byte.

Only change permissions inside a generated staging copy and the resulting archive.

Never delete or regenerate the data directory unless the user explicitly types:

`REBUILD THE DATA`

Treat these as production assets:

- `bronze/`
- `silver/`
- `reference/`
- `catalog/`
- `review/`
- `gold/`

## Confirmed Background

The existing archive was created with read-only directory permissions.

Its directory entries are:

`dr-xr-xr-x` (`0555`)

GNU tar on Render creates those directories as read-only and then cannot write their child files.

The replacement archive must store directories as:

`drwxr-xr-x` (`0755`)

Regular files should be stored as:

`-rw-r--r--` (`0644`)

The dataset is expected to include the complete existing application data directory, including these paths where present:

- `bronze/crime/2006.parquet` through `bronze/crime/2026.parquet`
- `bronze/crime/manifest.parquet`
- `bronze/crime/refresh_log.parquet`
- `silver/crime/crime_with_geography/2006.parquet` through `2026.parquet`
- `silver/geography/*`
- `reference/dataset_catalog.parquet`
- `reference/chicago/*`
- `review/*`
- `catalog/*`
- `gold/*`

Do not assume a dataset is present merely because it is on this list. Inventory the actual source and report what exists.

## Scope Lock

This task is limited to:

1. locating the actual application data directory;
2. inventorying and validating it;
3. creating a staging copy;
4. normalizing staging permissions;
5. building a portable archive;
6. locally extracting and verifying it;
7. creating reusable build and verification scripts;
8. documenting exact Render deployment steps.

Do not redesign deployment architecture.

Do not investigate cloud-storage alternatives.

Do not refactor unrelated application code.

Do not review unrelated tests or features.

Put nonessential findings under:

`Deferred — not required for this release`

Do not implement deferred items.

## Anti-Audit-Loop Execution Rule

Use this sequence:

1. Inspect once.
2. Record findings.
3. Execute.
4. Verify once.
5. Stop.

Treat verified facts as settled.

Do not repeatedly search for alternate data directories after one directory is uniquely confirmed.

Do not repeatedly recount files.

Do not rerun passing checksum comparisons.

Do not restart the entire task because one verification fails.

When a check fails:

1. identify the exact failure;
2. make the smallest targeted correction;
3. rerun only the failed check;
4. continue from the last successful checkpoint.

## Required Work

### Phase 1 — Locate the Source Data Directory

Locate the actual local data directory used by the application.

Determine it from repository code, configuration, environment handling, documentation, and the filesystem.

Do not assume its name.

Inspect only what is necessary to resolve the directory.

Record:

- resolved absolute source path
- configuration evidence supporting that path
- whether `DATA_ROOT`, `APP_DATA_DIR`, or another setting controls it

Stop if the production data directory cannot be uniquely identified.

### Phase 2 — Inventory the Source

Before copying or modifying anything, create a source inventory containing:

- relative path for every file
- file count
- total byte size
- SHA-256 checksum for every file
- Bronze crime years found
- Silver crime-with-geography years found
- missing years between 2006 and 2026
- manifests and refresh logs found
- reference datasets found
- geography datasets found
- contents present under `review/`, `catalog/`, and `gold/`

Expected Bronze and Silver year range:

`2006–2026`, inclusive

Stop if either required year series is incomplete.

Do not alter the source while inventorying it.

### Phase 3 — Check Available Disk Space

Before creating a staging copy, calculate enough free disk space for:

- the complete staging copy
- the compressed archive
- the complete test extraction
- reasonable overhead

Stop with the required and available space if disk space is insufficient.

### Phase 4 — Create the Staging Copy

Create a new, separate staging directory outside the production data tree.

Requirements:

- do not overwrite an existing staging directory silently
- do not alter the source
- copy the complete source tree
- preserve file contents exactly
- preserve all relative paths

Normalize permissions only in staging:

- directories: `0755`
- regular files: `0644`

On Windows, implement portable archive metadata explicitly rather than relying only on NTFS permission behavior.

### Phase 5 — Verify Source Against Staging

Compare source and staging using:

- same relative file list
- same file count
- same total bytes
- same individual file sizes
- same SHA-256 checksum for every file

Stop if any difference exists.

Do not rerun this comparison after it passes unless staging contents are subsequently changed.

### Phase 6 — Build the Archive

Create:

`bw-data-release.tar.gz`

Use safe, portable tar metadata.

The archive root must contain the data folders directly:

- `bronze/`
- `silver/`
- `reference/`
- `catalog/`
- `review/`
- `gold/`

Do not add an unnecessary enclosing directory such as:

- `data-upload/`
- `staging/`
- `bw-data-release/`

Include only folders that exist in the source, but report any expected top-level folder that is absent.

Avoid macOS/BSD metadata such as:

- `SCHILY.fflags`
- AppleDouble files
- `.DS_Store`

Do not include temporary files, the archive itself, verification output, or staging-control files inside the archive.

### Phase 7 — Inspect the Archive

Inspect the archive without extracting it.

Verify:

- directories are stored as `drwxr-xr-x`
- no directory is stored as `dr-xr-xr-x`
- regular files have safe readable permissions
- the archive has no unnecessary nesting
- Bronze years 2006–2026 are present
- Silver years 2006–2026 are present
- manifests are present
- expected reference and geography files are present
- source files remain unchanged
- there are no absolute paths
- there are no parent traversal paths such as `../`
- there are no unexpected metadata entries

If archive verification fails, make one targeted repair and rerun only archive verification.

Stop if it still fails.

### Phase 8 — Full Local Extraction Test

Create a second new, empty temporary directory.

Extract the complete archive into it.

Do not extract over the source or staging directory.

Verify the extraction succeeds without permission errors.

### Phase 9 — Verify Source Against Extracted Data

Compare source and extracted data using:

- same relative file list
- same file count
- same total bytes
- same individual file sizes
- same SHA-256 checksum for every file
- extracted directories writable by their owner
- expected top-level layout
- Bronze years 2006–2026
- Silver years 2006–2026

Stop if any checksum, path, count, size, year, or writability check fails.

### Phase 10 — Create Reusable Repository Scripts

Create or update these files:

- `scripts/build_data_release.py`
- `scripts/verify_data_release.py`
- `scripts/build-release.ps1`
- `scripts/verify-release.ps1`

Requirements:

- safe by default
- clear PowerShell usage
- cross-platform Python where reasonably possible
- refuse to use the production directory as staging or extraction output
- refuse to overwrite source data
- refuse ambiguous paths
- detect insufficient space
- calculate and compare SHA-256 hashes
- validate year coverage
- validate archive paths
- validate archive permissions
- return nonzero exit codes on failure
- produce concise logs
- avoid external downloads
- avoid requiring credentials
- do not invoke ingestion or enrichment

Reuse existing repository utilities when safe and directly relevant. Do not refactor unrelated code.

### Phase 11 — Create Deployment Documentation

Create:

`docs/render-data-deployment.md`

Include:

- resolved local data directory
- exact PowerShell build command
- exact PowerShell verification command
- output archive location
- output archive size
- summary of verification results
- exact Render upload destination
- exact Render extraction command
- required `DATA_ROOT`, `APP_DATA_DIR`, or other setting based on actual code
- exact Render commands to verify files and permissions after extraction
- exact application restart or redeploy step
- rollback guidance that does not delete the original data
- statement that Render must not be changed until local verification passes

Do not invent Render paths or environment variables. Derive them from the repository and the previously established deployment configuration. Clearly flag any item that cannot be determined locally.

## Approved Actions Without Asking

You may perform these actions autonomously:

- inspect relevant repository files
- inspect configuration and environment handling
- inspect the local data tree
- run Python and PowerShell scripts
- create staging and test-extraction directories
- copy files
- calculate SHA-256 hashes
- create, inspect, and extract archives
- create the required scripts
- create the deployment document
- run targeted tests
- run relevant formatting and lint checks
- generate logs and verification reports

Do not ask whether to proceed after each phase.

## Stop Conditions

Stop and provide a concise blocker report if:

1. the production data directory cannot be uniquely identified;
2. Bronze is missing any year from 2006 through 2026;
3. Silver is missing any year from 2006 through 2026;
4. source-to-staging checksums differ;
5. source-to-extraction checksums differ;
6. archive paths or permissions remain invalid after one targeted repair;
7. disk space is insufficient;
8. a required step would modify or delete production data;
9. a destructive Git command is required;
10. required credentials are unavailable;
11. an essential deployment path or environment setting cannot be determined safely.

Otherwise continue automatically.

## Completion Criteria

Do not declare completion until all of these are true:

- source data directory uniquely resolved
- Bronze 2006–2026 confirmed
- Silver 2006–2026 confirmed
- staging copy verified byte-for-byte
- archive created
- archive permissions verified
- archive layout verified
- clean local extraction completed
- extracted data verified byte-for-byte
- extracted directories verified writable
- reusable scripts created
- deployment documentation created
- no production source file changed

## Final Report

When finished, show:

1. the production data directory found;
2. configuration evidence used to identify it;
3. source file count and total size;
4. Bronze years found;
5. Silver years found;
6. reference and geography datasets found;
7. whether source-to-staging checksums passed;
8. whether source-to-extraction checksums passed;
9. archive path;
10. archive size;
11. scripts created or modified;
12. documentation created;
13. the exact next PowerShell command the user should run;
14. anything that still requires a user decision;
15. deferred items not implemented.

Then stop.

Do not upload anything and do not change Render.
