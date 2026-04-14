import Link from "next/link";
import { api } from "@/lib/api";
import { JournalTimeline } from "@/components/JournalTimeline";
import { SeverityBadge, StatusBadge } from "@/components/StatusBadge";
import { StatusOverride } from "@/components/StatusOverride";

export default async function VulnPage({
  params,
}: {
  params: { id: string };
}) {
  const id = Number(params.id);
  const vuln = await api.vulnerability(id).catch(() => null);

  if (!vuln) {
    return <div className="panel p-6">vulnerability not found.</div>;
  }

  return (
    <div className="space-y-6">
      <header>
        <div className="text-xs text-subt flex items-center gap-2">
          <Link href={`/projects/${vuln.project_id}`} className="hover:text-ink">
            project {vuln.project_id}
          </Link>
          <span>›</span>
          <span className="font-mono">
            {vuln.path}:{vuln.line_start}-{vuln.line_end}
          </span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">{vuln.title}</h1>
        <div className="mt-2 flex items-center gap-3 text-sm">
          <StatusBadge status={vuln.status} />
          {vuln.cwe_id && (
            <a
              href={`https://cwe.mitre.org/data/definitions/${vuln.cwe_id.split("-")[1]}.html`}
              target="_blank"
              rel="noreferrer"
              className="panel-2 px-2 py-0.5 text-xs rounded-sm font-mono hover:text-ink"
            >
              {vuln.cwe_id}
            </a>
          )}
          <span className="text-subt text-xs">
            impact <span className="text-ink font-mono">{vuln.impact}</span> ·
            likelihood <span className="text-ink font-mono">{vuln.likelihood}</span> ·
            priority <span className="text-ink font-mono">{vuln.priority}</span>
          </span>
        </div>
      </header>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          {vuln.short_desc && (
            <div className="panel p-4">
              <h3 className="text-sm font-medium mb-1">ranker rationale</h3>
              <p className="text-sm text-subt">{vuln.short_desc}</p>
            </div>
          )}

          <div className="panel p-4">
            <h3 className="text-sm font-medium mb-3">journal</h3>
            <JournalTimeline entries={vuln.journal} />
          </div>

          {vuln.draft_issue && (
            <div className="panel p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium">draft issue</h3>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={vuln.draft_issue.severity} />
                  <StatusBadge status={vuln.draft_issue.status} />
                </div>
              </div>
              <div className="font-medium text-ink text-sm">
                {vuln.draft_issue.title}
              </div>
              <pre className="mt-2 text-xs text-subt font-mono whitespace-pre-wrap break-words bg-panel-2 p-3 rounded border border-border max-h-[28rem] overflow-auto">
                {vuln.draft_issue.body_md}
              </pre>
              {vuln.draft_issue.github_issue_url && (
                <a
                  href={vuln.draft_issue.github_issue_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-[#4fae7a] hover:underline"
                >
                  → {vuln.draft_issue.github_issue_url}
                </a>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <StatusOverride vulnId={vuln.id} current={vuln.status} />

          <div className="panel p-4">
            <h3 className="text-sm font-medium mb-2">location</h3>
            <div className="text-xs text-subt font-mono">{vuln.path}</div>
            <div className="text-xs text-subt font-mono">
              lines {vuln.line_start}–{vuln.line_end}
            </div>
          </div>

          <div className="panel p-4">
            <h3 className="text-sm font-medium mb-1">cwe</h3>
            <div className="text-xs text-subt">
              {vuln.cwe_id ?? "(none)"}
              {vuln.cwe_id && (
                <>
                  {" · "}
                  <a
                    href={`https://cwe.mitre.org/data/definitions/${vuln.cwe_id.split("-")[1]}.html`}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-ink underline"
                  >
                    MITRE
                  </a>
                </>
              )}
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}
