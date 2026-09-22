# Render Data Deployment — versioned release roots

How the runtime data gets from a verified local `data/` tree onto the Render persistent disk,
and how the API is switched from one dataset to the next without a moment in which it can
read a half-replaced tree. The data is never in Git and never in a build artifact; it travels
out of band as the archive built by `scripts/build_data_release.py`.

**Nothing on Render changes until the local verification passes, and the live dataset is
never modified in place — a release is activated by switching a pointer, and the previous
release stays on disk until it is deliberately retired.**

## The Render service (verified by the owner in the dashboard and over SSH, 2026-09-21)

| Item | Value |
| --- | --- |
| Service | `neighborhood-intelligence-platform`, region Virginia (US East) |
| Compute | Standard — 1 CPU, 2 GB RAM |
| Persistent disk | 10 GB at `/var/data` (9.8 G total, 8.3 G free on 2026-09-21) |
| Deploy source | branch `main`, **Auto-Deploy OFF** (a merge deploys nothing; deploys are started by hand) |
| Live commit | `502c351` (V1) |
| Start command | `uv run --no-dev uvicorn bw_observatory.api.app:app --host 0.0.0.0 --port $PORT` |
| Pre-deploy command | blank |
| Shell access | Connect → SSH; key-based, verified working non-interactively from the owner's machine; `scp` to `/var/data` worked for the July upload |
| On the box | user `render`, checkout `/opt/render/project/src` (a git checkout), uv 0.10.2, Python 3.13.5 |

Because the service starts through `uv`, every command below that runs project code on the
box is `uv run --no-dev python -m …` from `/opt/render/project/src`.

**A service with a persistent disk cannot be zero-downtime deployed:** Render stops the
instance, then starts the new one with the disk attached. Every deploy and every
environment-variable save that triggers a deploy is a brief public outage (typically one to
three minutes). The data steps below never restart the service; only the code deploy and
env-var changes do.

## What the API reads

The backend resolves its data root from `BW_DATA_DIR` (falling back to `DATA_DIR`) and reads,
relative to that root, per request:

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

Production is **already versioned**: the July dataset lives in its own directory and
`BW_DATA_DIR` points straight at it. The V2 layout keeps that directory exactly where it is
and adds a pointer beside it:

```
/var/data/
  bw-release-20260726/      the July dataset production runs today — untouched, the rollback target
  bw-release-20260921/      the next dataset, staged and verified before it is current
  current -> bw-release-20260921        a symlink; the ONLY thing a switch changes
  incoming/                 archives + .sha256 sidecars as transferred (kept until retired)
  bw-live/ data-upload/ extracted/ silver/ *.tar.gz      July leftovers (~0.9 GB); not live, not used
```

`current` sits in `/var/data` next to the release directories, and every symlink target below
is written **relative to `/var/data`** (`bw-release-…`, no path prefix). A relative symlink
target is resolved from the directory that contains the link, so `/var/data/current ->
bw-release-20260921` means `/var/data/bw-release-20260921`. Never write a target such as
`releases/…` or `../…` here — there is no `releases/` directory.

`BW_DATA_DIR=/var/data/current`. `Settings` resolves that path once when it is built — per
API request, per CLI run — so a request never reads Silver from one release and Bronze from
another if the pointer moves mid-request, and a refresh run is pinned to the release that
was current when it started (`config.py`, `_pin_data_root`; `tests/test_config.py`). The
refresh scheduler, when enabled, therefore writes into whichever release is current.

## Build and verify locally (PowerShell)

```powershell
# One archive per release, named for the day it was cut. Refuses to overwrite an existing
# archive (the previous release's) unless --overwrite is given. Verifies staging checksums,
# archive permissions, clean extraction, extracted-vs-source SHA-256, and writes a
# <archive>.sha256 sidecar (LF line ending, `sha256sum -c` format) for the far side.
# Exits non-zero on any failure.
uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz

# Re-verify an existing archive without rebuilding it (also rewrites the sidecar).
uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz --verify-only

# Prove the local tree itself before cutting it: every year present, ids unique and identical
# across Bronze/Silver, manifest rows + checksums match, no id in two years, quality file.
uv run python -m bw_observatory.ops.verify_data_root
```

Staging and the test extraction live under `%TEMP%\bw-data-release\`, outside the repository,
so they never churn Git or OneDrive. The source `data/` tree is never modified. Archives are
untracked and must never be staged (`git status` will list them; leave them).

Release cut 2026-09-21: `bw-data-release-2026-09-21.tar.gz`, 549,011,035 bytes (523.58 MiB),
SHA-256 `e1eba8285f1dde8acd857e18f9f2cad2aaddd46af1f050a7f6d53313f2939b33`, data through
2026-09-06, source watermark 2026-09-13T15:54:07.

## Transfer

Plain `scp` over the service's SSH works (that is how the July archive arrived). Copy the
archive and its sidecar into `/var/data/incoming/` on the **persistent disk** (not `/tmp`,
which does not survive a restart):

```bash
# on the laptop; <srv> is the service id from Connect → SSH
ssh <srv>@ssh.virginia.render.com 'mkdir -p /var/data/incoming && df -h /var/data'
scp bw-data-release-2026-09-21.tar.gz bw-data-release-2026-09-21.tar.gz.sha256 \
    <srv>@ssh.virginia.render.com:/var/data/incoming/
