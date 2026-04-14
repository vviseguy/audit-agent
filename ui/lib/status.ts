// One place to map vulnerability status → color + label + priority-bucket.
// Keeps the grid, the tooltip, and the detail page consistent.

export type Status =
  | "new"
  | "needs_delve"
  | "low_priority"
  | "false_positive"
  | "delved"
  | "draft_issue"
  | "issue_sent"
  | "closed"
  | "ignored";

export const STATUS_LABEL: Record<Status, string> = {
  new: "New",
  needs_delve: "Needs Delve",
  low_priority: "Low Priority",
  false_positive: "False Positive",
  delved: "Delved",
  draft_issue: "Draft Issue",
  issue_sent: "Issue Sent",
  closed: "Closed",
  ignored: "Ignored",
};

export const STATUS_COLOR: Record<Status, string> = {
  new: "#3b4150",
  needs_delve: "#d4a45c",
  low_priority: "#4a4e5c",
  false_positive: "#2b2f3c",
  delved: "#9a6ad1",
  draft_issue: "#5884d9",
  issue_sent: "#4fae7a",
  closed: "#3a3e4a",
  ignored: "#2b2f3c",
};

export function statusClass(status: string): string {
  const s = status as Status;
  return `sq-status-${s}`;
}

export function priorityBucket(priority: number): string {
  if (priority >= 20) return "sq-p20";
  if (priority >= 16) return "sq-p16";
  if (priority >= 12) return "sq-p12";
  if (priority >= 8) return "sq-p8";
  if (priority >= 4) return "sq-p4";
  return "sq-p1";
}

// Square-grid color encoding.
//
// Two orthogonal axes collapsed onto a single hue:
//   lifecycle — black = untouched (never assessed), gray = dismissed, color = in flight
//   security  — green → yellow → orange → red, driven by priority (impact × likelihood)
//
// An extremely high priority (>=23) gets a white ring to make "very bad" outliers pop.
// issue_sent items are tinted toward a calmer teal-green since they're already out the
// door — a distinct signal from an open finding at the same priority.
export function vulnColor(status: string, priority: number): string {
  if (status === "new" && priority === 0) return "#0d0f16"; // untouched black
  if (
    status === "ignored" ||
    status === "false_positive" ||
    status === "closed"
  ) {
    return "#2b2f3c"; // dismissed, near-black gray
  }
  if (status === "low_priority") return "#4a4e5c"; // muted gray

  if (status === "issue_sent") return "#4fae7a"; // shipped — resolved green

  // In-flight (needs_delve, delved, draft_issue, or anything else with a score).
  const p = Math.max(1, Math.min(25, priority || 1));
  if (p <= 5) return "#5e9e6a"; // green — low risk
  if (p <= 10) return "#b9b04a"; // olive/yellow — watch
  if (p <= 15) return "#d4a45c"; // amber — concerning
  if (p <= 20) return "#d87a3c"; // orange — high
  return "#d04a4a"; // red — very bad
}

export function isVeryHighPriority(priority: number): boolean {
  return priority >= 23;
}

export const ALL_STATUSES: Status[] = [
  "new",
  "needs_delve",
  "low_priority",
  "false_positive",
  "delved",
  "draft_issue",
  "issue_sent",
  "closed",
  "ignored",
];
