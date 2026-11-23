# Production catch-up plan — 2026-10-27

**Status: PLAN ONLY. Nothing in this document has been executed.** Every step that changes
Render, Vercel, the persistent disk, `/var/data/current`, or an environment variable needs the
owner's explicit approval at that step (CLAUDE.md §6, §14). Mechanisms are the ones already
documented in `render-data-deployment.md` and `methodology/CRIME_DATA_OPERATING_MODEL.md`; this
plan sequences them and does not introduce new ones.

Evidence labels: **VERIFIED** (observed today) · **INFERRED** (strong indirect evidence) ·
**NOT VERIFIED** · **BLOCKED**.

---

## 0. Production release root (Part 1)

**`BLOCKED — RENDER SSH ACCESS REQUIRED`.** The service's SSH address (`srv-…@ssh.virginia.render.com`,
dashboard → Connect → SSH) is not recorded in the repository, and Render has no API key or CLI on
this machine. A Render host key is present in `~/.ssh/known_hosts`, so key-based SSH has worked
from this machine before.

| Item | Status | Evidence available today |
|---|---|---|
| `/var/data/current` target | **INFERRED** `bw-release-20260921` | Catalogue baseline line, 2026-09-22: "`current` → `bw-release-20260921`". Live `/freshness` (2026-10-27): `data_through 2026-09-06`, `source_watermark 2026-09-13T15:54:07`, exactly the 2026-09-21 cut record (`render-data-deployment.md` §Build). |
| Release directory name | INFERRED as above | The `/findings` endpoint, which reports it, is not deployed. |
| Release manifest / checksums | **NOT VERIFIED** on the box | Local archive `bw-data-release-2026-09-21.tar.gz`, SHA-256 `e1eba828…2939b33` per the runbook; local manifest `dataset_last_updated 2026-09-14T10:56:44Z`. |
| Crime data-through | **VERIFIED** `2026-09-06` | Live `/freshness`. |
| Bronze / Silver rows by recent year | **NOT VERIFIED** on the box | Local copy, same refresh run: Bronze/Silver 2024 259,621 · 2025 238,091 · 2026 157,987 (citywide, all rows incl. `source_removed`). Live `/pulse/ward20?year=2025` = 7,817; `/pulse/ward20?year=2026` = 5,333 through 09-06. |
| September release immutable? | **INFERRED** unchanged since cut | No refresh since 2026-09-15 03:10 and no reconciliation since 03:29:13.820879 (live `/freshness`), both before the 2026-09-21 cut. Nothing makes it *read-only*; the scheduler, if enabled, would write into it (operating model §Production scheduling). |
| `BW_DATA_DIR=/var/data/current` | INFERRED | Catalogue baseline 2026-09-22. |
| `BW_REFRESH_SCHEDULE` unset | **INFERRED** | 1,024 h without a refresh while the code runs a catch-up within 2 min of any start if it is set. |
| Render Auto-Deploy OFF | **INFERRED** | Runbook (owner-verified 2026-09-21); PR #3 merged to `main` 2026-09-23 and production still serves pre-PR #3 code (`/findings` 404, no `measurement` in `/pulse`). |
| Vercel not Git-auto-deploying `main` | **INFERRED** | Latest production deployment `dpl_DS3WWrQX6GjxybCm4jbFKaSMSUhG`, 2026-09-22 21:04 UTC, 6 s CLI build; two later merges to `main` created no deployment. The project's Git-link field could not be read from the CLI. |

**Read-only commands to run once SSH is available** (`<srv>` from the dashboard):

```bash
ssh <srv>@ssh.virginia.render.com '
  cd /var/data && readlink current && ls -la && df -h /var/data
  env | grep -E "^(BW_|DATA_DIR)" ; echo "schedule=${BW_REFRESH_SCHEDULE:-UNSET}"
  cd /opt/render/project/src && git rev-parse HEAD
  ls current/bronze/crime/refresh.lock 2>/dev/null || echo "no lock"
  sha256sum incoming/*.tar.gz 2>/dev/null; cat incoming/*.sha256 2>/dev/null
  uv run --no-dev python -m bw_observatory.ops.verify_data_root --data-dir /var/data/current
'
```

