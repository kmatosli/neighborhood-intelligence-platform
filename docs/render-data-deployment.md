# Render Data Deployment — versioned release roots

How the runtime data gets from a verified local `data/` tree onto the Render persistent disk,
and how the API is switched from one dataset to the next without a moment in which it can
read a half-replaced tree. The data is never in Git and never in a build artifact; it travels
out of band as the archive built by `scripts/build_data_release.py`.

**Nothing on Render changes until the local verification passes, and the live dataset is
never modified in place — a release is activated by switching a pointer, and the previous
release stays on disk until it is deliberately retired.**

## The Render service (verified by the owner in the dashboard, 2026-09-21)

| Item | Value |
| --- | --- |
| Service | `neighborhood-intelligence-platform`, region Virginia (US East) |
| Compute | Standard — 1 CPU, 2 GB RAM |
| Persistent disk | 10 GB at `/var/data` |
| Deploy source | branch `main`, **Auto-Deploy OFF** (a merge deploys nothing; deploys are started by hand) |
| Live commit | `502c351` (V1) |
| Start command | `uv run --no-dev uvicorn bw_observatory.api.app:app --host 0.0.0.0 --port $PORT` |
| Pre-deploy command | blank |
| Shell access | Connect → SSH (key-based; prove it works before relying on it, see Transfer) |

Because the service starts through `uv`, every command below that runs project code on the
box is `uv run --no-dev python -m …` from the deployed checkout (Render's default is
`/opt/render/project/src`; confirm with `pwd` in the SSH session).

**A service with a persistent disk cannot be zero-downtime deployed:** Render stops the
instance, then starts the new one with the disk attached. Every deploy and every
environment-variable save that triggers a deploy is a brief public outage (typically one to
three minutes). The data steps below never restart the service; only the code deploy and
env-var changes do.

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

`BW_DATA_DIR=/var/data/current`. `Settings` resolves that path once when it is built — per
API request, per CLI run — so a request never reads Silver from one release and Bronze from
another if the pointer moves mid-request, and a refresh run is pinned to the release that
was current when it started (`config.py`, `_pin_data_root`; `tests/test_config.py`).

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
# Needs the V2 checkout on the box (the verifier ships with V2), so this runs after the
# V2 backend deploy; until then, check the extraction by shape only:
find /var/data/releases/2026-09-21 -type f | wc -l        # expect 64
du -sm /var/data/releases/2026-09-21                        # expect ≈ 678 MiB
cd /opt/render/project/src   # the deployed checkout (confirm with pwd)
uv run --no-dev python -m bw_observatory.ops.verify_data_root --data-dir /var/data/releases/2026-09-21
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
ls /var/data/releases/2026-07-26-v1                      # bronze silver …
ln -s releases/2026-07-26-v1 /var/data/current
```

The July root is expected to fail `verify_data_root` on one known point once V2 code is on
the box — `2024: 18 Bronze id(s) with no Silver row` (the drift the 2026-07-26 Bronze
restore left, repaired locally by V2-004). That is its pre-existing state, not damage.

Then set `BW_DATA_DIR=/var/data/current` in the Render environment together with the V2
backend deploy (one outage instead of two; Auto-Deploy is off, so save the variable and
then "Deploy latest commit" by hand). The API now serves the same July bytes through the
symlink; verify `/api/v1/health`, `/api/v1/years`, and one data endpoint before continuing. The flat top-level folders are now
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
uv run --no-dev python -m bw_observatory.ops.verify_data_root   # the live root (BW_DATA_DIR)

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
one previous release on disk at all times.

Disk budget (10 GB disk): July flat layout ≈ 0.44 GB (its hard-linked release copy costs
nothing extra) + archive ≈ 0.5 GB under `incoming/` + extracted release ≈ 0.68 GB +
refresh staging headroom ≈ 0.1 GB (one year's Bronze+Silver, staged beside the live files)
≈ **1.75 GB in use** with both releases retained. Minimum free space to start:
**≥ 1.5 GB** (`df -h /var/data` before the transfer). Verification adds nothing: it reads.

## Items to confirm before any of this runs on Render

- **SSH actually authenticates** (a public key must be registered on the Render account;
  the dashboard shows the command regardless): `ssh <srv>@ssh.virginia.render.com 'echo ok'`,
  then a 1-byte `scp` into `/var/data/incoming/` before the real transfer.
- **Where the deployed checkout lives** on the instance (`pwd` in the SSH session).
- **Free space**: `df -h /var/data` ≥ 1.5 GB.
- `review/` (block-level CSV for local review, ≈ 0.3 MB) ships with the archive; exclude it
  before transfer if it should not be on the disk.
