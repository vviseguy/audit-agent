"use client";

import { useMemo, useState } from "react";
import { api, type DraftIssue, type Project } from "@/lib/api";
import { SeverityBadge } from "./StatusBadge";

type PromoteOutcome = {
  draft_issue_id: number;
  success: boolean;
  github_issue_url: string | null;
  error: string | null;
};

export function DraftIssueReview({
  projects,
  initialProjectId,
  initialDrafts,
  initialSeverity = null,
  initialCwe = null,
}: {
  projects: Project[];
  initialProjectId: number;
  initialDrafts: DraftIssue[];
  initialSeverity?: string | null;
  initialCwe?: string | null;
}) {
  const [projectId, setProjectId] = useState(initialProjectId);
  const [drafts, setDrafts] = useState(initialDrafts);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [severityFilter, setSeverityFilter] = useState<string | null>(
    initialSeverity
  );
  const [cweFilter, setCweFilter] = useState<string | null>(initialCwe);
  const [busy, setBusy] = useState(false);
  const [outcomes, setOutcomes] = useState<PromoteOutcome[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return drafts.filter((d) => {
      if (severityFilter && (d.severity ?? "").toLowerCase() !== severityFilter.toLowerCase()) {
        return false;
      }
      if (cweFilter && (d.cwe_id ?? "").toLowerCase() !== cweFilter.toLowerCase()) {
        return false;
      }
      return true;
    });
  }, [drafts, severityFilter, cweFilter]);

  const [previewId, setPreviewId] = useState<number | null>(
    initialDrafts[0]?.id ?? null
  );

  const preview = useMemo(
    () => filtered.find((d) => d.id === previewId) ?? filtered[0] ?? null,
    [filtered, previewId]
  );

  const severityOptions = useMemo(
    () => Array.from(new Set(drafts.map((d) => (d.severity ?? "").toLowerCase()).filter(Boolean))).sort(),
    [drafts]
  );
  const cweOptions = useMemo(
    () => Array.from(new Set(drafts.map((d) => d.cwe_id ?? "").filter(Boolean))).sort(),
    [drafts]
  );

  const switchProject = async (id: number) => {
    setProjectId(id);
    setSelected(new Set());
    setOutcomes(null);
    setError(null);
    try {
      const next = await api.drafts(id);
      setDrafts(next);
      setPreviewId(next[0]?.id ?? null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(filtered.map((d) => d.id)));
  const clearAll = () => setSelected(new Set());

  const promote = async () => {
    if (!selected.size) return;
    setBusy(true);
    setOutcomes(null);
    setError(null);
    try {
      const res = await api.promoteDrafts(
        projectId,
        Array.from(selected),
        "pwa-user"
      );
      setOutcomes(res.outcomes);
      const sentIds = new Set(
        res.outcomes.filter((o) => o.success).map((o) => o.draft_issue_id)
      );
      setDrafts((prev) => prev.filter((d) => !sentIds.has(d.id)));
      setSelected(new Set());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subt">draft issues</div>
          <h1 className="text-2xl font-semibold tracking-tight">
            batch review & promote
          </h1>
          <div className="text-subt text-sm mt-1">
            the Delver writes here, never directly to GitHub. select drafts and
            approve to ship them in one batch.
          </div>
        </div>
        <div className="flex items-center gap-1 text-sm flex-wrap">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => switchProject(p.id)}
              className={
                "px-2 py-1 rounded-sm border " +
                (p.id === projectId
                  ? "border-border bg-panel-2 text-ink"
                  : "border-transparent text-subt hover:text-ink")
              }
            >
              {p.name}
            </button>
          ))}
        </div>
      </header>

      <div className="panel p-3 flex items-center gap-2 flex-wrap">
        <button
          onClick={selectAll}
          className="panel-2 border border-border hover:bg-panel px-3 py-1 text-xs"
        >
          select all
        </button>
        <button
          onClick={clearAll}
          className="panel-2 border border-border hover:bg-panel px-3 py-1 text-xs"
        >
          clear
        </button>
        <div className="text-xs text-subt font-mono">
          {selected.size} / {filtered.length} selected
          {filtered.length !== drafts.length && (
            <span className="ml-1">({drafts.length} total)</span>
          )}
        </div>
        <div className="flex items-center gap-2 ml-3">
          <select
            value={severityFilter ?? ""}
            onChange={(e) => setSeverityFilter(e.target.value || null)}
            className="panel-2 border border-border px-2 py-1 text-xs"
          >
            <option value="">all severities</option>
            {severityOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={cweFilter ?? ""}
            onChange={(e) => setCweFilter(e.target.value || null)}
            className="panel-2 border border-border px-2 py-1 text-xs"
          >
            <option value="">all CWEs</option>
            {cweOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {(severityFilter || cweFilter) && (
            <button
              onClick={() => {
                setSeverityFilter(null);
                setCweFilter(null);
              }}
              className="text-xs text-subt hover:text-ink"
            >
              clear filters
            </button>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={promote}
            disabled={busy || !selected.size}
            className="px-3 py-1 text-sm font-medium border rounded-sm disabled:opacity-50"
            style={{
              borderColor: "#4fae7a88",
              background: "#4fae7a22",
              color: "#4fae7a",
            }}
          >
            {busy ? "sending…" : `approve & send ${selected.size || ""}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="panel p-3 text-sm text-[#d04a4a]">error: {error}</div>
      )}

      {outcomes && (
        <div className="panel p-3 text-sm space-y-1">
          <div className="text-xs text-subt mb-1">promotion results</div>
          {outcomes.map((o) => (
            <div key={o.draft_issue_id} className="flex items-center gap-2">
              <span
                className="font-mono text-xs"
                style={{ color: o.success ? "#4fae7a" : "#d04a4a" }}
              >
                {o.success ? "✓" : "✗"}
              </span>
              <span className="text-subt text-xs">#{o.draft_issue_id}</span>
              {o.github_issue_url ? (
                <a
                  href={o.github_issue_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-[#4fae7a] hover:underline truncate"
                >
                  {o.github_issue_url}
                </a>
              ) : (
                <span className="text-xs text-[#d04a4a] truncate">
                  {o.error ?? "failed"}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 space-y-1 max-h-[70vh] overflow-auto pr-1">
          {filtered.length === 0 && (
            <div className="panel p-6 text-sm text-subt">
              {drafts.length === 0
                ? "no drafts waiting. run a delve session to create some."
                : "no drafts match the current filters."}
            </div>
          )}
          {filtered.map((d) => {
            const isSelected = selected.has(d.id);
            const isPreview = previewId === d.id;
            return (
              <div
                key={d.id}
                onClick={() => setPreviewId(d.id)}
                className={
                  "panel p-3 cursor-pointer border " +
                  (isPreview ? "border-[#5884d9]" : "border-border")
                }
              >
                <div className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggle(d.id)}
                    className="mt-1 accent-[#4fae7a]"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <SeverityBadge severity={d.severity} />
                      <span className="text-xs text-subt font-mono">
                        #{d.id}
                      </span>
                    </div>
                    <div className="text-sm text-ink truncate">{d.title}</div>
                    <div className="text-xs text-subt mt-1 font-mono">
                      updated{" "}
                      {new Date(d.updated_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="lg:col-span-3">
          {preview ? (
            <div className="panel p-4 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityBadge severity={preview.severity} />
                <span className="text-xs text-subt font-mono">
                  #{preview.id}
                </span>
                {preview.cwe_id && (
                  <span className="text-xs text-subt font-mono">
                    {preview.cwe_id}
                  </span>
                )}
              </div>
              <h2 className="text-lg font-medium text-ink">{preview.title}</h2>
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-[10px] text-subt uppercase tracking-wide mr-1">
                  labels on promote
                </span>
                {buildLabels(preview).map((l) => (
                  <span
                    key={l}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded-sm border border-border bg-panel-2 text-subt"
                  >
                    {l}
                  </span>
                ))}
              </div>
              <pre className="text-xs text-subt font-mono whitespace-pre-wrap break-words bg-panel-2 p-3 rounded border border-border max-h-[60vh] overflow-auto">
                {preview.body_md}
              </pre>
            </div>
          ) : (
            <div className="panel p-6 text-sm text-subt">
              select a draft to preview its rendered body.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function buildLabels(d: DraftIssue): string[] {
  const labels = ["audit-agent"];
  const sev = (d.severity ?? "").toLowerCase();
  if (sev) labels.push(`severity:${sev}`);
  if (d.cwe_id) labels.push(d.cwe_id.toLowerCase());
  return labels;
}
