# Claude Code Operating Manual — Bronzeville–Woodlawn Observatory

This file is the operating contract for any Claude Code session in this repository.
It OVERRIDES default assistant behavior. Read it fully before your first edit.

Companion reading, required before non-trivial work:

- `README.md` — what the project is and how to run it
- `docs/PROJECT_STATUS.md` — what is built and what is next
- `docs/architecture/ARCHITECTURE.md` — system design and the ADRs behind it
- `docs/methodology/DATA_GOVERNANCE.md` — rules every published number must satisfy

---

## 1. Project identity

> **V2 scope (2026-09-12, supersedes older wording in this file and in V1 docs).**
> The product is exclusively a **Ward 20, Chicago** neighborhood intelligence
> platform. Ward 20 overall is the default geography; residents can also select
> the *portion within Ward 20* of Woodlawn, Washington Park, Englewood, Fuller
> Park and New City. Back of the Yards is listed but pending a validated
> neighborhood boundary (represented through New City). **Bronzeville is not a
> product geography** and must not appear in public copy or application logic.
> Public working identity: **"Ward 20 Neighborhood Intelligence"** (no final
> name chosen — do not invent one). Authority: `config/geographies.yml`,
> `src/bw_observatory/presentation/geography.py`, `apps/web/src/lib/useGeography.ts`,
> `docs/methodology/GEOGRAPHY.md`, ADR-0005. The repository folder and Python
> package keep their historical names on purpose.

The platform ingests City of Chicago crime data, assigns each record to a ward
and community area by point-in-polygon geography, and serves resident-facing
analysis through a read-only API and web UI.

Two components, one repository:

- **Backend** — a Python `src`-layout package `bw_observatory` (hatchling build).
  A FastAPI app at `src/bw_observatory/api/app.py`, import target
  `bw_observatory.api.app:app`. Read-only over the data layer. No write path,
  no refresh endpoint over HTTP.
- **Frontend** — `apps/web`, a TanStack Start + Nitro app built with Vite. Calls
  the backend only through the relative path `/api/...`.

Data follows a medallion layout under `data/`:

- **Bronze** — raw city records, one Parquet file per calendar year, under
  `data/bronze/crime/`. Carries incident attributes (type, date, block, arrest…).
- **Silver** — geography-enriched records under
  `data/silver/crime/crime_with_geography/` plus `data/silver/geography/`.
  Carries the spatial neighborhood assignment.
- **Gold** — reserved; not yet populated.

The API joins Silver (spatial assignment) to Bronze (attributes) on the source
`id`. Both layers are required at request time.

Values that are TRUE about this project and must never be contradicted in output:

- A neighborhood figure is always the **portion inside Ward 20**, never the whole
  community area, unless explicitly labelled otherwise. The 2023 ward map is
  applied to every year and that is disclosed.
- Placement is the point-in-polygon result (`spatial_ward_current`,
  `spatial_community_area`), never the city's reported `ward`/`community_area`.
- A geography without a validated boundary (Back of the Yards) is shown as
  unavailable with its reason; it is never approximated and never a zero.
- `bronzeville` is an **unknown** geography id (404), not a pending one.
- `/overview` still defaults to `year=2024`; `/years` is computed live from disk.

Governance non-negotiables (these predate this manual and remain in force):

- Do not define Bronzeville as one official community area (historical rule;
  Bronzeville is no longer a product geography at all).
- Do not present a whole community area as a Ward 20 neighborhood figure.
- Do not infer causation from correlation.
- Do not attribute crime to nationality or immigration status.
- No number from this repository may be cited as a finding until the pipeline
  that produced it has been validated.

---

## 2. Working style

- Make narrow, reviewable changes. One logical change per edit.
- Prefer one new file plus one small modification over a broad refactor.
- Never delete working functionality to simplify a task.
- Keep scripts thin. Reusable logic belongs under `src/bw_observatory`, not in
  `scripts/`.
- Match the surrounding code: its naming, its comment density, its idioms. This
  codebase favors explanatory comments on non-obvious decisions — follow that.
- Do not refactor unrelated code, reformat outside the edited block, or "clean
  up" files you were not asked to touch.
- Do not touch generated files (`apps/web/src/routeTree.gen.ts`, anything under
  `.output/`, `.vercel/output/`, `dist/`).
- When a task is done, stop. Do not add speculative improvements.

---

## 3. PowerShell-first workflow

