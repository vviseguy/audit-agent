-- Cyber Audit Agent — SQLite schema
-- One DB file holds structured entities. ChromaDB handles embeddings separately.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------- Reference data ----------

CREATE TABLE IF NOT EXISTS cwe (
  id           TEXT PRIMARY KEY,              -- 'CWE-89'
  name         TEXT NOT NULL,
  short_desc   TEXT,
  detail       TEXT,
  consequences TEXT,
  mitigations  TEXT,
  parent_id    TEXT                            -- FK to cwe.id, nullable
);
CREATE INDEX IF NOT EXISTS idx_cwe_parent ON cwe(parent_id);

-- ---------- Projects ----------

CREATE TABLE IF NOT EXISTS github_token (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  label             TEXT NOT NULL,
  secret_ref        TEXT NOT NULL,             -- env var name, not the secret itself
  scope             TEXT NOT NULL CHECK (scope IN ('read_only','read_and_issues','issues_only')),
  validated_at      TIMESTAMP,
  validation_result TEXT                       -- JSON blob
);

CREATE TABLE IF NOT EXISTS project (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  name                TEXT NOT NULL UNIQUE,
  create_issues       INTEGER NOT NULL DEFAULT 0,  -- bool
  default_risk_lens   TEXT NOT NULL DEFAULT 'balanced',
  daily_token_budget  INTEGER NOT NULL DEFAULT 2000000,
  per_session_pct_cap REAL    NOT NULL DEFAULT 30.0,
  read_token_id       INTEGER REFERENCES github_token(id),
  issues_token_id     INTEGER REFERENCES github_token(id),
  created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS repo (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  url             TEXT NOT NULL,
  owner           TEXT NOT NULL,              -- for allow-list checks
  name            TEXT NOT NULL,              -- repo name
  branch          TEXT NOT NULL DEFAULT 'main',
  last_commit_sha TEXT,
  clone_path      TEXT,
  UNIQUE(project_id, owner, name)
);
CREATE INDEX IF NOT EXISTS idx_repo_project ON repo(project_id);

-- ---------- Scheduling ----------

CREATE TABLE IF NOT EXISTS session (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  type             TEXT NOT NULL CHECK (type IN ('understand','rank','delve','full')),
  risk_lens        TEXT NOT NULL,
  interest_prompt  TEXT,
  scheduled_for    TIMESTAMP NOT NULL,
  recurrence_cron  TEXT,
  session_pct_cap  REAL NOT NULL DEFAULT 30.0,
  -- Total agile-hours this session was budgeted to consume. Populated from
  -- the Ranker's effort_hours at queue time (delve sessions) or from a
  -- type-specific default (understand/rank). Used by the forecast engine.
  budget_hours     REAL,
  -- Hours still owed after prior halted runs. Starts at budget_hours and is
  -- decremented each time a run finishes or halts. When it hits 0 the
  -- session goes to 'done'; otherwise the scheduler picks it up again in the
  -- next availability window.
  remaining_hours  REAL,
  status           TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','done','halted','cancelled')),
  created_by       TEXT,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_session_project ON session(project_id);
CREATE INDEX IF NOT EXISTS idx_session_sched   ON session(scheduled_for);

CREATE TABLE IF NOT EXISTS run (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id             INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  started_at             TIMESTAMP,
  finished_at            TIMESTAMP,
  status                 TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','done','halted','error')),
  tokens_in              INTEGER NOT NULL DEFAULT 0,
  tokens_out             INTEGER NOT NULL DEFAULT 0,
  cost_usd               REAL    NOT NULL DEFAULT 0,
  pct_daily_budget_used  REAL    NOT NULL DEFAULT 0,
  halted_reason          TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_session ON run(session_id);

-- ---------- Vulnerabilities (persistent across runs) ----------

CREATE TABLE IF NOT EXISTS vulnerability (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id        INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  repo_id           INTEGER NOT NULL REFERENCES repo(id)    ON DELETE CASCADE,
  path              TEXT NOT NULL,
  line_start        INTEGER NOT NULL,
  line_end          INTEGER NOT NULL,
  cwe_id            TEXT REFERENCES cwe(id),
  title             TEXT NOT NULL,
  short_desc        TEXT,
  impact            INTEGER,                 -- 1..5
  likelihood        INTEGER,                 -- 1..5
  priority          INTEGER,                 -- impact * likelihood
  effort_hours      REAL,                    -- Ranker's agile-hours estimate for delving this finding
  status            TEXT NOT NULL DEFAULT 'new'
    CHECK (status IN ('new','needs_delve','low_priority','false_positive',
                      'delved','draft_issue','issue_sent','closed','ignored')),
  first_seen_run_id INTEGER REFERENCES run(id),
  last_seen_run_id  INTEGER REFERENCES run(id),
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, repo_id, path, line_start, line_end, cwe_id)
);
CREATE INDEX IF NOT EXISTS idx_vuln_project  ON vulnerability(project_id);
CREATE INDEX IF NOT EXISTS idx_vuln_status   ON vulnerability(status);
CREATE INDEX IF NOT EXISTS idx_vuln_priority ON vulnerability(priority);

-- ---------- Understander annotations ----------

CREATE TABLE IF NOT EXISTS annotation (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id         INTEGER NOT NULL REFERENCES repo(id) ON DELETE CASCADE,
  path            TEXT NOT NULL,
  claude_md_path  TEXT,
  summary         TEXT NOT NULL,
  trust_boundary  INTEGER NOT NULL DEFAULT 0,
  entry_point     INTEGER NOT NULL DEFAULT 0,
  dataflows_json  TEXT,
  last_run_id     INTEGER REFERENCES run(id),
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(repo_id, path)
);

-- ---------- Journal (timeline of all agent actions) ----------

CREATE TABLE IF NOT EXISTS journal_entry (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  vulnerability_id INTEGER REFERENCES vulnerability(id) ON DELETE CASCADE,
  run_id           INTEGER REFERENCES run(id),
  agent            TEXT NOT NULL,
  action           TEXT NOT NULL,
  payload_json     TEXT,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_journal_vuln    ON journal_entry(vulnerability_id);
CREATE INDEX IF NOT EXISTS idx_journal_run     ON journal_entry(run_id);
CREATE INDEX IF NOT EXISTS idx_journal_created ON journal_entry(created_at);

-- ---------- Draft issues (staging area before GitHub promotion) ----------

CREATE TABLE IF NOT EXISTS draft_issue (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  vulnerability_id  INTEGER NOT NULL REFERENCES vulnerability(id) ON DELETE CASCADE,
  project_id        INTEGER NOT NULL REFERENCES project(id)       ON DELETE CASCADE,
  title             TEXT NOT NULL,
  body_md           TEXT NOT NULL,
  severity          TEXT,
  status            TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','approved','sent','rejected','superseded')),
  github_issue_url  TEXT,
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_by       TEXT,
  approved_at       TIMESTAMP,
  sent_at           TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_draft_project ON draft_issue(project_id);
CREATE INDEX IF NOT EXISTS idx_draft_status  ON draft_issue(status);
CREATE INDEX IF NOT EXISTS idx_draft_vuln    ON draft_issue(vulnerability_id);

-- ---------- Daily token accounting ----------

CREATE TABLE IF NOT EXISTS token_ledger (
  day         DATE PRIMARY KEY,
  tokens_in   INTEGER NOT NULL DEFAULT 0,
  tokens_out  INTEGER NOT NULL DEFAULT 0,
  cost_usd    REAL    NOT NULL DEFAULT 0
);

-- ---------- Availability windows ----------
-- The general weekly pattern: one row per enabled (day_of_week, hour) cell.
-- day_of_week: 0=Mon..6=Sun, to match Python's datetime.weekday().
-- Absence of a row means that hour is NOT available.
CREATE TABLE IF NOT EXISTS availability_cell (
  day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
  hour        INTEGER NOT NULL CHECK(hour BETWEEN 0 AND 23),
  PRIMARY KEY(day_of_week, hour)
);

-- One-off overrides over specific datetime ranges. mode='blocked' forces that
-- range OFF even if the general pattern says ON (e.g. a deadline week where
-- you need the box for something else); mode='available' forces it ON
-- (e.g. "extra audit push this Sunday afternoon").
CREATE TABLE IF NOT EXISTS availability_override (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  start_at   TIMESTAMP NOT NULL,
  end_at     TIMESTAMP NOT NULL,
  mode       TEXT NOT NULL CHECK(mode IN ('available','blocked')),
  note       TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_avail_override_start ON availability_override(start_at);
