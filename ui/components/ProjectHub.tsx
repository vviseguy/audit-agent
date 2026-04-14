"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  type Project,
  type ProjectForecast,
  type ProjectPatch,
  type ProjectTokenBrief,
  type TokenRow,
  type Vulnerability,
} from "@/lib/api";
import { computeProjectAlerts, type ProjectAlert } from "@/lib/alerts";
import { SquareGrid } from "./SquareGrid";

type Tab = "overview" | "settings" | "tokens";

export function ProjectHub({
  initialProject,
  vulns,
  globalTokens,
}: {
  initialProject: Project;
  vulns: Vulnerability[];
  globalTokens: TokenRow[];
}) {
  const [project, setProject] = useState(initialProject);
  const [tab, setTab] = useState<Tab>("overview");
  const counts = countByStatus(vulns);

  const alerts = computeProjectAlerts(project);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subt uppercase tracking-wider">
            Project
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {project.name}
          </h1>
          <div className="text-subt text-sm mt-1">
            Default lens{" "}
            <span className="text-ink">{project.default_risk_lens}</span>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link
            className="panel px-3 py-1.5 text-sm hover:bg-panel2"
            href="/queue"
          >
            Queue Session
          </Link>
          <Link
            className="panel px-3 py-1.5 text-sm hover:bg-panel2 relative"
            href={`/draft-issues?project=${project.id}`}
          >
            Drafts
            {(project.draft_count ?? 0) > 0 && (
              <span className="ml-2 text-xs text-[#d4a45c] font-mono">
                {project.draft_count}
              </span>
            )}
          </Link>
          <Link
            className="panel px-3 py-1.5 text-sm hover:bg-panel2"
            href={`/history?project=${project.id}`}
          >
            History
          </Link>
        </div>
      </header>

      {alerts.length > 0 && <AlertBanner alerts={alerts} />}

      <nav className="panel-2 inline-flex text-xs overflow-hidden">
        {(["overview", "settings", "tokens"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-4 py-1.5 capitalize transition-colors"
            style={{
              background: tab === t ? "#323b54" : "transparent",
              color: tab === t ? "#ecf0f8" : "#9aa3b8",
            }}
          >
            {t}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <OverviewTab project={project} vulns={vulns} counts={counts} />
      )}
      {tab === "settings" && (
        <SettingsTab project={project} onSaved={setProject} />
      )}
      {tab === "tokens" && (
        <TokensTab
          project={project}
          globalTokens={globalTokens}
          onChange={setProject}
        />
      )}
    </div>
  );
}

function OverviewTab({
  project,
  vulns,
  counts,
}: {
  project: Project;
  vulns: Vulnerability[];
  counts: Record<string, number>;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Total" value={vulns.length} />
        <Stat
          label="Needs Delve"
          value={counts.needs_delve ?? 0}
          accent="#d4a45c"
        />
        <Stat label="Delved" value={counts.delved ?? 0} accent="#9a6ad1" />
        <Stat
          label="Draft Issue"
          value={counts.draft_issue ?? 0}
          accent="#5884d9"
        />
        <Stat
          label="Issue Sent"
          value={counts.issue_sent ?? 0}
          accent="#4fae7a"
        />
      </div>

      {project.forecast && project.forecast.pending_count > 0 && (
        <ForecastHint forecast={project.forecast} />
      )}

      <SquareGrid vulns={vulns} />
    </div>
  );
}

const LENS_OPTIONS = [
  "balanced",
  "high_impact",
  "high_likelihood",
  "ui_visible",
  "custom",
];

function SettingsTab({
  project,
  onSaved,
}: {
  project: Project;
  onSaved: (p: Project) => void;
}) {
  const [lens, setLens] = useState(project.default_risk_lens);
  const [createIssues, setCreateIssues] = useState(!!project.create_issues);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const dirty =
    lens !== project.default_risk_lens ||
    createIssues !== !!project.create_issues;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const patch: ProjectPatch = {
        default_risk_lens: lens,
        create_issues: createIssues ? 1 : 0,
      };
      await api.updateProject(project.id, patch);
      onSaved({ ...project, ...patch });
    } catch (e: any) {
      setErr(e.message ?? "save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel p-4 space-y-4 max-w-xl">
      <h2 className="text-sm font-medium">Project Settings</h2>
      <div className="grid grid-cols-1 gap-3 text-xs">
        <label className="space-y-1">
          <div className="text-subt">Default risk lens</div>
          <select
            value={lens}
            onChange={(e) => setLens(e.target.value)}
            className="w-full bg-panel border border-border px-2 py-1.5 font-mono"
          >
            {LENS_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
        <div className="text-[11px] text-subt italic">
          Daily token budget and per-session caps are configured globally in{" "}
          <span className="font-mono">config.yaml</span>.
        </div>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={createIssues}
            onChange={(e) => setCreateIssues(e.target.checked)}
          />
          <span>Create GitHub issues on promote</span>
        </label>
      </div>
      {err && <div className="text-[#d04a4a] text-xs">{err}</div>}
      <div className="flex items-center gap-2">
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="panel-2 px-3 py-1 text-xs disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {dirty && (
          <span className="text-[#d4a45c] text-xs">Unsaved changes</span>
        )}
      </div>
      <DangerZone project={project} />
    </section>
  );
}