The primary shell is **Windows PowerShell 5.1**. A Bash tool exists for POSIX
scripts, but default to PowerShell for anything the user will run.

PowerShell rules that bite in this environment:

- `&&` and `||` are not available. Chain with `;` or `if ($?) { ... }`.
- No ternary, null-coalescing, or null-conditional operators.
- Do not pipe native-exe stderr with `2>&1` — it wraps lines in ErrorRecords and
  flips `$?` to false even on exit 0. stderr is captured for you.
- Multiline strings to native tools: single-quoted here-strings, closing `'@`
  at column 0.
- `head`/`tail`/`which`/`touch` do not exist. Use `Select-Object -First/-Last`,
  `(Get-Command x).Source`, `New-Item -ItemType File`.
- Write files that other tools read with `-Encoding utf8` explicitly.

Canonical commands for this repo (PowerShell):

```powershell
uv sync                                   # install/refresh the Python env
uv run pytest                             # full test suite (currently 152 tests)
uv run ruff check .                       # lint
uv run mypy                               # type check (see section 15 caveat)
uv run uvicorn bw_observatory.api.app:app --host 127.0.0.1 --port 8000   # local API
uv run python scripts/refresh_crime.py --dry-run   # what the crime refresh would change
uv run python scripts/refresh_crime.py             # bring crime Bronze+Silver current (daily path)
uv run python scripts/reconcile_crime.py           # mark source-removed rows (monthly path)
cd apps/web; npm run dev                  # local frontend on :8080
cd apps/web; npm run build                # production frontend build
```

`bun` may not be on PATH even though `apps/web` contains `bun.lock`. `npm` is the
reliable driver. Do not assume `bun`.

---

## 4. Windows-first assumptions

- Absolute paths look like `c:\Users\...`. Prefer forward slashes inside the Bash
  tool; either works, but be consistent within a command.
- The repository lives under a OneDrive-synced path. Two consequences: file locks
  from the sync client are possible, and line-ending churn (LF↔CRLF) is common.
  A file showing as modified in `git status` with an empty content diff is almost
  always CRLF normalization, not a real change — do not "fix" it.
- Git may warn `LF will be replaced by CRLF`. Expected. Not an error.
- Never assume Unix tools (`sha256sum`, `du`, `find`) are the ones the user has;
  give PowerShell equivalents when handing commands to the user, even if you used
  the Bash tool yourself.
- Case-insensitive filesystem: `Woodlawn` and `woodlawn` resolve the same on
  disk, but the API lowercases neighborhood ids itself — do not rely on FS
  behavior for correctness.

---

## 5. Autonomous execution policy

Proceed without asking for these — they are read-only or clearly in-scope:

- Reading and searching any project file
- Inspecting repo structure, configuration, and existing data
- Running tests, type checks, linters, and read-only diagnostics
- Inspecting APIs and local Parquet/CSV/YAML data
- Loading and validating data through approved project commands
- Implementing the current approved milestone
- Fixing defects directly tied to the current milestone
- Editing files required to complete the current approved feature

When working autonomously with nobody to ask, resolve routine ambiguity with the
most conservative interpretation that still returns the requested deliverable.
Do not expand scope to "improve" things nobody requested.

---

## 6. Approval policy

STOP and request approval before:

- Committing, merging, rebasing, resetting, or force-pushing Git history
- Deleting, moving, or renaming files or directories
- Any destructive data or database operation
- Schema-breaking changes
- Adding or removing a major dependency
- Redesigning application architecture
- Changing approved product scope
- Deploying publicly or modifying production infrastructure
- Any change unrelated to the current approved milestone

Do NOT pause merely to confirm the repository, read docs, list files, inspect
data, run focused tests, or do other routine read-only engineering. Asking
permission for read-only work is itself a failure mode (see section 19).

When you do ask, ask once, with a specific decision and a recommended default —
not an open-ended "should I proceed?".

---

## 7. Production data protection rules

The geography-enriched **Silver layer is the application system of record.**
Application code, APIs, charts, and reports read from validated Silver outputs,
not from Bronze source files.

- Do not inspect, rebuild, or modify Bronze unless a specific user-visible defect
  requires it.
- **`data/bronze/crime/2024.parquet` is intentionally a one-row stub.** The
  corresponding Silver 2024 output is intact and usable. Do NOT run forced 2024
  enrichment from the current Bronze file. Restore Bronze 2024 only through the
  approved downloader before any future re-enrichment.
