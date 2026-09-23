import { createFileRoute, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { WireShell, DisclosureNote } from "@/components/WireShell";
import { NotConnectedCard } from "@/components/Pending";
import { QuestionHeader } from "@/components/QuestionHeader";
import { IncidentsTable } from "@/components/IncidentsTable";
import { PulseChart, type ChartMode } from "@/components/PulseChart";
import { useBrief, type BriefItem } from "@/lib/brief";
import { useYear } from "@/lib/useYear";
import { geographyHeadingName, useGeography } from "@/lib/useGeography";
import {
  fetchFreshness,
  fetchPulse,
  formatCount,
  formatPercentChange,
  formatSignedCount,
  isStaleStatus,
  periodLabel,
  residentDate,
  type BeatConcentration,
  type BroadCategoryChange,
  type CrimeFreshness,
  type IssueCard as IssueCardData,
  type MeasurementNotes,
  type PrimaryTypeChange,
  type PulseResponse,
} from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Neighborhood Pulse — Ward 20 Neighborhood Intelligence" },
      {
        name: "description",
        content:
          "What changed in Ward 20 and the neighborhoods within it, where it changed, who is responsible, and what residents can do next. From the City of Chicago Crimes dataset.",
      },
    ],
  }),
  component: Overview,
});

function Overview() {
  // Year and geography are read from the one canonical place each (the URL's `?year` and
  // `?geo`, via useYear / useGeography). The shell renders the switchers; this page just
  // consumes the resolved values.
  const {
    year,
    isLoading: yearsLoading,
    isError: yearsError,
    error: yearsErr,
    isEmpty,
  } = useYear();
  const {
    geographyId,
    geography,
    isLoading: geoLoading,
    isError: geoError,
    error: geoErr,
  } = useGeography();

  const pulseQuery = useQuery({
    queryKey: ["pulse", geographyId, year],
    queryFn: ({ signal }) => fetchPulse(geographyId as string, year as number, signal),
    enabled: year !== null && geographyId !== null,
    retry: false,
    placeholderData: keepPreviousData,
  });

  // How current the data is. A failure here must never hide the page: the banner simply does
  // not render, because a missing freshness check is not a reason to withhold the figures.
  const freshnessQuery = useQuery({
    queryKey: ["freshness"],
    queryFn: ({ signal }) => fetchFreshness(signal),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const data = pulseQuery.data;

  if (yearsLoading || geoLoading) return <LoadingState />;
  if (yearsError) {
    return (
      <ErrorState
        message={yearsErr?.message ?? "The list of available years could not be loaded."}
      />
    );
  }
  if (geoError) {
    return (
      <ErrorState message={geoErr?.message ?? "The list of geographies could not be loaded."} />
    );
  }
  if (isEmpty) {
    return (
      <ErrorState message="No year has completed geography enrichment yet, so there is nothing to show." />
    );
  }
  if (pulseQuery.isError) return <ErrorState message={(pulseQuery.error as Error).message} />;
  if (!data || year === null || geographyId === null) return <LoadingState />;

  return (
    <PulseContent
      data={data}
      isUpdating={pulseQuery.isFetching}
      freshness={freshnessQuery.data ?? null}
      areaShare={geography?.share_of_area_in_ward_pct ?? null}
    />
  );
}

function PulseContent({
  data,
  isUpdating,
  freshness,
  areaShare,
}: {
  data: PulseResponse;
  isUpdating: boolean;
  freshness: CrimeFreshness | null;
  /** Percent of the community area's AREA inside Ward 20 — an area share, not an incident share. */
  areaShare: number | null;
}) {
  const priorYear = data.year - 1;
  const period = periodLabel(data.year, data.is_year_to_date);

  return (
    <WireShell dateThrough={data.provenance.data_through}>
      <FreshnessBanner freshness={freshness} />
      {/* 1. Scope */}
      <section aria-labelledby="scope" className="mb-6">
        <QuestionHeader
          id="scope"
          eyebrow="Neighborhood Pulse"
          question={
            <>
              What changed in{" "}
              {geographyHeadingName(data.neighborhood_name, data.provenance.boundary_type)}
            </>
          }
          lede="What changed in your neighborhood, where it changed, who is responsible, and what residents can do next."
        >
          {/* What place the figures cover — the ward, or only the part of an area inside it.
              This is the one geographic fact a reader must not miss. */}
          <p className="mt-2 max-w-2xl rounded-md border bg-accent/40 p-2 text-sm text-muted-foreground">
            {data.provenance.geography_scope} Comparisons use the{" "}
            <strong>same period last year</strong>, so a partial year is never compared with a
            completed year.
            {areaShare != null && (
              <>
                {" "}
                Because areas differ in size and population, a count here is not comparable with
                another area&apos;s until both are set against the same measure —{" "}
                <strong>counts alone are not a safety ranking</strong>.
              </>
            )}
          </p>
        </QuestionHeader>
      </section>

      {/* The year switcher lives in the shell (top of the page). When a new year is loading,
          say so here rather than swapping the visible figures without warning. */}
      {isUpdating && (
        <p role="status" aria-live="polite" className="mb-6 text-base text-muted-foreground">
          Updating…
        </p>
      )}

      {/* 2. Headline */}
      <section aria-labelledby="headline" className="mb-8">
        <p className="wire-label mb-2">The headline</p>
        <h2 id="headline" className="font-serif text-xl leading-snug sm:text-2xl">
          {data.headline}
        </h2>
        {data.is_year_to_date && (
          <p className="mt-3 rounded-md border bg-caution/20 p-3 text-base" role="note">
            <strong>{data.year} year-to-date.</strong> Figures cover January 1 through{" "}
            {residentDate(data.provenance.data_through)} and will keep rising as the year continues.
          </p>
        )}
        {data.measurement?.provisional_period && (
          <p
            className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-base"
            role="note"
          >
            <strong>Provisional.</strong> This period ends close to the newest data the City has
            published, and records are still arriving for it. Counts will rise, and an apparent
            decline may shrink as late reports land.
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
      <MeasurementStrip measurement={data.measurement} />

      <DataTrust data={data} period={period} />
    </WireShell>
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
      <CategoryCard
        label="Largest reported increase"
        category={data.largest_increase}
        period={comp}
      />
      <CategoryCard
        label="Largest reported decline"
        category={data.largest_decline}
        period={comp}
      />
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
        {data.provenance.source_dataset_id}). A record is counted only when its published
        coordinates fall inside the boundary: {data.provenance.boundary_source}. The ward map is the{" "}
        {data.provenance.ward_vintage} map, applied to every year so years are comparable. Broad
        categories partition every report into one bucket and are defined in the published
        methodology. The most recent weeks are usually incomplete.
      </DisclosureNote>
    </section>
  );
}

// -- 6. beat concentration -------------------------------------------------------------

function BeatConcentrationSection({ data, period }: { data: PulseResponse; period: string }) {
  // Every beat is reachable. Truncating to a top-N hid 13 of 21 beats, which made a beat look
  // absent when it was only ranked low.
  const [showAll, setShowAll] = useState(false);
  const all = data.beats;
  const beats = showAll ? all : all.slice(0, 8);
  const max = Math.max(...beats.map((b) => b.current), 1);
  if (all.length === 0) return null;
  // Almost every beat spills over the boundary by a record or two, so counting any overlap
  // would report "23 of 23" and teach the reader to ignore the notice. Only beats that are
  // MATERIALLY outside are counted — the ones where the local figure is a small slice of the
  // beat a CPD beat meeting actually covers.
  const straddling = all.filter(
    (b) => b.share_of_beat_inside != null && b.share_of_beat_inside < MOSTLY_INSIDE,
  ).length;

  return (
    <section aria-labelledby="concentration" className="mt-8">
      <h2 id="concentration" className="font-serif text-xl">
        Where incidents concentrate
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Reported incidents by police beat in {data.neighborhood_name}, {period}. A larger share does
        not by itself measure police performance.
      </p>
      {straddling > 0 && (
        <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-base">
          <strong>These counts are clipped to {data.neighborhood_name}.</strong> {straddling} of{" "}
          {all.length} beats listed reach materially beyond it — for some, most of the beat is
          outside — so the “whole beat” column shows the figure a CPD beat meeting for that beat
          would use. Beat rows use the beat CPD published on each record; ward and neighborhood
          figures use the mapped location, and the two disagree for about one record in nine.
        </p>
      )}
      <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[40rem] text-base">
          <caption className="sr-only">Reported incidents by beat, {period}</caption>
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-3 py-2 text-center">
                Beat
              </th>
              <th scope="col" className="px-3 py-2">
                This period
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                In {data.neighborhood_name}
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Whole beat
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Share
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {beats.map((b) => (
              <tr key={b.beat} className="border-b last:border-0">
                <th scope="row" className="px-3 py-2 text-center font-medium tabular-nums">
                  {b.beat_display}
                </th>
                <td className="px-3 py-2">
                  <div
                    className="h-3 rounded-sm bg-primary/80"
                    style={{ width: `${(b.current / max) * 100}%`, minWidth: 4 }}
                  />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCount(b.current)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.whole_beat_current != null ? (
                    <>
                      {formatCount(b.whole_beat_current)}
                      {b.share_of_beat_inside != null && b.share_of_beat_inside < MOSTLY_INSIDE && (
                        <span className="ml-1 whitespace-nowrap text-sm text-muted-foreground">
                          (only {Math.round(b.share_of_beat_inside * 100)}% here)
                        </span>
                      )}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{Math.round(b.share * 100)}%</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.absolute_change !== null ? formatSignedCount(b.absolute_change) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {all.length > 8 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 text-base underline underline-offset-4"
        >
          {showAll ? "Show the 8 largest beats" : `Show all ${all.length} beats`}
        </button>
      )}
    </section>
  );
}

// A beat at or above this share of its activity inside the selected geography is treated as
// local for disclosure purposes; below it, the whole-beat figure is materially different.
const MOSTLY_INSIDE = 0.95;

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
  // Every crime type present in the data is reachable. A top-12 cut hid 14 of 26 types, which
  // made a rare type (PROSTITUTION had 1 report in Ward 20 in 2025) look like missing data.
  const [showAll, setShowAll] = useState(false);
  const ranked = [...drivers].sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0));
  const sorted = showAll ? ranked : ranked.slice(0, 12);
  const enforcementShown = sorted.some((d) => d.enforcement_generated);

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
        the specific CPD types behind the broad categories above. A type with no reports shows zero
        — that is a count, not missing data.
      </p>
      {enforcementShown && (
        <p className="mt-2 rounded-md border border-sky-500/40 bg-sky-500/10 p-3 text-base">
          Rows marked <strong>enforcement-led</strong> are recorded almost only when police act on
          them, so the count follows enforcement activity rather than how often the behaviour
          happens. A fall can mean less enforcement, not less behaviour.
        </p>
      )}
      <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[46rem] text-base">
          <caption className="sr-only">Crime types by change, {period}</caption>
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-3 py-2">
                Crime type
              </th>
              <th scope="col" className="px-3 py-2">
                Broad category
              </th>
              {header("current", "This period")}
              {header("prior", "Prior period")}
              {header("absolute_change", "Change")}
              {header("percent_change", "% change")}
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => (
              <tr key={d.primary_type} className="border-b last:border-0">
                <th scope="row" className="px-3 py-2 font-normal">
                  {d.primary_type}
                  {d.enforcement_generated && (
                    <span className="ml-2 whitespace-nowrap rounded border border-sky-500/50 px-1.5 py-0.5 text-sm text-muted-foreground">
                      enforcement-led
                    </span>
                  )}
                </th>
                <td className="px-3 py-2 text-muted-foreground">{d.broad_label}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCount(d.current)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {d.prior !== null ? formatCount(d.prior) : "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatSignedCount(d.absolute_change)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatPercentChange(d.percent_change)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ranked.length > 12 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 text-base underline underline-offset-4"
        >
          {showAll ? "Show the 12 largest changes" : `Show all ${ranked.length} crime types`}
        </button>
      )}
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
            A printable one-page brief with what changed, questions to ask, and who is responsible.{" "}
            {brief.items.length > 0 && <strong>{brief.items.length} issue(s) ready.</strong>}
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
          <NotConnectedCard key={item.label} label={item.label} source={item.source} />
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
          Source: {data.provenance.source_dataset_name} ({data.provenance.source_dataset_id}), City
          of Chicago. Last refreshed {data.provenance.last_refresh}. Data through{" "}
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
        <li>
          Raw-data integrity check: {q.bronze_integrity_verified ? "verified" : "not verified"}.
        </li>
        <li>
          Geography: {data.provenance.geography_scope} Boundary source:{" "}
          {data.provenance.boundary_source}({data.provenance.ward_vintage} ward map). A neighborhood
          figure here is never the figure for the whole community area.
        </li>
        <li>
          Reports are not convictions, records may be revised after publication, and exact addresses
          are masked to the block. Wards, community areas, police beats, and census tracts are
          different boundaries.
        </li>
        <li>
          A neighborhood without a validated boundary is shown as unavailable, and its absence is
          not a count of zero.
        </li>
      </ul>
    </section>
  );
}

// -- states ----------------------------------------------------------------------------

/**
 * How current the data is. Rendered at the top of the page because a resident reading a figure
 * needs to know it is 16 days old before they read it, not after. Renders nothing when the
 * check is unavailable or the data is current — a banner that always shows gets ignored.
 */
function FreshnessBanner({ freshness }: { freshness: CrimeFreshness | null }) {
  if (!freshness || !isStaleStatus(freshness.status)) return null;

  const label =
    freshness.status === "refresh_failed"
      ? "The last update attempt failed."
      : freshness.status === "never_refreshed"
        ? "This data has not been updated since it was first loaded."
        : "This data is not up to date.";

  return (
    <div
      role="status"
      className="mb-6 rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-base"
    >
      <strong>{label}</strong>{" "}
      {freshness.data_through && (
        <>
          The most recent reported incident is from {residentDate(freshness.data_through)}
          {freshness.days_behind != null ? `, ${freshness.days_behind} days ago` : ""}.{" "}
        </>
      )}
      {freshness.source_lag_days != null && (
        <>The City withholds roughly the last {freshness.source_lag_days} days. </>
      )}
      Figures below are the latest available, not today&apos;s.
    </div>
  );
}

/**
 * Properties of the dataset that could explain part of a pattern. This is deliberately plain
 * and unstyled-as-a-warning: none of it means anything is wrong, only that a reader should know
 * which differences come from how the records are made rather than from the neighbourhood.
 */
function MeasurementStrip({ measurement }: { measurement: MeasurementNotes | null }) {
  if (!measurement || measurement.notes.length === 0) return null;
  return (
    <section aria-labelledby="measurement" className="mt-8">
      <h2 id="measurement" className="font-serif text-xl">
        How these records are made
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        None of the following means a figure is wrong. They are properties of the dataset, so a
        reader can tell a change in the neighborhood from a change in the measurement.
      </p>
      <ul className="mt-3 space-y-2 rounded-lg border bg-card p-4 text-base">
        {measurement.notes.map((note) => (
          <li key={note} className="flex gap-2">
            <span aria-hidden="true" className="text-muted-foreground">
              •
            </span>
            <span>{note}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LoadingState() {
  return (
    <WireShell>
      <div role="status" aria-live="polite" className="py-12 text-center">
        <p className="font-serif text-xl">Loading Ward 20 data…</p>
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
