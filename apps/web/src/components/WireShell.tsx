import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import type { NeighborhoodAvailability } from "@/lib/api";

const NAV = [
  { to: "/", label: "Overview", question: "What changed?" },
  { to: "/trends", label: "Trends", question: "Is it getting better or worse?" },
  {
    to: "/authority",
    label: "Services & Accountability",
    question: "Are services delivered, and is the alderperson using their tools?",
  },
  { to: "/beat-meeting", label: "Beat Meeting", question: "What should residents ask?" },
  {
    to: "/community-change",
    label: "Community Change",
    question: "How is the neighborhood changing?",
  },
] as const;

export function WireShell({
  children,
  neighborhood = "Woodlawn",
  dateThrough,
  neighborhoods,
}: {
  children: ReactNode;
  neighborhood?: string;
  /** Real "data through" date from the API. Omitted until the data says. */
  dateThrough?: string;
  /** Availability comes from the API, which reads the same config as the pipeline. */
  neighborhoods?: NeighborhoodAvailability[];
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const options: NeighborhoodAvailability[] = neighborhoods ?? [
    { neighborhood_id: "woodlawn", display_name: "Woodlawn", available: true, reason: null },
    {
      neighborhood_id: "bronzeville",
      display_name: "Bronzeville",
      available: false,
      reason: "Boundary pending approval.",
    },
  ];

  const bronzeville = options.find((n) => n.neighborhood_id === "bronzeville");
  const compareBlocked = !bronzeville?.available;

  return (
    <div className="min-h-dvh bg-background text-foreground">
      {/* Development-data notice. Not "LIVE" — the data lags and is under review. */}
      <div
        className="w-full border-b bg-caution/30 px-4 py-1.5 text-center text-xs font-medium text-caution-foreground"
        role="note"
      >
        Development preview — reported crime data under review. Not for official public use.
      </div>

      <header className="border-b bg-paper">
        <div className="mx-auto max-w-5xl px-4 py-3">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:flex sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="wire-label">South Side Civic Data · v0.1</div>
              <div className="truncate font-serif text-lg font-semibold">
                Bronzeville &amp; Woodlawn Watch
              </div>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Facts about safety, community change, and public accountability.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <label className="wire-label sr-only" htmlFor="nbhd">
                Neighborhood
              </label>
              <select
                id="nbhd"
                defaultValue={neighborhood}
                className="min-h-11 rounded-md border bg-card px-2 py-1.5 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                aria-describedby={compareBlocked ? "nbhd-note" : undefined}
              >
                {options.map((option) => (
                  <option
                    key={option.neighborhood_id}
                    value={option.display_name}
                    disabled={!option.available}
                  >
                    {option.display_name}
                    {option.available ? "" : ` — ${option.reason ?? "Unavailable."}`}
                  </option>
                ))}
                {/* Compare needs both neighborhoods. It stays disabled until Bronzeville
                    has an approved boundary. */}
                <option value="Compare" disabled={compareBlocked}>
                  Compare
                  {compareBlocked ? " — Boundary pending approval." : ""}
                </option>
              </select>
            </div>
          </div>

          {compareBlocked && (
            <p id="nbhd-note" className="mt-2 text-sm text-muted-foreground">
              Bronzeville is unavailable: <strong>Boundary pending approval.</strong> No Bronzeville
              figures are shown, and its absence is not a count of zero.
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {dateThrough && <span>Data through {dateThrough}</span>}
          </div>
        </div>

        <nav aria-label="Primary" className="mx-auto max-w-5xl px-2 pb-1">
          <ul className="flex gap-1 overflow-x-auto">
            {NAV.map((n) => {
              const active = pathname === n.to;
              return (
                <li key={n.to} className="shrink-0">
                  <Link
                    to={n.to}
                    className={
                      "block min-h-11 rounded-t-md border-b-2 px-3 py-2 text-base transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
                      (active
                        ? "border-primary font-semibold text-primary"
                        : "border-transparent text-muted-foreground hover:text-foreground")
                    }
                  >
                    <span className="block leading-tight">{n.label}</span>
                    <span className="block text-[13px] font-normal opacity-70">{n.question}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>

      <footer className="border-t bg-paper">
        <div className="mx-auto max-w-5xl px-4 py-6 text-sm text-muted-foreground">
          <p>
            Counts are reported incidents from the City of Chicago Crimes dataset (ijzp-q8t2).
            Reports are not convictions, and records may be revised after publication.
          </p>
          <p className="mt-1">
            Geographies shown are distinct: neighborhoods (community areas) differ from wards,
            police beats, and census tracts. Exact addresses are never shown.
          </p>
        </div>
      </footer>
    </div>
  );
}

export function DisclosureNote({ children }: { children: ReactNode }) {
  return (
    <details className="mt-3 rounded-md border bg-card px-3 py-2 text-base">
      <summary className="min-h-11 cursor-pointer py-2 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        See how we calculated this
      </summary>
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
        <div className="text-base text-muted-foreground">{children ?? label}</div>
      </div>
    </div>
  );
}