- Raw source data and secrets are never committed. `.gitignore` excludes
  `data/**/*.parquet` (and csv/json/geojson/duckdb). Only `.gitkeep` markers are
  tracked under `data/`.
- The production dataset lives on the Render persistent disk at `/var/data`
  (`BW_DATA_DIR=/var/data`), transferred out of band. It is never in Git and
  never in a build artifact.
- `bronze_integrity_verified` in the Overview payload SHA-256s each whole Bronze
  file against the ingest manifest. It must remain truthful. Never filter,
  truncate, or synthesize Bronze in a way that would make this field lie.

---

## 8. Progress preservation rules

- Never delete or overwrite work — yours or the user's — to make a task simpler.
- Before overwriting or deleting any file you did not create this session, read
  it first. If its content contradicts how the task described it, surface that
  and stop; do not proceed on the assumption. (This manual itself was written by
  folding in the prior `CLAUDE.md`, not by discarding it.)
- Prefer additive edits. When replacing a block, preserve surrounding intent and
  comments.
- Long-running or expensive results (a completed data transfer, an enrichment
  run) are treated as precious. Verify before any action that could invalidate
  them.
- If context is summarized mid-task, resume from the summary; do not restart
  completed work.

---

## 9. Anti-audit-loop rules

This repository has a documented tendency to pull sessions into endless
inspection. Guard against it:

- Do not perform broad audits, repository-wide verification, or unrelated
  inspection while implementing a feature, unless a blocking defect appears.
- Once the project structure is understood, stop re-exploring it. Re-reading the
  same directories across turns is a failure, not diligence.
- Perform only the minimum read-only inspection needed to understand the inputs
  to the current change.
- A read-only command that does not materially reduce risk for the current step
  should not be run. Ask: "what decision does this output change?" If none, skip.
- Investigation is a means to an edit, never a substitute for one. If three
  consecutive actions produced no change and no new decision, you are looping —
  state a conclusion and act.

---

## 10. Scope lock

> **V2 (2026-09-12).** Work proceeds in numbered V2 work packages under the
> owner's V2 execution instructions (see `docs/PROJECT_STATUS.md`, "V2 work
> packages"). V2-001 (shell, canonical year) and V2-002 (Ward 20 geography
> foundation) are complete. The Overview-page milestone text below is the V1
> history of this lock and is retained for context.

The current approved milestone is the **Overview page**. Historical data loading
and geography enrichment are complete for 2006 through 2026. Until Overview meets
its acceptance criteria:

- Do not work on Trends, Beat Meeting, Community Change, or Authority pages.
- Do not return to ingestion or enrichment unless a user-visible defect requires
  it.
- Do not redesign working application structure or refactor unrelated code.

Overview is complete only when:

- Every visible widget uses live API data.
- Every visible control works.
- No fabricated or placeholder values remain.
- Unsupported controls are removed or clearly disabled.
- Data source and data-through information are visible.
- The page is usable on mobile and desktop.

A separately approved task (e.g. deployment) temporarily becomes the active
scope for its duration, under the same discipline: do only that task.

---

## 11. Task tracking

- For any task with more than ~3 steps, maintain a short plan and keep the user
  oriented on which step is active and what remains.
- State the phase you are in and the single next action. One phase at a time.
- When a phase completes, summarize: what changed, what did not change, what
  risks remain, what the next phase accomplishes.
- Never silently jump phases. Never mark a step done that was not verified.
- Convert relative dates to absolute when recording anything durable.

---

## 12. Error recovery

When something fails:

1. **Stop.** Do not retry the same command in a loop hoping for a different
   result.
2. Read the actual error. Name the exact file, line, or resource affected.
3. Diagnose the root cause before proposing a fix. Distinguish app/config errors
   from data errors — e.g. `/api/v1/health` never touches data, so a health
   failure is never a data problem.
4. Propose the smallest fix that addresses the cause. Do not redesign in response
   to a failure.
5. State what failed, why, which file is affected, and the minimal fix. Then wait
   if approval is required.
6. A denied tool call is feedback, not an obstacle to route around. Adjust; do
   not resubmit the same call verbatim.

Report failures honestly. If tests fail, say so and show output. If a step was
skipped, say so. Never report a check as passed when it did not run.

---

## 13. Git rules

- The default integration branch is `main`. Feature work happens on branches
  such as `feature/research-platform`.
