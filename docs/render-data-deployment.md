# Render Data Deployment — versioned release roots

How the runtime data gets from a verified local `data/` tree onto the Render persistent disk,
and how the API is switched from one dataset to the next without a moment in which it can
read a half-replaced tree. The data is never in Git and never in a build artifact; it travels
out of band as the archive built by `scripts/build_data_release.py`.

**Nothing on Render changes until the local verification passes, and the live dataset is
never modified in place — a release is activated by switching a pointer, and the previous
release stays on disk until it is deliberately retired.**

## What the API reads

The backend resolves its data root from `BW_DATA_DIR` (falling back to `DATA_DIR`) and reads,
relative to that root, per request (nothing is cached across requests, and the root is not
resolved at start-up, so a change to what the root points at is visible immediately):

- `bronze/crime/<year>.parquet` (2006–newest), `bronze/crime/manifest.parquet`, and the run
  bookkeeping (`refresh_log`, `incremental_refresh_log`, `reconciliation_log`)
- `silver/crime/crime_with_geography/<year>.parquet` (2006–newest), with the
  `source_status` columns written by reconciliation
- `silver/geography/geography_quality.parquet`
- `reference/` (boundary sources; not read by the API but needed by any enrichment on the box)

The archive root contains `bronze/`, `silver/`, `reference/`, `catalog/`, `review/`, `gold/`
directly (no enclosing folder), so extracting it into a release directory yields exactly those
paths under that directory.

## Layout on the disk

```
/var/data/
  releases/
    2026-07-26-v1/          the July dataset production runs today (bronze/, silver/, …)
    2026-09-21/             the next dataset, staged and verified before it is current
  current -> releases/2026-09-21          a symlink; the ONLY thing the switch changes
  incoming/                 archives + .sha256 sidecars as transferred (kept until retired)
```

`BW_DATA_DIR=/var/data/current`. The refresh scheduler, when enabled, writes through the same
symlink, so a daily refresh always lands in the release that is current.

The one-time migration from the flat July layout (`/var/data/bronze` …) to this layout is in
"First-time migration" below; it is done with hard links so the live API never sees a missing
folder.

## Build and verify locally (PowerShell)

```powershell
# One archive per release, named for the day it was cut. Refuses to overwrite an existing
# archive (the previous release's) unless --overwrite is given. Verifies staging checksums,
# archive permissions, clean extraction, extracted-vs-source SHA-256, and writes a
# <archive>.sha256 sidecar for the far side. Exits non-zero on any failure.
uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz

# Re-verify an existing archive without rebuilding it.
uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz --verify-only

# Prove the local tree itself before cutting it: every year present, ids unique and identical
# across Bronze/Silver, manifest rows + checksums match, no id in two years, quality file.
uv run python -m bw_observatory.ops.verify_data_root
```

Staging and the test extraction live under `%TEMP%\bw-data-release\`, outside the repository,
so they never churn Git or OneDrive. The source `data/` tree is never modified. Archives are
untracked and must never be staged (`git status` will list them; leave them).

## Transfer

The transfer mechanism depends on the Render plan and is not recorded in this repo. Paid
Render services expose SSH; `scp` the archive and its sidecar into `/var/data/incoming/` on the
**persistent disk** (not `/tmp`, which does not survive a restart):

```bash
# on the laptop
scp bw-data-release-2026-09-21.tar.gz bw-data-release-2026-09-21.tar.gz.sha256 \
    <service-ssh-host>:/var/data/incoming/
```

Then, in the service Shell, prove the copy before touching anything else:

```bash
cd /var/data/incoming && sha256sum -c bw-data-release-2026-09-21.tar.gz.sha256   # expect: OK
```

## Stage and verify the release (live dataset untouched)

```bash
mkdir -p /var/data/releases/2026-09-21
tar -xzf /var/data/incoming/bw-data-release-2026-09-21.tar.gz -C /var/data/releases/2026-09-21
ls /var/data/releases/2026-09-21                                   # bronze silver reference …

