"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type NewRepo, type TokenRow } from "@/lib/api";

const LENSES = [
  "balanced",
  "high_impact",
  "high_likelihood",
  "ui_visible",
  "custom",
];

// Inputs use a darker shade than the modal panel so they read as inset.
const INPUT_CLASS =
  "w-full bg-[#141826] border border-[#353e57] px-2 py-1.5 font-mono text-xs " +
  "focus:outline-none focus:border-[#5884d9] rounded-sm";

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
        <NewProjectModal
          initialTokens={tokens}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function NewProjectModal({
  initialTokens,
  onClose,
}: {
  initialTokens: TokenRow[];
  onClose: () => void;
}) {
  const router = useRouter();
  const [tokens, setTokens] = useState<TokenRow[]>(dedupeTokens(initialTokens));
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [lens, setLens] = useState("balanced");
  const [createIssues, setCreateIssues] = useState(false);
  // One token covers both roles. If the selected token's scope is
  // read_and_issues it's applied to both; if read_only only the read slot
  // is filled (promote will fail until a second token is added later).
  const [tokenId, setTokenId] = useState<number | null>(null);
  const [repos, setRepos] = useState<NewRepo[]>([blankRepo()]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Auto-suggest the project name from the first parseable repo until the
  // user types something themselves.
  useEffect(() => {
    if (nameTouched) return;
    const first = repos.find((r) => parseOwnerName(r.url));
    if (!first) return;
    const parsed = parseOwnerName(first.url);
    if (parsed && parsed.name !== name) {
      setName(parsed.name);
    }
  }, [repos, nameTouched, name]);

  // Only read-capable tokens are pickable here — one token per project.
  const pickableTokens = tokens.filter(
    (t) => t.scope === "read_only" || t.scope === "read_and_issues"
  );
  const selectedToken = tokens.find((t) => t.id === tokenId) ?? null;
  const selectedCoversIssues = selectedToken?.scope === "read_and_issues";

  const updateRepo = (idx: number, patch: Partial<NewRepo>) =>
    setRepos((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, ...patch } : r))
    );
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
        // Budget + per-session cap come from global config.yaml — the
        // backend falls back to its defaults when we omit them here.
        daily_token_budget: 2_000_000,
        per_session_pct_cap: 30,
        create_issues: createIssues,
        read_token_id: tokenId,
        issues_token_id: selectedCoversIssues ? tokenId : null,
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

  const refreshTokens = async () => {
    try {
      const next = await api.tokens();
      setTokens(dedupeTokens(next));
    } catch {
      /* keep prior list */
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

        <label className="space-y-1 block">
          <div className="text-subt text-xs uppercase tracking-wider">
            Name
          </div>
          <input
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setNameTouched(true);
            }}
            placeholder="juice-shop"
            className={INPUT_CLASS}
          />
        </label>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-subt text-xs uppercase tracking-wider">
              Repos
            </div>
            <button
              onClick={addRepo}
              className="panel-2 px-3 py-1.5 text-xs hover:bg-panel"
            >
              + Add Repo
            </button>
          </div>
          <div className="space-y-3">
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

        <TokenSection
          pickableTokens={pickableTokens}
          tokenId={tokenId}
          onChange={setTokenId}
          createIssues={createIssues}
          selectedCoversIssues={selectedCoversIssues}
          onTokensRefresh={refreshTokens}
        />

        <div className="space-y-2">
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-xs text-subt hover:text-ink flex items-center gap-2 font-mono uppercase tracking-wider"
          >
            <span
              className="inline-block transition-transform"
              style={{
                transform: showAdvanced ? "rotate(90deg)" : "rotate(0deg)",
              }}
            >
              ▸
            </span>
            Advanced
          </button>
          {showAdvanced && (
            <div className="panel-2 p-3 space-y-3 text-xs">
              <label className="space-y-1 block">
                <div className="text-subt">Default risk lens</div>
                <select
                  value={lens}
                  onChange={(e) => setLens(e.target.value)}
                  className={INPUT_CLASS}
                >
                  {LENSES.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createIssues}
                  onChange={(e) => setCreateIssues(e.target.checked)}
                />
                <span>Create GitHub issues on promote</span>
              </label>
              <div className="text-subt text-[11px] leading-relaxed">
                Daily budget and per-session caps are configured globally in{" "}
                <span className="font-mono text-ink">config.yaml</span> and
                apply to every project.
              </div>
            </div>
          )}
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

