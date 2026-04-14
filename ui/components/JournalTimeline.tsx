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

export function JournalTimeline({ entries }: { entries: JournalEntry[] }) {
  if (!entries.length) {
    return <div className="text-subt text-sm">no journal entries yet</div>;
  }
  return (
    <ol className="relative border-l border-border pl-4 space-y-3">
      {entries.map((e) => {
        const payload = e.payload_json ? safeJson(e.payload_json) : null;
        const color = AGENT_COLOR[e.agent] ?? "#8b91a4";
        return (
          <li key={e.id} className="relative">
            <span
              className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full"
              style={{ background: color }}
            />
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-medium text-ink" style={{ color }}>
                {e.agent}
              </span>
              <span className="text-subt">
                {ACTION_LABEL[e.action] ?? e.action}
              </span>
              <span className="text-subt text-xs ml-auto font-mono">
                {new Date(e.created_at).toLocaleString()}
              </span>
            </div>
            {payload && (
              <pre className="mt-1 text-xs text-subt font-mono whitespace-pre-wrap break-words bg-panel-2 p-2 rounded border border-border">
                {formatPayload(payload)}
              </pre>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function safeJson(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function formatPayload(p: any): string {
  if (p == null) return "";
  if (typeof p === "string") return p;
  // For the common cases, collapse into pretty key:value so the timeline
  // stays scannable instead of dumping a wall of JSON.
  if ("rationale" in p) return p.rationale;
  if ("exploit_scenario" in p) return p.exploit_scenario;
  if ("github_issue_url" in p) return `→ ${p.github_issue_url}`;
  if ("title" in p && "severity" in p) return `${p.severity.toUpperCase()} — ${p.title}`;
  return JSON.stringify(p, null, 2);
}
