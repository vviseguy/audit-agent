"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function BudgetMeter() {
  const [data, setData] = useState<{
    tokens_used_today: number;
    daily_token_budget: number;
    pct: number;
  } | null>(null);

  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      try {
        const d = await api.budgetToday();
        if (mounted) setData(d);
      } catch {
        /* offline */
      }
    };
    tick();
    const id = setInterval(tick, 15_000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  if (!data) return <div className="text-xs text-subt">budget …</div>;

  const pct = Math.min(100, data.pct);
  const color = pct > 85 ? "#d04a4a" : pct > 60 ? "#d4a45c" : "#4fae7a";

  return (
    <div className="flex items-center gap-2 text-xs text-subt">
      <span className="font-mono">
        {Math.round(data.tokens_used_today / 1000)}k / {Math.round(data.daily_token_budget / 1000)}k
      </span>
      <div className="w-24 h-1.5 bg-panel2 rounded overflow-hidden">
        <div
          className="h-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="font-mono w-10 text-right">{pct.toFixed(1)}%</span>
    </div>
  );
}
