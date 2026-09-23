"""Typed response models for the public read API.

Every field a resident sees carries its provenance. `prior_year` values are `None` when the
prior year has not been enriched — never zero, never inferred, and the frontend is required
to say so rather than draw an arrow.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MonthlyPoint(BaseModel):
    """One month of reported incidents."""

    month: int = Field(ge=1, le=12)
    month_label: str
    incidents: int = Field(ge=0)


class CategoryCount(BaseModel):
    """One crime grouping, as defined in config/crime_categories.yml."""

    key: str
    label: str
    count: int = Field(ge=0)
    prior_year_count: int | None = None
    description: str = ""


class DataQuality(BaseModel):
    """What the reader needs in order to decide how much to trust the numbers."""

    total_bronze_records_year: int = Field(ge=0)
    records_without_coordinates: int = Field(ge=0)
    records_outside_boundaries: int = Field(ge=0)
    records_invalid_coordinates: int = Field(ge=0)
    community_area_mismatches: int = Field(ge=0)
    bronze_integrity_verified: bool


class Provenance(BaseModel):
    source_dataset_id: str
    source_dataset_name: str
    boundary_type: str
    boundary_source: str
    boundary_vintage: str
    last_refresh: str
    data_through: str
    #: The ward map every figure is measured against, and one plain sentence on what the
    #: figures cover (all of the ward, or only the part of an area inside it).
    ward_source: str = ""
    ward_vintage: str = ""
    geography_scope: str = ""


class NeighborhoodAvailability(BaseModel):
    """One product geography and whether it can be shown. An unavailable geography carries
    its reason; its absence is never a count of zero."""

    neighborhood_id: str
    display_name: str
    available: bool
    reason: str | None = None
    #: The boundary system: "ward", "community_area_portion", or "neighborhood_portion".
    kind: str = "community_area_portion"
    #: Official community-area number for an area within the ward.
    community_area: str | None = None
    #: For a pending neighborhood, the official geography that contains it.
    represented_by: str | None = None
    #: Plain-language name of the boundary system, and the exact source when answerable.
    boundary_system: str = ""
    boundary_source: str | None = None
    #: Measured size of the portion inside the ward (documentation values from the registry;
    #: see config/geographies.yml `measurement`). Published so analytics can warn about small
    #: denominators; no suppression rule is implied.
    intersection_sq_mi: float | None = None
    share_of_ward_area_pct: float | None = None
    share_of_area_in_ward_pct: float | None = None


class IncidentRecord(BaseModel):
    """One reported incident, as published by the city plus this project's spatial result.

    Only fields the City of Chicago already publishes. Locations are block-level — Chicago
    redacts the house number, and this project never attempts to recover it. No victim or
    offender identity is present in the source data, and none is derived here. `arrest` is
    a fact about a report, not an outcome: no case status is inferred.
    """

    id: str
    case_number: str | None = None
    date: str
    updated_on: str | None = None
    block: str | None = None
    primary_type: str | None = None
    description: str | None = None
    location_description: str | None = None
    arrest: bool | None = None
    domestic: bool | None = None
    beat: str | None = None
    district: str | None = None
    ward: str | None = None
    community_area: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geography_status: str | None = None


class IncidentPage(BaseModel):
    neighborhood_id: str
    year: int
    total_records: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    records: list[IncidentRecord]

    #: `ward`, `district` and `beat` filter on the fields CPD publishes on each record, while
    #: the records themselves were selected by point-in-polygon. The two frames disagree for a
    #: minority of records, so such a filter can drop rows that ARE inside the geography. The
    #: count of rows dropped that way is published here rather than left silent.
    published_field_filters: list[str] = Field(default_factory=list)
    excluded_by_published_field_filters: int = Field(default=0, ge=0)


class OverviewResponse(BaseModel):
    neighborhood_id: str
    neighborhood_name: str
    year: int

    #: True when the year is incomplete — data stops before 31 December. A year-to-date
    #: figure must never be set against a full year without saying so.
    is_year_to_date: bool = False

    total_incidents: int = Field(ge=0)
    total_incidents_prior_year: int | None = None

    categories: list[CategoryCount]
    monthly_trend: list[MonthlyPoint]

    comparison_available: bool
    comparison_note: str

    headline: str

    provenance: Provenance
    data_quality: DataQuality
    #: Properties of the dataset that could explain part of the pattern (see MeasurementNotes).
    measurement: MeasurementNotes | None = None
    neighborhoods: list[NeighborhoodAvailability]


# ==========================================================================================
# Neighborhood Pulse — the resident-facing "what changed, where, who is responsible" model.
#
# All comparisons use the SAME period a year earlier (Jan 1 → the same month/day), so a
# partial year is never set against a completed year. Every prior/change field is None when
# the prior year is not answerable — never zero, never inferred.
# ==========================================================================================


class PeriodBounds(BaseModel):
    """A comparison window: the counted span and its total."""

    start: str  # ISO date, inclusive
    end: str  # ISO date, inclusive
    incidents: int = Field(ge=0)


class ChangeMetric(BaseModel):
    """A count with its same-period prior value and the change between them."""

    current: int = Field(ge=0)
    prior: int | None = None
    absolute_change: int | None = None
    #: None when there is no prior, or the prior is zero (a percentage would be undefined).
    percent_change: float | None = None


class BroadCategoryChange(BaseModel):
    """One broad, resident-facing category (a partition of the total) and its change."""

    key: str
    label: str
    current: int = Field(ge=0)
    prior: int | None = None
    absolute_change: int | None = None
    percent_change: float | None = None


class PrimaryTypeChange(BaseModel):
    """One raw CPD `primary_type` and its change — the detail behind a broad category."""

    primary_type: str
    broad_category: str
    broad_label: str
    current: int = Field(ge=0)
    prior: int | None = None
    absolute_change: int | None = None
    percent_change: float | None = None

    #: True when this offence is recorded almost only where police act on it, so the count
    #: tracks enforcement activity rather than how often the behaviour occurs. Never present
    #: a change in one of these as a change in neighbourhood conditions.
    enforcement_generated: bool = False


class BeatConcentration(BaseModel):
    """One police beat's share of the neighborhood and its same-period change."""

    beat: str  # raw published value, e.g. "0321"
    beat_display: str  # resident-facing, e.g. "321"
    current: int = Field(ge=0)
    prior: int | None = None
    #: Share of the current-period neighborhood total, 0..1.
    share: float = Field(ge=0, le=1)
    absolute_change: int | None = None
    percent_change: float | None = None

    #: The beat's whole-beat count for the same period, across the whole city, not clipped to
    #: the selected geography. A CPD beat meeting covers the whole beat, so a resident needs
    #: both numbers to compare what they are told with what they read here.
    whole_beat_current: int | None = None
    #: `current / whole_beat_current` — how much of the beat's activity falls inside the
    #: selected geography. Below 1.0 the beat extends beyond it.
    share_of_beat_inside: float | None = None
    #: True when the beat reaches outside the selected geography.
    extends_beyond_geography: bool = False


