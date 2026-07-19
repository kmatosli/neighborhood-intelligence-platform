import { createFileRoute, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { WireShell, DisclosureNote } from "@/components/WireShell";
import { IncidentsTable } from "@/components/IncidentsTable";
import { PulseChart, type ChartMode } from "@/components/PulseChart";
import { useBrief, type BriefItem } from "@/lib/brief";
import {
  fetchEnrichedYears,
  fetchPulse,
  formatCount,
  formatPercentChange,
  formatSignedCount,
  periodLabel,
  residentDate,
  type BeatConcentration,
  type BroadCategoryChange,
  type IssueCard as IssueCardData,
  type PrimaryTypeChange,
  type PulseResponse,
} from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Neighborhood Pulse — Bronzeville & Woodlawn Watch" },
      {
        name: "description",
        content:
          "What changed in Woodlawn, where it changed, who is responsible, and what residents can do next. From the City of Chicago Crimes dataset.",
      },
    ],
  }),
  component: Overview,
});

const NEIGHBORHOOD = "woodlawn";

function Overview() {
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const yearsQuery = useQuery({
    queryKey: ["years"],
    queryFn: ({ signal }) => fetchEnrichedYears(signal),
    retry: false,
  });

  const year = selectedYear ?? yearsQuery.data?.latest ?? null;

  const pulseQuery = useQuery({
    queryKey: ["pulse", NEIGHBORHOOD, year],
    queryFn: ({ signal }) => fetchPulse(NEIGHBORHOOD, year as number, signal),
    enabled: year !== null,
    retry: false,
    placeholderData: keepPreviousData,
  });

  const years = yearsQuery.data?.years ?? [];
  const data = pulseQuery.data;

  if (yearsQuery.isLoading) return <LoadingState />;
  if (yearsQuery.isError) return <ErrorState message={(yearsQuery.error as Error).message} />;
  if (yearsQuery.data && years.length === 0) {
    return (
      <ErrorState message="No year has completed geography enrichment yet, so there is nothing to show." />
    );
  }
  if (pulseQuery.isError) return <ErrorState message={(pulseQuery.error as Error).message} />;
  if (!data || year === null) return <LoadingState />;

  return (
    <PulseContent
      data={data}
      years={years}
      selectedYear={year}
      onSelectYear={setSelectedYear}
      isUpdating={pulseQuery.isFetching}
    />
  );
}

