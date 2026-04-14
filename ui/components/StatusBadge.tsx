import { STATUS_COLOR, STATUS_LABEL, type Status } from "@/lib/status";

export function StatusBadge({ status }: { status: string }) {
  const s = status as Status;
  const bg = STATUS_COLOR[s] ?? "#3b4150";
  const label = STATUS_LABEL[s] ?? status;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-xs"
      style={{ background: `${bg}33`, color: bg, border: `1px solid ${bg}55` }}
    >
      <span className="w-2 h-2 rounded-sm" style={{ background: bg }} />
      {label}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  // Aligned with the SquareGrid vulnColor palette so the two visual systems
  // read as the same language: green = low risk, red = very bad.
  const map: Record<string, string> = {
    info: "#8b91a4",
    low: "#5e9e6a",
    medium: "#b9b04a",
    high: "#d87a3c",
    critical: "#d04a4a",
  };
  const bg = map[severity] ?? "#8b91a4";
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-semibold uppercase tracking-wider"
      style={{ background: `${bg}22`, color: bg, border: `1px solid ${bg}55` }}
    >
      {severity}
    </span>
  );
}