# Full consistency proof of the staged root — streams, bounded memory, read-only.
cd /opt/render/project/src   # the deployed checkout; wherever `bw_observatory` imports from
python -m bw_observatory.ops.verify_data_root --data-dir /var/data/releases/2026-09-21
# expect: RESULT: PASS, and the Freshness line's data_through / source_watermark equal the
# values the local run printed before the archive was cut.
```

If this prints anything but PASS, stop: remove `/var/data/releases/2026-09-21` and start again.
Production has not been affected.

## First-time migration (July flat layout → release roots)

Done once, while the API still has `BW_DATA_DIR=/var/data`. Hard links (`cp -al`) make the
release copy instantly and without extra space, and the original folders stay in place, so the
running API never sees a missing file.

```bash
mkdir -p /var/data/releases/2026-07-26-v1
for d in bronze silver reference catalog review gold; do
  [ -d "/var/data/$d" ] && cp -al "/var/data/$d" "/var/data/releases/2026-07-26-v1/$d"
done
python -m bw_observatory.ops.verify_data_root --data-dir /var/data/releases/2026-07-26-v1
ln -s releases/2026-07-26-v1 /var/data/current
```

Then set `BW_DATA_DIR=/var/data/current` in the Render environment (this restarts the
service). The API now serves the same July bytes through the symlink; verify `/api/v1/health`,
`/api/v1/years`, and one data endpoint before continuing. The flat top-level folders are now
redundant hard links; leave them until the new release has been live and verified, then
remove only them (`rm -rf /var/data/bronze …` removes links, not the release's files).

## Switch (atomic) and rollback

A symlink is replaced atomically by renaming a new one over it; `ln -sfn` is **not** atomic
(it unlinks, then creates). Every request opens its files after the rename, so no request
ever mixes two releases except one already in flight across the instant of the switch.

```bash
# activate
ln -s releases/2026-09-21 /var/data/current.next && mv -T /var/data/current.next /var/data/current
readlink /var/data/current                     # releases/2026-09-21
python -m bw_observatory.ops.verify_data_root  # against the live root (BW_DATA_DIR)

# rollback — identical mechanism, previous target
ln -s releases/2026-07-26-v1 /var/data/current.next && mv -T /var/data/current.next /var/data/current
```

No restart is needed for either direction. The refresh scheduler must be **off** (or its lock
absent: `ls /var/data/current/bronze/crime/refresh.lock` shows nothing) at the moment of a
switch, so that no writer is mid-run in the release being left.

After the switch, confirm end to end through the public path (no data host leaked):

```bash
curl -s "$RENDER_EXTERNAL_URL/api/v1/health"                  # {"status":"ok"}
curl -s "$RENDER_EXTERNAL_URL/api/v1/years"                   # 21 years, latest 2026
curl -s "$RENDER_EXTERNAL_URL/api/v1/freshness"               # data_through 2026-09-06 (for the 2026-09-21 release)
curl -s "$RENDER_EXTERNAL_URL/api/v1/pulse/ward20?year=2025"  # 7813 incidents
```

`bronze_integrity_verified` in the overview payload SHA-256s each Bronze file against the
manifest that ships inside the release; it must read `true`.

## Retiring a release

Only after the new release has served traffic and been verified, and only with explicit
approval: `rm -rf /var/data/releases/<old>` and its archive under `incoming/`. Keep at least
one previous release on disk at all times. Disk budget (5 GB): July ≈ 0.44 GB, this release
≈ 0.68 GB extracted + ≈ 0.5 GB archive.

## Items to confirm before any of this runs on Render

- **SSH / transfer path** for this service (plan-dependent; not recorded here).
- **Where the deployed checkout lives** on the instance, for `python -m bw_observatory…`
  (the `cd` above is Render's usual path; confirm in the Shell with `pwd`).
- **Instance size** before enabling `BW_REFRESH_SCHEDULE` — see
  `methodology/CRIME_DATA_OPERATING_MODEL.md`, "Production scheduling".
- `review/` (block-level CSV for local review, ≈ 0.3 MB) ships with the archive; exclude it
  before transfer if it should not be on the disk.
