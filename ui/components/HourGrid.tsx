"use client";

import { useState } from "react";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

export type CellKey = `${number}-${number}`;

function toKey(dow: number, hour: number): CellKey {
  return `${dow}-${hour}`;
}

export function HourGrid({
  enabled,
  onChange,
  readOnly = false,
  // Weekly-preview overlays: each cell can carry a colored dot if the
  // forecast placed work in that (day, hour).
  overlays,
}: {
  enabled: Set<CellKey>;
  onChange?: (next: Set<CellKey>) => void;
  readOnly?: boolean;
  overlays?: Map<CellKey, { color: string; label?: string }>;
}) {
  // Drag-to-paint: track whether the initial cell was an on->off toggle or
  // an off->on toggle so dragging applies the same direction across cells.
  const [dragMode, setDragMode] = useState<"on" | "off" | null>(null);

  const toggle = (key: CellKey, force?: "on" | "off") => {
    if (readOnly || !onChange) return;
    const next = new Set(enabled);
    const mode = force ?? (next.has(key) ? "off" : "on");
    if (mode === "on") next.add(key);
    else next.delete(key);
    onChange(next);
  };

  return (
    <div
      className="inline-block select-none"
      onMouseLeave={() => setDragMode(null)}
      onMouseUp={() => setDragMode(null)}
    >
      <div className="flex">
        <div className="w-8" />
        {HOURS.map((h) => (
          <div
            key={h}
            className="w-5 text-[9px] text-subt text-center font-mono"
          >
            {h % 3 === 0 ? h.toString().padStart(2, "0") : ""}
          </div>
        ))}
      </div>
      {DAYS.map((label, dow) => (
        <div key={dow} className="flex items-center">
          <div className="w-8 text-[10px] text-subt font-mono">{label}</div>
          {HOURS.map((h) => {
            const key = toKey(dow, h);
            const on = enabled.has(key);
            const overlay = overlays?.get(key);
            return (
              <button
                key={h}
                type="button"
                onMouseDown={(e) => {
                  if (readOnly) return;
                  e.preventDefault();
                  const newMode = on ? "off" : "on";
                  setDragMode(newMode);
                  toggle(key, newMode);
                }}
                onMouseEnter={() => {
                  if (dragMode) toggle(key, dragMode);
                }}
                title={
                  overlay?.label
                    ? `${label} ${h}:00 — ${overlay.label}`
                    : `${label} ${h}:00`
                }
                className="w-5 h-5 relative border border-border/60"
                style={{
                  background: on ? "#3a5a8f" : "#141722",
                }}
              >
                {overlay && (
                  <span
                    className="absolute inset-0 m-auto w-1.5 h-1.5 rounded-full"
                    style={{ background: overlay.color }}
                  />
                )}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function cellsToSet(cells: [number, number][]): Set<CellKey> {
  const s = new Set<CellKey>();
  for (const [d, h] of cells) s.add(toKey(d, h));
  return s;
}

export function setToCells(s: Set<CellKey>): [number, number][] {
  const out: [number, number][] = [];
  for (const k of s) {
    const [d, h] = k.split("-").map(Number);
    out.push([d, h]);
  }
  return out;
}
