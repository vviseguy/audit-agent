"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, type NewRepo, type TokenRow } from "@/lib/api";

const LENSES = [
  "balanced",
  "high_impact",
  "high_likelihood",
  "ui_visible",
  "custom",
];

export function NewProjectButton({ tokens }: { tokens: TokenRow[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="panel px-3 py-1.5 text-sm hover:bg-panel2"
      >
        + New Project
      </button>
      {open && (
        <NewProjectModal tokens={tokens} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

function NewProjectModal({
  tokens,
  onClose,
}: {
  tokens: TokenRow[];
  onClose: () => void;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [lens, setLens] = useState("balanced");
  const [budgetM, setBudgetM] = useState("2");
  const [pctCap, setPctCap] = useState("30");
  const [createIssues, setCreateIssues] = useState(false);
  const [readTokenId, setReadTokenId] = useState<number | null>(null);
  const [issuesTokenId, setIssuesTokenId] = useState<number | null>(null);
  const [repos, setRepos] = useState<NewRepo[]>([blankRepo()]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const readTokens = tokens.filter(
    (t) => t.scope === "read_only" || t.scope === "read_and_issues"
  );
  const issuesTokens = tokens.filter(
    (t) => t.scope === "issues_only" || t.scope === "read_and_issues"
  );

  const updateRepo = (idx: number, patch: Partial<NewRepo>) => {
    setRepos((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, ...patch } : r))
    );
  };
  const addRepo = () => setRepos((prev) => [...prev, blankRepo()]);
  const removeRepo = (idx: number) =>
    setRepos((prev) => prev.filter((_, i) => i !== idx));

  const canSubmit =
    name.trim().length > 0 &&
    repos.length > 0 &&
    repos.every((r) => isGithubUrl(r.url));

  const submit = async () => {
    setSaving(true);
    setErr(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        default_risk_lens: lens,
        daily_token_budget: Math.max(0, Math.round(Number(budgetM) * 1_000_000)),
        per_session_pct_cap: Math.max(0, Math.min(100, Number(pctCap))),
        create_issues: createIssues,
        read_token_id: readTokenId,
        issues_token_id: issuesTokenId,
        repos: repos.map((r) => ({
          url: r.url.trim(),
          branch: r.branch.trim() || "main",
        })),
      });
      router.push(`/projects/${created.id}`);
      router.refresh();
    } catch (e: any) {
      setErr(e.message ?? "Create failed");
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="panel p-5 w-full max-w-2xl space-y-4 mt-10"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">New Project</h2>
          <button
            onClick={onClose}
            className="text-subt hover:text-ink text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <label className="space-y-1 md:col-span-2">
            <div className="text-subt">Name</div>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="juice-shop"
              className="w-full bg-panel-2 border border-border px-2 py-1.5 font-mono"
            />
          </label>
          <label className="space-y-1">
            <div className="text-subt">Default risk lens</div>
            <select
              value={lens}
              onChange={(e) => setLens(e.target.value)}
              className="w-full bg-panel-2 border border-border px-2 py-1.5 font-mono"
            >
              {LENSES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <div className="text-subt">Daily budget (M tokens)</div>
            <input
              type="number"
              step="0.1"
              value={budgetM}
              onChange={(e) => setBudgetM(e.target.value)}
              className="w-full bg-panel-2 border border-border px-2 py-1.5 font-mono"
            />
          </label>
          <label className="space-y-1">
            <div className="text-subt">Per-session cap (%)</div>
            <input
              type="number"
              step="1"
              value={pctCap}
              onChange={(e) => setPctCap(e.target.value)}
              className="w-full bg-panel-2 border border-border px-2 py-1.5 font-mono"
            />
          </label>
          <label className="flex items-center gap-2 md:col-span-2">
            <input
              type="checkbox"
              checked={createIssues}
              onChange={(e) => setCreateIssues(e.target.checked)}
            />
            <span>Create GitHub issues on promote</span>
          </label>
        </div>

        <div className="space-y-2">
          <div className="text-subt text-xs uppercase tracking-wider">
            GitHub tokens (optional — bind later from the project page)
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <TokenSelect
              label="Read"
              value={readTokenId}
              options={readTokens}
              onChange={setReadTokenId}
            />
            <TokenSelect
              label="Issues"
              value={issuesTokenId}
              options={issuesTokens}
              onChange={setIssuesTokenId}
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-subt text-xs uppercase tracking-wider">
              Repos
            </div>
            <button
              onClick={addRepo}
              className="panel-2 px-2 py-1 text-xs hover:bg-panel"
            >
              + Add Repo
            </button>
          </div>
          <div className="space-y-2">
            {repos.map((r, i) => (
              <RepoRow
                key={i}
                repo={r}
                canRemove={repos.length > 1}
                onChange={(patch) => updateRepo(i, patch)}
                onRemove={() => removeRepo(i)}
              />
            ))}
          </div>
        </div>

        {err && <div className="text-[#d04a4a] text-xs">{err}</div>}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="panel-2 px-3 py-1.5 text-xs hover:bg-panel"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit || saving}
            className="px-3 py-1.5 text-xs disabled:opacity-50"
            style={{
              background: "#323b54",
              color: "#ecf0f8",
              border: "1px solid #4a5373",
            }}
          >
            {saving ? "Creating…" : "Create Project"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TokenSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: number | null;
  options: TokenRow[];
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="space-y-1">
      <div className="text-subt">{label} token</div>
      <select
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : Number(e.target.value))
        }
        className="w-full bg-panel-2 border border-border px-2 py-1.5 font-mono"
      >
        <option value="">— None —</option>
        {options.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label} ({t.scope})
          </option>
        ))}
      </select>
    </label>
  );
}

