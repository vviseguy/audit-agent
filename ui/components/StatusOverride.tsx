"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ALL_STATUSES, STATUS_LABEL } from "@/lib/status";

export function StatusOverride({
  vulnId,
  current,
}: {
  vulnId: number;
  current: string;
}) {
  const [status, setStatus] = useState(current);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await api.overrideStatus(vulnId, status, note || undefined);
      setMsg("saved");
      setTimeout(() => setMsg(null), 2000);
    } catch (e: any) {
      setMsg(`error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel p-3 space-y-2">
      <div className="text-xs text-subt">manual override</div>
      <div className="flex items-center gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="bg-panel-2 border border-border rounded px-2 py-1 text-sm"
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="note (optional)"
          className="flex-1 bg-panel-2 border border-border rounded px-2 py-1 text-sm"
        />
        <button
          onClick={save}
          disabled={saving}
          className="panel-2 border border-border hover:bg-panel px-3 py-1 text-sm disabled:opacity-50"
        >
          {saving ? "…" : "save"}
        </button>
      </div>
      {msg && <div className="text-xs text-subt">{msg}</div>}
    </div>
  );
}
