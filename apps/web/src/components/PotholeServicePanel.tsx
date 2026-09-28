/**
 * City Services → Potholes. The first complete 311 analytical surface.
 *
 * Its job is to prove the domain works coherently, so it is deliberately plain. What it must not
 * do is let a number appear without the interpretation it needs:
 *
 * - raw and primary counts are shown together, because they mean different things;
 * - a completion time says, on screen, that a closure is not proof of a repair;
 * - portion counts carry each area's share of the ward's land and are not a ranking;
 * - the absence of a street-mileage denominator is stated, so counts are never read as rates.
 */

import { useQuery } from "@tanstack/react-query";
import {
  fetchServiceCategory,
  formatCount,
  MONTH_ABBREVIATIONS,
  residentDate,
  type ServiceCategoryReport,
} from "@/lib/api";

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/** Whole days. "same day" rather than "0 days", which reads as missing rather than immediate. */
function days(value: number): string {
  const whole = Math.round(value);
  return whole === 0 ? "same day" : `${formatCount(whole)} ${whole === 1 ? "day" : "days"}`;
}

/** Describes how long open requests have been open without implying a distribution from one row. */
function openAgeNote(
  count: number,
  median: number | null,
  oldest: number | null,
): string | undefined {
  if (count === 0) return undefined;
  if (count === 1) return oldest === null ? undefined : `Open ${days(oldest)}`;
  if (median === null) return undefined;
  const tail = oldest === null ? "" : `, oldest ${days(oldest)}`;
  return `Median ${days(median)} open${tail}`;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="wire-label">{label}</p>
      <p className="mt-1 font-serif text-xl tabular-nums">{value}</p>
      {note && <p className="mt-1 text-sm text-muted-foreground">{note}</p>}
    </div>
  );
}

