/**
 * Typed client for the Observatory read API.
 *
 * The only source of numbers on this site. There are no sample metrics and no fallback
 * values: if the API cannot answer, the page says so rather than showing something
 * plausible. Requests use the relative path /api/..., which the Vite dev server proxies to
 * the local FastAPI process — no production URL is hardcoded.
 */

export type MonthlyPoint = {
  month: number;
  month_label: string;
  incidents: number;
};

export type CategoryCount = {
  key: string;
  label: string;
  count: number;
  /** null means the prior year has not been enriched. It never means zero. */
  prior_year_count: number | null;
  description: string;
};

export type DataQuality = {
  total_bronze_records_year: number;
  records_without_coordinates: number;
  records_outside_boundaries: number;
  records_invalid_coordinates: number;
  community_area_mismatches: number;
  bronze_integrity_verified: boolean;
};

export type Provenance = {
  source_dataset_id: string;
  source_dataset_name: string;
  boundary_type: string;
  boundary_source: string;
  boundary_vintage: string;
  last_refresh: string;
  data_through: string;
  /** The ward map the figures are measured against, and what place they cover. */
  ward_source: string;
  ward_vintage: string;
  geography_scope: string;
};

export type GeographyKind = "ward" | "community_area_portion" | "neighborhood_portion";

/** One product geography: Ward 20 overall, or an area within Ward 20. */
export type NeighborhoodAvailability = {
  /** The geography id used in URLs and API paths (e.g. "ward20", "woodlawn"). */
  neighborhood_id: string;
  display_name: string;
  available: boolean;
  /** Why it cannot be shown. Never "0 incidents". */
  reason: string | null;
  kind: GeographyKind;
  /** Official community-area number for an area within the ward. */
  community_area: string | null;
  /** For a pending neighborhood, the official geography that contains it. */
  represented_by: string | null;
  /** Square miles of the community area that lie inside Ward 20. */
  intersection_sq_mi?: number | null;
  /** Percent of Ward 20's AREA this portion covers. Not a share of incidents. */
  share_of_ward_area_pct?: number | null;
  /**
   * Percent of the community area's AREA that is inside Ward 20 — e.g. Woodlawn 50.1%,
   * Englewood 23.0%. This is an area share, never an incident share; the two differ and
   * must never be labelled interchangeably.
   */
  share_of_area_in_ward_pct?: number | null;
};

export type GeographyCatalog = {
  ward: {
    ward_id: string;
    geography_id: string;
    display_name: string;
    source: string;
    source_dataset_id: string;
    source_vintage: string;
    notes: string;
  };
  default_geography_id: string;
  geographies: NeighborhoodAvailability[];
  other_community_areas_in_ward: {
    community_area: string;
    community_area_name: string;
    share_of_ward_area_pct: number | null;
  }[];
};

export type EnrichedYears = {
  years: number[];
  latest: number | null;
};

export type OverviewResponse = {
  neighborhood_id: string;
  neighborhood_name: string;
  year: number;
  /** True when the year is incomplete: data stops before 31 December. */
  is_year_to_date: boolean;
  total_incidents: number;
  total_incidents_prior_year: number | null;
  categories: CategoryCount[];
  monthly_trend: MonthlyPoint[];
  comparison_available: boolean;
  comparison_note: string;
  headline: string;
  provenance: Provenance;
  data_quality: DataQuality;
  neighborhoods: NeighborhoodAvailability[];
};

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Reject anything that is not the shape we expect, rather than rendering half a page. */
function assertOverview(data: unknown): asserts data is OverviewResponse {
  const value = data as Partial<OverviewResponse> | null;

  const valid =
    value !== null &&
    typeof value === "object" &&
    typeof value.neighborhood_name === "string" &&
    typeof value.total_incidents === "number" &&
    typeof value.headline === "string" &&
    typeof value.comparison_available === "boolean" &&
    Array.isArray(value.categories) &&
    Array.isArray(value.monthly_trend) &&
    Array.isArray(value.neighborhoods) &&
    value.provenance !== undefined &&
    value.data_quality !== undefined;

  if (!valid) {
    throw new ApiError("The server returned data in an unexpected shape.", 500);
  }
}