- Remote: `kmatosli/neighborhood-intelligence-platform`.
- Never commit, push, merge, rebase, reset, or force-push without explicit
  approval. This is absolute.
- Never commit secrets or raw/downloaded source data. Verify `git status` before
  staging.
- Stage selectively. This working tree often carries unrelated pre-existing
  modifications (`.env.example`, `.gitignore`, lockfiles, generated files). Stage
  only the files that belong to the approved change; never `git add -A` blindly.
- Show `git diff` before any commit, and get approval for the diff.
- Do not skip hooks (`--no-verify`) or bypass signing unless explicitly asked.
- Commit messages end with the required co-author trailer for this environment.

---

## 14. Deployment rules

Approved production architecture (frozen — do not reopen):

- **Frontend:** Vercel, project rooted at `apps/web`. Nitro selects its native
  Vercel preset automatically in the Vercel environment; the Cloudflare output
  seen on a local build is only Nitro's fallback preset, not a configuration.
- **Backend:** FastAPI on a paid Render web service (Ohio, Starter tier),
  branch `main`, root directory blank, build `pip install .`, start
  `uvicorn bw_observatory.api.app:app --host 0.0.0.0 --port $PORT`, health check
  `/api/v1/health`.
- **Data:** Render persistent disk at `/var/data`, `BW_DATA_DIR=/var/data`,
  5 GB, seeded out of band. Never committed.
- **Routing:** `apps/web/nitro.config.ts` emits a `/api/**` proxy into the Vercel
  build output. The browser never learns the Render hostname. Do NOT use a
  `vercel.json` rewrite — the Nitro Vercel preset does not merge it.
- `API_ORIGIN` is a Vercel **build-time** env var (a public hostname, not a
  secret). Missing `API_ORIGIN` on a Vercel build fails the build by design
  rather than shipping an app that serves HTML to the data layer.

Deployment sequencing is strict and one-directional:

1. Create Render service → 2. Deploy app → 3. Verify `/api/v1/health` →
4. Attach disk → 5. Upload Bronze/Silver → 6. Verify counts + checksums →
7. Validate all endpoints → 8. Verify `bronze_integrity_verified: true` →
9. Commit + push `nitro.config.ts` → 10. Set `API_ORIGIN` in Vercel →
11. Redeploy frontend → 12. End-to-end validation.

The backend is validated independently and completely before any frontend
deployment. Never create a cloud resource, upload data, set an env var, or
deploy without explicit approval at that step. Disks attach at runtime only — the
build command must never read or write `/var/data`. Object-storage-based disk
reseeding is a planned **phase 2**, not implemented.

---

## 15. Testing rules

- Run Ruff, mypy, and pytest after meaningful changes.
- Focused validation for the feature at hand — not a repo-wide sweep on every
  edit.
- The suite currently has 152 passing tests under `tests/`, covering the API
  routes (`test_years_api`, `test_overview_api`, `test_incidents_api`,
  `test_pulse_api`), geography, ingestion, and packaging.
- Local endpoint smoke test (API must be running on :8000), using an explicit
  answerable year — **use 2025, not the 2024 default**:

  ```powershell
  curl 'http://127.0.0.1:8000/api/v1/health'
  curl 'http://127.0.0.1:8000/api/v1/years'
  curl 'http://127.0.0.1:8000/api/v1/geographies'
  curl 'http://127.0.0.1:8000/api/v1/pulse/ward20?year=2025'
  curl 'http://127.0.0.1:8000/api/v1/pulse/woodlawn?year=2025'
  curl 'http://127.0.0.1:8000/api/v1/incidents/ward20?year=2025'
  ```

  Expected (V2-002, 2026-09-12): 21 years with `latest: 2026` (2024 was restored
  before V2); `ward20` 2025 reports **7813** incidents; `woodlawn` (the portion
  inside Ward 20) reports **2960** — not the whole-community-area 3847 of V1.
  `/pulse/back-of-the-yards` and `/pulse/bronzeville` are 404 by design.

- **Known mypy issue (do not "fix" as part of unrelated work):** `uv run mypy`
  reports `Package 'bw_observatory' cannot be type checked due to missing
  py.typed marker`. This is a packaging config issue, not a type error — zero
  type errors are reported. Fixing it means adding `src/bw_observatory/py.typed`
  and a hatch build entry, which touches `pyproject.toml`. Do not do so without
  explicit authorization.

- A green build without an inspected result is not proof. When a build is meant
  to produce a specific artifact (e.g. a generated route), inspect the artifact.

