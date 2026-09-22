/**
 * The global year switcher, shown in the shell on pages where year is an active analytical
 * context. It reads and writes the one canonical year (the URL's `?year`, via useYear), so
 * switching here changes the year everywhere and the choice survives navigation and reload.
 *
 * A native <select> is deliberate: it is keyboard accessible, screen-reader friendly, and the
 * best small-screen control the platform can offer without reimplementing a listbox. Every
 * non-normal condition — loading, error, no answerable years — is shown honestly rather than
 * rendering an empty control that looks usable but is not.
 */

import { useYear } from "@/lib/useYear";

export function YearControl() {
  const { year, setYear, years, isLoading, isError, isEmpty } = useYear();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2" aria-busy="true">
        <span className="wire-label">Year</span>
        <span role="status" className="text-sm text-muted-foreground">
          Loading years…
        </span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2">
        <span className="wire-label">Year</span>
        <span role="status" className="text-sm text-muted-foreground">
          Year list unavailable
        </span>
      </div>
    );
  }

  if (isEmpty || year === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="wire-label">Year</span>
        <span role="status" className="text-sm text-muted-foreground">
          No answerable years yet
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="year-control" className="wire-label">
        Year
      </label>
      <select
        id="year-control"
        value={year}
        onChange={(event) => setYear(Number(event.target.value))}
        className="min-h-11 rounded-md border bg-card px-2 py-1.5 text-base tabular-nums focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {/* Newest first so the current year is the easiest to reach. */}
        {[...years].reverse().map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}
