import { createFileRoute, Link } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { ServicePanel, type ServicePanelData } from "@/components/ServicePanel";
import { useBrief } from "@/lib/brief";

export const Route = createFileRoute("/authority")({
  head: () => ({
    meta: [
      { title: "Services & Accountability — Bronzeville & Woodlawn Watch" },
      {
        name: "description",
        content:
          "Are neighborhood services being delivered, and is the alderperson using the tools they actually have? Service problems, department performance, ward action, and resident verification.",
      },
    ],
  }),
  component: Services,
});

// Ward-level service measures. Every one is honestly "not connected" until its dataset is
// wired in — no letter grade, no invented number.
const SCORECARD = [
  { label: "Open 311 requests", source: "Chicago 311 (CSR)" },
  { label: "Requests submitted YTD", source: "Chicago 311 (CSR)" },
  { label: "Median completion time", source: "Chicago 311 (CSR)" },
  { label: "Requests older than 30 days", source: "Chicago 311 (CSR)" },
  { label: "Repeat complaints", source: "Chicago 311 (CSR)" },
  { label: "Resident-confirmed resolutions", source: "Resident reporting (planned)" },
  { label: "Menu-money projects underway", source: "Aldermanic menu program" },
  { label: "Overdue commitments", source: "Ward publications" },
];

const NOT_CONNECTED = "No data source is connected yet, so no figures are shown.";

