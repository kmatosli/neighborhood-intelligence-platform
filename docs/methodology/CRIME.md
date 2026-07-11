# Crime Data Methodology

## Source

- **Dataset.** Crimes — 2001 to Present, City of Chicago Data Portal
- **Dataset ID.** `ijzp-q8t2`
- **Data endpoint.** `https://data.cityofchicago.org/resource/ijzp-q8t2.json`
- **Metadata endpoint.** `https://data.cityofchicago.org/api/views/ijzp-q8t2`
- **Analysis period.** **January 1, 2006 to present.** Earlier records exist in the source
  but are not analyzed here.

## What this data is

**Reported crimes.** Every record is an incident *reported to and recorded by* the Chicago
Police Department. It is not a measure of crime that occurred.

The gap matters. Crimes that are not reported do not appear. A rise in reports can mean more
crime, more reporting, or a change in how incidents are recorded — and these are not
distinguishable from the data alone. Any published trend must be described as a trend in
**reported** crime.

## What the data does not mean

**Arrest does not mean conviction.** The `arrest` field records that an arrest was made in
connection with an incident. It says nothing about charges filed, prosecution, or guilt.
Never present arrest counts as counts of offenders, and never imply a person is guilty.

**Crime is not attributable to nationality or immigration status.** The dataset contains no
such fields, and neither may be inferred from it. See
[EVENTS_AND_POLICY_CONTEXT.md](EVENTS_AND_POLICY_CONTEXT.md).

**Association is not cause.** A change that coincides with an event or policy is an
association, and must be published as one.

## Known data properties

**Reporting lag.** The most recent **approximately seven days** may be incomplete or
unavailable. Trend charts must exclude or clearly mark the incomplete tail — a naive "last
7 days" comparison will always show a fictitious decline.

**Records are corrected.** Incidents are revised after publication as investigations
proceed; classifications change and records are sometimes removed. `updated_on` carries the
revision timestamp. Deduplication keeps the record with the newest `updated_on` for a given
`id`. This means historical numbers legitimately change over time, and the site must say so
rather than presenting the past as fixed.

**Exact addresses are not displayed.** Chicago publishes block-level locations. The project
does not attempt to de-blur them or reconstruct precise addresses.

**Coordinates may be missing.** A meaningful share of records have no `latitude`/`longitude`
— ungeocoded or withheld locations. In a live 10-record sample, 1 record lacked coordinates.
These are **valid crimes**. They are counted in totals, excluded from maps and
point-in-polygon neighborhood assignment, and their excluded count is disclosed on every
geography-dependent figure. See [VALIDATION.md](../architecture/VALIDATION.md).

Because of this, a neighborhood count and a citywide total are not reconcilable by simple
subtraction, and the site must explain the difference wherever both appear.

## Crime groupings

Raw `primary_type` and `iucr` values are too granular and too idiosyncratic for a resident
to read directly. The site groups them.

**Every grouping must be documented and configurable.** The mapping lives in configuration,
not hardcoded in analysis code, and is published on the Methodology page. A reader must be
able to see exactly which source categories fed any group they are shown — grouping choices
change what a trend looks like, so they are a methodological claim, not an implementation
detail.

Groupings are **not built** yet.

## Rates

Any per-capita rate requires a population denominator from census/ACS, carrying its margin
of error. Until that exists, the site publishes **counts only**, never rates.