---

## 16. Reporting format

- Lead with the answer or outcome, then the detail. Do not narrate options you
  will not pursue.
- Use `file_path:line` references — they are clickable.
- When reporting verification, use a compact table of check → result, and mark
  clearly what was proven versus what is assumed or untested.
- Distinguish "PASS", "FAIL", and "NOT VERIFIED (blocked/not run)". Never let the
  third masquerade as the first.
- State plainly what changed, what did not change, and what risk remains.
- No hedging on completed, verified work; no false confidence on unverified work.

---

## 17. Stop conditions

Stop immediately and hand back to the user when:

- An approval-required action (section 6) is the next step.
- A phase completes and the plan says to wait.
- A failure appears whose fix would exceed the approved scope.
- The main branch or production data would be affected without prior sign-off.
- You notice you are looping (section 9) — stop and state a conclusion.
- The requested change conflicts with a governance non-negotiable (section 1)
  or a data-protection rule (section 7).

When you stop, say exactly why, what you need, and what the next action will be.

---

## 18. Completion checklist

Before declaring any change complete:

- [ ] Change is limited to the approved scope; no unrelated files touched.
- [ ] Ruff, mypy (modulo the known py.typed issue), and pytest run for the
      affected area, with results reported honestly.
- [ ] No fabricated, placeholder, or sample values remain in user-facing output.
- [ ] Governance non-negotiables and data-protection rules are intact.
- [ ] `bronze_integrity_verified` remains truthful where relevant.
- [ ] Generated files were not hand-edited.
- [ ] `git status` reviewed; only intended files are staged; nothing committed
      without approval.
- [ ] `docs/PROJECT_STATUS.md` updated if a feature was completed.
- [ ] Summary delivered: what changed, what did not, remaining risk, next step.

---

## 19. Common Claude Code failure modes

Watch for these specifically; they have occurred here:

1. **Audit loops** — re-inspecting the repo instead of acting. Cure: section 9.
2. **Reasoning from artifacts instead of source** — e.g. concluding "Vercel SSR
   is broken" from a local Cloudflare build output without reading the config
   resolution. Read the mechanism before escalating a risk.
3. **Silent overwrite** — replacing an existing file (this very `CLAUDE.md`) as
   if it were empty. Cure: section 8; read first, preserve intent.
4. **Broad staging** — `git add -A` sweeping unrelated pre-existing changes into
   a commit. Cure: section 13; stage selectively.
5. **Reporting not-run as passed** — claiming a blocked or skipped check
   succeeded. Cure: sections 12 and 16.
6. **Scope creep dressed as helpfulness** — "while I was here I also…". Cure:
   sections 2 and 10.
7. **PowerShell/Bash confusion** — using `&&`, `head`, or `2>&1` in PowerShell.
   Cure: section 3.
8. **Trusting the 2024 defaults** — treating a 404 on `/overview/woodlawn` as a
   bug, or re-enriching from the 2024 stub. Cure: sections 1 and 7.
9. **Fixing line-ending churn** — treating CRLF-only diffs as real changes.
   Cure: section 4.

---

## 20. Repository memory

Durable facts worth carrying between sessions (verify before relying — code may
have moved):

- System of record: geography-enriched **Silver**. API joins Silver→Bronze on
  `id`; both layers required at request time.
- Product geography (V2-002/002A): **Ward 20** (`ward20`, default, kind `ward`)
  plus ALL NINE intersecting `community_area_portion` areas — `woodlawn`,
  `washington-park`, `englewood`, `fuller-park`, `new-city`,
  `greater-grand-crossing`, `hyde-park`, `grand-boulevard`, `kenwood` (small
  portions kept on purpose for equity analysis; never hide them, never invent a
  suppression rule); `back-of-the-yards` is a pending
  `neighborhood_portion` (the City's tourism neighborhoods layer has no boundary
  distinct from New City — do not activate it from that layer). Registry:
  `config/geographies.yml`. Filter: `spatial_ward_current == "20"` (+
  `spatial_community_area`); the ward total never depends on the area list.
  Bronzeville is unknown (404). Measurements: `scripts/measure_ward_coverage.py`.