const PANELS: ServicePanelData[] = [
  {
    id: "potholes",
    title: "Potholes and street repair",
    currentCondition:
      "Pothole patching and street resurfacing are two different processes with two different owners. This panel keeps them separate.",
    connected: false,
    intendedSource: "Chicago 311 pothole requests + CDOT",
    primaryAuthority: "Chicago Department of Transportation (CDOT), via 311 operations",
    supportingAuthority: "Ward office for escalation and menu-money resurfacing selection",
    alderpersonCan: [
      "Escalate overdue 311 tickets to CDOT",
      "Select residential streets for resurfacing through ward menu money",
      "Publish the backlog and explain which streets were chosen",
      "Disclose utility conflicts and expected construction windows",
    ],
    alderpersonCannot: [
      "Guarantee every street is repaved",
      "Perform patching or resurfacing directly",
      "Override CDOT engineering or citywide capital priorities",
    ],
    moneyAndProjects:
      "Patching is CDOT operating work. Resurfacing of residential streets is often funded through the ward's annual menu money; major streets may use city, state, federal, utility, or capital funds.",
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: [
      "File a pothole request through 311 and keep the request number",
      "Ask the ward office to escalate an overdue ticket",
      "Add this issue to your beat-meeting brief",
    ],
    accountabilityQuestions: {
      department: [
        "Why is this request still open?",
        "What is the expected repair window?",
        "Is this a patch or a resurfacing issue?",
      ],
      alderperson: [
        "Was this overdue request escalated?",
        "Is the block in the resurfacing backlog, and was menu money considered?",
        "Why was another block selected first?",
      ],
      resident: [
        "Was the pothole actually repaired?",
        "Was it only temporarily patched?",
        "Did the same problem recur?",
      ],
    },
    evidenceNote:
      "The correct standard is not whether every street was repaved, but whether the ward used objective condition information, disclosed the backlog, prioritized need, explained choices, and accounted for available funds.",
  },
  {
    id: "resurfacing",
    title: "Street resurfacing tracker",
    currentCondition:
      "Resurfacing is a capital process, distinct from 311 patching. This tracker models each block from request through completion and resident verification.",
    connected: false,
    intendedSource: "Aldermanic menu-money records + CDOT capital project records",
    primaryAuthority: "CDOT capital program; ward menu-money selection for residential streets",
    alderpersonCan: [
      "Publish which blocks were selected and why",
      "Publish streets inspected but not selected",
      "Report expected construction windows and completion",
    ],
    alderpersonCannot: [
      "Use capital menu money as an ordinary recurring operating fund",
      "Guarantee a construction year against utility or engineering constraints",
    ],
    moneyAndProjects:
      "Tracks menu-money amount, other capital amount, funding source, and selection reason per block. No schedule is fabricated where the data are not connected.",
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: [
      "Ask which streets are scheduled this year",
      "Ask why a specific block was or was not selected",
      "Verify completion after the promised window",
    ],
    accountabilityQuestions: {
      department: ["What is the construction schedule?", "What utility conflicts exist?"],
      alderperson: [
        "Has the ward published its resurfacing backlog?",
        "How was menu money allocated across competing blocks?",
      ],
      resident: ["Was the block actually resurfaced?", "Was completion within the promised window?"],
    },
    evidenceNote:
      "Fields modelled: request, inspection, cost estimate, selection reason, utility conflict, promised year, start, completion, and resident verification.",
  },
  {
    id: "alley-resurfacing",
    title: "Alley resurfacing",
    currentCondition:
      "A separate process from street resurfacing and entirely separate from snow removal. Alleys have their own eligibility and selection.",
    connected: false,
    intendedSource: "Aldermanic menu-money records (alley projects)",
    primaryAuthority: "CDOT; ward menu-money selection",
    alderpersonCan: [
      "Assess alley resurfacing requests and eligibility",
      "Select eligible alleys through menu money",
      "Publish expected year and cost",
    ],
    alderpersonCannot: [
      "Guarantee every alley is resurfaced",
      "Treat alley resurfacing as routine recurring maintenance",
    ],
    moneyAndProjects: "Menu-money eligibility and project selection. " + NOT_CONNECTED,
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: ["Request an alley inspection", "Ask about menu-money eligibility"],
    accountabilityQuestions: {
      department: ["Is the alley eligible?", "What is the estimated cost?"],
      alderperson: ["Was the alley considered for menu money?", "What was the delay reason?"],
      resident: ["Was the alley resurfaced?", "Was drainage improved?"],
    },
    evidenceNote: "Modelled separately from snow removal and street resurfacing.",
  },
  {
    id: "snow",
    title: "Snow removal",
    currentCondition:
      "Chicago generally prioritizes arterial roads, then residential streets, then sanitation access. The city does NOT routinely plow public alleys. This page does not promise routine alley plowing.",
    connected: false,
    intendedSource: "Chicago 311 snow/ice complaints + Streets & Sanitation",
    primaryAuthority: "Chicago Department of Streets and Sanitation",
    alderpersonCan: [
      "Coordinate with Streets and Sanitation and escalate blocked garbage or emergency access",
      "Communicate city snow policy clearly",
      "Organize volunteers and maintain senior or disability assistance lists",
      "Negotiate group contractor options where lawful and advocate for policy change",
    ],
    alderpersonCannot: [
      "Independently order citywide crews to plow every alley",
      "Guarantee routine alley plowing",
      "Use capital menu money as an ordinary recurring snow-removal operating fund without lawful authority",
    ],
    moneyAndProjects: "Snow operations are a city operating function, not menu-money capital work.",
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: [
      "Report an unplowed street or blocked access through 311",
      "Register a senior or disabled resident for the access program (below)",
      "Ask the ward to escalate blocked emergency access",
    ],
    accountabilityQuestions: {
      department: [
        "How long after the snowfall was this street cleared?",
        "Why was a side street missed?",
      ],
      alderperson: [
        "How is city alley policy being communicated to residents?",
        "What assistance exists for seniors and disabled residents?",
      ],
      resident: ["Was the street cleared?", "Was garbage or emergency access restored?"],
    },
    evidenceNote:
      "Streets and alleys are tracked separately. The city's alley policy is stated plainly rather than implying a plowing promise.",
  },
  {
    id: "senior-snow-access",
    title: "Senior and disability snow access",
    currentCondition:
      "A dedicated view for a Senior Access program covering the path from a rear door to the garage or alley, garbage-cart access, and emergency-lane access. No ward assistance program is currently documented from a connected source.",
    connected: false,
    intendedSource: "Ward program records + resident registration (planned)",
    primaryAuthority: "Ward office (program operation); Streets and Sanitation (city service)",
    alderpersonCan: [
      "Maintain a senior and disability registration list",
      "Coordinate volunteers or contractors for access clearing",
      "Prioritize senior-heavy blocks",
    ],
    alderpersonCannot: [
      "Guarantee citywide alley plowing",
      "Compel city crews to clear private paths",
    ],
    moneyAndProjects: "Program cost and funding source would be shown here once documented.",
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: [
      "Register a senior or disabled resident for assistance",
      "Report an unresolved access complaint",
    ],
    accountabilityQuestions: {
      department: ["Is emergency access maintained?"],
      alderperson: ["Is there a documented senior access program, and who does it serve?"],
      resident: ["Was rear-door-to-alley access actually cleared?"],
    },
    evidenceNote: "Participation counts are never invented; the honest empty state is shown until a program is documented.",
  },
  {
    id: "rats",
    title: "Rats and rodent abatement",
    currentCondition:
      "Rodent complaints are tracked with response and recurrence, and related garbage, vacant-lot, and building complaints. Low complaint volume does not necessarily mean low need.",
    connected: false,
    intendedSource: "Chicago 311 rodent complaints + Streets & Sanitation (Rodent Control)",
    primaryAuthority: "Chicago Department of Streets and Sanitation — Bureau of Rodent Control",
    alderpersonCan: [
      "Escalate overdue requests and request hotspot treatment",
      "Coordinate related sanitation, vacant-lot, and building issues",
      "Publish ward trends and convene department meetings",
    ],
    alderpersonCannot: [
      "Personally perform treatment",
      "Guarantee eradication",
      "Conclude low need from low complaint counts",
    ],
    moneyAndProjects: "City operating service; not menu-money capital work.",
    promisesAndDeadlines: NOT_CONNECTED,
    residentActions: [
      "File a rodent complaint through 311",
      "Report related garbage or vacant-lot conditions",
      "Confirm whether the problem recurred after closure",
    ],
    accountabilityQuestions: {
      department: [
        "What was the response time?",
        "Was the block treated, and did the problem recur?",
      ],
      alderperson: ["Were overdue requests escalated?", "Were related conditions coordinated?"],
      resident: ["Was the infestation actually reduced?", "Did it return within 90 days?"],
    },
    evidenceNote:
      "Warning shown to residents: low complaint volume does not necessarily mean low need.",
  },
];

