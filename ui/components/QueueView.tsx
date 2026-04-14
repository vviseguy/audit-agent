"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type AvailabilityDoc,
  type AvailabilityOverride,
  type ForecastPlan,
  type Project,
} from "@/lib/api";
import { HourGrid, cellsToSet, setToCells, type CellKey } from "./HourGrid";

type Mode = "general" | "weekly";

function fmtDate(s: string) {
  const d = new Date(s.replace(" ", "T"));
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

function fmtTime(s: string) {
  const d = new Date(s.replace(" ", "T"));
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtHoursHuman(h: number): string {
  if (h < 1) return `${Math.round(h * 60)}m`;
  const whole = Math.floor(h);
  const rem = Math.round((h - whole) * 60);
  return rem ? `${whole}h${rem}m` : `${whole}h`;
}

// Colors used to tag project work in the weekly grid overlay + queue list.
const PROJECT_COLORS = [
  "#d4a45c",
  "#4fae7a",
  "#9a6ad1",
  "#5884d9",
  "#d04a4a",
  "#7ac1c1",
];
function colorForProject(id: number): string {
  return PROJECT_COLORS[id % PROJECT_COLORS.length];
}

export function QueueView({
  initialAvailability,
  initialForecast,
  projects,
}: {
  initialAvailability: AvailabilityDoc;
  initialForecast: ForecastPlan;
  projects: Project[];
}) {
  const [mode, setMode] = useState<Mode>("weekly");
  const [cells, setCells] = useState<Set<CellKey>>(
    cellsToSet(initialAvailability.cells)
  );
  const [overrides, setOverrides] = useState<AvailabilityOverride[]>(
    initialAvailability.overrides
  );
  const [forecast, setForecast] = useState<ForecastPlan>(initialForecast);
  const [projectFilter, setProjectFilter] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // The weekly grid overlays: which (day, hour) cells the forecast puts work in.
  // Derived from the current forecast's assignments. One dot per cell colored
  // by the first project that lands there — the tooltip shows the details.
  const weeklyOverlays = useMemo(() => {
    const map = new Map<CellKey, { color: string; label?: string }>();
    for (const w of forecast.windows) {
      for (const a of w.assignments) {
        const d = new Date(a.start_at.replace(" ", "T"));
        const end = new Date(a.end_at.replace(" ", "T"));
        // Paint every hour cell that the assignment covers.
        const cur = new Date(d);
        cur.setMinutes(0, 0, 0);
        while (cur < end) {
          const key: CellKey = `${cur.getDay() === 0 ? 6 : cur.getDay() - 1}-${cur.getHours()}`;
          if (!map.has(key)) {
            map.set(key, {
              color: colorForProject(a.project_id),
              label: `${a.project_name} · ${a.title}`,
            });
          }
          cur.setHours(cur.getHours() + 1);
        }
      }
    }
    return map;
  }, [forecast]);

  const refreshForecast = async () => {
    try {
      const next = await api.forecast(projectFilter ?? undefined, 7);
      setForecast(next);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refreshForecast();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectFilter]);

  const saveCells = async () => {
    setSaving(true);
    try {
      await api.saveAvailabilityCells(setToCells(cells));
      setDirty(false);
      await refreshForecast();
    } finally {
      setSaving(false);
    }
  };

  const visibleWindows = forecast.windows.filter((w) => w.assignments.length > 0);
  const totalHours = visibleWindows.reduce((s, w) => s + w.used_hours, 0);
  const totalItems = new Set(
    visibleWindows.flatMap((w) => w.assignments.map((a) => `${a.item_kind}:${a.item_id}`))
  ).size;

  // Final ETA per work item: the end_at of its last slice (where
  // continues_into_next_window is false). Items that span multiple windows
  // surface this so the user sees "finishes ~<time>" on every slice, not
  // just the last one.
  const etaByItem = useMemo(() => {
    const map = new Map<string, string>();
    for (const w of forecast.windows) {
      for (const a of w.assignments) {
        const key = `${a.item_kind}:${a.item_id}`;
        if (!a.continues_into_next_window) {
          map.set(key, a.end_at);
        }
      }
    }
    return map;
  }, [forecast]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subt">scheduling</div>
          <h1 className="text-2xl font-semibold tracking-tight">queue</h1>
          <div className="text-subt text-sm mt-1">
            set your weekly availability below; the queue packs pending work
            into open windows and shows ETAs.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="panel-2 flex text-xs">
            <button
              onClick={() => setMode("general")}
              className="px-3 py-1.5"
              style={{ background: mode === "general" ? "#1b1f2b" : "transparent" }}
            >
              general pattern
            </button>
            <button
              onClick={() => setMode("weekly")}
              className="px-3 py-1.5"
              style={{ background: mode === "weekly" ? "#1b1f2b" : "transparent" }}
            >
              this week
            </button>
          </div>
          <select
            value={projectFilter ?? ""}
            onChange={(e) =>
              setProjectFilter(e.target.value ? Number(e.target.value) : null)
            }
            className="panel-2 px-2 py-1.5 text-xs"
          >
            <option value="">all projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      <section className="panel p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">
            {mode === "general"
              ? "general weekly pattern · click cells to toggle"
              : "this week · general pattern with forecast overlay"}
          </h2>
          <div className="flex items-center gap-2 text-xs">
            {dirty && (
              <span className="text-[#d4a45c]">unsaved changes</span>
            )}
            <button
              disabled={!dirty || saving}
              onClick={saveCells}
              className="panel-2 px-2 py-1 text-xs disabled:opacity-50"
            >
              {saving ? "saving…" : "save pattern"}
            </button>
          </div>
        </div>
        <HourGrid
          enabled={cells}
          onChange={(next) => {
            setCells(next);
            setDirty(true);
          }}
          readOnly={mode === "weekly"}
          overlays={mode === "weekly" ? weeklyOverlays : undefined}
        />
        <div className="text-[11px] text-subt flex gap-4">
          <span>
            {cells.size} hour{cells.size === 1 ? "" : "s"}/week available
          </span>
          {mode === "weekly" && (
            <span>
              dots = work the forecast would run here · colored by project
            </span>
          )}
        </div>
      </section>

      <OverrideList
        overrides={overrides}
        onAdd={async (body) => {
          const { id } = await api.addOverride(body);
          setOverrides((prev) =>
            [...prev, { id, created_at: "", ...body, note: body.note ?? null }]
              .sort((a, b) => a.start_at.localeCompare(b.start_at))
          );
          await refreshForecast();
        }}
        onDelete={async (id) => {
          await api.deleteOverride(id);
          setOverrides((prev) => prev.filter((o) => o.id !== id));
          await refreshForecast();
        }}
      />

      <section className="space-y-2">
        <div className="flex items-end justify-between">
          <h2 className="text-sm font-medium">the queue</h2>
          <div className="text-xs text-subt font-mono">
            {totalItems} items · ~{fmtHoursHuman(totalHours)} scheduled
          </div>
        </div>

        {visibleWindows.length === 0 ? (
          <div className="panel p-6 text-center text-subt text-sm">
            nothing scheduled. {cells.size === 0 ? "set availability above to start packing." : "no pending work to place."}
          </div>
        ) : (
          <div className="panel divide-y divide-border">
            {visibleWindows.map((w, i) => {
              const start = new Date(w.start_at.replace(" ", "T"));
              const end = new Date(w.end_at.replace(" ", "T"));
              return (
                <div key={`${w.start_at}-${i}`} className="p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-baseline gap-2">
                      <span className="text-ink font-medium">
                        {fmtDate(w.start_at)}
                      </span>
                      <span className="text-subt font-mono">
                        {fmtTime(w.start_at)}–{fmtTime(w.end_at)}
                      </span>
                    </div>
                    <div className="text-subt font-mono">
                      {fmtHoursHuman(w.used_hours)} / {fmtHoursHuman(w.capacity_hours)}
                    </div>
                  </div>
                  <hr className="border-border" />
                  <ul className="space-y-1 text-sm">
                    {w.assignments.map((a, j) => {
                      const finalEta = etaByItem.get(
                        `${a.item_kind}:${a.item_id}`
                      );
                      const spans =
                        a.continues_into_next_window ||
                        a.continued_from_prior_window;
                      return (
                        <li
                          key={`${a.item_kind}-${a.item_id}-${j}`}
                          className="flex items-center gap-3"
                        >
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ background: colorForProject(a.project_id) }}
                          />
                          <span className="text-subt font-mono text-xs w-20">
                            {fmtTime(a.start_at)}–{fmtTime(a.end_at)}
                          </span>
                          <span className="text-ink flex-1 truncate">
                            {a.title}
                            {a.continued_from_prior_window && (
                              <span className="ml-2 text-[10px] text-[#8eb0ef]">
                                ← resumed
                              </span>
                            )}
                            {a.continues_into_next_window && (
                              <span className="ml-2 text-[10px] text-[#8eb0ef]">
                                continues →
                              </span>
                            )}
                          </span>
                          {finalEta && spans && (
                            <span
                              className="text-[10px] text-[#8eb0ef] font-mono whitespace-nowrap"
                              title="final ETA across all windows"
                            >
                              finishes ~{fmtDate(finalEta)} {fmtTime(finalEta)}
                            </span>
                          )}
                          <span className="text-subt text-xs">
                            {a.project_name}
                          </span>
                          <span className="text-subt font-mono text-xs w-12 text-right">
                            {fmtHoursHuman(a.hours)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {forecast.unscheduled.length > 0 && (
        <section className="panel p-4 space-y-2">
          <h2 className="text-sm font-medium">
            won&apos;t fit in the next 7 days ·{" "}
            <span className="text-[#d4a45c]">
              {forecast.unscheduled.length} items
            </span>
          </h2>
          <div className="text-xs text-subt">
            widen availability or extend the horizon to schedule these.
          </div>
          <ul className="text-xs space-y-1">
            {forecast.unscheduled.slice(0, 10).map((u) => (
              <li
                key={`${u.item_kind}-${u.item_id}`}
                className="flex items-center gap-3"
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: colorForProject(u.project_id) }}
                />
                <span className="text-ink flex-1 truncate">{u.title}</span>
                <span className="text-subt">{u.project_name}</span>
                <span className="text-subt font-mono">
                  {fmtHoursHuman(u.hours_remaining)}
                </span>
              </li>
            ))}
            {forecast.unscheduled.length > 10 && (
              <li className="text-subt">
                + {forecast.unscheduled.length - 10} more…
              </li>
            )}
          </ul>
        </section>
      )}
    </div>
  );
}

function OverrideList({
  overrides,
  onAdd,
  onDelete,
}: {
  overrides: AvailabilityOverride[];
  onAdd: (body: {
    start_at: string;
    end_at: string;
    mode: "available" | "blocked";
    note?: string | null;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [oMode, setOMode] = useState<"available" | "blocked">("blocked");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!start || !end) return;
    setBusy(true);
    try {
      await onAdd({
        start_at: start.replace("T", " "),
        end_at: end.replace("T", " "),
        mode: oMode,
        note: note || null,
      });
      setStart("");
      setEnd("");
      setNote("");
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">one-off overrides</h2>
        <button
          onClick={() => setOpen((o) => !o)}
          className="panel-2 px-2 py-1 text-xs"
        >
          {open ? "cancel" : "+ override"}
        </button>
      </div>
      {open && (
        <div className="panel-2 p-3 space-y-2 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <div className="text-subt">start</div>
              <input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="w-full bg-panel border border-border px-2 py-1 font-mono"
              />
            </label>
            <label className="space-y-1">
              <div className="text-subt">end</div>
              <input
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="w-full bg-panel border border-border px-2 py-1 font-mono"
              />
            </label>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={oMode === "blocked"}
                onChange={() => setOMode("blocked")}
              />
              blocked (off)
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={oMode === "available"}
                onChange={() => setOMode("available")}
              />
              available (on)
            </label>
          </div>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="note (optional)"
            className="w-full bg-panel border border-border px-2 py-1"
          />
          <button
            onClick={submit}
            disabled={busy || !start || !end}
            className="panel px-3 py-1 text-xs disabled:opacity-50"
          >
            add override
          </button>
        </div>
      )}
      {overrides.length === 0 ? (
        <div className="text-subt text-xs">
          no one-off blocks or extra windows scheduled.
        </div>
      ) : (
        <ul className="text-xs space-y-1">
          {overrides.map((o) => (
            <li key={o.id} className="flex items-center gap-3">
              <span
                className="w-2 h-2 rounded-sm"
                style={{
                  background: o.mode === "blocked" ? "#d04a4a" : "#4fae7a",
                }}
              />
              <span className="text-ink font-mono">
                {fmtDate(o.start_at)} {fmtTime(o.start_at)}–{fmtTime(o.end_at)}
              </span>
              <span className="text-subt">{o.mode}</span>
              {o.note && <span className="text-subt italic">{o.note}</span>}
              <button
                onClick={() => onDelete(o.id)}
                className="ml-auto text-subt hover:text-[#d04a4a]"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
