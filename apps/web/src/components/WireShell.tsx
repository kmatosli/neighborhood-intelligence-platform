import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { YearControl } from "@/components/YearControl";
import { GeographyControl } from "@/components/GeographyControl";
import { useGeography } from "@/lib/useGeography";

// The question-oriented navigation: each section is named by the resident question it answers,
// not by a generic technical noun. Preserve this framing — it is the product's point of view.
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

// Routes where geography and year are active analytical contexts, so the shell shows the
// switchers. Coming-soon sections are omitted deliberately: a control that changed nothing
// visible on the page it sits on would read as broken. Add a route here when it starts
// consuming the context.
const CONTEXT_AWARE_ROUTES = new Set<string>(["/"]);

export function WireShell({
  children,
  dateThrough,
}: {
  children: ReactNode;
  /** Real "data through" date from the API. Omitted until the data says. */
  dateThrough?: string;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { unsupported, geography } = useGeography();
  const showContext = CONTEXT_AWARE_ROUTES.has(pathname);

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
          {/* Identity: the neutral working name until the final product name is chosen. It
              wraps on a phone rather than truncating — the name is the geography. */}
          <div className="min-w-0">
            <div className="wire-label">Chicago · Ward 20 · development preview</div>
            <div className="font-serif text-lg font-semibold leading-tight">
              Ward 20 Neighborhood Intelligence
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Facts about safety, community change, and public accountability in Ward 20.
            </p>
          </div>

          {/* Context bar: geography and year (where they act) and the data-through date. It
              wraps instead of overflowing, so it stays usable from 320px up to 200% zoom. */}
          {showContext && (
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
              <GeographyControl />
              <YearControl />
              {dateThrough && (
                <span className="text-sm text-muted-foreground">Data through {dateThrough}</span>
              )}
            </div>
          )}

          {/* A `?geo` the API cannot answer is never silently swapped for the default: say
              what was asked for, why it is unavailable, and what is being shown instead. */}
          {showContext && unsupported && (
            <p role="status" className="mt-2 text-sm text-muted-foreground">
              {unsupported.display_name ? (
                <>
                  <strong>{unsupported.display_name}</strong> is not available yet:{" "}
                  {"reason" in unsupported && unsupported.reason
                    ? unsupported.reason
                    : "no validated boundary."}
                </>
              ) : (
                <>
                  <strong>“{unsupported.neighborhood_id}”</strong> is not a geography this site can
                  answer for.
                </>
              )}{" "}
              Showing {geography?.display_name ?? "Ward 20"} overall instead. Its absence is not a
              count of zero.
            </p>
          )}
        </div>

        {/* Mobile-first navigation: a stacked, full-width menu on phones, becoming a horizontal
            tab bar from `sm` up. It wraps rather than scrolls, so no section is hidden off-screen
            and there is never horizontal page overflow. The resident question is kept at every
            size — it is the label's meaning, not decoration. */}
        <nav aria-label="Primary" className="mx-auto max-w-5xl px-2 pb-1">
          <ul className="flex flex-col gap-1 sm:flex-row sm:flex-wrap">
            {NAV.map((n) => {
              const active = pathname === n.to;
              return (
                <li key={n.to} className="sm:shrink-0">
                  <Link
                    to={n.to}
                    aria-current={active ? "page" : undefined}
                    className={
                      "block min-h-11 rounded-md border-l-4 px-3 py-2 text-base transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary sm:rounded-none sm:rounded-t-md sm:border-l-0 sm:border-b-2 " +
                      (active
                        ? "border-primary bg-accent/60 font-semibold text-primary sm:bg-transparent"
                        : "border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground sm:hover:bg-transparent")
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
            Every figure is for the current Ward 20 footprint (the 2023 ward map, applied to every
            year), or for the part of a community area inside it — never for a whole community area.
            Wards, community areas, police beats, and census tracts are different boundaries and are
            never treated as the same thing. Exact addresses are never shown.
          </p>
          <p className="mt-1">
            This is not an official City of Chicago or Ward 20 office application.
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
