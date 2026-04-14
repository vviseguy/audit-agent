// Thin client for the FastAPI host. The UI never hits SQLite directly —
// this keeps policy (status enums, validation) in one place.

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return (await res.json()) as T;
}

export type ProjectForecast = {
  pending_count: number;
  delve_hours_remaining: number;
  avg_hours_per_finding: number;
};

export type ProjectTokenBrief = {
  id: number;
  label: string;
  scope: string;
  validated_at: string | null;
  validation_result: string | null;
};

export type Project = {
  id: number;
  name: string;
  default_risk_lens: string;
  create_issues: number;
  daily_token_budget: number;
  per_session_pct_cap: number;
  vuln_total: number;
  vuln_needs_delve: number;
  vuln_issue_sent: number;
  next_scheduled: string | null;
  delve_hours_remaining?: number;
  forecast?: ProjectForecast;
  read_token?: ProjectTokenBrief | null;
  issues_token?: ProjectTokenBrief | null;
  draft_count?: number;
};

export type ProjectPatch = {
  default_risk_lens?: string;
  daily_token_budget?: number;
  per_session_pct_cap?: number;
  create_issues?: number;
  // 0 unsets the binding; positive int binds to that github_token row.
  read_token_id?: number;
  issues_token_id?: number;
};

export type NewRepo = {
  url: string;
  branch: string;
};

export type NewProject = {
  name: string;
  default_risk_lens: string;
  daily_token_budget: number;
  per_session_pct_cap: number;
  create_issues: boolean;
  read_token_id: number | null;
  issues_token_id: number | null;
  repos: NewRepo[];
};

export type Vulnerability = {
  id: number;
  project_id: number;
  repo_id: number;
  path: string;
  line_start: number;
  line_end: number;
  cwe_id: string | null;
  title: string;
  short_desc: string | null;
  impact: number;
  likelihood: number;
  priority: number;
  effort_hours: number | null;
  status: string;
  repo_owner?: string;
  repo_name?: string;
};

export type JournalEntry = {
  id: number;
  vulnerability_id: number | null;
  run_id: number | null;
  agent: string;
  action: string;
  payload_json: string | null;
  created_at: string;
  vuln_title?: string;
};

export type DraftIssue = {
  id: number;
  vulnerability_id: number;
  project_id: number;
  title: string;
  body_md: string;
  severity: string;
  status: string;
  github_issue_url: string | null;
  created_at: string;
  updated_at: string;
  cwe_id?: string | null;
  vuln_path?: string | null;
};

export type SessionRow = {
  id: number;
  project_id: number;
  type: string;
  risk_lens: string;
  interest_prompt: string | null;
  scheduled_for: string;
  recurrence_cron: string | null;
  session_pct_cap: number;
  status: string;
  created_by: string | null;
  created_at: string;
};

export type TokenRow = {
  id: number;
  label: string;
  scope: string;
  validated_at: string | null;
  validation_result: string | null;
  projects: string | null;
};

export type AppConfig = {
  budgets: Record<string, any>;
  concurrency: Record<string, any>;
  paths: Record<string, any>;
  scheduler: Record<string, any>;
};

export type AvailabilityOverride = {
  id: number;
  start_at: string;
  end_at: string;
  mode: "available" | "blocked";
  note: string | null;
  created_at: string;
};

export type AvailabilityDoc = {
  cells: [number, number][]; // [dow, hour]
  overrides: AvailabilityOverride[];
};

export type ForecastAssignment = {
  item_kind: "vulnerability" | "session";
  item_id: number;
  project_id: number;
  project_name: string;
  title: string;
  start_at: string;
  end_at: string;
  hours: number;
  continued_from_prior_window: boolean;
  continues_into_next_window: boolean;
};

export type ForecastWindow = {
  start_at: string;
  end_at: string;
  capacity_hours: number;
  used_hours: number;
  free_hours: number;
  assignments: ForecastAssignment[];
};

export type ForecastUnscheduled = {
  item_kind: "vulnerability" | "session";
  item_id: number;
  project_id: number;
  project_name: string;
  title: string;
  hours_remaining: number;
  priority: number;
};

export type ForecastPlan = {
  windows: ForecastWindow[];
  unscheduled: ForecastUnscheduled[];
};

