import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";

const NAV = [
  { to: "/", label: "Overview", question: "What changed?" },
  { to: "/trends", label: "Trends", question: "Is it getting better or worse?" },
  { to: "/beat-meeting", label: "Beat Meeting", question: "What should residents ask?" },
  { to: "/community-change", label: "Community Change", question: "How is the neighborhood changing?" },
] as const;

export function WireShell({
  children,
  neighborhood = "Woodlawn",
  dateThrough = "Data through Dec 31, 2024",
}: {
  children: ReactNode;
  neighborhood?: "Bronzeville" | "Woodlawn" | "Compare";
  dateThrough?: string;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="min-h-dvh bg-background text-foreground">
      {/* Dev build banner */}
      <div
        className="w-full border-b bg-caution/30 px-4 py-1.5 text-center text-xs font-medium text-caution-foreground"
        role="note"
      >
        Development build — wireframe using 2024 Woodlawn sample data. Not for public use.
      </div>

      {/* Header */}
      <header className="border-b bg-paper">
        <div className="mx-auto max-w-5xl px-4 py-3">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:flex sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="wire-label">South Side Civic Data · v0.1</div>
              <div className="truncate font-serif text-lg font-semibold">
                Bronzeville &amp; Woodlawn Neighborhood Brief
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <label className="wire-label sr-only" htmlFor="nbhd">Neighborhood</label>
              <select
                id="nbhd"
                defaultValue={neighborhood}
                className="rounded-md border bg-card px-2 py-1.5 text-sm"
              >
                <option>Bronzeville</option>
                <option>Woodlawn</option>
                <option>Compare</option>
              </select>
              <button
                type="button"
                className="rounded-md border bg-card px-3 py-1.5 text-sm hover:bg-accent"
                aria-label="Share this brief"
              >
                Share
              </button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>{dateThrough}</span>
            <span aria-hidden>·</span>
            <span>
              Data status: <span className="text-foreground">Current</span> (updated nightly from Chicago Data Portal)
            </span>
          </div>
        </div>

        {/* Nav */}
        <nav aria-label="Primary" className="mx-auto max-w-5xl px-2 pb-1">
          <ul className="flex gap-1 overflow-x-auto">
            {NAV.map((n) => {
              const active = pathname === n.to;
              return (
                <li key={n.to} className="shrink-0">
                  <Link
                    to={n.to}
                    className={
                      "block rounded-t-md border-b-2 px-3 py-2 text-sm transition-colors " +
                      (active
                        ? "border-primary font-semibold text-primary"
                        : "border-transparent text-muted-foreground hover:text-foreground")
                    }
                  >
                    <span className="block leading-tight">{n.label}</span>
                    <span className="block text-[11px] font-normal opacity-70">{n.question}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>

      <footer className="border-t bg-paper">
        <div className="mx-auto max-w-5xl px-4 py-6 text-xs text-muted-foreground">
          <p>
            Sample data shown reflects Woodlawn 2024 reports from the Chicago Data Portal
            for wireframe review only. Counts may be revised.
          </p>
          <p className="mt-1">
            Geographies shown are distinct: neighborhoods (community areas) differ from
            wards, police beats, and census tracts.
          </p>
        </div>
      </footer>
    </div>
  );
}

export function DisclosureNote({ children }: { children: ReactNode }) {
  return (
    <details className="mt-3 rounded-md border bg-card px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium">See how we calculated this</summary>
      <div className="mt-2 text-muted-foreground">{children}</div>
    </details>
  );
}

export function WirePanel({
  label,
  height = 160,
  children,
}: {
  label: string;
  height?: number;
  children?: ReactNode;
}) {
  return (
    <div
      className="wire-box flex items-center justify-center rounded-md p-4 text-center"
      style={{ minHeight: height }}
      aria-label={label}
    >
      <div>
        <div className="wire-label">Wireframe</div>
        <div className="text-sm text-muted-foreground">{children ?? label}</div>
      </div>
    </div>
  );
}