class ArrestSummary(BaseModel):
    """Arrests recorded on reports — NOT a clearance, prosecution, or conviction rate."""

    count: int = Field(ge=0)
    total: int = Field(ge=0)
    #: Arrests as a share of reported incidents in the current period, 0..1.
    percent: float = Field(ge=0, le=1)
    prior_count: int | None = None
    prior_percent: float | None = None


class MonthlyComparisonPoint(BaseModel):
    """One month, current year vs the same month a year earlier (equivalent period only)."""

    month: int = Field(ge=1, le=12)
    month_label: str
    current: int | None = None  # None for months not yet reached in a partial year
    prior: int | None = None  # None outside the equivalent period, or if no comparison
    is_partial_month: bool = False
    in_comparison_window: bool = True


class MonthlyCategoryPoint(BaseModel):
    """One month of the current year, broken into broad categories (they sum to `total`)."""

    month: int = Field(ge=1, le=12)
    month_label: str
    counts: dict[str, int]
    total: int = Field(ge=0)
    is_partial_month: bool = False


class IssueCard(BaseModel):
    """A data-backed issue with its responsible authority and a resident next step.

    Every field is derived from the counts on the page or is clearly-labelled civic guidance.
    No cause is inferred: an issue names what the data shows and who is responsible for it.
    """

    id: str
    kind: str
    title: str
    finding: str
    supporting_stat: str
    comparison_period: str
    beat: str | None = None
    primary_authority: str
    supporting_authority: str | None = None
    alderperson_role: str
    resident_action: str
    suggested_question: str
    evidence: str


class MeasurementNotes(BaseModel):
    """What the dataset itself could be doing to a pattern, for the selected geography/year.

    Every field here is a property of the records, not of the neighborhood. They are published
    so a reader can tell "the area changed" from "the measurement changed".
    """

    #: Records in the geography whose published coordinates could not be placed in a polygon.
    unplaced_records: int = Field(default=0, ge=0)
    #: Records where CPD's published beat and the point-in-polygon beat disagree. Expected to
    #: be ~11% because published coordinates are masked to the block, which cannot resolve a
    #: beat boundary; it is not an error.
    beat_definition_disagreements: int = Field(default=0, ge=0)
    #: Same, for ward and community area. Smaller, because the polygons are larger.
    ward_definition_disagreements: int = Field(default=0, ge=0)
    community_area_definition_disagreements: int = Field(default=0, ge=0)
    #: Records the City has since withdrawn. Kept as provenance, excluded from every figure.
    source_removed_records: int = Field(default=0, ge=0)
    #: True when the reporting period is recent enough that late-arriving records are still
    #: likely to raise the count. A decline here may shrink as records arrive.
    provisional_period: bool = False
    #: Plain-language notes a view can render without re-deriving any of the above.
    notes: list[str] = Field(default_factory=list)


class PulseResponse(BaseModel):
    neighborhood_id: str
    neighborhood_name: str
    year: int
    is_year_to_date: bool = False
    data_through: str

    current_period: PeriodBounds
    prior_period: PeriodBounds | None = None
    comparison_available: bool
    comparison_note: str

    # Headline + narrative are composed server-side from the fields below and nothing else.
    headline: str
    narrative: str

    # Metric cards.
    incidents: ChangeMetric
    largest_increase: BroadCategoryChange | None = None
    largest_decline: BroadCategoryChange | None = None
    beat_largest_increase: BeatConcentration | None = None
    arrests: ArrestSummary

    # Charts.
    monthly_comparison: list[MonthlyComparisonPoint]
    monthly_categories: list[MonthlyCategoryPoint]

    # Breakdowns.
    broad_categories: list[BroadCategoryChange]
    category_drivers: list[PrimaryTypeChange]
    beats: list[BeatConcentration]

    # Issues residents should watch.
    issues: list[IssueCard]

    provenance: Provenance
    data_quality: DataQuality
    #: Properties of the dataset that could explain part of the pattern (see MeasurementNotes).
    measurement: MeasurementNotes | None = None
    neighborhoods: list[NeighborhoodAvailability]
