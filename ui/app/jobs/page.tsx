import { api } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  queued: "#5884d9",
  running: "#d4a45c",
  done: "#4fae7a",
  halted: "#d04a4a",
  cancelled: "#8b91a4",
};

const HALT_LABEL: Record<string, string> = {
  schedule_expired: "schedule window closed",
  rate_limit_session_cap: "hit session budget cap",
  agent_cap: "hit per-agent call cap",
  daily_budget_exceeded: "daily token budget exceeded",
};

export default async function JobsPage() {
  const [sessions, runs, projects, budget] = await Promise.all([
    api.sessions().catch(() => []),
    api.runs(50).catch(() => []),
    api.projects().catch(() => []),
    api.budgetToday().catch(() => null),
  ]);

  const projectName = (id: number) =>
    projects.find((p) => p.id === id)?.name ?? `p${id}`;

  const upcoming = sessions
    .filter((s) => s.status === "queued")
    .sort((a, b) => a.scheduled_for.localeCompare(b.scheduled_for));
  const running = sessions.filter((s) => s.status === "running");
  const recent = sessions
    .filter((s) => s.status === "done" || s.status === "halted" || s.status === "cancelled")
    .sort((a, b) => b.scheduled_for.localeCompare(a.scheduled_for))
    .slice(0, 20);

  return (
    <div className="space-y-5">
      <header>
        <div className="text-xs text-subt">jobs</div>
        <h1 className="text-2xl font-semibold tracking-tight">scheduler</h1>
        <div className="text-subt text-sm mt-1">
          upcoming, running, and recently halted sessions — with the binding
          constraint recorded on halt.
        </div>
      </header>

      {budget && (
        <div className="panel p-4">
          <div className="flex items-center justify-between text-xs text-subt mb-1">
            <span>daily token budget</span>
            <span className="font-mono">
              {budget.tokens_used_today.toLocaleString()} /{" "}
              {budget.daily_token_budget.toLocaleString()} · {budget.pct}%
            </span>
          </div>
          <div className="h-2 bg-panel-2 rounded-sm overflow-hidden">
            <div
              className="h-full"
              style={{
                width: `${Math.min(100, budget.pct)}%`,
                background:
                  budget.pct > 85
                    ? "#d04a4a"
                    : budget.pct > 60
                    ? "#d4a45c"
                    : "#4fae7a",
              }}
            />
          </div>
        </div>
      )}

      <Section title="running" rows={running} projectName={projectName} />
      <Section title="upcoming" rows={upcoming} projectName={projectName} />

      <div className="panel p-4">
        <h2 className="text-sm font-medium mb-3">recent runs</h2>
        {runs.length === 0 ? (
          <div className="text-subt text-sm">no runs yet.</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-subt text-left">
                <th className="pb-2 font-normal">run</th>
                <th className="pb-2 font-normal">status</th>
                <th className="pb-2 font-normal">tokens</th>
                <th className="pb-2 font-normal">% daily</th>
                <th className="pb-2 font-normal">started</th>
                <th className="pb-2 font-normal">halted reason</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {runs.map((r) => {
                const color = STATUS_COLOR[r.status] ?? "#8b91a4";
                return (
                  <tr key={r.id} className="border-t border-border">
                    <td className="py-1 text-subt">#{r.id}</td>
                    <td className="py-1">
                      <span style={{ color }}>{r.status}</span>
                    </td>
                    <td className="py-1 text-subt">
                      {(r.tokens_in + r.tokens_out).toLocaleString()}
                    </td>
                    <td className="py-1 text-subt">
                      {r.pct_daily_budget_used?.toFixed(1) ?? "—"}
                    </td>
                    <td className="py-1 text-subt">
                      {r.started_at
                        ? new Date(r.started_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="py-1 text-subt">
                      {r.halted_reason
                        ? HALT_LABEL[r.halted_reason] ?? r.halted_reason
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <Section title="recent sessions" rows={recent} projectName={projectName} />
    </div>
  );
}

function Section({
  title,
  rows,
  projectName,
}: {
  title: string;
  rows: Awaited<ReturnType<typeof api.sessions>>;
  projectName: (id: number) => string;
}) {
  return (
    <div className="panel p-4">
      <h2 className="text-sm font-medium mb-3">{title}</h2>
      {rows.length === 0 ? (
        <div className="text-subt text-sm">nothing {title}.</div>
      ) : (
        <ul className="space-y-1 text-sm">
          {rows.map((s) => {
            const color = STATUS_COLOR[s.status] ?? "#8b91a4";
            return (
              <li
                key={s.id}
                className="flex items-center gap-3 border-t border-border pt-1"
              >
                <span
                  className="w-2 h-2 rounded-sm"
                  style={{ background: color }}
                />
                <span className="text-ink text-xs">{projectName(s.project_id)}</span>
                <span className="text-subt text-xs font-mono">{s.type}</span>
                <span className="text-subt text-xs">{s.risk_lens}</span>
                <span className="text-subt text-xs font-mono ml-auto">
                  {new Date(s.scheduled_for).toLocaleString()}
                </span>
                <span className="text-xs" style={{ color }}>
                  {s.status}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