`verify_data_root` exists only in V2+ code (it is in `e00665c`); it is read-only and streams.
Expected: `current -> bw-release-20260921`, `schedule=UNSET`, `RESULT: PASS`. **Any other
answer stops every production step below** until it is explained.

---

## 1. PR #3 coordinated code deployment (Part 4)

**EXECUTION GATE: verify active Render release before production action.**

| Item | Value |
|---|---|
| Commit to deploy | **`566c981`** (`origin/main`, merge of PR #3). Contains V2-006 (`a8be4a5`), the design record (`f4b3539`), V2-007 Brief (`48a050f`, `81ef908`) and `7a850ce`. **Contains no 311 code.** PR #4 must stay unmerged until this deployment is accepted, or the deploy must name `566c981` explicitly. |
| Current backend | **INFERRED `e00665c`** (catalogue baseline 2026-09-22; endpoint evidence today). Confirm with `git rev-parse HEAD` on the box. |
| Current frontend | Vercel `dpl_DS3WWrQX6GjxybCm4jbFKaSMSUhG` → `https://bronzeville-woodlawn-observatory-oz7emjrch-kmatoslis-projects.vercel.app`, aliased to `bronzeville-woodlawn-observatory.vercel.app`. |
| Data | The September release stays active. No env-var change, no pointer change. |

**API compatibility with the September release.** PR #3 code reads only what that release
already has: Silver mismatch flags and `source_status` (measurement notes), Bronze/Silver for
the brief, `config/` from Git. The previous session rendered both V2-006 and V2-007 against this
same release (PROJECT_STATUS V2-006/V2-007 test notes). All new response fields are additive, so
the **old frontend keeps working against the new backend**, but the **new frontend cannot run
against the old backend** (the Brief calls `/api/v1/findings`). The order is therefore backend
first, frontend second.

### Backend (Render), one outage of about 1–3 min

1. `git ls-remote origin main` → `566c981…` (the commit Render will pull).
2. Dashboard → Manual Deploy → **Deploy a specific commit → `566c981`** (or "latest commit" only
   if step 1 matched and PR #4 is still unmerged).
3. Watch the deploy log reach "Live"; the start command is unchanged.

### Backend acceptance (public Render origin, before touching Vercel)

| Check | Expected |
|---|---|
| `/api/v1/health` | `{"status":"ok"}` |
| `/api/v1/years` | 21 years, `latest: 2026` |
| `/api/v1/freshness` | unchanged from today: `data_through 2026-09-06`, `status stale` (correctly stale; the code deploy does not fix data) |
| `/api/v1/pulse/ward20?year=2025` | 7,817 incidents; payload now has `measurement` (beat 885, ward 248, community area 683 per V2-006 notes); `beats[]` rows carry `whole_beat_current`, `share_of_beat_inside`, `extends_beyond_geography` |
| Enforcement flag | `category_drivers[]` with `primary_type` PROSTITUTION/NARCOTICS/… carry `enforcement_generated: true`; others `false` |
| `/api/v1/pulse/ward20?year=2026` | `measurement.provisional_period: true` |
| `/api/v1/findings?geo=ward20&year=2025` | 200; `data_release: "bw-release-20260921"` (**this also closes Part 1's release-identity item**); F-001 7,817 vs 8,215 (−398, −4.8%); F-002, F-003, F-010 present; `withheld` and `data_gaps` populated; no `C-00x` (311 drafts are not on `main`) |
| `/api/v1/overview/ward20?year=2025` | 200; `bronze_integrity_verified: true` |
| `/api/v1/pulse/bronzeville`, `/pulse/back-of-the-yards` | 404 |
| `/api/v1/city-services/years` | **404** (proves no 311 shipped) |

### Frontend (Vercel CLI, from a clean checkout of `566c981`)

The working tree carries unrelated drift (`apps/web/package-lock.json`, untracked files), so
build from a separate worktree, not the working tree:

```powershell
git worktree add ..\nip-deploy-566c981 566c981
cd ..\nip-deploy-566c981\apps\web
npm ci
vercel pull --yes --environment=production      # brings API_ORIGIN (build-time) into .vercel/
vercel build --prod
vercel deploy --prebuilt --prod                 # note the new dpl_… id and URL
```

### Frontend acceptance (public site, through the `/api/**` proxy)

- The page loads with no console errors; the network shows only relative `/api/...` calls (no Render hostname).
- The freshness banner shows "stale" and data through 6 Sep 2026.
- The Neighborhood Intelligence Brief renders for Ward 20 2025 with the −4.8% finding, its
  classification label, release `bw-release-20260921`, and working deep links (`geo`/`year` kept).
- The measurement strip is visible; drivers show the enforcement-led label; all 28 types and all
  beats are reachable through "Show all"; beat rows show whole-beat context.
- The 2026 view shows the provisional label. The Woodlawn portion shows the "not a safety ranking" note.
- Mobile width (≈390 px) and desktop both render (headless Chrome method, as in V2 verification).
- The Trends page still shows its placeholders and **no** City Services panel (311 is not on `main`).

### Rollback

- **Backend:** Render → Manual Deploy → specific commit **`e00665c`** (the INFERRED current
  commit; use whatever `git rev-parse HEAD` printed in §0). Another brief outage. The data is untouched.
- **Frontend:** `vercel promote https://bronzeville-woodlawn-observatory-oz7emjrch-kmatoslis-projects.vercel.app`
  (or `vercel rollback dpl_DS3WWrQX6GjxybCm4jbFKaSMSUhG`). This is instant and needs no build.
- **Order:** roll back the frontend first (an old frontend is safe on either backend), then the backend.

---

## 2. Crime refresh and reconciliation (Part 5)

**EXECUTION GATE: verify active Render release before production action.** The September
release is never modified: every write goes into a new root.

### What is already explained (VERIFIED locally; INFERRED identical in production)

The drift `/freshness` reports (2025 −42, 2026 −149, and −1/−1/−2/−2/−7/−6 for 2017, 2018,
2021–2024) is the refresh of 2026-09-15 03:09 counting *all* local rows against the source. The
reconciliation of 03:12 (`run_id f79e368f…`) then marked exactly those rows `source_removed`:
1 + 1 + 2 + 2 + 7 + 6 + 42 + 149 = **210**, with `missing_locally 0` and nothing deleted. Silver
confirms 210 `source_removed` rows. **Five are Ward 20** (2024: 1, 2025: 1, 2026: 3), and every
published figure already excludes them (`current_source_view`). Production's
`last_reconciliation.end_time` (`03:29:13.820879`) is byte-identical to the local log.

So this drift is **explained, not unresolved**. `/freshness` did not net out rows already marked
removed, so the same negative numbers would reappear after every refresh. Owner decision 16
corrects the semantics (Crime Sprint 1, commit `fix(freshness)`): `/freshness` reports the raw
source/local difference, the recognized source removals, and **`unexplained_reconciliation_drift`
= `source − (local − recognized source_removed)`**, the integrity signal. **Acceptance requires
it to be 0 for every year.**

**Gap found:** 2010 has never been id-reconciled; it is in neither 2026-09-15 run. Only its row
count was compared. The full reconciliation below includes it.

### Execution path (recommended: the local path, which was proven in September)

The 2026-09-21 release was produced this way. The alternative of refreshing on the box into a
copied root has never been run in production. **Risk:** Windows Application Control blocks
`pyogrio` on this machine (V2 checkpoint memory). Enrichment of changed rows reads the boundary
files through geopandas, so the real refresh may fail at enrichment even if the dry run passes.
If it does, use the on-box fallback (step 4b).

| # | Step | Command / action | Acceptance |
|---|---|---|---|
| 1 | Preserve the September snapshot | `uv run python scripts/build_data_release.py --output bw-data-release-2026-09-21.tar.gz --verify-only` | The sidecar matches (`e1eba828…`). This archive is the immutable "before" for revision analysis. |
| 2 | Source metadata | `uv run python scripts/audit_source_readiness.py` (read-only) or the portal's `rowsUpdatedAt` for `ijzp-q8t2` | The source has updated after 2026-09-14T10:56:44Z |
| 3 | Dry run | `uv run python scripts/refresh_crime.py --dry-run` | It reports fetched, inserted, updated, moved partition, missing geography, and touched years. **Expected scale (INFERRED, not a target):** ~6 weeks of daily batches; the 2026-09-14 two-month catch-up fetched 49,981. Touched years: 2026 mostly, with edits back to 2024–2025. |
| 4a | Real refresh (local) | `uv run python scripts/refresh_crime.py` | `status complete`; invariants proved; `rows_missing_geography` = 0 or each one listed; the watermark advanced |
| 4b | *Fallback (on-box)* | On Render: `cp -a /var/data/bw-release-20260921 /var/data/bw-release-YYYYMMDD` (free space ≥ 1.5 GB first), then `BW_DATA_DIR=/var/data/bw-release-YYYYMMDD uv run --no-dev python -m bw_observatory.ops.refresh_crime` | Same as 4a. `current` is untouched, because `Settings` pins the root from the env var. |
| 5 | Full reconciliation, **all 21 years** | PowerShell: `$y = 2006..2026 \| ForEach-Object { "--year"; "$_" }; uv run python scripts/reconcile_crime.py --dry-run @y`, then the same without `--dry-run` (the default scope is only the two newest years plus drift years, which is how 2010 was missed) | It ends with a per-year table |
| 6 | Investigate every non-zero result | For each year: `newly_removed` → **source removal** (expected; kept as provenance); `missing_locally` → **local gap**, re-run the refresh with `--since <earlier updated_on>`, never publish over it; `reappeared` → restored, listed | **Unexplained drift = 0 for every year**, or the release is not cut |
| 7 | Classify what changed between Sep and the new release | Diff by `id` against the step-1 archive: **added** · **removed** (`source_removed`) · **revised** (`primary_type`/`iucr`/`fbi_code`/`arrest`/`domestic`/`date` changed; `rows_moved_partition` = year moved) · **geography changed** (`spatial_ward_current` or `spatial_community_area` changed) | Every Ward 20 count change from Sep to new is fully accounted for by these four classes. The output is retained (it is the first CA-11 revision record). |
| 8 | Silver | Only changed rows are enriched by the refresh. **No full re-enrichment.** The 2024 stub rule no longer applies (2024 was restored before V2), but forced re-enrichment stays out of this plan. | `verify_data_root` → PASS |
| 9 | Ward 20 frame rules | `/pulse` locally for `ward20` and all nine portions; `uv run python scripts/measure_ward_coverage.py` | The ward total does not change if the portion list changes; the portions sum to the ward total; Back of the Yards is unavailable; `bronzeville` is 404; placement is spatial only |
| 10 | Build the release | Write `release.json` (owner decision 11) and build Gold (Crime Sprint 1 builder, which must PASS its Silver reconciliation and, with the September archive as prior, the revision-events invariant); then `uv run python scripts/build_data_release.py --output bw-data-release-YYYY-MM-DD.tar.gz` | The new archive name never overwrites September; the release is self-describing |
| 11 | Checksum | The builder writes the `.sha256` sidecar | `--verify-only` passes |
| 12 | Release verification (local) | `uv run python -m bw_observatory.ops.verify_data_root`; full pytest; local API smoke tests (CLAUDE.md §15, using 2025 **and** the new 2026) | PASS; figures match step 7 |
| 13 | Stage | `scp` the archive and sidecar to `/var/data/incoming/`; `sha256sum -c`; extract to `/var/data/bw-release-YYYYMMDD`; run `verify_data_root --data-dir` on it | OK + PASS; `current` still points to September |
| 14 | Atomic switch | `cd /var/data && ln -s bw-release-YYYYMMDD current.next && mv -T current.next current` | `readlink current` = the new release; scheduler off, no `refresh.lock` |
| 15 | Restart | **Not required by the mechanism.** `Settings` pins the root per request. Skip unless the owner wants a clean process. | n/a |
| 16 | Acceptance | `/freshness` shows the new data-through (≈ source date − 7 days) and status `current` (≤ 48 h since the refresh); `/years`; `/pulse/ward20?year=2025` and `?year=2026` match step 7; `/findings` `data_release` = the new name; `bronze_integrity_verified: true` | All pass |
| 17 | Rollback | `cd /var/data && ln -s bw-release-20260921 current.next && mv -T current.next current` | Instant; no restart; September is unchanged, so rollback is exact |

**Order relative to §1:** deploy PR #3 code **first**, on the September data, so that its
`/findings` exposes `data_release` and the switch can be verified by name. Then switch the data.

---

## 3. Scheduler activation acceptance (Part 6)

**Approved in principle; not executed. EXECUTION GATE: verify active Render release before
production action.**

**Architecture decided (owner decision 13, 2026-10-27): public releases are immutable.** The
existing scheduler runs inside the API process and refreshes **whatever `current` points to, in
place**; that design is **rejected** and the scheduler must not be enabled as it stands. Future
automated publication is copy-on-write: active release → new candidate release (copy) → refresh
candidate → reconcile candidate → rebuild derived products (Gold) → verify → atomic pointer
switch. If candidate verification fails, `current` is unchanged and the candidate never becomes
public. Implementing that pipeline is a separate work package (not Crime Sprint 1);
`BW_REFRESH_SCHEDULE` stays off until it exists and the criteria below pass against it.

Before enabling `BW_REFRESH_SCHEDULE=16:30`, all of the following must hold:

1. One supervised real refresh has completed in production through the same CLI (`ops.refresh_crime`), with `status complete`.
2. One supervised reconciliation has completed, covering all 21 years, with unexplained drift 0.
3. Memory: peak RSS during refresh plus API traffic is under 1.5 GB of the 2 GB Standard instance, measured in the Render metrics graph during step 1 (the 2026-09-15 local measurement was ≈ 1.2 GB worst case).
4. No lock contention: a second refresh started during step 1 exits with code 3, and nothing else holds `refresh.lock` afterwards.
5. No partial state is visible to requests: during step 1, repeated `/pulse` calls return either the old or the new totals, never a mix (per-year atomic swap plus root pinning).
6. `/freshness` moves from `stale` to `current` after step 1, and `last_successful_refresh` equals the run's end time.
7. The release build succeeds on the refreshed root (`build_data_release` plus `verify_data_root` PASS).
8. Rollback has been proven once: switch `current` back to the previous release and forward again, verified by `/findings data_release`.
9. The scheduler runs the copy-on-write candidate pipeline above, using the identical refresh and reconcile CLIs; no scheduler-only data path exists, and nothing writes into `current`.
10. It cannot overlap itself: the lock is shared with manual runs, and the timeout is `BW_REFRESH_TIMEOUT_SECONDS=10800`.
11. Failure is visible: a failed run leaves `/freshness` at `refresh_failed` with `last_run_error`, and the service log shows the `Scheduler:` exit code. Rehearse this once locally, with the network off.
12. A forced candidate failure (for example a failing reconciliation check) leaves `current` and every public figure unchanged.

After enabling it, the service restarts (an env-var save deploys), and the catch-up run fires
about 2 minutes after start if the last success is more than 24 h old. Then require:

- the catch-up run, plus **one observed scheduled 16:30 UTC run**, each logged `complete`
- `/freshness.last_successful_refresh` equal to that run's end time
- `status current`
- `data_through` advanced by the source's daily batch
- reconciliation on `BW_RECONCILE_DAY` observed once in the following month