export type RunRow = {
  id: number;
  session_id: number;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  pct_daily_budget_used: number;
  halted_reason: string | null;
};

export const api = {
  projects: () => request<Project[]>("/projects"),
  project: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (body: NewProject) =>
    request<{ id: number; name: string }>("/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProject: (id: number) =>
    request<{ ok: boolean; deleted_id: number; deleted_name: string }>(
      `/projects/${id}`,
      { method: "DELETE" }
    ),
  updateProject: (id: number, patch: ProjectPatch) =>
    request<{ ok: boolean; changed: number }>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  vulnerabilities: (projectId: number) =>
    request<Vulnerability[]>(`/projects/${projectId}/vulnerabilities`),
  vulnerability: (id: number) =>
    request<Vulnerability & { journal: JournalEntry[]; draft_issue: DraftIssue | null }>(
      `/vulnerabilities/${id}`
    ),
  projectJournal: (projectId: number, limit = 200) =>
    request<JournalEntry[]>(`/projects/${projectId}/journal?limit=${limit}`),
  drafts: (projectId: number) =>
    request<DraftIssue[]>(`/projects/${projectId}/draft_issues`),
  sessions: (projectId?: number) =>
    request<SessionRow[]>(
      projectId ? `/sessions?project_id=${projectId}` : "/sessions"
    ),
  runs: (limit = 50) => request<RunRow[]>(`/runs?limit=${limit}`),
  tokens: () => request<TokenRow[]>("/tokens"),
  createToken: (body: {
    label: string;
    secret_ref: string;
    scope: "read_only" | "read_and_issues" | "issues_only";
  }) =>
    request<{ id: number; deduped: boolean }>("/tokens", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteToken: (id: number) =>
    request<{ ok: boolean; deleted_id: number; deleted_label: string }>(
      `/tokens/${id}`,
      { method: "DELETE" }
    ),
  config: () => request<AppConfig>("/config"),
  availability: () => request<AvailabilityDoc>("/availability"),
  saveAvailabilityCells: (cells: [number, number][]) =>
    request<{ ok: boolean; saved: number }>("/availability/cells", {
      method: "POST",
      body: JSON.stringify({ cells }),
    }),
  addOverride: (body: {
    start_at: string;
    end_at: string;
    mode: "available" | "blocked";
    note?: string | null;
  }) =>
    request<{ id: number }>("/availability/overrides", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteOverride: (id: number) =>
    request<{ ok: boolean }>(`/availability/overrides/${id}`, {
      method: "DELETE",
    }),
  forecast: (projectId?: number, days = 7) =>
    request<ForecastPlan>(
      `/queue/forecast?days=${days}${projectId ? `&project_id=${projectId}` : ""}`
    ),
  budgetToday: () =>
    request<{ tokens_used_today: number; daily_token_budget: number; pct: number }>(
      "/budget/today"
    ),
  queueSession: (body: {
    project_id: number;
    type: string;
    risk_lens: string;
    interest_prompt?: string | null;
    scheduled_for: string;
    recurrence_cron?: string | null;
    session_pct_cap: number;
  }) =>
    request<{ session_id: number }>("/sessions/queue", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelSession: (id: number) =>
    request<{ ok: boolean }>(`/sessions/${id}/cancel`, { method: "POST" }),
  overrideStatus: (vulnId: number, status: string, note?: string) =>
    request<{ ok: boolean }>(`/vulnerabilities/${vulnId}/status`, {
      method: "POST",
      body: JSON.stringify({ status, note: note ?? null }),
    }),
  validateToken: (tokenId: number) =>
    request<{
      ok: boolean;
      repos: any[];
      token_label: string;
      scope: string;
      unlinked?: boolean;
      identity_ok?: boolean;
      identity_login?: string | null;
      intended_for_issues?: boolean;
    }>(`/tokens/${tokenId}/validate`, { method: "POST" }),
  promoteDrafts: (project_id: number, draft_issue_ids: number[], approved_by: string) =>
    request<{ outcomes: Array<{ draft_issue_id: number; success: boolean; github_issue_url: string | null; error: string | null }> }>(
      "/drafts/promote",
      {
        method: "POST",
        body: JSON.stringify({ project_id, draft_issue_ids, approved_by }),
      }
    ),
};
