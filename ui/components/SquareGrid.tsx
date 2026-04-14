"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ALL_STATUSES,
  STATUS_COLOR,
  STATUS_LABEL,
  isVeryHighPriority,
  priorityBucket,
  vulnColor,
  type Status,
} from "@/lib/status";
import type { Vulnerability } from "@/lib/api";

type Group = { key: string; label: string; items: Vulnerability[] };

function groupByArea(vulns: Vulnerability[]): Group[] {
  const buckets = new Map<string, Vulnerability[]>();
  for (const v of vulns) {
    const top = v.path.split(/[\\/]/)[0] || ".";
    if (!buckets.has(top)) buckets.set(top, []);
    buckets.get(top)!.push(v);
  }
  return [...buckets.entries()]
    .map(([key, items]) => ({
      key,
      label: key,
      items: items.sort((a, b) => b.priority - a.priority),
    }))
    .sort((a, b) => b.items.length - a.items.length);
}

export function SquareGrid({ vulns }: { vulns: Vulnerability[] }) {
  const [statusFilter, setStatusFilter] = useState<Set<Status>>(
    new Set(ALL_STATUSES)
  );
  const [minPriority, setMinPriority] = useState(0);
  const [hover, setHover] = useState<Vulnerability | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const filtered = useMemo(
    () =>
      vulns.filter(
        (v) => statusFilter.has(v.status as Status) && v.priority >= minPriority
      ),
    [vulns, statusFilter, minPriority]
  );

  const groups = useMemo(() => groupByArea(filtered), [filtered]);

  const toggleStatus = (s: Status) => {
    const next = new Set(statusFilter);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setStatusFilter(next);
  };

  return (
    <div className="space-y-4">
      <div className="panel p-3 flex flex-wrap items-center gap-3 text-xs">
        <span className="text-subt">status:</span>
        {ALL_STATUSES.map((s) => {
          const on = statusFilter.has(s);
          return (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className="flex items-center gap-1.5"
              style={{ opacity: on ? 1 : 0.35 }}
            >
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ background: STATUS_COLOR[s] }}
                aria-hidden
              />
              {STATUS_LABEL[s]}
            </button>
          );
        })}
        <span className="text-subt ml-4">min priority:</span>
        <input
          type="range"
          min={0}
          max={25}
          value={minPriority}
          onChange={(e) => setMinPriority(Number(e.target.value))}
          className="w-40"
        />
        <span className="font-mono text-subt w-6 text-right">{minPriority}</span>
        <span className="ml-auto text-subt">
          showing <span className="text-ink font-mono">{filtered.length}</span>{" "}
          of <span className="font-mono">{vulns.length}</span>
        </span>
      </div>

      <div className="panel p-4 space-y-5 relative">
        {groups.map((g) => (
          <section key={g.key}>
            <header className="flex items-baseline gap-2 mb-2">
              <h3 className="text-sm font-medium text-ink">{g.label}</h3>
              <span className="text-xs text-subt font-mono">({g.items.length})</span>
            </header>
            <div className="sq-grid">
              {g.items.map((v) => (
                <Link
                  key={v.id}
                  href={`/vulnerabilities/${v.id}`}
                  className={`sq ${priorityBucket(v.priority)}${
                    isVeryHighPriority(v.priority) ? " sq-very-high" : ""
                  }`}
                  style={{ background: vulnColor(v.status, v.priority) }}
                  onMouseEnter={(e) => {
                    setHover(v);
                    setHoverPos({ x: e.clientX, y: e.clientY });
                  }}
                  onMouseMove={(e) =>
                    setHoverPos({ x: e.clientX, y: e.clientY })
                  }
                  onMouseLeave={() => setHover(null)}
                  aria-label={`${v.title} (${v.cwe_id ?? "no cwe"}, priority ${v.priority})`}
                />
              ))}
            </div>
          </section>
        ))}

        {hover && (
          <div
            className="fixed z-50 pointer-events-none panel-2 text-xs p-2 shadow-xl max-w-xs"
            style={{
              left: Math.min(hoverPos.x + 12, window.innerWidth - 260),
              top: Math.min(hoverPos.y + 12, window.innerHeight - 110),
            }}
          >
            <div className="font-medium text-ink truncate">{hover.title}</div>
            <div className="text-subt font-mono">
              {hover.path}:{hover.line_start}-{hover.line_end}
            </div>
            <div className="mt-1 flex gap-3 text-subt">
              <span>{hover.cwe_id ?? "no CWE"}</span>
              <span>impact {hover.impact}</span>
              <span>likelihood {hover.likelihood}</span>
              <span>priority {hover.priority}</span>
            </div>
            <div
              className="mt-1"
              style={{ color: STATUS_COLOR[hover.status as Status] }}
            >
              {STATUS_LABEL[hover.status as Status] ?? hover.status}
            </div>
          </div>
        )}
      </div>

      <ColorLegend />
    </div>
  );
}

function ColorLegend() {
  return (
    <div className="text-[11px] text-subt flex flex-wrap items-center gap-3">
      <span>color:</span>
      <LegendSwatch color="#0d0f16" label="untouched" />
      <LegendSwatch color="#2b2f3c" label="dismissed" />
      <LegendSwatch color="#5e9e6a" label="low risk" />
      <LegendSwatch color="#b9b04a" label="watch" />
      <LegendSwatch color="#d4a45c" label="concerning" />
      <LegendSwatch color="#d87a3c" label="high" />
      <LegendSwatch color="#d04a4a" label="very bad" />
      <LegendSwatch color="#4fae7a" label="shipped" />
      <span className="ml-2">
        · border = priority (impact × likelihood) · white ring = critical
      </span>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className="inline-block w-3 h-3 rounded-sm"
        style={{ background: color }}
        aria-hidden
      />
      {label}
    </span>
  );
}