function DangerZone({ project }: { project: Project }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const matches = typed.trim() === project.name;

  const doDelete = async () => {
    if (!matches) return;
    setBusy(true);
    setErr(null);
    try {
      await api.deleteProject(project.id);
      router.push("/");
      router.refresh();
    } catch (e: any) {
      setErr(e.message ?? "Delete failed");
      setBusy(false);
    }
  };

  return (
    <div
      className="mt-4 pt-4 border-t"
      style={{ borderColor: "#d04a4a33" }}
    >
      <div className="text-[#d04a4a] text-xs uppercase tracking-wider font-semibold mb-2">
        Danger Zone
      </div>
      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="px-3 py-1 text-xs"
          style={{
            background: "#d04a4a22",
            color: "#d04a4a",
            border: "1px solid #d04a4a88",
          }}
        >
          Delete Project
        </button>
      ) : (
        <div className="space-y-2">
          <div className="text-xs text-subt">
            Cascades to all repos, sessions, runs, vulnerabilities, draft
            issues, and journal entries for this project. Linked tokens stay
            in the global pool. Type{" "}
            <span className="font-mono text-ink">{project.name}</span> to
            confirm.
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={project.name}
              className="bg-panel border border-border px-2 py-1 text-xs font-mono flex-1 max-w-xs"
            />
            <button
              onClick={doDelete}
              disabled={!matches || busy}
              className="px-3 py-1 text-xs disabled:opacity-40"
              style={{
                background: "#d04a4a",
                color: "#ffffff",
              }}
            >
              {busy ? "Deleting…" : "Delete Forever"}
            </button>
            <button
              onClick={() => {
                setConfirming(false);
                setTyped("");
                setErr(null);
              }}
              className="panel-2 px-3 py-1 text-xs"
            >
              Cancel
            </button>
          </div>
          {err && <div className="text-[#d04a4a] text-xs">{err}</div>}
        </div>
      )}
    </div>
  );
}

function TokensTab({
  project,
  globalTokens,
  onChange,
}: {
  project: Project;
  globalTokens: TokenRow[];
  onChange: (p: Project) => void;
}) {
  return (
    <section className="panel p-4 space-y-4">
      <div>
        <h2 className="text-sm font-medium">GitHub Tokens</h2>
        <div className="text-xs text-subt mt-1">
          Bind a token from the global pool to this project. The read token is
          used for clones and scans; the issues token promotes drafts to real
          GitHub issues. Both can be validated from here.
        </div>
      </div>

      <TokenPicker
        label="Read"
        project={project}
        role="read"
        bound={project.read_token ?? null}
        globalTokens={globalTokens.filter(
          (t) => t.scope === "read_only" || t.scope === "read_and_issues"
        )}
        onChange={onChange}
      />
      <TokenPicker
        label="Issues"
        project={project}
        role="issues"
        bound={project.issues_token ?? null}
        globalTokens={globalTokens.filter(
          (t) => t.scope === "issues_only" || t.scope === "read_and_issues"
        )}
        onChange={onChange}
      />

      {globalTokens.length === 0 && (
        <div className="text-xs text-subt">
          No tokens in the global pool yet. Add one from{" "}
          <Link className="underline" href="/settings">
            Settings
          </Link>{" "}
          or import a project.
        </div>
      )}
    </section>
  );
}