function MonthlyBars({ report }: { report: ServiceCategoryReport }) {
  const max = Math.max(...report.monthly.map((m) => m.raw), 1);
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border bg-card p-3">
      <div className="flex min-w-[32rem] items-end gap-2" role="img" aria-label="Requests by month">
        {report.monthly.map((month) => (
          <div key={month.month} className="flex flex-1 flex-col items-center gap-1">
            <span className="text-sm tabular-nums text-muted-foreground">{month.raw}</span>
            <div
              className="w-full rounded-sm bg-primary/80"
              style={{ height: `${Math.max((month.raw / max) * 120, 2)}px` }}
            />
            <span className="text-sm text-muted-foreground">
              {MONTH_ABBREVIATIONS[month.month - 1]}
            </span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        Requests by month
        {report.monthly.length < 12 && (
          <>
            , through {residentDate(report.data_through)}. Months the year has not reached are left
            out rather than shown as zero
          </>
        )}
        . Potholes are seasonal — freeze and thaw drive a spring peak — so a rise in March is
        expected rather than remarkable.
      </p>
    </div>
  );
}

export function PotholeServicePanel({ geographyId, year }: { geographyId: string; year: number }) {
  const query = useQuery({
    queryKey: ["city-services", "potholes", geographyId, year],
    queryFn: ({ signal }) => fetchServiceCategory("potholes", geographyId, year, signal),
    retry: false,
  });

  if (query.isLoading) {
    return (
      <p className="mt-3 text-base text-muted-foreground">Loading pothole service requests…</p>
    );
  }
  if (query.isError) {
    return (
      <div role="alert" className="mt-3 rounded-lg border bg-card p-4">
        <p className="text-base">{(query.error as Error).message}</p>
        <p className="mt-2 text-base text-muted-foreground">
          No figures are shown, because a placeholder number would be worse than none.
        </p>
      </div>
    );
  }
  const report = query.data;
  if (!report) return null;

  const completion = report.completion ?? null;
  const median = numberOrNull(completion?.median_days);
  const p25 = numberOrNull(completion?.p25_days);
  const p75 = numberOrNull(completion?.p75_days);
  const eligible = numberOrNull(completion?.eligible_requests);
  const change = report.prior_counts === null ? null : report.counts.raw - report.prior_counts.raw;
  const openCount = numberOrNull(report.open_ages.count) ?? 0;
  const openMedian = numberOrNull(report.open_ages.median_days);
  const openOldest = numberOrNull(report.open_ages.oldest_days);

  return (
    <div className="mt-4">
      {report.provisional && (
        <p
          role="note"
          className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-base"
        >
          <strong>Provisional.</strong> This period runs to {residentDate(report.data_through)} and
          records are still arriving, so these counts will rise.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Requests submitted"
          value={formatCount(report.counts.raw)}
          note="Every submission, including duplicates"
        />
        <Stat
          label="Primary requests"
          value={formatCount(report.counts.primary)}
          note={`${formatCount(report.counts.duplicates)} flagged as duplicates of another`}
        />
        <Stat
          label={`vs the same period in ${report.year - 1}`}
          value={
            report.prior_counts === null
              ? "—"
              : `${change !== null && change > 0 ? "+" : change !== null && change < 0 ? "−" : ""}${formatCount(Math.abs(change ?? 0))}`
          }
          note={
            report.prior_period_end
              ? `Compared with January 1 – ${residentDate(report.prior_period_end)}`
              : "No comparable prior period"
          }
        />
        <Stat
          label="Still open"
          value={formatCount(openCount)}
          note={openAgeNote(openCount, openMedian, openOldest)}
        />
      </div>

      {/* Street and alley are different assets and would need different exposure measures. */}
      {Object.keys(report.subcategories).length > 0 && (
        <p className="mt-3 text-base text-muted-foreground">
          {Object.entries(report.subcategories)
            .map(([key, count]) => `${formatCount(count)} ${key}`)
            .join(" · ")}
        </p>
      )}

      <MonthlyBars report={report} />

      {completion !== null && median !== null && (
        <section className="mt-4 rounded-lg border bg-card p-4">
          <h4 className="font-serif text-lg">How long requests stayed open</h4>
          <p className="mt-1 text-base">
            Median <strong>{days(median)}</strong> from request to closure
            {p25 !== null && p75 !== null && (
              <>
                {" "}
                · middle half between {days(p25)} and {days(p75)}
              </>
            )}
            {eligible !== null && <> · {formatCount(eligible)} requests counted</>}
          </p>
          {/* The limitation that matters most, on screen rather than filed elsewhere. */}
          <p className="mt-2 text-base text-muted-foreground">
            {String(completion.interpretation ?? "")}
          </p>
        </section>
      )}

      {report.portions.length > 0 && (
        <section className="mt-4">
          <h4 className="font-serif text-lg">Where requests came from</h4>
          <p className="mt-1 text-base text-muted-foreground">
            Parts of community areas inside Ward 20. These areas differ in size, so this is not a
            ranking of how well each is served.
          </p>
          <div className="mt-2 overflow-x-auto rounded-lg border bg-card">
            <table className="w-full min-w-[34rem] text-base">
              <thead>
                <tr className="border-b text-left">
                  <th scope="col" className="px-3 py-2">
                    Area
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    Requests
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    Primary
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    Share of requests
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    Share of ward land
                  </th>
                </tr>
              </thead>
              <tbody>
                {report.portions.map((portion) => (
                  <tr key={String(portion.geography_id)} className="border-b last:border-0">
                    <th scope="row" className="px-3 py-2 font-normal">
                      {String(portion.label)}
                    </th>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCount(numberOrNull(portion.raw) ?? 0)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCount(numberOrNull(portion.primary) ?? 0)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {numberOrNull(portion.share_of_ward_requests) !== null
                        ? `${Math.round((portion.share_of_ward_requests as number) * 100)}%`
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {numberOrNull(portion.share_of_ward_area_pct) !== null
                        ? `${Math.round(portion.share_of_ward_area_pct as number)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="mt-4 rounded-lg border bg-card p-4">
        <h4 className="font-serif text-lg">How to read this</h4>
        <ul className="mt-2 space-y-1 text-base">
          {report.methodology.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-muted-foreground">
          {Object.entries(report.excluded_from_analysis).length > 0 && (
            <>
              Excluded from these figures:{" "}
              {Object.entries(report.excluded_from_analysis)
                .map(([reason, count]) => `${formatCount(count)} ${reason.replace(/_/g, " ")}`)
                .join(", ")}
              .{" "}
            </>
          )}
          The ward recorded on the request differs from its mapped location for{" "}
          {formatCount(report.source_ward_disagreement)} records this year.
          {report.denominator === null && (
            <> No street-mileage denominator is available, so these are counts, not rates.</>
          )}
        </p>
      </section>
    </div>
  );
}
