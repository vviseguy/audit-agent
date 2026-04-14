"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type Project, type RunRow, type SessionRow } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  queued: "#5884d9",
  running: "#d4a45c",
  done: "#4fae7a",
  halted: "#d04a4a",
  cancelled: "#8b91a4",
};

export function RunLogView({
  initialRuns,
  sessions,
  projects,
}: {
  initialRuns: RunRow[];
  sessions: SessionRow[];
  projects: Project[];
}) {
  const [runs, setRuns] = useState(initialRuns);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const next = await api.runs(20);
        setRuns(next);
        setTick((t) => t + 1);
      } catch {
        // transient; keep last snapshot
      }
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const sessionsById = useMemo(() => {
    const m = new Map<number, SessionRow>();
    for (const s of sessions) m.set(s.id, s);
    return m;
  }, [sessions]);

  const projectName = (id: number) =>
    projects.find((p) => p.id === id)?.name ?? `p${id}`;

  const active = runs.find((r) => r.status === "running");
  const recent = runs.filter((r) => r !== active);

  // Group recent runs by session so a halted-then-resumed session reads as
  // one block in the log. Runs within a group are sorted oldest->newest.
  const grouped = useMemo(() => {
    const map = new Map<number, RunRow[]>();
    for (const r of recent) {
      const arr = map.get(r.session_id) ?? [];
      arr.push(r);
      map.set(r.session_id, arr);
    }
    const out: { sessionId: number; runs: RunRow[] }[] = [];
    for (const [sessionId, arr] of map.entries()) {
      arr.sort((a, b) => (a.started_at ?? "").localeCompare(b.started_at ?? ""));
      out.push({ sessionId, runs: arr });
    }
    out.sort((a, b) => {
      const at = a.runs[a.runs.length - 1].started_at ?? "";
      const bt = b.runs[b.runs.length - 1].started_at ?? "";
      return bt.localeCompare(at);
    });
    return out;
  }, [recent]);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subt">run log</div>
          <h1 className="text-2xl font-semibold tracking-tight">
            live agent activity
          </h1>
          <div className="text-subt text-sm mt-1">
            polls the server every 5s · tick {tick}
          </div>
        </div>
      </header>

      {active ? (
        <div className="panel p-4 space-y-3 border-[#d4a45c] border">
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ background: "#d4a45c" }}
            />
            <span className="text-[#d4a45c] text-sm font-medium">
              running · run #{active.id}
            </span>
            <span className="text-subt text-xs ml-auto font-mono">
              started{" "}
              {active.started_at
                ? new Date(active.started_at).toLocaleTimeString()
                : "—"}
            </span>
          </div>
          {(() => {
            const session = sessionsById.get(active.session_id);
            return session ? (
              <div className="text-xs text-subt font-mono">
                {projectName(session.project_id)} · {session.type} ·{" "}
                {session.risk_lens}
              </div>
            ) : null;
          })()}
          <div className="grid grid-cols-3 gap-3">
            <Stat
              label="tokens in"
              value={active.tokens_in.toLocaleString()}
            />
            <Stat
              label="tokens out"
              value={active.tokens_out.toLocaleString()}
            />
            <Stat
              label="% of daily"
              value={`${active.pct_daily_budget_used?.toFixed(1) ?? "0.0"}%`}
            />
          </div>
          <div className="h-2 bg-panel-2 rounded-sm overflow-hidden">
            <div
              className="h-full transition-all"
              style={{
                width: `${Math.min(
                  100,
                  active.pct_daily_budget_used ?? 0
                )}%`,
                background: "#d4a45c",
              }}
            />
          </div>
        </div>
      ) : (
        <div className="panel p-4 text-sm text-subt">
          no run is currently active. recent history below.
        </div>
      )}

      <div className="panel p-4">
        <h2 className="text-sm font-medium mb-3">recent runs · grouped by session</h2>
        {grouped.length === 0 ? (
          <div className="text-subt text-sm">no history yet.</div>
        ) : (
          <div className="space-y-4">
            {grouped.map(({ sessionId, runs: sessionRuns }) => {
              const session = sessionsById.get(sessionId);
              const resumed = sessionRuns.length > 1;
              const firstStart = sessionRuns[0].started_at;
              return (
                <div key={sessionId} className="border-t border-border pt-2">
                  <div className="flex items-baseline gap-2 text-xs">
                    <span className="text-ink font-medium">
                      session #{sessionId}
                    </span>
                    <span className="text-subt">
                      {session
                        ? `${projectName(session.project_id)} · ${session.type} · ${session.risk_lens}`
                        : "—"}
                    </span>
                    {resumed && (
                      <span
                        className="ml-1 px-1.5 py-0.5 rounded-sm text-[10px] font-medium"
                        style={{ background: "#5884d933", color: "#8eb0ef" }}
                        title="Session halted and was resumed later"
                      >
                        resumed ×{sessionRuns.length - 1}
                      </span>
                    )}
                    <span className="text-subt ml-auto font-mono">
                      {firstStart ? new Date(firstStart).toLocaleString() : "—"}
                    </span>
                  </div>
                  <ul className="mt-1 space-y-1 text-xs font-mono">
                    {sessionRuns.map((r, i) => {
                      const color = STATUS_COLOR[r.status] ?? "#8b91a4";
                      return (
                        <li
                          key={r.id}
                          className="flex items-center gap-3 pl-3"
                        >
                          <span
                            className="w-2 h-2 rounded-sm"
                            style={{ background: color }}
                          />
                          <span className="text-subt">#{r.id}</span>
                          <span className="text-subt">
                            attempt {i + 1}/{sessionRuns.length}
                          </span>
                          <span className="text-subt">
                            {r.started_at
                              ? new Date(r.started_at).toLocaleTimeString()
                              : "—"}
                            {r.finished_at ? (
                              <>
                                {" → "}
                                {new Date(r.finished_at).toLocaleTimeString()}
                              </>
                            ) : null}
                          </span>
                          <span className="text-subt ml-auto">
                            {(r.tokens_in + r.tokens_out).toLocaleString()} tok
                          </span>
                          <span className="text-subt">
                            {r.pct_daily_budget_used?.toFixed(1) ?? "0.0"}%
                          </span>
                          <span style={{ color }}>{r.status}</span>
                          {r.halted_reason && (
                            <span className="text-[#d04a4a] text-[10px]">
                              {r.halted_reason}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-2 px-3 py-2">
      <div className="text-subt text-xs">{label}</div>
      <div className="font-mono text-lg text-ink">{value}</div>
    </div>
  );
}
