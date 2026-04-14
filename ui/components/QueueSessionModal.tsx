"use client";

import { useState } from "react";
import { api, type Project } from "@/lib/api";

const RISK_LENSES: { key: string; label: string; desc: string }[] = [
  {
    key: "high_impact",
    label: "High Impact",
    desc: "privilege escalation, data exfiltration, RCE",
  },
  {
    key: "high_likelihood",
    label: "High Likelihood",
    desc: "easily-triggered by common input",
  },
  {
    key: "ui_visible",
    label: "UI-Visible",
    desc: "code reachable from public endpoints",
  },
  {
    key: "balanced",
    label: "Balanced",
    desc: "order by impact × likelihood equally",
  },
  {
    key: "custom",
    label: "Custom Interest",
    desc: "write your own lens prompt",
  },
];

const TYPES = ["understand", "rank", "delve", "full"];

export function QueueSessionModal({
  projects,
  initialDate,
  onClose,
  onQueued,
}: {
  projects: Project[];
  initialDate: Date;
  onClose: () => void;
  onQueued: () => void;
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? 0);
  const [type, setType] = useState("delve");
  const [lens, setLens] = useState("balanced");
  const [customPrompt, setCustomPrompt] = useState("");
  const [whenDate, setWhenDate] = useState(toLocalInput(initialDate));
  const [pctCap, setPctCap] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setOkMsg(null);
    try {
      const { session_id } = await api.queueSession({
        project_id: projectId,
        type,
        risk_lens: lens,
        interest_prompt: lens === "custom" ? customPrompt : null,
        scheduled_for: new Date(whenDate).toISOString(),
        recurrence_cron: null,
        session_pct_cap: pctCap,
      });
      setOkMsg(`session #${session_id} queued`);
      onQueued();
      setTimeout(onClose, 800);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-xl p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-subt">schedule</div>
            <h2 className="text-lg font-semibold">queue session</h2>
          </div>
          <button
            onClick={onClose}
            className="text-subt hover:text-ink text-sm"
          >
            close
          </button>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-subt">project</label>
          <select
            value={projectId}
            onChange={(e) => setProjectId(Number(e.target.value))}
            className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-sm"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-subt">type</label>
          <div className="flex gap-1">
            {TYPES.map((t) => (
              <button
                key={t}
                onClick={() => setType(t)}
                className={
                  "flex-1 px-2 py-1 text-xs rounded-sm border " +
                  (type === t
                    ? "border-[#5884d9] bg-[#5884d922] text-[#5884d9]"
                    : "border-border text-subt hover:text-ink")
                }
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-subt">risk lens</label>
          <div className="grid grid-cols-1 gap-1">
            {RISK_LENSES.map((r) => (
              <button
                key={r.key}
                onClick={() => setLens(r.key)}
                className={
                  "text-left px-3 py-2 rounded-sm border " +
                  (lens === r.key
                    ? "border-[#9a6ad1] bg-[#9a6ad122]"
                    : "border-border hover:border-[#9a6ad155]")
                }
              >
                <div className="text-sm text-ink">{r.label}</div>
                <div className="text-xs text-subt">{r.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {lens === "custom" && (
          <div className="space-y-1">
            <label className="text-xs text-subt">custom interest prompt</label>
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              rows={2}
              placeholder="e.g. focus on file upload and deserialization paths"
              className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-subt">when</label>
            <input
              type="datetime-local"
              value={whenDate}
              onChange={(e) => setWhenDate(e.target.value)}
              className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-subt">
              session cap: {pctCap}% of daily
            </label>
            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={pctCap}
              onChange={(e) => setPctCap(Number(e.target.value))}
              className="w-full accent-[#4fae7a]"
            />
          </div>
        </div>

        {error && (
          <div className="text-xs text-[#d04a4a]">error: {error}</div>
        )}
        {okMsg && <div className="text-xs text-[#4fae7a]">{okMsg}</div>}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="panel-2 border border-border px-3 py-1 text-sm hover:bg-panel"
          >
            cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || (lens === "custom" && !customPrompt.trim())}
            className="px-3 py-1 text-sm border rounded-sm disabled:opacity-50"
            style={{
              borderColor: "#4fae7a88",
              background: "#4fae7a22",
              color: "#4fae7a",
            }}
          >
            {busy ? "queueing…" : "queue session"}
          </button>
        </div>
      </div>
    </div>
  );
}

function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}