function TokenPicker({
  label,
  project,
  role,
  bound,
  globalTokens,
  onChange,
}: {
  label: string;
  project: Project;
  role: "read" | "issues";
  bound: ProjectTokenBrief | null;
  globalTokens: TokenRow[];
  onChange: (p: Project) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const boundId = bound?.id ?? null;
  const patchField =
    role === "read" ? "read_token_id" : "issues_token_id";

  const pick = async (value: string) => {
    const id = value === "" ? 0 : Number(value);
    setBusy(true);
    setErr(null);
    try {
      await api.updateProject(project.id, { [patchField]: id } as ProjectPatch);
      // Re-fetch the project to pick up the nested token brief with any
      // validation result the backend attaches.
      const next = await api.project(project.id);
      onChange(next);
    } catch (e: any) {
      setErr(e.message ?? "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const revalidate = async () => {
    if (!boundId) return;
    setBusy(true);
    setErr(null);
    try {
      await api.validateToken(boundId);
      const next = await api.project(project.id);
      onChange(next);
    } catch (e: any) {
      setErr(e.message ?? "Validation failed");
    } finally {
      setBusy(false);
    }
  };

  const result = parseResult(bound?.validation_result ?? null);
  const ok = result?.ok;
  const unlinked = result?.unlinked;

  return (
    <div className="panel-2 p-3 space-y-2">
      <div className="flex items-center gap-3 text-xs flex-wrap">
        <span className="text-subt w-16 uppercase tracking-wide font-semibold">
          {label}
        </span>
        <select
          value={boundId ?? ""}
          disabled={busy}
          onChange={(e) => pick(e.target.value)}
          className="bg-panel border border-border px-2 py-1 font-mono min-w-[180px] disabled:opacity-50"
        >
          <option value="">— Not linked —</option>
          {globalTokens.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label} ({t.scope})
            </option>
          ))}
        </select>
        {bound && (
          <button
            onClick={revalidate}
            disabled={busy}
            className="panel px-2 py-1 text-xs disabled:opacity-50"
          >
            {busy ? "Checking…" : "Re-check"}
          </button>
        )}
        {ok === true && !unlinked && (
          <span className="text-[#4fae7a]">✓ Validated</span>
        )}
        {ok === true && unlinked && (
          <span className="text-[#d4a45c]" title="Identity OK but no repos linked to check against">
            ◐ Identity OK
          </span>
        )}
        {ok === false && (
          <span className="text-[#d04a4a]">
            ✗ {result?.error ?? "Over-scoped or invalid"}
          </span>
        )}
        {bound && ok == null && (
          <span className="text-subt">Not yet checked</span>
        )}
      </div>
      {bound && (
        <div className="text-[11px] font-mono">
          {bound.validated_at ? (
            <span className="text-subt">
              Last checked {new Date(bound.validated_at).toLocaleString()}
            </span>
          ) : (
            <span className="text-[#d4a45c]">Never checked</span>
          )}
        </div>
      )}
      {err && <div className="text-[#d04a4a] text-xs">{err}</div>}
    </div>
  );
}

function AlertBanner({ alerts }: { alerts: ProjectAlert[] }) {
  const hasError = alerts.some((a) => a.kind === "error");
  const color = hasError ? "#d04a4a" : "#d4a45c";
  return (
    <div
      className="rounded-md px-4 py-2 text-xs space-y-1 border"
      style={{
        borderColor: color + "88",
        background: color + "18",
        color,
      }}
    >
      <div className="font-mono uppercase tracking-wider text-[10px]">
        {hasError ? "Configuration error" : "Configuration warning"}
      </div>
      {alerts.map((a, i) => (
        <div key={i}>{a.text}</div>
      ))}
    </div>
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
    <div className="panel-2 px-3 py-2">
      <div className="text-subt text-xs">{label}</div>
      <div
        className="font-mono text-xl"
        style={{ color: accent ?? "#e6e8ee" }}
      >
        {value}
      </div>
    </div>
  );
}

function ForecastHint({ forecast }: { forecast: ProjectForecast }) {
  const hours = forecast.delve_hours_remaining;
  const wallClockHours = hours / 0.6;
  const sessionsAt4h = Math.max(1, Math.ceil(wallClockHours / 4));
  return (
    <div className="panel-2 px-4 py-3 flex items-center gap-4 text-sm flex-wrap">
      <div className="text-subt text-xs uppercase tracking-wide">forecast</div>
      <div>
        <span className="text-ink font-mono">{forecast.pending_count}</span>{" "}
        <span className="text-subt">pending ·</span>{" "}
        <span className="text-ink font-mono">~{hours.toFixed(1)}h</span>{" "}
        <span className="text-subt">ranker agile-hours</span>
      </div>
      <div className="text-subt">
        ≈ {sessionsAt4h} session{sessionsAt4h === 1 ? "" : "s"} at a 4h window
      </div>
    </div>
  );
}

function countByStatus(vulns: Vulnerability[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const v of vulns) out[v.status] = (out[v.status] ?? 0) + 1;
  return out;
}

function parseResult(s: string | null): any {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}