function TokenSection({
  pickableTokens,
  tokenId,
  onChange,
  createIssues,
  selectedCoversIssues,
  onTokensRefresh,
}: {
  pickableTokens: TokenRow[];
  tokenId: number | null;
  onChange: (id: number | null) => void;
  createIssues: boolean;
  selectedCoversIssues: boolean;
  onTokensRefresh: () => Promise<void>;
}) {
  const [showNew, setShowNew] = useState(false);

  return (
    <section
      className="border rounded-md p-4 space-y-3"
      style={{ borderColor: "#5884d955", background: "#5884d910" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wider font-semibold text-[#c4d0ec]">
          GitHub Token
        </div>
        <button
          onClick={() => setShowNew((v) => !v)}
          className="text-xs text-[#c4d0ec] hover:text-ink"
        >
          {showNew ? "× cancel" : "+ add token"}
        </button>
      </div>
      <div className="text-[11px] text-subt leading-relaxed">
        One token handles both clones and issue promotion. Leave unlinked if
        all repos are public — clones still work. Use scope{" "}
        <span className="font-mono text-ink">read_and_issues</span> if you want
        to promote drafts to real GitHub issues.
      </div>

      <TokenPicker
        label="Token"
        value={tokenId}
        options={pickableTokens}
        onChange={onChange}
      />

      {createIssues && tokenId != null && !selectedCoversIssues && (
        <div className="text-[11px] text-[#d4a45c] leading-relaxed">
          Selected token is read-only but “Create GitHub issues on promote” is
          on. Either switch to a{" "}
          <span className="font-mono">read_and_issues</span> token or turn off
          issue promotion in Advanced.
        </div>
      )}

      {showNew && (
        <NewTokenInline
          onCreated={async (id, scope) => {
            await onTokensRefresh();
            if (scope === "read_only" || scope === "read_and_issues") {
              onChange(id);
            }
            setShowNew(false);
          }}
        />
      )}
    </section>
  );
}

function TokenPicker({
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
  const [status, setStatus] = useState<
    "idle" | "checking" | "ok" | "warn" | "bad"
  >("idle");
  const [note, setNote] = useState<string | null>(null);

  // Auto-validate whenever the user picks a different token.
  useEffect(() => {
    if (value == null) {
      setStatus("idle");
      setNote(null);
      return;
    }
    let cancelled = false;
    setStatus("checking");
    setNote(null);
    api
      .validateToken(value)
      .then((res) => {
        if (cancelled) return;
        if (res.ok && res.unlinked) {
          setStatus("warn");
          setNote("Identity OK · no repos linked yet");
        } else if (res.ok) {
          setStatus("ok");
          setNote(null);
        } else {
          setStatus("bad");
          setNote("Over-scoped or invalid");
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setStatus("bad");
        setNote(e.message ?? "Check failed");
      });
    return () => {
      cancelled = true;
    };
  }, [value]);

  return (
    <div className="space-y-1">
      <div className="text-subt text-[11px] uppercase tracking-wider">
        {label}
      </div>
      <div className="flex items-center gap-2">
        <select
          value={value ?? ""}
          onChange={(e) =>
            onChange(e.target.value === "" ? null : Number(e.target.value))
          }
          className={INPUT_CLASS + " flex-1"}
        >
          <option value="">— None (public repos only) —</option>
          {options.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label} ({t.scope})
            </option>
          ))}
        </select>
        <StatusPill status={status} note={note} />
      </div>
    </div>
  );
}

function StatusPill({
  status,
  note,
}: {
  status: "idle" | "checking" | "ok" | "warn" | "bad";
  note: string | null;
}) {
  if (status === "idle") return null;
  const map = {
    checking: { text: "Checking…", color: "#9aa3b8" },
    ok: { text: "✓ Valid", color: "#4fae7a" },
    warn: { text: "◐ Identity OK", color: "#d4a45c" },
    bad: { text: "✗ " + (note ?? "Invalid"), color: "#d04a4a" },
  } as const;
  const m = map[status];
  return (
    <span
      className="text-[11px] font-mono whitespace-nowrap"
      style={{ color: m.color }}
      title={note ?? undefined}
    >
      {m.text}
    </span>
  );
}

function NewTokenInline({
  onCreated,
}: {
  onCreated: (
    id: number,
    scope: "read_only" | "read_and_issues" | "issues_only"
  ) => Promise<void>;
}) {
  const [label, setLabel] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [scope, setScope] = useState<
    "read_only" | "read_and_issues" | "issues_only"
  >("read_and_issues");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit = label.trim().length > 0 && secretRef.trim().length > 0;

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.createToken({
        label: label.trim(),
        secret_ref: secretRef.trim(),
        scope,
      });
      await onCreated(res.id, scope);
    } catch (e: any) {
      setErr(e.message ?? "Create failed");
      setBusy(false);
    }
  };

  return (
    <div className="panel-2 p-3 space-y-2 border border-[#353e57]">
      <div className="text-[11px] text-subt uppercase tracking-wider">
        New Token
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="space-y-1">
          <div className="text-[11px] text-subt">Label</div>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="juice-shop read-only"
            className={INPUT_CLASS}
          />
        </label>
        <label className="space-y-1">
          <div className="text-[11px] text-subt">Env var holding the PAT</div>
          <input
            type="text"
            value={secretRef}
            onChange={(e) => setSecretRef(e.target.value)}
            placeholder="GITHUB_PAT_READ"
            className={INPUT_CLASS}
          />
        </label>
      </div>
      <label className="space-y-1 block">
        <div className="text-[11px] text-subt">Scope</div>
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as any)}
          className={INPUT_CLASS}
        >
          <option value="read_only">read_only</option>
          <option value="issues_only">issues_only</option>
          <option value="read_and_issues">read_and_issues</option>
        </select>
      </label>
      {err && <div className="text-[#d04a4a] text-xs">{err}</div>}
      <div className="flex justify-end">
        <button
          onClick={submit}
          disabled={!canSubmit || busy}
          className="px-3 py-1 text-xs disabled:opacity-50"
          style={{
            background: "#323b54",
            color: "#ecf0f8",
            border: "1px solid #4a5373",
          }}
        >
          {busy ? "Saving…" : "Save & Validate"}
        </button>
      </div>
    </div>
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
    <div className="panel-2 p-3 space-y-2">
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          value={repo.url}
          onChange={(e) => onChange({ url: e.target.value })}
          placeholder="https://github.com/owner/name"
          className={INPUT_CLASS + " flex-1 min-w-[220px]"}
          style={invalid ? { borderColor: "#d04a4a88" } : undefined}
        />
        <input
          type="text"
          value={repo.branch}
          onChange={(e) => onChange({ branch: e.target.value })}
          placeholder="branch"
          className={INPUT_CLASS + " w-28 flex-shrink-0"}
        />
        {canRemove && (
          <button
            onClick={onRemove}
            className="text-[#d04a4a] text-xs px-3 py-1.5 hover:bg-panel flex-shrink-0"
            aria-label="Remove repo"
          >
            Remove
          </button>
        )}
      </div>
      {parsed && (
        <div className="text-[11px] text-subt font-mono">
          → {parsed.owner}/{parsed.name}
        </div>
      )}
      {invalid && (
        <div className="text-[11px] text-[#d04a4a] font-mono">
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

function dedupeTokens(rows: TokenRow[]): TokenRow[] {
  const seen = new Set<string>();
  const out: TokenRow[] = [];
  for (const t of rows) {
    const key = `${t.label}::${t.scope}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}