function RepoRow({
  repo,
  canRemove,
  onChange,
  onRemove,
}: {
  repo: NewRepo;
  canRemove: boolean;
  onChange: (patch: Partial<NewRepo>) => void;
  onRemove: () => void;
}) {
  const parsed = parseOwnerName(repo.url);
  const hasUrl = repo.url.trim().length > 0;
  const invalid = hasUrl && !parsed;
  return (
    <div className="panel-2 p-3 space-y-1">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={repo.url}
          onChange={(e) => onChange({ url: e.target.value })}
          placeholder="https://github.com/owner/name"
          className="flex-1 bg-panel border border-border px-2 py-1 font-mono text-xs"
          style={invalid ? { borderColor: "#d04a4a88" } : undefined}
        />
        <input
          type="text"
          value={repo.branch}
          onChange={(e) => onChange({ branch: e.target.value })}
          placeholder="branch"
          className="w-24 bg-panel border border-border px-2 py-1 font-mono text-xs"
        />
        {canRemove && (
          <button
            onClick={onRemove}
            className="text-[#d04a4a] text-xs px-2 py-1 hover:bg-panel"
            aria-label="Remove repo"
          >
            Remove
          </button>
        )}
      </div>
      {parsed && (
        <div className="text-[11px] text-subt font-mono pl-1">
          → {parsed.owner}/{parsed.name}
        </div>
      )}
      {invalid && (
        <div className="text-[11px] text-[#d04a4a] font-mono pl-1">
          Not a recognized github.com URL
        </div>
      )}
    </div>
  );
}

function blankRepo(): NewRepo {
  return { url: "", branch: "main" };
}

const GITHUB_URL_RE =
  /^(?:https?:\/\/)?(?:www\.)?github\.com[:/]([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/i;

function parseOwnerName(url: string): { owner: string; name: string } | null {
  const m = url.trim().match(GITHUB_URL_RE);
  if (!m) return null;
  return { owner: m[1], name: m[2] };
}

function isGithubUrl(url: string): boolean {
  return parseOwnerName(url) !== null;
}
