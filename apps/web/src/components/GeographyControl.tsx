/**
 * The global geography switcher: Ward 20 overall, or an area within Ward 20.
 *
 * It reads and writes the one canonical geography (the URL's `?geo`, via useGeography), so
 * switching here changes the place everywhere and the choice survives navigation and reload.
 * A native <select> for the same reasons as YearControl: keyboard accessible, screen-reader
 * friendly, and the best small-screen control without reimplementing a listbox.
 *
 * A geography that cannot be shown yet (no validated boundary) stays in the list, disabled,
 * with its reason available below — it is never silently dropped and never silently replaced
 * by a neighbour's figures.
 */

import { geographyOptionLabel, useGeography } from "@/lib/useGeography";

export function GeographyControl() {
  const { geographyId, setGeography, geographies, isLoading, isError } = useGeography();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2" aria-busy="true">
        <span className="wire-label">Geography</span>
        <span role="status" className="text-sm text-muted-foreground">
          Loading geographies…
        </span>
      </div>
    );
  }

  if (isError || geographyId === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="wire-label">Geography</span>
        <span role="status" className="text-sm text-muted-foreground">
          Geography list unavailable
        </span>
      </div>
    );
  }

  const pending = geographies.filter((g) => !g.available);

  return (
    <div className="flex min-w-0 max-w-full items-center gap-2">
      <label htmlFor="geography-control" className="wire-label shrink-0">
        Geography
      </label>
      <select
        id="geography-control"
        value={geographyId}
        onChange={(event) => setGeography(event.target.value)}
        aria-describedby={pending.length ? "geography-pending" : undefined}
        className="min-h-11 min-w-0 rounded-md border bg-card px-2 py-1.5 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {geographies.map((g) => (
          <option key={g.neighborhood_id} value={g.neighborhood_id} disabled={!g.available}>
            {geographyOptionLabel(g)}
            {g.available ? "" : " — not yet available"}
          </option>
        ))}
      </select>
      {pending.length > 0 && (
        <span id="geography-pending" className="sr-only">
          {pending.map((g) => `${g.display_name}: ${g.reason ?? "Not yet available."}`).join(" ")}
        </span>
      )}
    </div>
  );
}
