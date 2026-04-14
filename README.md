# audit-agent — self-hosted cybersecurity audit agent

Three-agent pipeline that ingests GitHub repos, annotates them, ranks their
vulnerabilities by impact × likelihood, and delves into the top ones — producing
a tracked journal and draft GitHub issues that a human batch-approves in a PWA.

Built for an agentic engineering class final project. The design commitments:

- **Three YAML-specced agents**, one job each — Understander, Ranker, Delver.
  Model, prompts, tools and rate limits are swappable without code changes.
- **Agents run in Docker; the rest doesn't.** Only the code that reads untrusted
  source and calls the LLM is sandboxed; FastAPI, the scheduler and the PWA run
  on the host.
- **Vulnerabilities are persistent entities**, not ephemeral findings. Each run
  appends `journal_entry` rows so the history reads like a commit log.
- **Understand before you judge.** The first pass writes `CLAUDE.md` files into
  the clone; later passes read them as context.
- **Light-touch hallucination control.** Delvers must cite `file:line`; citations
  are checked at ingest time. No separate verifier agent.

## Architecture

```
 Project YAMLs ───► Scheduler (APScheduler in FastAPI on host)
                             │
                             ▼
                     Job dispatcher (host)
                             │
                     docker run agents:latest <run_id>
                             │
                     ┌───────┴───────┐
                     ▼               ▼
                 Understander    (on first run or changed files)
                             │
                             ▼
                      Ranker  (batched)
                             │
                             ▼
                      Delver  (top-K only)
                             │
                             ▼
             draft_issue rows + journal entries
                             │
                   human approval in PWA
                             │
                             ▼
                   real GitHub issues
```

**Host (no Docker):** FastAPI (`server/main.py`), APScheduler, Next.js PWA.
**Container (`Dockerfile.agents`):** Python 3.11, Semgrep, ChromaDB, Anthropic
SDK. Network: outbound to `api.anthropic.com` and `api.github.com` only.