export async function fetchOverview(
  neighborhoodId: string,
  year: number,
  signal?: AbortSignal,
): Promise<OverviewResponse> {
  const response = await fetch(`/api/v1/overview/${neighborhoodId}?year=${year}`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    let detail = `The data service returned an error (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Body was not JSON. Keep the status-based message rather than inventing one.
    }
    throw new ApiError(detail, response.status);
  }

  const data: unknown = await response.json();
  assertOverview(data);
  return data;
}

export type IncidentRecord = {
  id: string;
  case_number: string | null;
  date: string;
  updated_on: string | null;
  block: string | null;
  primary_type: string | null;
  description: string | null;
  location_description: string | null;
  arrest: boolean | null;
  domestic: boolean | null;
  beat: string | null;
  district: string | null;
  ward: string | null;
  community_area: string | null;
  latitude: number | null;
  longitude: number | null;
  geography_status: string | null;
};

export type IncidentPage = {
  neighborhood_id: string;
  year: number;
  total_records: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: IncidentRecord[];
  /**
   * Which of `ward` / `district` / `beat` were applied. These match the fields CPD publishes on
   * a record, while the records themselves were selected by point-in-polygon, so applying one
   * can remove records that ARE inside the geography.
   */
  published_field_filters?: string[];
  /** How many in-geography rows the published-field filters removed. Never left unshown. */
  excluded_by_published_field_filters?: number;
};

export type IncidentFilters = {
  primary_type?: string;
  broad_category?: string;
  block?: string;
  description?: string;
  location?: string;
  ward?: string;
  district?: string;
  beat?: string;
  search?: string;
  arrest?: "true" | "false";
  date_from?: string;
  date_to?: string;
};

export type IncidentSort = {
  sort_by: "date" | "block" | "primary_type" | "arrest" | "beat" | "district" | "ward";
  sort_dir: "asc" | "desc";
};

/**
 * One page of individual incidents. Pagination and filtering happen on the server — the
 * browser never downloads the full year to page through it locally.
 */
/** Build the query string shared by the incidents page and its CSV export. */
function incidentParams(
  year: number,
  filters: IncidentFilters,
  sort?: IncidentSort,
): URLSearchParams {
  const params = new URLSearchParams({ year: String(year) });
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  if (sort) {
    params.set("sort_by", sort.sort_by);
    params.set("sort_dir", sort.sort_dir);
  }
  return params;
}

export async function fetchIncidents(
  neighborhoodId: string,
  year: number,
  page: number,
  pageSize: number,
  filters: IncidentFilters,
  sort: IncidentSort,
  signal?: AbortSignal,
): Promise<IncidentPage> {
  const params = incidentParams(year, filters, sort);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));

  const response = await fetch(`/api/v1/incidents/${neighborhoodId}?${params.toString()}`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    let detail = `The data service returned an error (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON. Keep the status-based message rather than inventing one.
    }
    throw new ApiError(detail, response.status);
  }

  const data = (await response.json()) as IncidentPage;
  if (!Array.isArray(data.records) || typeof data.total_records !== "number") {
    throw new ApiError("The server returned incident data in an unexpected shape.", 500);
  }
  return data;
}

