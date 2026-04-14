"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { JournalEntry } from "@/lib/api";

const AGENT_COLOR: Record<string, string> = {
  understander: "#4fae7a",
  ranker: "#5884d9",
  delver: "#9a6ad1",
  system: "#8b91a4",
  user: "#d4a45c",
};

const ACTION_LABEL: Record<string, string> = {
  ranked: "ranked",
  delved: "delved",
  issue_drafted: "drafted issue",
  issue_updated: "updated issue",
  issue_sent: "sent to GitHub",
  status_changed: "status changed",
  pass_done: "pass done",
  note: "note",
  annotated: "annotated",
};

const AGENTS = ["understander", "ranker", "delver", "system", "user"];

export function HistoryFeed({ entries }: { entries: JournalEntry[] }) {
  const [agentFilter, setAgentFilter] = useState<Set<string>>(new Set(AGENTS));
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((e) => {
      if (!agentFilter.has(e.agent)) return false;
      if (q) {
        const hay = `${e.vuln_title ?? ""} ${e.action} ${e.agent} ${
          e.payload_json ?? ""
        }`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [entries, agentFilter, query]);

  const grouped = useMemo(() => groupByDay(filtered), [filtered]);

  const toggleAgent = (a: string) => {
    setAgentFilter((prev) => {
      const next = new Set(prev);
      if (next.has(a)) next.delete(a);
      else next.add(a);
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="panel p-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 text-xs">
          {AGENTS.map((a) => {
            const on = agentFilter.has(a);
            const color = AGENT_COLOR[a];
            return (
              <button
                key={a}
                onClick={() => toggleAgent(a)}
                className="px-2 py-1 rounded-sm border"
                style={{
                  background: on ? `${color}22` : "transparent",
                  borderColor: on ? `${color}88` : "var(--tw-color-border, #2a2f3a)",
                  color: on ? color : "#8b91a4",
                }}
              >
                {a}
              </button>
            );
          })}
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter by title, action, or payload…"
          className="flex-1 min-w-[200px] bg-panel-2 border border-border rounded px-2 py-1 text-sm"
        />
        <div className="text-xs text-subt font-mono">
          {filtered.length} / {entries.length} entries
        </div>
      </div>

      {grouped.length === 0 && (
        <div className="panel p-6 text-sm text-subt">no journal entries match.</div>
      )}

      {grouped.map(({ day, items }) => (
        <div key={day} className="panel p-4">
          <div className="text-xs text-subt font-mono mb-3">{day}</div>
          <ol className="relative border-l border-border pl-4 space-y-3">
            {items.map((e) => (
              <FeedEntry key={e.id} entry={e} />
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function FeedEntry({ entry }: { entry: JournalEntry }) {
  const color = AGENT_COLOR[entry.agent] ?? "#8b91a4";
  const action = ACTION_LABEL[entry.action] ?? entry.action;
  const payload = entry.payload_json ? safeJson(entry.payload_json) : null;
  const summary = payload ? summarize(payload) : null;
  return (
    <li className="relative">
      <span
        className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full"
        style={{ background: color }}
      />
      <div className="flex items-baseline gap-2 text-sm flex-wrap">
        <span className="font-medium" style={{ color }}>
          {entry.agent}
        </span>
        <span className="text-subt">{action}</span>
        {entry.vulnerability_id && entry.vuln_title && (
          <Link
            href={`/vulnerabilities/${entry.vulnerability_id}`}
            className="text-ink hover:underline truncate max-w-[36rem]"
          >
            {entry.vuln_title}
          </Link>
        )}
        <span className="text-subt text-xs ml-auto font-mono">
          {new Date(entry.created_at).toLocaleTimeString()}
        </span>
      </div>
      {summary && (
        <div className="mt-1 text-xs text-subt font-mono whitespace-pre-wrap break-words">
          {summary}
        </div>
      )}
    </li>
  );
}

function groupByDay(entries: JournalEntry[]): { day: string; items: JournalEntry[] }[] {
  const buckets = new Map<string, JournalEntry[]>();
  for (const e of entries) {
    const d = new Date(e.created_at);
    const key = d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
    });
    const bucket = buckets.get(key);
    if (bucket) bucket.push(e);
    else buckets.set(key, [e]);
  }
  return Array.from(buckets.entries()).map(([day, items]) => ({ day, items }));
}

function safeJson(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function summarize(p: any): string | null {
  if (p == null) return null;
  if (typeof p === "string") return p.slice(0, 240);
  if ("rationale" in p) return String(p.rationale).slice(0, 240);
  if ("exploit_scenario" in p) return String(p.exploit_scenario).slice(0, 240);
  if ("github_issue_url" in p) return `→ ${p.github_issue_url}`;
  if ("title" in p && "severity" in p)
    return `${String(p.severity).toUpperCase()} — ${p.title}`;
  if ("halted_reason" in p) return `halted: ${p.halted_reason}`;
  if ("from" in p && "to" in p) return `${p.from} → ${p.to}`;
  return null;
}