function PulseContent({
  data,
  years,
  selectedYear,
  onSelectYear,
  isUpdating,
}: {
  data: PulseResponse;
  years: number[];
  selectedYear: number;
  onSelectYear: (year: number) => void;
  isUpdating: boolean;
}) {
  const priorYear = data.year - 1;
  const period = periodLabel(data.year, data.is_year_to_date);

  return (
    <WireShell
      neighborhood={data.neighborhood_name}
      dateThrough={data.provenance.data_through}
      neighborhoods={data.neighborhoods}
    >
      {/* 1. Scope */}
      <section aria-labelledby="scope" className="mb-6">
        <p className="wire-label mb-1">Neighborhood Pulse</p>
        <h1 id="scope" className="font-serif text-2xl leading-snug sm:text-3xl">
          What changed in {data.neighborhood_name}
        </h1>
        <p className="mt-2 max-w-2xl text-base text-muted-foreground">
          What changed in your neighborhood, where it changed, who is responsible, and what
          residents can do next.
        </p>
        <p className="mt-2 max-w-2xl rounded-md border bg-accent/40 p-2 text-sm text-muted-foreground">
          Comparisons on this page use the <strong>same period last year</strong>, so a partial
          year is never compared with a completed year.
        </p>
      </section>

      <YearSelector
        years={years}
        selectedYear={selectedYear}
        onSelectYear={onSelectYear}
        isYearToDate={data.is_year_to_date}
        isUpdating={isUpdating}
      />

      {/* 2. Headline */}
      <section aria-labelledby="headline" className="mb-8">
        <p className="wire-label mb-2">The headline</p>
        <h2 id="headline" className="font-serif text-xl leading-snug sm:text-2xl">
          {data.headline}
        </h2>
        {data.is_year_to_date && (
          <p className="mt-3 rounded-md border bg-caution/20 p-3 text-base" role="note">
            <strong>{data.year} year-to-date.</strong> Figures cover January 1 through{" "}
            {residentDate(data.provenance.data_through)} and will keep rising as the year
            continues.
          </p>
        )}
        {!data.comparison_available && (
          <p className="mt-3 rounded-md border bg-accent/40 p-3 text-base" role="note">
            {data.comparison_note}
          </p>
        )}
      </section>

      {/* 3. Metric cards */}
      <MetricCards data={data} period={period} priorYear={priorYear} />

      {/* 4. Narrative */}
      <section aria-labelledby="narrative" className="mt-8">
        <h2 id="narrative" className="font-serif text-xl">
          What changed in {data.neighborhood_name}
        </h2>
        <p className="mt-2 whitespace-pre-line text-base leading-relaxed">{data.narrative}</p>
      </section>

      {/* 5. Chart */}
      <ChartSection data={data} priorYear={priorYear} />

      {/* 6. Geographic concentration */}
      <BeatConcentrationSection data={data} period={period} />

      {/* 7. Drivers */}
      <DriverTableSection drivers={data.category_drivers} period={period} priorYear={priorYear} />

      {/* 8 + 9. Issues residents should watch (with responsibility + resident action) */}
      <IssueCardsSection issues={data.issues} neighborhood={data.neighborhood_name} />

      {/* 10. Beat meeting */}
      <BeatMeetingCta />

      {/* 11. Community-change context */}
      <CommunityChangeContext />

      {/* 12. Supporting incident table */}
      <IncidentsTable
        neighborhoodId={data.neighborhood_id}
        neighborhoodName={data.neighborhood_name}
        year={data.year}
      />

      {/* 13. Data trust */}
      <DataTrust data={data} period={period} />
    </WireShell>
  );
}

// -- 1. year selector ------------------------------------------------------------------

function YearSelector({
  years,
  selectedYear,
  onSelectYear,
  isYearToDate,
  isUpdating = false,
}: {
  years: number[];
  selectedYear: number;
  onSelectYear: (year: number) => void;
  isYearToDate: boolean;
  isUpdating?: boolean;
}) {
  return (
    <div className="mb-6 rounded-lg border bg-card p-4">
      <label htmlFor="year" className="block text-base font-medium">
        Year
      </label>
      <div className="mt-2 flex items-center gap-3">
        <select
          id="year"
          value={selectedYear}
          onChange={(event) => onSelectYear(Number(event.target.value))}
          className="min-h-11 rounded-md border bg-background px-3 py-2 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {years.map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
        {isUpdating && (
          <span role="status" aria-live="polite" className="text-base text-muted-foreground">
            Updating…
          </span>
        )}
      </div>
      <p className="mt-2 text-base text-muted-foreground">
        Only years the data can fully answer are listed.{" "}
        {isYearToDate && (
          <strong>
            {selectedYear} is a partial year, compared with the same dates a year earlier.
          </strong>
        )}
      </p>
    </div>
  );
}

// -- 3. metric cards -------------------------------------------------------------------

function MetricCards({
  data,
  period,
  priorYear,
}: {
  data: PulseResponse;
  period: string;
  priorYear: number;
}) {
  const comp = data.comparison_available ? `vs same period ${priorYear}` : "no comparison yet";
  const arrestPct = Math.round(data.arrests.percent * 100);

  return (
    <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card
        label="Reported incidents"
        value={formatCount(data.incidents.current)}
        sub={period}
        detail={
          data.incidents.prior !== null
            ? `${formatSignedCount(data.incidents.absolute_change)} vs ${formatCount(data.incidents.prior)}`
            : "Comparison pending"
        }
      />
      <Card
        label="Change vs same period last year"
        value={formatPercentChange(data.incidents.percent_change)}
        sub={comp}
        detail={
          data.incidents.absolute_change !== null
            ? `${formatSignedCount(data.incidents.absolute_change)} reports`
            : "Comparison pending"
        }
      />
      <CategoryCard label="Largest reported increase" category={data.largest_increase} period={comp} />
      <CategoryCard label="Largest reported decline" category={data.largest_decline} period={comp} />
      <BeatCard beat={data.beat_largest_increase} period={comp} />
      <Card
        label="Arrests reported"
        value={`${arrestPct}%`}
        sub={`${formatCount(data.arrests.count)} of ${formatCount(data.arrests.total)} reports`}
        detail="An arrest is recorded on the report. It is not a clearance rate and does not establish prosecution or conviction."
      />
    </section>
  );
}

