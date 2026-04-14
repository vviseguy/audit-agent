import Link from "next/link";
import {
  api,
  type Project,
  type SessionRow,
  type TokenRow,
  type Vulnerability,
} from "@/lib/api";
import { isVeryHighPriority, vulnColor } from "@/lib/status";
import { computeProjectAlerts, worstKind } from "@/lib/alerts";
import { NewProjectButton } from "@/components/NewProjectModal";

type HomeData = {
  projects: Project[];
  sessions: SessionRow[];
  tokens: TokenRow[];
  vulnsByProject: Record<number, Vulnerability[]>;
};

async function getData(): Promise<HomeData> {
  const [projects, sessions, tokens] = await Promise.all([
    api.projects().catch(() => [] as Project[]),
    api.sessions().catch(() => [] as SessionRow[]),
    api.tokens().catch(() => [] as TokenRow[]),
  ]);
  const vulnLists = await Promise.all(
    projects.map((p) =>
      api.vulnerabilities(p.id).catch(() => [] as Vulnerability[])
    )
  );
  const vulnsByProject: Record<number, Vulnerability[]> = {};
  projects.forEach((p, i) => (vulnsByProject[p.id] = vulnLists[i]));
  return { projects, sessions, tokens, vulnsByProject };
}

export default async function ProjectsPage() {
  const { projects, sessions, tokens, vulnsByProject } = await getData();
  const running = sessions.filter((s) => s.status === "running");
  const queued = sessions.filter((s) => s.status === "queued");

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-subt text-sm mt-1">
            Repositories under continuous audit. Click a project for its grid
            view.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <NewProjectButton tokens={tokens} />
          <Link
            href="/queue"
            className="panel px-3 py-1.5 text-sm hover:bg-panel2"
          >
            + Queue Session
          </Link>
        </div>
      </header>

      <AgentCard
        running={running}
        queuedCount={queued.length}
        projects={projects}
      />

      {projects.length === 0 ? (
        <div className="panel p-8 text-center text-subt">
          No projects yet. Seed the demo with{" "}
          <code className="text-ink">python scripts/seed_demo.py</code>.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              vulns={vulnsByProject[p.id] ?? []}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentCard({
  running,
  queuedCount,
  projects,
}: {
  running: SessionRow[];
  queuedCount: number;
  projects: Project[];
}) {
  const projectById = new Map(projects.map((p) => [p.id, p]));
  return (
    <section className="panel p-4">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{
            background: running.length ? "#4fae7a" : "#3b4150",
            boxShadow: running.length ? "0 0 8px #4fae7a88" : undefined,
          }}
        />
        <h2 className="text-sm font-medium">Live Agent</h2>
        <span className="text-xs text-subt font-mono ml-auto">
          {running.length} running · {queuedCount} queued
        </span>
      </div>
      {running.length === 0 ? (
        <div className="text-xs text-subt">
          Agents idle. Queue a session from the{" "}
          <Link className="underline" href="/queue">
            Queue page
          </Link>
          .
        </div>
      ) : (
        <ul className="space-y-1 text-xs">
          {running.map((s) => {
            const proj = projectById.get(s.project_id);
            return (
              <li
                key={s.id}
                className="flex items-center gap-3 font-mono text-subt"
              >
                <span className="text-[#4fae7a]">●</span>
                <span className="text-ink">{proj?.name ?? `project#${s.project_id}`}</span>
                <span>{s.type}</span>
                <span>· lens {s.risk_lens}</span>
                <Link
                  href="/run-log"
                  className="ml-auto underline hover:text-ink"
                >
                  Run Log
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ProjectCard({
  project: p,
  vulns,
}: {
  project: Project;
  vulns: Vulnerability[];
}) {
  const alerts = computeProjectAlerts(p);
  const worst = worstKind(alerts);
  return (
    <Link
      href={`/projects/${p.id}`}
      className="panel p-4 hover:border-ink/40 transition-colors block"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium text-ink flex items-center gap-2">
          {p.name}
          {worst && (
            <AlertDot
              kind={worst}
              title={alerts.map((a) => `• ${a.text}`).join("\n")}
            />
          )}
        </div>
        <span className="text-xs text-subt">{p.default_risk_lens}</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <Stat label="Total" value={p.vuln_total} />
        <Stat
          label="Needs Delve"
          value={p.vuln_needs_delve}
          accent="#d4a45c"
        />
        <Stat label="Sent" value={p.vuln_issue_sent} accent="#4fae7a" />
      </div>
      {vulns.length > 0 && <MiniSquareGrid vulns={vulns} />}
      <div className="mt-3 flex items-center justify-between text-xs text-subt">
        <span>
          Next:{" "}
          {p.next_scheduled
            ? new Date(p.next_scheduled).toLocaleString()
            : "—"}
        </span>
        {p.delve_hours_remaining && p.delve_hours_remaining > 0 ? (
          <span
            className="text-ink/70"
            title="Ranker agile-hours for pending delves"
          >
            ~{p.delve_hours_remaining.toFixed(1)}h delve
          </span>
        ) : null}
      </div>
    </Link>
  );
}

function MiniSquareGrid({ vulns }: { vulns: Vulnerability[] }) {
  const sorted = [...vulns].sort((a, b) => b.priority - a.priority);
  return (
    <div
      className="mt-3 flex flex-wrap gap-[2px]"
      aria-label={`${vulns.length} vulnerabilities`}
    >
      {sorted.map((v) => (
        <span
          key={v.id}
          className="inline-block w-2 h-2 rounded-[1px]"
          style={{
            background: vulnColor(v.status, v.priority),
            outline: isVeryHighPriority(v.priority)
              ? "1px solid #ffffff88"
              : undefined,
          }}
          title={`${v.title} · priority ${v.priority}`}
        />
      ))}
    </div>
  );
}

function AlertDot({
  kind,
  title,
}: {
  kind: "error" | "warn";
  title: string;
}) {
  const color = kind === "error" ? "#d04a4a" : "#d4a45c";
  return (
    <span
      title={title}
      className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold leading-none"
      style={{
        background: color + "22",
        color,
        border: `1px solid ${color}88`,
      }}
      aria-label={kind === "error" ? "Configuration error" : "Configuration warning"}
    >
      !
    </span>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="panel-2 px-2 py-1.5">
      <div className="text-subt">{label}</div>
      <div
        className="font-mono text-base"
        style={{ color: accent ?? "#e6e8ee" }}
      >
        {value}
      </div>
    </div>
  );
}