```

Then, in the SSH session, prove the copy before touching anything else:

```bash
cd /var/data/incoming && sha256sum -c bw-data-release-2026-09-21.tar.gz.sha256   # expect: OK
```

## Stage and verify the release (live dataset untouched)

```bash
mkdir -p /var/data/bw-release-20260921
tar -xzf /var/data/incoming/bw-data-release-2026-09-21.tar.gz -C /var/data/bw-release-20260921
ls /var/data/bw-release-20260921                                   # bronze silver reference …

# Shape check, possible before V2 code is on the box:
find /var/data/bw-release-20260921 -type f | wc -l        # expect 64
du -sm /var/data/bw-release-20260921                        # expect ≈ 678 MiB

# Full consistency proof — streams, bounded memory, read-only. Needs the V2 checkout on the
# box (the verifier ships with V2), so this runs after the V2 backend deploy:
cd /opt/render/project/src
uv run --no-dev python -m bw_observatory.ops.verify_data_root --data-dir /var/data/bw-release-20260921
# expect: RESULT: PASS, and the Freshness line's data_through / source_watermark equal the
# values the local run printed before the archive was cut.
```

If this prints anything but PASS, stop: remove `/var/data/bw-release-20260921` and start
again. Production has not been affected.

## Initial pointer (once, before the V2 deploy)

The July root stays where it is. Create the pointer beside it, aimed at July, while the V1
API still reads `BW_DATA_DIR=/var/data/bw-release-20260726` directly — the running service
does not notice:

```bash
cd /var/data
ln -s bw-release-20260726 current
readlink current                                    # bw-release-20260726
ls current/bronze/crime/manifest.parquet            # resolves through the link
```

Then set `BW_DATA_DIR=/var/data/current` in the Render environment together with the V2
backend deploy (Auto-Deploy is off: save the variable, then "Deploy latest commit" by hand —
one outage rather than two, if the UI lets the save wait for the deploy). The V2 API now
serves the same July bytes through the symlink; verify `/api/v1/health`, `/api/v1/years`,
`/api/v1/geographies`, and one data endpoint before continuing.

Once V2 code is on the box, `verify_data_root` on the July root is expected to report one
known point — `2024: 18 Bronze id(s) with no Silver row` (the drift the 2026-07-26 Bronze
restore left, repaired locally by V2-004). That is its pre-existing state, not damage.

## Switch (atomic) and rollback

A symlink is replaced atomically by renaming a new one over it; `ln -sfn` is **not** atomic
(it unlinks, then creates). Every request pins its root when it starts, so no request ever
mixes two releases. Both commands are run from `/var/data` so the relative targets are
unambiguous; the mechanism was exercised on Linux (rename over a symlink leaves no
`current.next` behind and rollback is symmetric).

```bash
cd /var/data

# activate
ln -s bw-release-20260921 current.next && mv -T current.next current
readlink current                                    # bw-release-20260921
cd /opt/render/project/src && uv run --no-dev python -m bw_observatory.ops.verify_data_root   # the live root

# rollback — identical mechanism, previous target
cd /var/data
ln -s bw-release-20260726 current.next && mv -T current.next current
readlink current                                    # bw-release-20260726
```

No restart is needed for either direction. The refresh scheduler must be **off** (or its lock
absent: `ls /var/data/current/bronze/crime/refresh.lock` shows nothing) at the moment of a
switch, so that no writer is mid-run in the release being left.

After the switch, confirm end to end through the public path (no data host leaked):

```bash
curl -s "$PUBLIC/api/v1/health"                  # {"status":"ok"}
curl -s "$PUBLIC/api/v1/years"                   # 21 years, latest 2026
curl -s "$PUBLIC/api/v1/freshness"               # data_through 2026-09-06 (for the 2026-09-21 release)
curl -s "$PUBLIC/api/v1/pulse/ward20?year=2025"  # 7813 incidents
```

`bronze_integrity_verified` in the overview payload SHA-256s each Bronze file against the
manifest that ships inside the release; it must read `true`.

## Retiring a release

Only after the new release has served traffic and been verified, and only with explicit
approval: `rm -rf /var/data/bw-release-<old>` and its archive under `incoming/`. Keep at
least one previous release on disk at all times. The July leftovers (`bw-live/`,
`data-upload/`, `extracted/`, `silver/`, the two July tarballs, ≈ 0.9 GB) are likewise the
owner's call; nothing reads them.

Disk budget (10 GB disk, 8.3 GB free before this release): July root ≈ 0.58 GB (already in
use) + archive ≈ 0.52 GB under `incoming/` + extracted release ≈ 0.68 GB + refresh staging
headroom ≈ 0.1 GB (one year's Bronze+Silver, staged beside the live files) ≈ **1.3 GB of new
use**. Minimum free space to start: **≥ 1.5 GB** (`df -h /var/data` before the transfer).
Verification adds nothing: it reads.

## Items to confirm before any of this runs on Render

- **Free space**: `df -h /var/data` ≥ 1.5 GB (8.3 GB on 2026-09-21).
- **The scheduler is off** (`BW_REFRESH_SCHEDULE` unset) until the release switch is done.
- `review/` (block-level CSV for local review, ≈ 0.3 MB) ships with the archive; exclude it
  before transfer if it should not be on the disk.