function Card({
  label,
  value,
  sub,
  detail,
}: {
  label: string;
  value: string;
  sub: string;
  detail: string;
}) {
  return (
    <article className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="wire-label">{label}</h3>
      <div className="mt-2 font-serif text-3xl font-semibold tabular-nums">{value}</div>
      <p className="mt-1 text-sm text-muted-foreground">{sub}</p>
      <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
    </article>
  );
}

function CategoryCard({
  label,
  category,
  period,
}: {
  label: string;
  category: BroadCategoryChange | null;
  period: string;
}) {
  if (!category) {
    return (
      <article className="rounded-lg border bg-card p-4 shadow-sm">
        <h3 className="wire-label">{label}</h3>
        <div className="mt-2 font-serif text-2xl font-semibold text-muted-foreground">—</div>
        <p className="mt-1 text-sm text-muted-foreground">
          No comparison available, so no category change can be shown.
        </p>
      </article>
    );
  }
  return (
    <article className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="wire-label">{label}</h3>
      <div className="mt-2 font-serif text-2xl font-semibold">{category.label}</div>
      <p className="mt-1 text-base tabular-nums">
        {formatSignedCount(category.absolute_change)}{" "}
        <span className="text-muted-foreground">
          ({formatPercentChange(category.percent_change)})
        </span>
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {formatCount(category.current)} now · {period}
      </p>
    </article>
  );
}

function BeatCard({ beat, period }: { beat: BeatConcentration | null; period: string }) {
  if (!beat) {
    return (
      <article className="rounded-lg border bg-card p-4 shadow-sm">
        <h3 className="wire-label">Beat with largest increase</h3>
        <div className="mt-2 font-serif text-2xl font-semibold text-muted-foreground">—</div>
        <p className="mt-1 text-sm text-muted-foreground">
          No beat shows a reliable increase this period.
        </p>
      </article>
    );
  }
  return (
    <article className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="wire-label">Beat with largest increase</h3>
      <div className="mt-2 font-serif text-3xl font-semibold tabular-nums">
        Beat {beat.beat_display}
      </div>
      <p className="mt-1 text-base tabular-nums">
        {formatSignedCount(beat.absolute_change)}{" "}
        <span className="text-muted-foreground">
          to {formatCount(beat.current)} · {period}
        </span>
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        Incident counts alone do not measure police performance.
      </p>
    </article>
  );
}

// -- 5. chart --------------------------------------------------------------------------

const CHART_MODES: { key: ChartMode; label: string }[] = [
  { key: "monthly_vs_prior", label: "Monthly vs prior year" },
  { key: "composition", label: "Category composition" },
  { key: "total", label: "Total incidents" },
];

