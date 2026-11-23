/**
 * Crime Trends → 1 · Change. Live data only, from GET /api/v1/trends/{geo}/change.
 *
 * Answers, in order: what changed; which crime types account for it (every type, reconciled
 * to the total); the counts underneath; whether it is part of a longer movement; how this
 * calendar span compares with earlier years; whether the period is provisional; whether a
 * retained earlier release revised it; whether the direction depends on the comparison window;
 * and whether the mix of crime changed even if the total did not.
 *
 * Rules carried from the API: counts always lead and every percentage sits beside its counts;
 * overlays are never stacked as parts of a whole; nothing here says why a number moved.
 */

import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchChange,
  formatCount,
  formatPercentChange,
  formatShare,
  formatSignedCount,
  isStaleStatus,
  periodRange,
  residentDate,
  type ChangeResponse,
  type ChangeWindowKind,
  type CompositionYear,
} from "@/lib/api";

const WINDOW_OPTIONS: { kind: ChangeWindowKind; label: string }[] = [
  { kind: "ytd", label: "Year to date" },
  // The API key stays `t12m`; the comparison is two equal 365-day periods (owner, 2026-10-28).
  { kind: "t12m", label: "Trailing 365 days vs previous 365 days" },
  { kind: "full_year", label: "Latest complete year" },
];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const BAR_COLOR = "#1f6f8b";
const PARTIAL_COLOR = "#c8d6db";

