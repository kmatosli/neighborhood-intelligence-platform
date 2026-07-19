import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  fetchIncidents,
  formatCount,
  incidentsCsvUrl,
  type IncidentFilters,
  type IncidentRecord,
  type IncidentSort,
} from "@/lib/api";

const EMPTY_FILTERS: IncidentFilters = {};
const DEFAULT_SORT: IncidentSort = { sort_by: "date", sort_dir: "desc" };
const PAGE_SIZES = [25, 50, 100];

/** Raw CPD crime types offered in the filter. From what the city actually publishes. */
const CRIME_TYPES = [
  "BATTERY", "THEFT", "CRIMINAL DAMAGE", "ASSAULT", "MOTOR VEHICLE THEFT", "BURGLARY",
  "ROBBERY", "WEAPONS VIOLATION", "DECEPTIVE PRACTICE", "CRIMINAL TRESPASS", "NARCOTICS",
  "OTHER OFFENSE", "HOMICIDE",
]; // fmt: skip

/** Broad, resident-facing categories — the partition defined in the methodology config. */
const BROAD_CATEGORIES = [
  { key: "violent_crime", label: "Violent crime" },
  { key: "property_crime", label: "Property crime" },
  { key: "public_order", label: "Public order" },
  { key: "weapons", label: "Weapons" },
  { key: "narcotics", label: "Narcotics" },
  { key: "other", label: "Other" },
];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Format a published timestamp WITHOUT applying the browser's timezone. The city publishes
 * local Chicago wall-clock time with no offset (e.g. "2026-06-24T15:40:00.000"); parsing it
 * through Date() would shift it by the viewer's own timezone. So we read the parts directly.
 */
function formatDateTime(value: string, hour24: boolean): string {
  const [datePart, timePart] = value.split("T");
  if (!datePart) return value;
  const [y, m, d] = datePart.split("-").map(Number);
  const hhmm = (timePart ?? "00:00").slice(0, 5);
  if (hour24) return `${datePart} ${hhmm}`;
  const [hh, mm] = hhmm.split(":").map(Number);
  const meridiem = hh >= 12 ? "PM" : "AM";
  const hour12 = hh % 12 === 0 ? 12 : hh % 12;
  const monthLabel = MONTHS[(m ?? 1) - 1] ?? "";
  return `${monthLabel} ${d}, ${y}, ${hour12}:${String(mm).padStart(2, "0")} ${meridiem}`;
}

type Column = {
  key: string;
  label: string;
  sortBy?: IncidentSort["sort_by"];
  align: "left" | "center";
  render: (r: IncidentRecord, hour24: boolean) => React.ReactNode;
};

const COLUMNS: Column[] = [
  { key: "date", label: "Date and time", sortBy: "date", align: "left", render: (r, h) => formatDateTime(r.date, h) },
  { key: "block", label: "Block", sortBy: "block", align: "left", render: (r) => r.block ?? "not published" },
  { key: "type", label: "Crime type", sortBy: "primary_type", align: "center", render: (r) => r.primary_type ?? "not published" },
  { key: "desc", label: "Description", align: "left", render: (r) => r.description ?? "not published" },
  { key: "loc", label: "Location", align: "left", render: (r) => r.location_description ?? "not published" },
  { key: "arrest", label: "Arrest", sortBy: "arrest", align: "center", render: (r) => (r.arrest === null ? "not published" : r.arrest ? "Yes" : "No") },
  { key: "beat", label: "Beat", sortBy: "beat", align: "center", render: (r) => r.beat ?? "—" },
  { key: "district", label: "District", sortBy: "district", align: "center", render: (r) => r.district ?? "—" },
  { key: "ward", label: "Ward", sortBy: "ward", align: "center", render: (r) => r.ward ?? "—" },
];

