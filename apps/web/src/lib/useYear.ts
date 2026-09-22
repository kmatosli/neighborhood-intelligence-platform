/**
 * The one place year lives.
 *
 * Year is a primary analytical context, so it belongs in the URL: `/?year=2024` is
 * shareable, bookmarkable, and survives back/forward and a refresh. The root route validates
 * `?year` and `retainSearchParams` keeps it attached while a reader moves between sections,
 * so this hook never needs its own store — the URL is the single source of truth, and every
 * page that shows or sets the year reads it through here.
 *
 * The list of selectable years is never hardcoded: it comes from `/api/v1/years`, the years
 * the backend can actually answer. When no valid year is in the URL, the effective year is
 * the latest enriched year — the same default the Overview page used before this hook.
 */

import { useCallback } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { fetchEnrichedYears } from "@/lib/api";

export type YearState = {
  /** The effective year, or null while the year list is still loading. */
  year: number | null;
  /** Update the URL's `?year`, staying on the current page. */
  setYear: (year: number) => void;
  /** Selectable years from the API, newest last. Empty until loaded. */
  years: number[];
  /** The newest enriched year, or null before the list loads. */
  latest: number | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  /** True once the list has loaded and the backend reports no answerable years. */
  isEmpty: boolean;
};

export function useYear(): YearState {
  // `strict: false` reads the search params regardless of which route is rendering the hook,
  // so the shared shell and any page resolve the same value.
  const search = useSearch({ strict: false }) as { year?: number };
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["years"],
    queryFn: ({ signal }) => fetchEnrichedYears(signal),
    retry: false,
  });

  const years = query.data?.years ?? [];
  const latest = query.data?.latest ?? null;

  // A year in the URL is honoured only if the backend can actually answer it; anything else
  // (missing, malformed, or a year with no data) falls back to the latest enriched year
  // rather than requesting a year that would 404.
  const requested = search.year;
  const year = requested != null && years.includes(requested) ? requested : latest;

  const setYear = useCallback(
    (next: number) => {
      // This hook runs on several routes, so useNavigate() is unparameterized and TanStack
      // cannot infer the target route's search shape — it types the reducer's return as
      // `never`. The update is a plain merge onto the validated root search (`?year`), so cast
      // the options to navigate's own parameter type rather than threading a per-route `from`.
      navigate({
        search: (prev: Record<string, unknown>) => ({ ...prev, year: next }),
      } as Parameters<typeof navigate>[0]);
    },
    [navigate],
  );

  return {
    year,
    setYear,
    years,
    latest,
    isLoading: query.isLoading,
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
    isEmpty: query.data != null && years.length === 0,
  };
}
