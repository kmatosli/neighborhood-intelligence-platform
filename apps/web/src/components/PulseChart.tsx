import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  BroadCategoryChange,
  MonthlyCategoryPoint,
  MonthlyComparisonPoint,
} from "@/lib/api";
import { formatCount } from "@/lib/api";

export type ChartMode = "monthly_vs_prior" | "composition" | "total";

/** Restrained, distinguishable series colours. Colour never carries meaning alone — every
 * chart has a legend and an accessible table with the same numbers. */
const CATEGORY_COLORS: Record<string, string> = {
  violent_crime: "#9d2b2b",
  property_crime: "#1f6f8b",
  public_order: "#b8860b",
  weapons: "#5b4a8a",
  narcotics: "#3f7d55",
  other: "#6b7280",
};

const CURRENT_COLOR = "#1f6f8b";
const PRIOR_COLOR = "#c8d6db";

function useMounted(): boolean {
  // Charts render only after mount: the SSR pass has no width, and recharts is a client
  // library. This avoids a hydration mismatch and a zero-width first paint.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

function ChartFrame({
  title,
  summary,
  children,
  table,
}: {
  title: string;
  summary: string;
  children: React.ReactNode;
  table: React.ReactNode;
}) {
  return (
    <figure className="rounded-lg border bg-card p-3">
      <div className="h-72 w-full" role="img" aria-label={`${title}. ${summary}`}>
        {children}
      </div>
      <figcaption className="mt-2 text-sm text-muted-foreground">{summary}</figcaption>
      <details className="mt-2 text-sm">
        <summary className="min-h-11 cursor-pointer py-2 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
          View the same data as a table
        </summary>
        <div className="mt-2 overflow-x-auto">{table}</div>
      </details>
    </figure>
  );
}

export function PulseChart({
  mode,
  monthlyComparison,
  monthlyCategories,
  broadCategories,
  year,
  priorYear,
  comparisonAvailable,
}: {
  mode: ChartMode;
  monthlyComparison: MonthlyComparisonPoint[];
  monthlyCategories: MonthlyCategoryPoint[];
  broadCategories: BroadCategoryChange[];
  year: number;
  priorYear: number;
  comparisonAvailable: boolean;
}) {
  const mounted = useMounted();

  if (mode === "monthly_vs_prior") {
    const points = monthlyComparison.filter((p) => p.in_comparison_window);
    const data = points.map((p) => ({
      month: p.month_label,
      [`${year}`]: p.current ?? 0,
      [`${priorYear}`]: p.prior ?? 0,
      partial: p.is_partial_month,
    }));
    const summary = comparisonAvailable
      ? `Reported incidents by month, ${year} versus the equivalent period in ${priorYear}. A hatched final bar marks the current, still-incomplete month.`
      : `Reported incidents by month in ${year}. No prior-year comparison is available yet.`;
    return (
      <ChartFrame title={`Monthly incidents, ${year} vs ${priorYear}`} summary={summary}
        table={
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 pr-4">Month</th>
                <th className="py-1 pr-4 text-right">{year}</th>
                <th className="py-1 text-right">{priorYear}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.month} className="border-b last:border-0">
                  <th scope="row" className="py-1 pr-4 font-normal">
                    {p.month_label}
                    {p.is_partial_month ? " (partial)" : ""}
                  </th>
                  <td className="py-1 pr-4 text-right tabular-nums">{formatCount(p.current ?? 0)}</td>
                  <td className="py-1 text-right tabular-nums">
                    {comparisonAvailable ? formatCount(p.prior ?? 0) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      >
        {mounted && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 16, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" fontSize={12} tickLine={false} />
              <YAxis fontSize={12} width={44} tickLine={false} allowDecimals={false} />
              <Tooltip formatter={(v: number) => formatCount(v)} />
              <Legend />
              {comparisonAvailable && (
                <Bar dataKey={`${priorYear}`} fill={PRIOR_COLOR} radius={[2, 2, 0, 0]} />
              )}
              <Bar dataKey={`${year}`} fill={CURRENT_COLOR} radius={[2, 2, 0, 0]}>
                {data.map((entry, index) => (
                  <Cell key={index} fillOpacity={entry.partial ? 0.55 : 1} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartFrame>
    );
  }

  if (mode === "composition") {
    const keys = broadCategories.map((c) => c.key);
    const labels = Object.fromEntries(broadCategories.map((c) => [c.key, c.label]));
    const data = monthlyCategories.map((p) => ({
      month: p.month_label,
      total: p.total,
      ...p.counts,
    }));
    const summary =
      "Reported incidents by month, split into broad categories. Segments stack to the month total shown above each bar.";
    return (
      <ChartFrame title="Monthly composition by category" summary={summary}
        table={
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 pr-4">Month</th>
                {broadCategories.map((c) => (
                  <th key={c.key} className="py-1 pr-3 text-right">{c.label}</th>
                ))}
                <th className="py-1 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {monthlyCategories.map((p) => (
                <tr key={p.month} className="border-b last:border-0">
                  <th scope="row" className="py-1 pr-4 font-normal">{p.month_label}</th>
                  {broadCategories.map((c) => (
                    <td key={c.key} className="py-1 pr-3 text-right tabular-nums">
                      {formatCount(p.counts[c.key] ?? 0)}
                    </td>
                  ))}
                  <td className="py-1 text-right tabular-nums font-medium">{formatCount(p.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      >
        {mounted && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 20, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="month" fontSize={12} tickLine={false} />
              <YAxis fontSize={12} width={44} tickLine={false} allowDecimals={false} />
              <Tooltip formatter={(v: number, name: string) => [formatCount(v), labels[name] ?? name]} />
              <Legend formatter={(value: string) => labels[value] ?? value} />
              {keys.map((key, index) => (
                <Bar key={key} dataKey={key} stackId="c" fill={CATEGORY_COLORS[key] ?? "#6b7280"}>
                  {index === keys.length - 1 && (
                    <LabelList dataKey="total" position="top" fontSize={11} formatter={(v: number) => formatCount(v)} />
                  )}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartFrame>
    );
  }

  // total
  const points = monthlyCategories;
  const data = points.map((p) => ({ month: p.month_label, total: p.total, partial: p.is_partial_month }));
  const periodTotal = points.reduce((sum, p) => sum + p.total, 0);
  const summary = `One bar per month of reported incidents in ${year}. The months shown add up to ${formatCount(periodTotal)}.`;
  return (
    <ChartFrame title={`Total reported incidents by month, ${year}`} summary={summary}
      table={
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-1 pr-4">Month</th>
              <th className="py-1 text-right">Reported incidents</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.month} className="border-b last:border-0">
                <th scope="row" className="py-1 pr-4 font-normal">{p.month_label}</th>
                <td className="py-1 text-right tabular-nums">{formatCount(p.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {mounted && (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
            <XAxis dataKey="month" fontSize={12} tickLine={false} />
            <YAxis fontSize={12} width={44} tickLine={false} allowDecimals={false} />
            <Tooltip formatter={(v: number) => formatCount(v)} />
            <Bar dataKey="total" fill={CURRENT_COLOR} radius={[2, 2, 0, 0]}>
              <LabelList dataKey="total" position="top" fontSize={11} formatter={(v: number) => formatCount(v)} />
              {data.map((entry, index) => (
                <Cell key={index} fillOpacity={entry.partial ? 0.55 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