function ChartSection({ data, priorYear }: { data: PulseResponse; priorYear: number }) {
  const [mode, setMode] = useState<ChartMode>("monthly_vs_prior");
  return (
    <section aria-labelledby="chart" className="mt-8">
      <h2 id="chart" className="font-serif text-xl">
        Trend and composition
      </h2>
      <div role="tablist" aria-label="Chart mode" className="mt-2 flex flex-wrap gap-2">
        {CHART_MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            role="tab"
            aria-selected={mode === m.key}
            onClick={() => setMode(m.key)}
            className={
              "min-h-11 rounded-md border px-3 py-2 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
              (mode === m.key
                ? "border-primary bg-primary/10 font-medium text-primary"
                : "bg-background hover:bg-accent")
            }
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="mt-3">
        <PulseChart
          mode={mode}
          monthlyComparison={data.monthly_comparison}
          monthlyCategories={data.monthly_categories}
          broadCategories={data.broad_categories}
          year={data.year}
          priorYear={priorYear}
          comparisonAvailable={data.comparison_available}
        />
      </div>
      <DisclosureNote>
        Monthly counts come from the City of Chicago Crimes dataset (
        {data.provenance.source_dataset_id}). A record is counted as {data.neighborhood_name} only
        when its published coordinates fall inside the official {data.neighborhood_name}{" "}
        community-area boundary. Broad categories partition every report into one bucket and are
        defined in the published methodology. The most recent weeks are usually incomplete.
      </DisclosureNote>
    </section>
  );
}

// -- 6. beat concentration -------------------------------------------------------------

function BeatConcentrationSection({ data, period }: { data: PulseResponse; period: string }) {
  const beats = data.beats.slice(0, 8);
  const max = Math.max(...beats.map((b) => b.current), 1);
  if (beats.length === 0) return null;

  return (
    <section aria-labelledby="concentration" className="mt-8">
      <h2 id="concentration" className="font-serif text-xl">
        Where incidents concentrate
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Reported incidents by police beat in {data.neighborhood_name}, {period}. A larger share
        does not by itself measure police performance.
      </p>
      <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[40rem] text-base">
          <caption className="sr-only">Reported incidents by beat, {period}</caption>
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-3 py-2 text-center">Beat</th>
              <th scope="col" className="px-3 py-2">This period</th>
              <th scope="col" className="px-3 py-2 text-right">Reports</th>
              <th scope="col" className="px-3 py-2 text-right">Share</th>
              <th scope="col" className="px-3 py-2 text-right">Change</th>
            </tr>
          </thead>
          <tbody>
            {beats.map((b) => (
              <tr key={b.beat} className="border-b last:border-0">
                <th scope="row" className="px-3 py-2 text-center font-medium tabular-nums">
                  {b.beat_display}
                </th>
                <td className="px-3 py-2">
                  <div className="h-3 rounded-sm bg-primary/80" style={{ width: `${(b.current / max) * 100}%`, minWidth: 4 }} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCount(b.current)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{Math.round(b.share * 100)}%</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.absolute_change !== null ? formatSignedCount(b.absolute_change) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// -- 7. drivers ------------------------------------------------------------------------

type DriverSortKey = "current" | "prior" | "absolute_change" | "percent_change";

function DriverTableSection({
  drivers,
  period,
  priorYear,
}: {
  drivers: PrimaryTypeChange[];
  period: string;
  priorYear: number;
}) {
  const [sortKey, setSortKey] = useState<DriverSortKey>("absolute_change");
  const sorted = [...drivers].sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0)).slice(0, 12);

  const header = (key: DriverSortKey, label: string) => (
    <th scope="col" className="px-3 py-2 text-right">
      <button
        type="button"
        onClick={() => setSortKey(key)}
        className={
          "inline-flex min-h-11 items-center gap-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
          (sortKey === key ? "font-semibold text-primary" : "")
        }
        aria-sort={sortKey === key ? "descending" : "none"}
      >
        {label}
        {sortKey === key ? " ↓" : ""}
      </button>
    </th>
  );

  return (
    <section aria-labelledby="drivers" className="mt-8">
      <h2 id="drivers" className="font-serif text-xl">
        Problems driving the change
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Detailed City of Chicago crime types, {period} vs the same period in {priorYear}. These are
        the specific CPD types behind the broad categories above.
      </p>
      <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[46rem] text-base">
          <caption className="sr-only">Crime types by change, {period}</caption>
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-3 py-2">Crime type</th>
              <th scope="col" className="px-3 py-2">Broad category</th>
              {header("current", "This period")}
              {header("prior", "Prior period")}
              {header("absolute_change", "Change")}
              {header("percent_change", "% change")}
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => (
              <tr key={d.primary_type} className="border-b last:border-0">
                <th scope="row" className="px-3 py-2 font-normal">{d.primary_type}</th>
                <td className="px-3 py-2 text-muted-foreground">{d.broad_label}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCount(d.current)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {d.prior !== null ? formatCount(d.prior) : "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatSignedCount(d.absolute_change)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatPercentChange(d.percent_change)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// -- 8 + 9. issue cards ----------------------------------------------------------------

function issueToBrief(issue: IssueCardData): BriefItem {
  return {
    id: `overview:${issue.id}`,
    source: "overview",
    category: issue.kind,
    title: issue.title,
    supportingStat: issue.supporting_stat,
    comparisonPeriod: issue.comparison_period,
    beat: issue.beat,
    primaryAuthority: issue.primary_authority,
    supportingAuthority: issue.supporting_authority,
    alderpersonRole: issue.alderperson_role,
    residentQuestion: issue.suggested_question,
    evidence: issue.evidence,
    addedAt: Date.now(),
  };
}

function IssueCardsSection({
  issues,
  neighborhood,
}: {
  issues: IssueCardData[];
  neighborhood: string;
}) {
  const brief = useBrief();
  if (issues.length === 0) return null;

  return (
    <section aria-labelledby="issues" className="mt-8">
      <h2 id="issues" className="font-serif text-xl">
        Issues residents should watch
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Each is drawn from the counts on this page. No cause is inferred, and each names who is
        responsible and what residents can do.
      </p>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {issues.map((issue) => {
          const id = `overview:${issue.id}`;
          const added = brief.has(id);
          return (
            <article key={issue.id} className="rounded-lg border bg-card p-4 shadow-sm">
              <h3 className="font-serif text-lg font-semibold">{issue.title}</h3>
              <p className="mt-1 text-base">{issue.finding}</p>
              <dl className="mt-3 space-y-1 text-sm">
                <Row term="Supporting figure" desc={issue.supporting_stat} />
                <Row term="Comparison" desc={issue.comparison_period} />
                <Row term="Primary authority" desc={issue.primary_authority} />
                {issue.supporting_authority && (
                  <Row term="Supporting" desc={issue.supporting_authority} />
                )}
                <Row term="Alderperson" desc={issue.alderperson_role} />
                <Row term="Residents can" desc={issue.resident_action} />
                {issue.suggested_question && (
                  <Row term="Ask" desc={`“${issue.suggested_question}”`} />
                )}
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => (added ? brief.remove(id) : brief.add(issueToBrief(issue)))}
                  aria-pressed={added}
                  className={
                    "min-h-11 rounded-md border px-4 py-2 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
                    (added
                      ? "border-primary bg-primary/10 font-medium text-primary"
                      : "bg-background hover:bg-accent")
                  }
                >
                  {added ? "✓ Added to brief" : "Add to brief"}
                </button>
                <Link
                  to="/beat-meeting"
                  className="inline-flex min-h-11 items-center rounded-md border bg-background px-4 py-2 text-base hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  Open my brief
                </Link>
              </div>
            </article>
          );
        })}
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        {brief.items.length > 0
          ? `${brief.items.length} item${brief.items.length === 1 ? "" : "s"} in your brief for ${neighborhood}.`
          : "Add issues to build a brief you can take to your beat meeting."}
      </p>
    </section>
  );
}

function Row({ term, desc }: { term: string; desc: string }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2">
      <dt className="text-muted-foreground">{term}</dt>
      <dd>{desc}</dd>
    </div>
  );
}

// -- 10. beat meeting cta --------------------------------------------------------------

function BeatMeetingCta() {
  const brief = useBrief();
  return (
    <section aria-labelledby="beat-cta" className="mt-8 rounded-lg border bg-accent/50 p-5">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h2 id="beat-cta" className="font-serif text-lg font-semibold">
            Prepare for my beat meeting
          </h2>
          <p className="mt-1 text-base text-muted-foreground">
            A printable one-page brief with what changed, questions to ask, and who is
            responsible.{" "}
            {brief.items.length > 0 && (
              <strong>{brief.items.length} issue(s) ready.</strong>
            )}
          </p>
        </div>
        <Link
          to="/beat-meeting"
          className="inline-flex min-h-11 shrink-0 items-center rounded-md bg-primary px-4 py-2 text-base font-medium text-primary-foreground hover:opacity-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Prepare my brief
        </Link>
      </div>
    </section>
  );
}

// -- 11. community change context ------------------------------------------------------

const COMING_SOON = [
  { label: "Population change", source: "U.S. Census / ACS" },
  { label: "Housing costs", source: "ACS, Cook County Assessor" },
  { label: "Building permits", source: "City of Chicago building permits" },
  { label: "311 service requests", source: "Chicago 311 (CSR) dataset" },
  { label: "Business openings & closures", source: "Business licenses (BACP)" },
  { label: "Transit access", source: "CTA ridership" },
];

function CommunityChangeContext() {
  return (
    <section aria-labelledby="community" className="mt-8">
      <h2 id="community" className="font-serif text-xl">
        Community-change context
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Crime is one domain of neighborhood conditions, not the definition of the neighborhood.
        These sources are not connected yet — no figures are shown.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {COMING_SOON.map((item) => (
          <div key={item.label} className="rounded-lg border border-dashed bg-card/50 p-4">
            <h3 className="text-base font-medium">{item.label}</h3>
            <p className="mt-1 text-sm text-muted-foreground">Data source not yet connected.</p>
            <p className="mt-1 text-sm text-muted-foreground">Intended source: {item.source}.</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// -- 13. data trust --------------------------------------------------------------------

function DataTrust({ data, period }: { data: PulseResponse; period: string }) {
  const q = data.data_quality;
  return (
    <section aria-labelledby="trust" className="mt-8 rounded-lg border bg-card p-4">
      <h2 id="trust" className="font-serif text-lg font-semibold">
        How much to trust these numbers
      </h2>
      <ul className="mt-2 space-y-1 text-base text-muted-foreground">
        <li>
          Source: {data.provenance.source_dataset_name} ({data.provenance.source_dataset_id}),
          City of Chicago. Last refreshed {data.provenance.last_refresh}. Data through{" "}
          {residentDate(data.provenance.data_through)} ({period}).
        </li>
        <li>
          Citywide in {data.year}, {formatCount(q.records_without_coordinates)} of{" "}
          {formatCount(q.total_bronze_records_year)} reported incidents had no coordinates and
          cannot be placed in a neighborhood, so they are not counted here.
        </li>
        <li>
          Records with coordinates outside Chicago: {formatCount(q.records_outside_boundaries)}.
          Unusable coordinates: {formatCount(q.records_invalid_coordinates)}.
        </li>
        <li>Raw-data integrity check: {q.bronze_integrity_verified ? "verified" : "not verified"}.</li>
        <li>
          Reports are not convictions, records may be revised after publication, and exact
          addresses are masked to the block. Neighborhoods (community areas) differ from wards,
          police beats, and census tracts.
        </li>
        <li>
          Bronzeville is not shown: its boundary is pending approval, and its absence is not a
          count of zero.
        </li>
      </ul>
    </section>
  );
}

// -- states ----------------------------------------------------------------------------

function LoadingState() {
  return (
    <WireShell>
      <div role="status" aria-live="polite" className="py-12 text-center">
        <p className="font-serif text-xl">Loading Woodlawn data…</p>
        <p className="mt-2 text-base text-muted-foreground">
          Reading reported incidents from the Chicago Crimes dataset.
        </p>
      </div>
    </WireShell>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <WireShell>
      <div role="alert" className="rounded-lg border bg-card p-6">
        <h1 className="font-serif text-xl font-semibold">This data could not be loaded</h1>
        <p className="mt-2 text-base">{message}</p>
        <p className="mt-3 text-base text-muted-foreground">
          No figures are shown, because a placeholder number would be worse than none. Check that
          the data service is running, then reload the page.
        </p>
      </div>
    </WireShell>
  );
}