function useMounted(): boolean {
  // recharts needs a measured width; render charts only after mount (no SSR mismatch).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split(" ")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function ChangeSection({ geographyId, year }: { geographyId: string; year: number }) {
  const [windowKind, setWindowKind] = useState<ChangeWindowKind>("ytd");
  const query = useQuery({
    queryKey: ["trends-change", geographyId, year, windowKind],
    queryFn: ({ signal }) => fetchChange(geographyId, year, windowKind, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });

  return (
    <section aria-labelledby="change" className="mb-12">
      <p className="wire-label mb-1">Section 1</p>
      <h2 id="change" className="font-serif text-2xl">
        Change
      </h2>
      <p className="mt-1 max-w-2xl text-base text-muted-foreground">
        What changed, which crime types account for it, and how it compares with earlier years.
        Counts lead; percentages are shown only beside the counts they come from.
      </p>

      <fieldset className="mt-4">
        <legend className="text-sm font-medium">Compare</legend>
        <div className="mt-1 flex flex-wrap gap-2" role="radiogroup" aria-label="Comparison window">
          {WINDOW_OPTIONS.map((option) => (
            <label
              key={option.kind}
              className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                windowKind === option.kind ? "border-foreground bg-muted font-medium" : ""
              }`}
            >
              <input
                type="radio"
                name="change-window"
                value={option.kind}
                checked={windowKind === option.kind}
                onChange={() => setWindowKind(option.kind)}
                className="sr-only"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      {query.isLoading && <p className="mt-4 text-base text-muted-foreground">Loading…</p>}
      {query.isError && (
        <p role="alert" className="mt-4 rounded-md border border-destructive/50 p-3 text-base">
          {query.error instanceof Error ? query.error.message : "The analysis could not be loaded."}
        </p>
      )}
      {query.data && <ChangeBody data={query.data} />}
    </section>
  );
}

function ChangeBody({ data }: { data: ChangeResponse }) {
  if (data.analysis_status !== "ok") {
    const heading =
      data.analysis_status === "aggregates_stale"
        ? "The analysis is out of date with the data and is not shown."
        : data.analysis_status === "window_unavailable"
          ? "This comparison cannot be made from the published data."
          : "The analysis is not available for this data release.";
    return (
      <div role="status" className="mt-4 rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
        <strong>{heading}</strong> <span className="text-base">{data.unavailable_reason}</span> No
        figure is shown rather than one that may not match the records.
      </div>
    );
  }
  const identity = data.identity!;
  const window = data.window!;
  const decomposition = data.decomposition!;
  const total = decomposition.total;

  return (
    <div className="mt-4 space-y-8">
      <IdentityStrip data={data} />

      {/* What changed? */}
      <div className="rounded-lg border bg-card p-4">
        <p className="wire-label">What changed</p>
        <p className="mt-1 font-serif text-xl">
          {formatCount(total.current)} reported incidents in {periodRange(window.current)}, against{" "}
          {formatCount(total.comparison)} in {periodRange(window.comparison)}:{" "}
          {formatSignedCount(total.absolute_change)}
          {total.percent_change !== null && <> ({formatPercentChange(total.percent_change)})</>}.
        </p>
        {total.percent_withheld_reason && (
          <p className="mt-1 text-sm text-muted-foreground">
            No percentage: {total.percent_withheld_reason}.
          </p>
        )}
        {window.note && <p className="mt-1 text-sm text-muted-foreground">{window.note}</p>}
        <p className="mt-1 text-sm text-muted-foreground">{identity.geography_frame}</p>
      </div>

      <DecompositionTable data={data} />
      <SensitivityTable data={data} />
      <HistoryPanel data={data} />
      <TrendPanel data={data} />
      <CompositionPanel data={data} />
      <RevisionPanel data={data} />

      <section aria-labelledby="change-limits">
        <h3 id="change-limits" className="font-serif text-lg">
          What these figures do not tell you
        </h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-base">
          {data.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function IdentityStrip({ data }: { data: ChangeResponse }) {
  const identity = data.identity!;
  const stale = isStaleStatus(identity.freshness_status);
  return (
    <div className="space-y-2">
      {stale && (
        <div
          role="status"
          className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-base"
        >
          <strong>This data is not up to date.</strong> The most recent reported incident is from{" "}
          {residentDate(identity.data_through)}. Figures below are the latest available, not
          today&apos;s.
        </div>
      )}
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <div>
          <dt className="inline text-muted-foreground">Geography: </dt>
          <dd className="inline">{identity.geography_label}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Data through: </dt>
          <dd className="inline">
            {residentDate(identity.data_through)}
            {identity.provisional && (
              <span
                className="ml-2 rounded border border-amber-600/60 px-1.5 py-0.5 text-xs font-medium"
                title={identity.provisional_rule}
              >
                Provisional
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Source: </dt>
          <dd className="inline">{identity.source}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Data release: </dt>
          <dd className="inline">
            {identity.release_id}
            {identity.release_status !== "release" && " (development)"}
          </dd>
        </div>
      </dl>
      {identity.provisional && (
        <p className="text-sm text-muted-foreground">{identity.provisional_rule}</p>
      )}
    </div>
  );
}

function DecompositionTable({ data }: { data: ChangeResponse }) {
  const decomposition = data.decomposition!;
  const anchor = data.anchors.decomposition ?? "drivers";
  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Which crime types account for the movement
      </h3>
      <p className="mt-1 text-base text-muted-foreground">
        Every crime type reported in either period, largest movement first. A percentage is withheld
        when the comparison count is below {decomposition.min_prior_type}.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-1 pr-2 font-medium">Crime type</th>
              <th className="py-1 pr-2 font-medium">Group</th>
              <th className="py-1 pr-2 text-right font-medium">Now</th>
              <th className="py-1 pr-2 text-right font-medium">Before</th>
              <th className="py-1 pr-2 text-right font-medium">Change</th>
              <th className="py-1 pr-2 text-right font-medium">% change</th>
              <th className="py-1 text-right font-medium">Share of gross movement</th>
            </tr>
          </thead>
          <tbody>
            {decomposition.types.map((t) => (
              <tr key={t.primary_type} className="border-b last:border-0">
                <td className="py-1 pr-2">
                  {titleCase(t.primary_type)}
                  {t.enforcement_generated && (
                    <span
                      className="ml-1 rounded bg-muted px-1 text-xs"
                      title="Recorded mostly when police act"
                    >
                      enforcement-led
                    </span>
                  )}
                </td>
                <td className="py-1 pr-2 text-muted-foreground">{t.broad_label}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{formatCount(t.current)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{formatCount(t.comparison)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {formatSignedCount(t.absolute_change)}
                </td>
                <td
                  className="py-1 pr-2 text-right tabular-nums"
                  title={t.percent_withheld_reason ?? undefined}
                >
                  {formatPercentChange(t.percent_change)}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {formatShare(t.gross_movement_share)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t font-medium">
              <td className="py-1 pr-2">All types</td>
              <td />
              <td className="py-1 pr-2 text-right tabular-nums">
                {formatCount(decomposition.total.current)}
              </td>
              <td className="py-1 pr-2 text-right tabular-nums">
                {formatCount(decomposition.total.comparison)}
              </td>
              <td className="py-1 pr-2 text-right tabular-nums">
                {formatSignedCount(decomposition.total.absolute_change)}
              </td>
              <td className="py-1 pr-2 text-right tabular-nums">
                {formatPercentChange(decomposition.total.percent_change)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {decomposition.reconciles
          ? `The type changes add up exactly to the overall change (${formatSignedCount(decomposition.sum_of_type_changes)}).`
          : "The type changes do not reconcile to the total; treat this table with caution."}{" "}
        {decomposition.gross_movement_note}
      </p>
    </section>
  );
}

function SensitivityTable({ data }: { data: ChangeResponse }) {
  const sensitivity = data.sensitivity!;
  const anchor = data.anchors.sensitivity ?? "windows";
  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Does the direction depend on the comparison?
      </h3>
      <p className="mt-1 text-base text-muted-foreground">
        {sensitivity.directions_agree === true && "All three comparisons point the same way. "}
        {sensitivity.directions_agree === false &&
          "The comparisons point in different directions, so the answer depends on the period chosen. "}
        {sensitivity.note}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-1 pr-2 font-medium">Comparison</th>
              <th className="py-1 pr-2 font-medium">Periods</th>
              <th className="py-1 pr-2 text-right font-medium">Now</th>
              <th className="py-1 pr-2 text-right font-medium">Before</th>
              <th className="py-1 text-right font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {sensitivity.windows.map((w) => (
              <tr key={w.kind} className="border-b last:border-0">
                <td className="py-1 pr-2">
                  {WINDOW_OPTIONS.find((o) => o.kind === w.kind)?.label}
                </td>
                {w.direction === "unavailable" ? (
                  <td colSpan={4} className="py-1 text-muted-foreground">
                    Not available: {w.unavailable_reason}
                  </td>
                ) : (
                  <>
                    <td className="py-1 pr-2 text-muted-foreground">
                      {periodRange(w.current!)} vs {periodRange(w.comparison!)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {formatCount(w.current_total!)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {formatCount(w.comparison_total!)}
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      {formatSignedCount(w.absolute_change)}
                      {w.percent_change !== null && ` (${formatPercentChange(w.percent_change)})`}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HistoryPanel({ data }: { data: ChangeResponse }) {
  const history = data.history!;
  const mounted = useMounted();
  const anchor = data.anchors.history ?? "history";
  const annual = history.annual.map((a) => ({ ...a, label: String(a.year) }));
  const trailing = history.trailing_12_months.map((p) => ({
    ...p,
    label: `${MONTHS[p.month - 1]} ${p.year}`,
  }));
  const partial = history.annual.filter((a) => !a.complete);

  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Is this part of a longer movement?
      </h3>

      <figure className="mt-2 rounded-lg border bg-card p-3">
        <div
          className="h-64 w-full"
          role="img"
          aria-label="Reported incidents per year. The same figures are in the table below."
        >
          {mounted && (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={annual} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip formatter={(value: number) => formatCount(value)} />
                <Bar
                  dataKey="total"
                  name="Reported incidents"
                  isAnimationActive={false}
                  shape={(props: unknown) => {
                    const p = props as {
                      x: number;
                      y: number;
                      width: number;
                      height: number;
                      payload: { complete: boolean };
                    };
                    return (
                      <rect
                        x={p.x}
                        y={p.y}
                        width={p.width}
                        height={p.height}
                        fill={p.payload.complete ? BAR_COLOR : PARTIAL_COLOR}
                      />
                    );
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <figcaption className="mt-2 text-sm text-muted-foreground">
          Reported incidents per calendar year.
          {partial.length > 0 &&
            ` ${partial.map((a) => a.year).join(", ")} is partial (through ${residentDate(partial[partial.length - 1].through)}) and drawn lighter; it is not comparable with a full year.`}
        </figcaption>
      </figure>

      {trailing.length > 0 && (
        <figure className="mt-4 rounded-lg border bg-card p-3">
          <div
            className="h-56 w-full"
            role="img"
            aria-label="Rolling total of the last 12 complete months."
          >
            {mounted && (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trailing} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    interval="preserveStartEnd"
                    minTickGap={40}
                  />
                  <YAxis tick={{ fontSize: 11 }} width={48} />
                  <Tooltip formatter={(value: number) => formatCount(value)} />
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="12-month total"
                    stroke={BAR_COLOR}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <figcaption className="mt-2 text-sm text-muted-foreground">
            Each point is the total of the 12 complete calendar months ending that month (unlike the
            comparison above, which uses equal 365-day periods). The latest point is{" "}
            {formatCount(trailing[trailing.length - 1].total)} (
            {trailing[trailing.length - 1].label}).
          </figcaption>
        </figure>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="mb-1 text-left font-medium">Complete years</caption>
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 pr-2 font-medium">Span</th>
                <th className="py-1 pr-2 text-right font-medium">Lowest</th>
                <th className="py-1 pr-2 text-right font-medium">Median</th>
                <th className="py-1 text-right font-medium">Highest</th>
              </tr>
            </thead>
            <tbody>
              {history.spans.map((s) => (
                <tr key={s.label} className="border-b last:border-0">
                  <td className="py-1 pr-2">
                    {s.label} ({s.first_year}–{s.last_year})
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">{formatCount(s.minimum)}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{formatCount(s.median)}</td>
                  <td className="py-1 text-right tabular-nums">{formatCount(s.maximum)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="mb-1 text-left font-medium">
              The same calendar span in earlier years
              {history.same_span[0] && ` (${history.same_span[0].span_label})`}
            </caption>
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 pr-2 font-medium">Earlier years</th>
                <th className="py-1 pr-2 text-right font-medium">Lowest</th>
                <th className="py-1 pr-2 text-right font-medium">Median</th>
                <th className="py-1 pr-2 text-right font-medium">Highest</th>
                <th className="py-1 text-right font-medium">Now</th>
              </tr>
            </thead>
            <tbody>
              {history.same_span.map((s) => (
                <tr key={s.lookback_years} className="border-b last:border-0">
                  <td className="py-1 pr-2">
                    Previous {s.lookback_years} ({s.values.length} available)
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">
                    {s.minimum === null ? "—" : formatCount(s.minimum)}
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">
                    {s.median === null ? "—" : formatCount(s.median)}
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">
                    {s.maximum === null ? "—" : formatCount(s.maximum)}
                  </td>
                  <td className="py-1 text-right tabular-nums">{formatCount(s.current)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted-foreground">
            A plain comparison with the same dates in earlier years — not a seasonal adjustment.
          </p>
        </div>
      </div>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer">Annual totals as a table</summary>
        <table className="mt-2 w-full max-w-sm text-sm">
          <tbody>
            {history.annual.map((a) => (
              <tr key={a.year} className="border-b last:border-0">
                <td className="py-0.5 pr-2">{a.year}</td>
                <td className="py-0.5 pr-2 text-right tabular-nums">{formatCount(a.total)}</td>
                <td className="py-0.5 text-muted-foreground">
                  {a.complete ? "" : `partial, through ${residentDate(a.through)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

function TrendPanel({ data }: { data: ChangeResponse }) {
  const anchor = data.anchors.trend ?? "trend";
  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Direction across complete years
      </h3>
      <ul className="mt-2 space-y-1 text-base">
        {data.trend.map((t) => (
          <li key={t.span_label}>
            <span className="font-medium">{t.span_label}:</span> {t.label}{" "}
            <span className="text-sm text-muted-foreground">({t.n} years)</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-sm text-muted-foreground">
        Kendall&apos;s tau-b compares every pair of years. A detectable direction is not necessarily
        a large one, and it does not say why totals moved.
      </p>
    </section>
  );
}

function CompositionPanel({ data }: { data: ChangeResponse }) {
  const composition = data.composition!;
  const anchor = data.anchors.composition ?? "composition";
  const [showAll, setShowAll] = useState(false);
  const years = useMemo(() => {
    const all = composition.years;
    if (showAll || all.length <= 6) return all;
    // First year, every fifth year, and the last two complete years.
    const picked = all.filter(
      (y, i) => i === 0 || i >= all.length - 2 || (y.year - all[0].year) % 5 === 0,
    );
    return picked;
  }, [composition.years, showAll]);

  const table = (kind: "partition" | "overlays") => {
    const columns = years[0]?.[kind] ?? [];
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-1 pr-2 font-medium">Year (total)</th>
              {columns.map((c) => (
                <th key={c.key} className="py-1 pr-2 text-right font-medium">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y: CompositionYear) => (
              <tr key={y.year} className="border-b last:border-0">
                <td className="py-1 pr-2">
                  {y.year} ({formatCount(y.total)})
                </td>
                {y[kind].map((s) => (
                  <td key={s.key} className="py-1 pr-2 text-right tabular-nums">
                    {formatCount(s.count)}{" "}
                    <span className="text-muted-foreground">({formatShare(s.share)})</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Did the mix of crime change?
      </h3>
      <p className="mt-1 text-base text-muted-foreground">
        {composition.first_year}–{composition.last_complete_year}, complete years only. Each cell is
        a count and its share of that year&apos;s total.
      </p>
      <h4 className="mt-3 text-sm font-medium">Broad groups (each report in exactly one)</h4>
      {table("partition")}
      <h4 className="mt-4 text-sm font-medium">
        Overlays (overlapping lenses — not parts of the total, never added together)
      </h4>
      {table("overlays")}
      <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
        {composition.overlay_definitions.map((o) => (
          <li key={o.key}>
            <span className="font-medium text-foreground">{o.label}:</span> {o.description}{" "}
            {o.caveats.join(" ")}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-sm text-muted-foreground">{composition.note}</p>
      {composition.years.length > 6 && (
        <button
          type="button"
          className="mt-2 text-sm underline"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? "Show selected years" : `Show all ${composition.years.length} years`}
        </button>
      )}
    </section>
  );
}

function RevisionPanel({ data }: { data: ChangeResponse }) {
  const anchor = data.anchors.revisions ?? "revisions";
  const revisions = data.revisions;
  return (
    <section aria-labelledby={anchor}>
      <h3 id={anchor} className="font-serif text-lg">
        Did a later release revise these figures?
      </h3>
      {!revisions ? (
        <p className="mt-1 text-base text-muted-foreground">{data.revisions_note}</p>
      ) : (
        <>
          <p className="mt-1 text-base">
            Compared with release {revisions.prior_release_id},{" "}
            {formatCount(revisions.incidents_revised)} incidents touching these periods were added,
            withdrawn, reclassified, re-dated or re-placed.
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-1 pr-2 font-medium">Period</th>
                  <th className="py-1 pr-2 text-right font-medium">{revisions.prior_release_id}</th>
                  <th className="py-1 pr-2 text-right font-medium">
                    {revisions.current_release_id}
                  </th>
                  <th className="py-1 text-right font-medium">Entered / left</th>
                </tr>
              </thead>
              <tbody>
                {[revisions.current_period, revisions.comparison_period].map((side) => (
                  <tr key={side.period.start} className="border-b last:border-0">
                    <td className="py-1 pr-2">{periodRange(side.period)}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {formatCount(side.prior_release_total)}
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">
                      {formatCount(side.current_release_total)}
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      +{formatCount(side.entries)} / −{formatCount(side.exits)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{revisions.note}</p>
        </>
      )}
    </section>
  );
}