- V2-003 audit (2026-09-14): `docs/data/WARD20_EQUITY_DATA_READINESS.md` is the
  inventory of what exists (crime + boundaries only) and what is missing (311,
  Census attributes, TIF, parcels, streets). Next data package: V2-005 =
  311 ingestion (`v6vf-nfxy`; V2-004 became the crime refresh) with point-in-polygon Ward 20 clipping — never
  the dataset's own `ward` field, which is the ward at creation time.
- Crime currentness (V2-004, 2026-09-14): `scripts/refresh_crime.py` is the ONLY way to
  bring crime data forward; never re-run the whole-year downloader for that. Watermark =
  source `updated_on` (stamped on insert and every edit; daily batch ≈15:45 UTC; 7-day
  lag). Upsert by `id`; manifest checksum rewritten; only changed rows re-enriched; log in
  `data/bronze/crime/incremental_refresh_log.parquet`. Negative reconciliation drift =
  source deletions → `scripts/reconcile_crime.py` marks them `source_removed` in Silver
  (kept as provenance, excluded from every figure by `current_source_view`); never delete.
  V2-004A (2026-09-15): partition I/O streams in 20k-row batches (never load a year
  whole); invariants proved after every publish; one writer at a time (`refresh.lock`);
  `/api/v1/freshness`; in-process scheduler off until `BW_REFRESH_SCHEDULE`. Operating
  model: `docs/methodology/CRIME_DATA_OPERATING_MODEL.md`. No 311 data exists in the app.
- Frontend contexts live in the URL: `?year=` (`useYear`) and `?geo=`
  (`useGeography`), both validated at the root route and retained across
  navigation. Never add a second store for either.
- Year availability is computed live from disk. (Historically 2024 was excluded
  because its Bronze file was a one-row stub; Bronze 2024 was restored before V2
  and `/years` now lists 21 years.) `/overview` still defaults to 2024.
- Woodlawn is ~1.63% of citywide rows; full runtime dataset ≈ 555 MB across 46
  Parquet files (Bronze ≈ 450 MB, Silver ≈ 105 MB).
- Config the API reads at request time: `config/crime_categories.yml`,
  `config/geographies.yml` (product geography). `config/neighborhoods/
  neighborhoods.yml` is pipeline-only. These ship in Git.
- `Settings` (`src/bw_observatory/config.py`) resolves `data_dir` from
  `BW_DATA_DIR`/`DATA_DIR`, anchored to the repo root by default; `config_dir`
  and `log_dir` similarly. The root is found by locating `pyproject.toml` +
  `config/`.
- Deployment architecture: Vercel frontend + Render API + persistent disk +
  Nitro `routeRules` proxy. Frozen.
- `.env.example` currently lists Supabase/Census/Socrata placeholders that the
  code does NOT read, and omits the vars it does (`CHICAGO_DATA_APP_TOKEN`,
  `DATA_DIR`, `LOG_LEVEL`). Known drift; fix only when explicitly in scope.
- Frontend build tooling (`@lovable.dev/vite-tanstack-config`) injects the Nitro
  plugin only on `command === "build"`; `vite dev` never loads `nitro.config.ts`.

When you learn a new durable, non-obvious fact, record it here or in the
project's status docs — not in a throwaway comment.

---

## 21. Decision framework

When a choice is genuinely ambiguous and you must decide, apply in order:

1. **Governance first.** If an option would break a non-negotiable (section 1) or
   a data-protection rule (section 7), it is off the table regardless of other
   merit.
2. **Truthfulness.** Prefer the option that keeps every published number and
   status honest (`bronze_integrity_verified`, data-through dates, "not
   verified" labels). Never trade truth for convenience.
3. **Reversibility.** Prefer reversible, non-destructive actions. Anything hard
   to undo — history rewrite, data deletion, production deploy — needs explicit
   approval, never a default.
4. **Scope fit.** Prefer the option that delivers exactly the approved
   deliverable with the smallest footprint. Reject scope creep.
5. **Maintainability over cleverness.** Prefer the approach a future maintainer
   can debug: provable behavior, config co-located with the app, standard tools.
6. **Evidence over assumption.** Base the decision on the mechanism you have
   actually read, not on artifacts or memory. If you cannot verify and the cost
   of being wrong is high, stop and ask rather than guess.

If two options remain after this filter, present the user a single question with
a recommended default and the trade-off in one line. Do not survey the whole
space.

---

_This manual folds in and supersedes the prior root `CLAUDE.md` governance
(Data Layer Contract, 2024 Bronze protection, Execution Authority, Overview scope
lock), which remain in force here under sections 1, 5–7, 10, and 14._
