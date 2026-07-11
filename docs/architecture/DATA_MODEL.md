# Data Model

Planned entities. **None of these tables exist yet.** Only the in-flight validation of raw
crime dictionaries is implemented; there is no persistence layer. Keys and fields below are
proposals to guide implementation, not descriptions of a built schema.

Status values: `Not built` · `Partial` · `Built`.

---

## crime_incident

**Purpose.** One reported crime incident, normalized from the Chicago crime dataset.
The core fact table.

**Proposed primary key.** `id` (the source Socrata record ID; stable across corrections).

**Major fields.** `id`, `case_number`, `occurred_at` (from `date`), `iucr`,
`primary_type`, `description`, `location_description`, `arrest`, `domestic`, `beat`,
`district`, `ward`, `community_area`, `year`, `updated_on`, `latitude`, `longitude`,
`neighborhood_key` (nullable), `crime_group` (from the configurable mapping),
`refresh_run_id`.

**Notes.** `latitude`/`longitude`/`neighborhood_key` are nullable by design. Corrections
are handled by keeping the row with the newest `updated_on` for a given `id`.

**Status.** `Partial` — validation contract exists; no table.

---

## data_refresh_run

**Purpose.** One ingestion attempt. Makes refreshes auditable and lets the Data Health page
show what happened and when.

**Proposed primary key.** `refresh_run_id` (surrogate).

**Major fields.** `refresh_run_id`, `source_dataset_id`, `started_at`, `completed_at`,
`status` (`success` | `failed` | `partial`), `rows_fetched`, `rows_written`,
`rows_rejected`, `rows_missing_coordinates`, `max_updated_on_seen`, `error_message`,
`schema_ok`.

**Status.** `Not built`.

---

## geography_dimension

**Purpose.** The raw spatial reference layer: official polygons as published (community
areas, and any other official geography we ingest).

**Proposed primary key.** `geography_key` (surrogate); natural key `(geography_type, source_id)`.

**Major fields.** `geography_key`, `geography_type` (e.g. `community_area`), `source_id`,
`name`, `geometry`, `source_dataset_id`, `ingested_at`.

**Status.** `Not built`.

---

## neighborhood_dimension

**Purpose.** The two neighborhoods this project reports on. Distinct from
`geography_dimension` because Bronzeville is **not** a single official community area and
must carry its own approved boundary and provenance.

**Proposed primary key.** `neighborhood_key`.

**Major fields.** `neighborhood_key`, `name` (`Bronzeville` | `Woodlawn`),
`boundary_source` (`official_community_area` | `approved_custom_geojson`), `geometry`,
`definition_notes`, `approved_by`, `approved_on`, `version`.

**Notes.** Boundary definition is versioned. Any change to the Bronzeville polygon changes
every historical number, so the version must be recorded with published figures. See
[ADR-0004](ADR/ADR-0004-neighborhood-boundary-strategy.md).

**Status.** `Not built` — Bronzeville boundary not yet approved.

---

## census_metric

**Purpose.** Census and ACS measures (population, income, housing, vacancy) for context and
per-capita rates.

**Proposed primary key.** `(geography_key, metric_code, period)`.

**Major fields.** `geography_key`, `metric_code`, `metric_label`, `period`, `value`,
`margin_of_error`, `source_dataset_id`, `refresh_run_id`.

**Notes.** ACS estimates carry margins of error. Any published rate derived from ACS must
surface that uncertainty rather than presenting a point estimate as exact.

**Status.** `Not built`.

---

## election_result

**Purpose.** Voter turnout and results, to show civic participation alongside outcomes.

**Proposed primary key.** `(election_id, precinct_id, contest_id)`.

**Major fields.** `election_id`, `election_date`, `precinct_id`, `contest_id`,
`contest_name`, `registered_voters`, `ballots_cast`, `turnout_pct`, `geography_key`,
`source_dataset_id`.

**Notes.** Precinct boundaries change between elections; precinct-to-neighborhood mapping
must be resolved per election year, not once.

**Status.** `Not built`.

---

## event_calendar

**Purpose.** Dated contextual events (holidays, sports, school calendar, weather episodes,
neighborhood events) used as **context only**.

**Proposed primary key.** `event_id`.

**Major fields.** `event_id`, `event_type`, `name`, `start_date`, `end_date`,
`geographic_scope`, `source`, `notes`.

**Notes.** Never used to assert causation. See
[EVENTS_AND_POLICY_CONTEXT.md](../methodology/EVENTS_AND_POLICY_CONTEXT.md).

**Status.** `Not built`.

---

## policy_event

**Purpose.** Dated policy and enforcement changes (ordinances, federal or state actions,
CPD policy shifts, COVID orders) that form the backdrop to any trend.

**Proposed primary key.** `policy_event_id`.

**Major fields.** `policy_event_id`, `title`, `level` (`federal` | `state` | `county` |
`city`), `effective_date`, `end_date`, `responsible_body`, `summary`, `source_url`.

**Notes.** A policy date next to a trend change is an association, presented as such.

**Status.** `Not built`.

---

## public_commitment

**Purpose.** Public promises made by officials and agencies, with their status over time.
The backbone of the "Who Is Responsible" page.

**Proposed primary key.** `commitment_id`.

**Major fields.** `commitment_id`, `made_by` (person or body), `role`, `commitment_text`,
`made_on`, `source_url`, `target_date`, `status` (`stated` | `in_progress` | `met` |
`unmet` | `unclear`), `status_evidence_url`, `last_reviewed_on`.

**Notes.** Status changes must cite evidence. `unclear` is a legitimate status and is
preferable to guessing.

**Status.** `Not built`.
