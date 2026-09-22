/**
 * The shared "not yet connected" presentation.
 *
 * Several sections exist before their data does. Each of them must say so in one consistent
 * way, so a reader learns the vocabulary once: a notice at the top of the page, a dashed frame
 * where a visualization will go, a dash where a figure will go, and controls that are visibly
 * disabled rather than silently inert. None of these ever renders a number, a mark, or an axis
 * — an empty chart would read as "zero", and a populated one would be a fabrication.
 *
 * Before V2-001 each coming-soon page carried its own copy of these. Consolidating them keeps
 * the wording (and the caveats it carries) identical everywhere and gives later V2 pages one
 * place to reach for.
 */

import type { ReactNode } from "react";

/** The page-level notice that the section below is not yet connected to validated live data. */
export function ComingSoonNotice({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 rounded-md border bg-caution/20 p-3 text-base" role="note">
      <strong>Live data coming soon.</strong> {children}
    </p>
  );
}

/**
 * A visualization with no validated data behind it yet. Renders no marks and no numbers, and
 * names what is planned so the page still communicates its purpose.
 */
export function PendingVisual({ height, planned }: { height: number; planned: string }) {
  return (
    <div
      className="mt-3 flex items-center justify-center rounded-md border border-dashed bg-muted/30 p-4 text-center"
      style={{ minHeight: height }}
      role="note"
    >
      <div className="max-w-md">
        <p className="wire-label">Live data coming soon</p>
        <p className="mt-1 text-base">
          This visualization is not yet connected to validated live data.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">Planned: {planned}</p>
      </div>
    </div>
  );
}

/** A headline figure whose value has not been computed. The dash never stands in for zero. */
export function PendingStat({
  label,
  note = "Live data coming soon",
}: {
  label: string;
  /** Why there is no figure — by default the generic notice, or the unconnected source. */
  note?: string;
}) {
  return (
    <div className="rounded-lg border border-dashed bg-card/50 p-3">
      <div className="wire-label">{label}</div>
      <div className="mt-1 font-serif text-3xl text-muted-foreground" aria-hidden="true">
        —
      </div>
      <div className="text-xs text-muted-foreground">{note}</div>
    </div>
  );
}

/** A planned data area with no source connected yet. Names the intended source when known. */
export function NotConnectedCard({ label, source }: { label: string; source?: string }) {
  return (
    <div className="rounded-lg border border-dashed bg-card/50 p-4">
      <h3 className="text-base font-medium">{label}</h3>
      <p className="mt-1 text-sm text-muted-foreground">Data source not yet connected.</p>
      {source && <p className="mt-1 text-sm text-muted-foreground">Intended source: {source}.</p>}
    </div>
  );
}

/** The id every disabled control points at for its "why is this disabled" description. */
const PENDING_CONTROLS_ID = "controls-pending";

/**
 * A group of controls that are disabled until the page is connected to live data. Disabled,
 * not removed: the reader can see what the page will let them ask, without a control that
 * silently does nothing when used. The explanatory line is announced with each control.
 */
export function PendingControls({
  label,
  columns,
  children,
}: {
  label: string;
  /** Tailwind grid-cols class for the `sm` breakpoint and up; phones always get one column. */
  columns: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={label}
      className={`mb-6 grid gap-3 rounded-lg border bg-card p-4 ${columns}`}
    >
      <p id={PENDING_CONTROLS_ID} className="wire-label col-span-full">
        Controls are disabled until this page is connected to live data
      </p>
      {children}
    </section>
  );
}

export function PendingControl({
  label,
  id,
  options,
}: {
  label: string;
  id?: string;
  options: string[];
}) {
  const controlId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <label htmlFor={controlId} className="wire-label mb-1 block text-muted-foreground">
        {label}
      </label>
      <select
        id={controlId}
        disabled
        aria-describedby={PENDING_CONTROLS_ID}
        className="w-full cursor-not-allowed rounded-md border bg-muted px-2 py-1.5 text-sm text-muted-foreground opacity-70"
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