/** Years the API can actually answer for. Never a hardcoded list. */
export async function fetchEnrichedYears(signal?: AbortSignal): Promise<EnrichedYears> {
  const response = await fetch("/api/v1/years", {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiError(
      `Could not load the list of available years (${response.status}).`,
      response.status,
    );
  }

  const data = (await response.json()) as EnrichedYears;
  if (!Array.isArray(data.years)) {
    throw new ApiError("The server returned an unexpected list of years.", 500);
  }
  return data;
}

/** The places the API can answer for, with provenance. Never a hardcoded list. */
export async function fetchGeographies(signal?: AbortSignal): Promise<GeographyCatalog> {
  const response = await fetch("/api/v1/geographies", {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiError(
      `Could not load the list of geographies (${response.status}).`,
      response.status,
    );
  }

  const data = (await response.json()) as GeographyCatalog;
  if (!Array.isArray(data.geographies) || typeof data.default_geography_id !== "string") {
    throw new ApiError("The server returned an unexpected list of geographies.", 500);
  }
  return data;
}

/** URL for the CSV export of the current filtered/sorted incident set. */
export function incidentsCsvUrl(
  neighborhoodId: string,
  year: number,
  filters: IncidentFilters,
  sort: IncidentSort,
): string {
  return `/api/v1/incidents/${neighborhoodId}/export.csv?${incidentParams(year, filters, sort).toString()}`;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** "2026 year-to-date" vs "2024". The distinction is never dropped. */
export function periodLabel(year: number, isYearToDate: boolean): string {
  return isYearToDate ? `${year} year-to-date` : `${year}`;
}

// ==========================================================================================
// Neighborhood Pulse
// ==========================================================================================

export type PeriodBounds = { start: string; end: string; incidents: number };

export type ChangeMetric = {
  current: number;
  prior: number | null;
  absolute_change: number | null;
  percent_change: number | null;
};

export type BroadCategoryChange = {
  key: string;
  label: string;
  current: number;
  prior: number | null;
  absolute_change: number | null;
  percent_change: number | null;
};

export type PrimaryTypeChange = {
  primary_type: string;
  broad_category: string;
  broad_label: string;
  current: number;
  prior: number | null;
  absolute_change: number | null;
  percent_change: number | null;
  /**
   * True when the offence is recorded almost only where police act on it, so the count
   * tracks enforcement activity rather than how often the behaviour happens. Never present a
   * change in one of these as a change in neighbourhood conditions.
   */
  enforcement_generated?: boolean;
};

/**
 * What the dataset itself could be doing to the figures. Every field describes the records,
 * never the neighbourhood, so a reader can tell "the area changed" from "the measurement
 * changed".
 */
export type MeasurementNotes = {
  unplaced_records: number;
  beat_definition_disagreements: number;
  ward_definition_disagreements: number;
  community_area_definition_disagreements: number;
  source_removed_records: number;
  /** The period is recent enough that records are still arriving. */
  provisional_period: boolean;
  notes: string[];
};

export type BeatConcentration = {
  beat: string;
  beat_display: string;
  /** Incidents inside the selected geography. */
  current: number;
  prior: number | null;
  share: number;
  absolute_change: number | null;
  percent_change: number | null;
  /** The whole beat's count for the same period — what a CPD beat meeting covers. */
  whole_beat_current?: number | null;
  /** current / whole_beat_current. Below 1 the beat reaches outside the geography. */
  share_of_beat_inside?: number | null;
  extends_beyond_geography?: boolean;
};

export type ArrestSummary = {
  count: number;
  total: number;
  percent: number;
  prior_count: number | null;
  prior_percent: number | null;
};

export type MonthlyComparisonPoint = {
  month: number;
  month_label: string;
  current: number | null;
  prior: number | null;
  is_partial_month: boolean;
  in_comparison_window: boolean;
};

export type MonthlyCategoryPoint = {
  month: number;
  month_label: string;
  counts: Record<string, number>;
  total: number;
  is_partial_month: boolean;
};

export type IssueCard = {
  id: string;
  kind: string;
  title: string;
  finding: string;
  supporting_stat: string;
  comparison_period: string;
  beat: string | null;
  primary_authority: string;
  supporting_authority: string | null;
  alderperson_role: string;
  resident_action: string;
  suggested_question: string;
  evidence: string;
};

export type PulseResponse = {
  neighborhood_id: string;
  neighborhood_name: string;
  year: number;
  is_year_to_date: boolean;
  data_through: string;
  current_period: PeriodBounds;
  prior_period: PeriodBounds | null;
  comparison_available: boolean;
  comparison_note: string;
  headline: string;
  narrative: string;
  incidents: ChangeMetric;
  largest_increase: BroadCategoryChange | null;
  largest_decline: BroadCategoryChange | null;
  beat_largest_increase: BeatConcentration | null;
  arrests: ArrestSummary;
  monthly_comparison: MonthlyComparisonPoint[];
  monthly_categories: MonthlyCategoryPoint[];
  broad_categories: BroadCategoryChange[];
  category_drivers: PrimaryTypeChange[];
  beats: BeatConcentration[];
  issues: IssueCard[];
  provenance: Provenance;
  data_quality: DataQuality;
  /** Properties of the dataset that could explain part of the pattern. */
  measurement: MeasurementNotes | null;
  neighborhoods: NeighborhoodAvailability[];
};

export async function fetchPulse(
  neighborhoodId: string,
  year: number,
  signal?: AbortSignal,
): Promise<PulseResponse> {
  const response = await fetch(`/api/v1/pulse/${neighborhoodId}?year=${year}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let detail = `The data service returned an error (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Not JSON. Keep the status-based message.
    }
    throw new ApiError(detail, response.status);
  }
  const data = (await response.json()) as PulseResponse;
  if (typeof data.headline !== "string" || !Array.isArray(data.broad_categories)) {
    throw new ApiError("The server returned Pulse data in an unexpected shape.", 500);
  }
  return data;
}

/** "July 9, 2026" from an ISO date. Resident-friendly; never shows an ISO date in prose. */
export function residentDate(iso: string): string {
  const parsed = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

/** "+2.9%" / "−1.4%" / "—". A true minus sign, never a hyphen, and never a fake zero. */
export function formatPercentChange(pct: number | null): string {
  if (pct === null) return "—";
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

export function formatSignedCount(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toLocaleString("en-US")}`;
}

// ==========================================================================================
// Data freshness
// ==========================================================================================

/**
 * How current the crime data is. `status` is the API's own verdict, not a guess made here:
 * `current` | `stale` | `refresh_failed` | `never_refreshed`. A stale platform says so rather
 * than presenting old figures as today's.
 */
export type CrimeFreshness = {
  status: string;
  reasons: string[];
  data_through: string | null;
  days_behind: number | null;
  last_successful_refresh: string | null;
  refresh_running: boolean;
  source_lag_days: number | null;
};

export async function fetchFreshness(signal?: AbortSignal): Promise<CrimeFreshness> {
  const response = await fetch("/api/v1/freshness", {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(`Could not load data freshness (${response.status}).`, response.status);
  }
  const data = (await response.json()) as CrimeFreshness;
  if (typeof data.status !== "string") {
    throw new ApiError("The server returned an unexpected freshness payload.", 500);
  }
  return data;
}

/** True when the platform should warn that figures are not up to date. */
export function isStaleStatus(status: string): boolean {
  return status !== "current";
}