Two data stores: **SQLite** for structured entities and joins, **ChromaDB** for
two collections (`cwe_entries` for CWE semantic lookup; `project_memory` for the
Delver's "have we seen this before?" similarity search).

## First-time setup (Windows dev box)

```powershell
# 1. Python 3.14 host
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # then add ANTHROPIC_API_KEY

# 2. Build the agents container
docker build -f Dockerfile.agents -t agents:latest .

# 3. Seed the CWE store (MITRE XML -> SQLite + ChromaDB)
python -m rag.build_cwe_store

# 4. Seed the demo project so the PWA has something to show
python scripts/seed_demo.py

# 5. Host services (two terminals)
uvicorn server.main:app --host 0.0.0.0 --port 8000
cd ui && npm install && npm run dev
```

Open http://localhost:3000. The Projects page should show `juice-shop-demo`.

## Home-box deploy

Same steps on the home machine. Once running, both services should bind to
`0.0.0.0`. The PWA installs from the mobile browser via Add to Home Screen.
For HTTPS-on-LAN (required by some phones before they'll install a PWA), use
Tailscale MagicDNS — it hands out a free HTTPS hostname with a trusted cert.

Avoid Windows sleep while sessions are queued: the scheduler surfaces missed
sessions on next boot via `scheduler.catch_up_missed_on_boot`, but it can only
catch up what it can see.

## Configuration

- `config.yaml` — global budgets, concurrency, scheduler window, server/UI ports.
- `projects/*.yaml` — importable project specs. Import with
  `python scripts/import_project.py projects/example.yaml`. After import, the
  UI is the editing surface.
- `agents/*.yaml` — per-agent model, prompts, tools, rate limits. Adding a
  specialist agent = dropping a new YAML plus a prompt file.
- `.env` — `ANTHROPIC_API_KEY` and GitHub PATs referenced by `github_token`
  rows.

## Verifying the pipeline without burning tokens

```powershell
python scripts/smoke_rank.py       # stubs Anthropic, exercises ranker
python scripts/smoke_delve.py      # stubs Anthropic, exercises delver
python scripts/smoke_github.py     # stubs GitHub, exercises token validation
python scripts/smoke_scheduler.py  # drives scheduler tick with stub dispatcher
```

## Demo script (5 minutes)

Walk through the PWA end-to-end after `seed_demo.py` has run.

1. **Projects page on phone PWA** — open `http://<lan-ip>:3000` on a phone
   that's joined the Tailnet; install as PWA; click `juice-shop-demo`.
2. **Grid view** — the headline. Hover a red square to show the tooltip with
   CWE, priority, last journal entry. Toggle status filters and the priority
   slider to show the filter-without-reload pattern.
3. **Vulnerability detail** — click a square. The journal timeline shows
   understander → ranker → delver for that finding. The draft issue body is
   rendered directly from `draft_issue.body_md` so what you see is what ships.
4. **Calendar** — queue a new `delve` session. Pick risk lens = `high_impact`,
   set cap = 20%. Show the token pre-flight passing for `juice-shop-demo`.
5. **Draft Issues** — batch-review surface. Select two drafts, click
   **Approve & Send**. Real GitHub issues appear and the vulnerabilities flip
   to `issue_sent`.
6. **History** — commit-graph feed showing understander, ranker and delver
   actions over time, filterable by agent. Demonstrates "vulnerabilities as
   persistent entities" visually.
7. **Agent-independent engine** — open `agents/ranker.yaml`, change `model`
   from `claude-sonnet-4-6` to `claude-haiku-4-5-20251001`, re-queue a rank
   session from the calendar, show the Jobs page picking it up with the new
   model. No Python changes.

## Rubric coverage

Patterns exercised (targeting 5 of 6):

1. **Prompt engineering** — per-agent system prompts (`prompts/*.md`), strict
   JSON output schemas (`schemas/*.schema.json`), answer-tool pattern for
   structured outputs in `tools/rank_candidates_batch.py` and
   `tools/create_draft_issue.py`.
2. **Context management / RAG** — per-file `CLAUDE.md` annotations compress
   repo context; ChromaDB holds two collections
   (`cwe_entries` + `project_memory`); the Delver does a similarity search
   over past journal entries before writing its analysis
   (`tools/retrieve_similar_vulnerabilities.py`).
3. **Tool calling** — `tools/` registry via `@tool` decorator; agents reference
   tools by name in their YAML; new tools drop in without engine changes.
4. **Multiple agents** — Understander → Ranker → Delver, orchestrated by an
   agent-independent engine in `engine/`.
5. **Hallucination control (light-touch)** — citation-required output schema;
   `file:line` range checked against the repo at ingest time; broken citations
   are dropped. No dedicated verifier agent.

## Layout

```
final-final-project/
  agents/        # YAML specs per agent
  prompts/       # system prompts, loaded by YAMLs
  schemas/       # JSON output schemas
  engine/        # agent-independent runner, registry, budget guard
  tools/         # @tool decorated Python, one per tool
  orchestrator/  # understand_pass / rank_pass / delve_pass / run_job entrypoint
  rag/           # CWE store builder + project_memory upsertion
  gh/            # client, token_validator, issue_formatter, promote
  server/        # FastAPI host + scheduler + dispatch
  db/            # SQLite schema + store helpers
  ui/            # Next.js 14 PWA
  scripts/       # import_project, seed_demo, smoke_*
  Dockerfile.agents
  config.yaml
  projects/*.yaml
```

## Known limits

- Docker Desktop's network rules on Windows are looser than on Linux. The real
  guardrail is the fine-grained PAT + read-only clone, not the network policy.
- If the `sqlite-vec` wheel is unavailable on Windows/Python 3.14, ChromaDB
  handles the embedding store end-to-end; no sqlite-vec dependency at runtime.
- Scheduler drift from Windows sleep is mitigated by the boot-time catch-up
  path, but long sleep windows still need manual confirmation.