export function IncidentsTable({
  neighborhoodId,
  neighborhoodName,
  year,
}: {
  neighborhoodId: string;
  neighborhoodName: string;
  year: number;
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [filters, setFilters] = useState<IncidentFilters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<IncidentFilters>(EMPTY_FILTERS);
  const [sort, setSort] = useState<IncidentSort>(DEFAULT_SORT);
  const [hour24, setHour24] = useState(false);

  // A new year is a different result set; reset everything that indexes into it.
  useEffect(() => {
    setPage(1);
    setFilters(EMPTY_FILTERS);
    setDraft(EMPTY_FILTERS);
    setSort(DEFAULT_SORT);
  }, [year]);

  const query = useQuery({
    queryKey: ["incidents", neighborhoodId, year, page, pageSize, filters, sort],
    queryFn: ({ signal }) =>
      fetchIncidents(neighborhoodId, year, page, pageSize, filters, sort, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });

  function applyFilters(next: IncidentFilters) {
    setDraft(next);
    setFilters(next);
    setPage(1);
  }
  function clearFilters() {
    setDraft(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }
  function toggleSort(sortBy: IncidentSort["sort_by"]) {
    setSort((prev) =>
      prev.sort_by === sortBy
        ? { sort_by: sortBy, sort_dir: prev.sort_dir === "asc" ? "desc" : "asc" }
        : { sort_by: sortBy, sort_dir: "desc" },
    );
    setPage(1);
  }

  const data = query.data;
  const totalPages = data?.total_pages ?? 0;

  const chips = useMemo(
    () =>
      Object.entries(filters)
        .filter(([, v]) => v)
        .map(([k, v]) => ({ k, v: v as string })),
    [filters],
  );

  const csvHref = incidentsCsvUrl(neighborhoodId, year, filters, sort);

  return (
    <section aria-labelledby="incidents" className="mt-8">
      <h2 id="incidents" className="font-serif text-xl">
        Supporting evidence: reported incidents
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Individual reported incidents from the City of Chicago Crimes dataset spatially assigned
        to {neighborhoodName}. Reports are not convictions. Locations are block-level; exact
        addresses are never shown.
      </p>

      {/* Filters */}
      <div className="mt-4 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-medium">Filter incidents</h3>
          <label className="flex items-center gap-2 text-sm">
            <span>Time format</span>
            <button
              type="button"
              onClick={() => setHour24((v) => !v)}
              className="min-h-11 rounded-md border bg-background px-3 py-2 hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              aria-pressed={hour24}
            >
              {hour24 ? "24-hour" : "12-hour"}
            </button>
          </label>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Search" htmlFor="f-search">
            <input
              id="f-search"
              type="search"
              value={draft.search ?? ""}
              placeholder="block, description, location…"
              onChange={(e) => setDraft({ ...draft, search: e.target.value || undefined })}
              onKeyDown={(e) => e.key === "Enter" && applyFilters(draft)}
              className={inputClass}
            />
          </Field>
          <Field label="Broad category" htmlFor="f-broad">
            <select
              id="f-broad"
              value={draft.broad_category ?? ""}
              onChange={(e) => applyFilters({ ...draft, broad_category: e.target.value || undefined })}
              className={inputClass}
            >
              <option value="">All categories</option>
              {BROAD_CATEGORIES.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Crime type (CPD)" htmlFor="f-type">
            <select
              id="f-type"
              value={draft.primary_type ?? ""}
              onChange={(e) => applyFilters({ ...draft, primary_type: e.target.value || undefined })}
              className={inputClass}
            >
              <option value="">All types</option>
              {CRIME_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Block contains" htmlFor="f-block">
            <input
              id="f-block"
              type="search"
              value={draft.block ?? ""}
              placeholder="e.g. 63RD"
              onChange={(e) => setDraft({ ...draft, block: e.target.value || undefined })}
              onKeyDown={(e) => e.key === "Enter" && applyFilters(draft)}
              onBlur={() => applyFilters(draft)}
              className={inputClass}
            />
          </Field>
          <Field label="Beat" htmlFor="f-beat">
            <input
              id="f-beat"
              type="search"
              value={draft.beat ?? ""}
              placeholder="e.g. 321"
              onChange={(e) => setDraft({ ...draft, beat: e.target.value || undefined })}
              onKeyDown={(e) => e.key === "Enter" && applyFilters(draft)}
              onBlur={() => applyFilters(draft)}
              className={inputClass}
            />
          </Field>
          <Field label="Arrest" htmlFor="f-arrest">
            <select
              id="f-arrest"
              value={draft.arrest ?? ""}
              onChange={(e) =>
                applyFilters({ ...draft, arrest: (e.target.value || undefined) as IncidentFilters["arrest"] })
              }
              className={inputClass}
            >
              <option value="">All</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </Field>
          <Field label="Date from" htmlFor="f-from">
            <input
              id="f-from"
              type="date"
              value={draft.date_from ?? ""}
              onChange={(e) => applyFilters({ ...draft, date_from: e.target.value || undefined })}
              className={inputClass}
            />
          </Field>
          <Field label="Date to" htmlFor="f-to">
            <input
              id="f-to"
              type="date"
              value={draft.date_to ?? ""}
              onChange={(e) => applyFilters({ ...draft, date_to: e.target.value || undefined })}
              className={inputClass}
            />
          </Field>
          <div className="flex items-end gap-2">
            <button type="button" onClick={() => applyFilters(draft)} className={buttonClass}>
              Search
            </button>
            <button type="button" onClick={clearFilters} className={buttonClass}>
              Clear
            </button>
          </div>
        </div>

        {chips.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Active filters">
            {chips.map((chip) => (
              <span key={chip.k} className="inline-flex items-center gap-1 rounded-full border bg-accent/50 px-3 py-1 text-sm">
                {chip.k.replace(/_/g, " ")}: {chip.v}
                <button
                  type="button"
                  aria-label={`Remove ${chip.k} filter`}
                  onClick={() => applyFilters({ ...filters, [chip.k]: undefined })}
                  className="ml-1 rounded-full px-1 hover:bg-background focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* States */}
      {query.isLoading && (
        <p role="status" aria-live="polite" className="mt-4 text-base text-muted-foreground">
          Loading incidents…
        </p>
      )}
      {query.isError && (
        <p role="alert" className="mt-4 rounded-md border bg-card p-4 text-base">
          Incidents could not be loaded: {(query.error as Error).message}. No rows are shown,
          because a placeholder row would be worse than none.
        </p>
      )}

      {data && !query.isError && (
        <>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-base text-muted-foreground" aria-live="polite">
              {formatCount(data.total_records)} matching incident{data.total_records === 1 ? "" : "s"} in {year}
              {data.total_pages > 0 && <> · page {data.page} of {formatCount(data.total_pages)}</>}
              {query.isFetching && <span className="ml-2">Updating…</span>}
            </p>
            <div className="flex items-center gap-3 text-sm">
              <label className="flex items-center gap-2">
                Rows
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                  className="min-h-11 rounded-md border bg-background px-2 py-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  {PAGE_SIZES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </label>
              <a
                href={csvHref}
                className="min-h-11 rounded-md border bg-background px-3 py-2 hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                download
              >
                Export CSV
              </a>
            </div>
          </div>

          {data.records.length === 0 ? (
            <p role="status" className="mt-3 rounded-md border bg-card p-4 text-base">
              No incidents match these filters. That is what the data says — nothing has been
              hidden, and no example rows are shown in place of real ones.
            </p>
          ) : (
            <div className="mt-3 max-h-[70vh] overflow-auto rounded-lg border bg-card">
              <table className="w-full min-w-[64rem] text-sm">
                <caption className="sr-only">
                  Reported incidents in {neighborhoodName}, {year}
                </caption>
                <thead className="sticky top-0 z-10 bg-card">
                  <tr className="border-b text-left">
                    {COLUMNS.map((col) => (
                      <th
                        key={col.key}
                        scope="col"
                        className={`px-3 py-2 ${col.align === "center" ? "text-center" : "text-left"}`}
                        aria-sort={
                          col.sortBy && sort.sort_by === col.sortBy
                            ? sort.sort_dir === "asc"
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                      >
                        {col.sortBy ? (
                          <button
                            type="button"
                            onClick={() => toggleSort(col.sortBy!)}
                            className="inline-flex min-h-11 items-center gap-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                          >
                            {col.label}
                            {sort.sort_by === col.sortBy ? (sort.sort_dir === "asc" ? " ↑" : " ↓") : ""}
                          </button>
                        ) : (
                          col.label
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.records.map((record) => (
                    <tr key={record.id} className="border-b align-top last:border-0">
                      {COLUMNS.map((col) => (
                        <td
                          key={col.key}
                          className={`max-w-[16rem] truncate px-3 py-2 ${
                            col.align === "center" ? "text-center tabular-nums" : "text-left"
                          } ${col.key === "date" ? "whitespace-nowrap" : ""}`}
                          title={typeof col.render(record, hour24) === "string" ? String(col.render(record, hour24)) : undefined}
                        >
                          {col.render(record, hour24)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {totalPages > 1 && (
            <nav aria-label="Incident pages" className="mt-3 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page <= 1}
                className={`${buttonClass} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                Previous
              </button>
              <span className="text-base text-muted-foreground tabular-nums">
                Page {data.page} of {formatCount(totalPages)}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={data.page >= totalPages}
                className={`${buttonClass} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

const inputClass =
  "mt-1 min-h-11 w-full rounded-md border bg-background px-2 py-2 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const buttonClass =
  "min-h-11 rounded-md border bg-background px-4 py-2 text-base hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-base">
        {label}
      </label>
      {children}
    </div>
  );
}
