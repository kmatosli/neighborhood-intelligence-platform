import { useBrief, type BriefItem } from "@/lib/brief";

/**
 * The standard Services & Accountability issue panel. Every issue uses the same ten-part
 * structure so a resident always finds the same information in the same place, and so the
 * distinction between department responsibility, alderperson responsibility, and resident
 * verification is never blurred.
 *
 * Metrics are only ever shown when a live data source is connected. Until then a panel shows
 * an honest "data source not yet connected" state naming the intended source. No number is
 * invented, and no letter grade is manufactured.
 */

export type ServiceMetric = { label: string; value: string; note?: string };

export type ServicePanelData = {
  id: string;
  title: string;
  /** What the data shows now, or the honest state if no source is connected. */
  currentCondition: string;
  /** Present only when a source is connected; otherwise the honest empty state is shown. */
  metrics?: ServiceMetric[];
  /** The public dataset(s) that would populate this panel, named honestly. */
  intendedSource: string;
  connected: boolean;
  primaryAuthority: string;
  supportingAuthority?: string;
  alderpersonCan: string[];
  alderpersonCannot: string[];
  wardHasDone?: string;
  moneyAndProjects: string;
  promisesAndDeadlines: string;
  residentActions: string[];
  accountabilityQuestions: { department: string[]; alderperson: string[]; resident: string[] };
  evidenceNote: string;
};

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="wire-label">{title}</h4>
      <div className="mt-1 text-base text-muted-foreground">{children}</div>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function ServicePanel({ data }: { data: ServicePanelData }) {
  const brief = useBrief();
  const briefId = `services:${data.id}`;
  const added = brief.has(briefId);

  const item: BriefItem = {
    id: briefId,
    source: "services",
    category: "service",
    title: `Service: ${data.title}`,
    supportingStat: data.connected ? (data.metrics?.[0]?.value ?? "See panel") : "Data source not yet connected",
    comparisonPeriod: "current",
    primaryAuthority: data.primaryAuthority,
    supportingAuthority: data.supportingAuthority ?? null,
    alderpersonRole: `Can: ${data.alderpersonCan[0] ?? ""} Cannot: ${data.alderpersonCannot[0] ?? ""}`,
    residentQuestion: data.accountabilityQuestions.alderperson[0] ?? "",
    evidence: data.evidenceNote,
    addedAt: Date.now(),
  };

  return (
    <article id={data.id} className="rounded-lg border bg-card p-5 shadow-sm">
      <h3 className="font-serif text-lg font-semibold">{data.title}</h3>

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <Block title="Current condition">{data.currentCondition}</Block>

        <Block title="Service performance">
          {data.connected && data.metrics ? (
            <dl className="grid grid-cols-2 gap-2">
              {data.metrics.map((m) => (
                <div key={m.label} className="rounded-md border bg-background p-2">
                  <dt className="text-sm">{m.label}</dt>
                  <dd className="font-serif text-xl tabular-nums text-foreground">{m.value}</dd>
                  {m.note && <dd className="text-xs">{m.note}</dd>}
                </div>
              ))}
            </dl>
          ) : (
            <div className="rounded-md border border-dashed bg-background/50 p-3 text-sm">
              <p className="font-medium text-foreground">Data source not yet connected.</p>
              <p className="mt-1">Intended source: {data.intendedSource}. No figures are shown.</p>
            </div>
          )}
        </Block>

        <Block title="Primary authority">
          {data.primaryAuthority}
          {data.supportingAuthority && (
            <p className="mt-1 text-sm">Supporting: {data.supportingAuthority}</p>
          )}
        </Block>

        <Block title="What the ward has done">
          {data.wardHasDone ?? "No ward action is documented from a connected source yet."}
        </Block>

        <Block title="Alderperson can">
          <List items={data.alderpersonCan} />
        </Block>
        <Block title="Alderperson cannot">
          <List items={data.alderpersonCannot} />
        </Block>

        <Block title="Money and projects">{data.moneyAndProjects}</Block>
        <Block title="Promises and deadlines">{data.promisesAndDeadlines}</Block>
      </div>

      <div className="mt-4 rounded-md border bg-background/60 p-3">
        <h4 className="wire-label">Accountability questions</h4>
        <div className="mt-2 grid gap-3 text-base text-muted-foreground sm:grid-cols-3">
          <div>
            <p className="text-sm font-medium text-foreground">Department should answer</p>
            <List items={data.accountabilityQuestions.department} />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">Alderperson should answer</p>
            <List items={data.accountabilityQuestions.alderperson} />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">Residents can verify</p>
            <List items={data.accountabilityQuestions.resident} />
          </div>
        </div>
      </div>

      <div className="mt-4">
        <Block title="Resident action">
          <List items={data.residentActions} />
        </Block>
      </div>

      <p className="mt-3 text-xs text-muted-foreground">Evidence &amp; verification: {data.evidenceNote}</p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => (added ? brief.remove(briefId) : brief.add(item))}
          aria-pressed={added}
          className={
            "min-h-11 rounded-md border px-4 py-2 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary " +
            (added
              ? "border-primary bg-primary/10 font-medium text-primary"
              : "bg-background hover:bg-accent")
          }
        >
          {added ? "✓ Added to brief" : "Add to meeting brief"}
        </button>
        <a
          href="https://311.chicago.gov/"
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-11 items-center rounded-md border bg-background px-4 py-2 text-base hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          File or track a 311 request ↗
        </a>
      </div>
    </article>
  );
}