// Remaining issue areas the page will grow into. Listed honestly, distinctly, and without
// invented figures, so alley issues are never collapsed into a single "alley" service.
const MORE_ISSUES = [
  "Garbage carts and missed collection",
  "Illegal dumping",
  "Streetlight outages",
  "Graffiti removal (public vs private property)",
  "Vacant and dangerous buildings",
  "Tree trimming and dangerous trees",
  "Sidewalk repair",
  "Abandoned vehicles",
  "Flooding and sewer complaints",
  "Traffic safety",
  "Park maintenance",
];

function Services() {
  const brief = useBrief();
  return (
    <WireShell>
      <section aria-labelledby="svc" className="mb-6">
        <p className="wire-label mb-1">Services &amp; Accountability</p>
        <h1 id="svc" className="font-serif text-2xl leading-snug sm:text-3xl">
          Are neighborhood services being delivered—and is the alderperson using the tools they
          actually have?
        </h1>
        <p className="mt-2 max-w-2xl text-base text-muted-foreground">
          Track service problems, department performance, ward action, money, promises, and
          whether residents confirm the work was completed.
        </p>
      </section>

      {/* Ward service scorecard — honest measures only, no letter grade */}
      <section aria-labelledby="scorecard" className="mb-8">
        <h2 id="scorecard" className="font-serif text-xl">
          Ward service scorecard
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          The actual measures, not a single grade. Each is shown only once its data source is
          connected.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {SCORECARD.map((m) => (
            <div key={m.label} className="rounded-lg border border-dashed bg-card/50 p-4">
              <div className="wire-label">{m.label}</div>
              <div className="mt-1 font-serif text-2xl text-muted-foreground" aria-hidden="true">
                —
              </div>
              <p className="text-xs text-muted-foreground">Source not yet connected: {m.source}.</p>
            </div>
          ))}
        </div>
      </section>

      {/* Standard issue panels */}
      <section aria-labelledby="issues" className="mb-8">
        <h2 id="issues" className="font-serif text-xl">
          Service issues
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          Each issue uses the same structure: condition, performance, primary authority, what the
          alderperson can and cannot do, money, promises, resident action, and verification.
        </p>
        <div className="mt-4 space-y-5">
          {PANELS.map((panel) => (
            <ServicePanel key={panel.id} data={panel} />
          ))}
        </div>
      </section>

      {/* More issue areas — honest, distinct, no invented figures */}
      <section aria-labelledby="more" className="mb-8">
        <h2 id="more" className="font-serif text-xl">
          More service areas
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          These areas use the same accountability structure and are being connected next. Alley
          issues are kept distinct — repair, resurfacing, lighting, cleaning, garbage access, and
          snow access are not one service.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MORE_ISSUES.map((label) => (
            <div key={label} className="rounded-lg border border-dashed bg-card/50 p-4">
              <h3 className="text-base font-medium">{label}</h3>
              <p className="mt-1 text-sm text-muted-foreground">Data source not yet connected.</p>
            </div>
          ))}
        </div>
      </section>

      {/* Service request explorer — honest empty state */}
      <section aria-labelledby="explorer" className="mb-8">
        <h2 id="explorer" className="font-serif text-xl">
          Service request explorer
        </h2>
        <div className="mt-3 rounded-lg border border-dashed bg-card/50 p-6 text-center">
          <p className="font-medium">Data source not yet connected.</p>
          <p className="mt-1 text-base text-muted-foreground">
            When the Chicago 311 (CSR) dataset is connected, this becomes a sortable, filterable,
            exportable table of individual service requests — request number, masked block, status,
            responsible department, days open, target time, overdue flag, and resident
            verification. No personal information is ever shown.
          </p>
        </div>
      </section>

      {/* Cross-page connections */}
      <section aria-labelledby="connections" className="mb-8">
        <h2 id="connections" className="font-serif text-xl">
          Connected accountability workflow
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          A service issue connects to the money that could fix it, the promise made about it, and
          the brief residents take to a meeting. These handoffs share one issue identifier.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <HandoffCard title="→ Meeting brief" body={`Add any service issue above to your brief. ${brief.items.length} item(s) collected.`} to="/beat-meeting" enabled />
          <HandoffCard title="→ Related promise" body="Promises tracking is a planned page. The shared issue model is ready to link to it." />
          <HandoffCard title="→ Related money / project" body="Menu-money and capital project tracking is a planned page. The shared issue model is ready to link to it." />
        </div>
      </section>

      <p className="text-sm text-muted-foreground">
        This is not an official City of Chicago or ward application. Department responsibilities and
        aldermanic powers are civic reference; service figures appear only when a public dataset is
        connected.
      </p>
    </WireShell>
  );
}

function HandoffCard({
  title,
  body,
  to,
  enabled,
}: {
  title: string;
  body: string;
  to?: string;
  enabled?: boolean;
}) {
  const inner = (
    <div
      className={
        "h-full rounded-lg border p-4 " +
        (enabled ? "bg-accent/40 hover:bg-accent" : "border-dashed bg-card/50")
      }
    >
      <h3 className="font-medium">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
  if (enabled && to) {
    return (
      <Link to={to} className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        {inner}
      </Link>
    );
  }
  return inner;
}
