# AgentLab Phase 1 + 2 Implementation Plan

> **For agentic workers:** Execute tasks in order. Each task ends with a verification gate —
> do not move on until the gate passes. Phases 3+ (replay, lab mode, trust routing) are
> explicitly OUT OF SCOPE until the user approves them.

**Goal:** A working vertical slice of AgentLab: a Python instrumentation SDK emits events from
an example multi-agent workflow → a FastAPI collector validates, stores (PostgreSQL/SQLite), and
broadcasts them → a React dashboard renders live agent topology, run timeline, metrics, and a
Wireshark-style message inspector.

**Architecture:** Monorepo with four isolated units: `packages/sdk-python` (zero-dependency
instrumentation SDK with background-thread event buffering), `apps/api` (FastAPI event collector +
read API + WebSocket fan-out, SQLAlchemy 2.0 projections), `apps/web` (Vite + React + TypeScript
SPA with React Flow topology and Recharts metrics), `examples/basic_multi_agent` (simulated
5-agent pipeline that seeds realistic demo runs without LLM keys). Raw events are the source of
truth; relational projections (runs/agents/messages/tool_calls/routing_decisions) are derived at
ingest time for fast queries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, PostgreSQL (Docker) /
SQLite (bare-metal dev + tests), React 18, Vite 6, TypeScript, Tailwind CSS v4, @xyflow/react 12,
Recharts, Zustand, react-router-dom, Docker Compose, nginx.

---

## Locked decisions (assumptions surfaced up front)

1. **React SPA via Vite, not Next.js.** Spec allows either; a WS-heavy internal dashboard gains
   nothing from SSR and a SPA keeps the Docker story (static files behind nginx) simple.
2. **SQLite by default outside Docker; PostgreSQL inside Docker Compose.** One `DATABASE_URL`
   switch. Tests and the 10-minute local quickstart need zero services; compose runs Postgres 16.
3. **Schema via `create_all` on startup for v0.1; Alembic deferred to roadmap.** Pre-1.0 with no
   deployed users, migrations are ceremony; documented in ARCHITECTURE.md.
4. **Trust/routing/lab/security data model ships now, features later.** Event types
   (`routing.decision`, `trust.updated`, `fault.injected`, …), agent trust/risk columns, and the
   RoutingDecision table land in Phase 1 because the demo emits them and the schema must not churn.
   The trust engine, lab UI, and quarantine flows are Phase 4 (needs approval).
5. **Auth = optional static API keys on the write path.** If `AGENTLAB_API_KEYS` is set the
   collector requires `X-API-Key`; otherwise open (local mode). Read API open in v0.1.
6. **Module-level decorators bind to the most recently constructed `AgentLabClient`** (resolved at
   call time), matching the DX in the product spec exactly.
7. **Event ordering** = `(timestamp, ingest sequence id)`. SDK also stamps a per-client
   monotonic `metadata._seq` for forensic tie-breaks.

## Cross-cutting contracts (all units must agree)

### Event envelope (SDK → `POST /api/events`, single object or `{"events": [...]}`)

```json
{
  "event_id": "uuid4 (SDK-generated, idempotency key)",
  "event_type": "message.sent",
  "timestamp": "2026-06-09T12:00:00.123Z",
  "project_id": "demo-project",
  "run_id": "run-…",
  "source_agent_id": "planner | null",
  "target_agent_id": "researcher | null",
  "payload": {},
  "metadata": {"_seq": 17, "parent_event_id": "uuid of enclosing agent span", "sdk": "agentlab-python/0.1.0"}
}
```

Response: `202 {"accepted": N, "duplicates": M}`. Unknown `event_type` → 422.
Event type registry (validated): `run.started|completed|failed`, `agent.started|completed|failed|heartbeat`,
`message.sent|received|failed`, `tool.called|completed|failed`, `model.called|completed|failed`,
`routing.decision`, `trust.updated`, `risk.updated`, `fault.injected`, `attack.injected`, `agent.quarantined`.

### Read API

```
GET  /api/health
GET  /api/projects                      → [{id, name, description, created_at, run_count, agent_count, last_activity_at}]
GET  /api/projects/{project_id}         → project + recent runs + agents
GET  /api/projects/{project_id}/runs    → [RunOut] (desc started_at)
GET  /api/runs/{run_id}                 → RunOut
GET  /api/runs/{run_id}/events          → [EventOut] ordered (timestamp, id), ?event_type=&agent_id=&limit=&offset=
GET  /api/runs/{run_id}/graph           → {run_id, nodes: [NodeOut], edges: [EdgeOut]}
GET  /api/runs/{run_id}/metrics         → {run_id, totals, per_agent, highlights}
GET  /api/agents/{agent_id}?project_id= → AgentOut
GET  /api/agents/{agent_id}/events      → [EventOut]
WS   /ws/projects/{project_id}          → server pushes {"type": "event", "data": EventOut}
POST /api/events                        → ingest (auth-gated when keys configured)
```

`NodeOut = {id, name, role, status, trust_score, risk_score, messages_in, messages_out, tool_calls,
errors, avg_latency_ms, tokens, cost_estimate}`
`EdgeOut = {id, source, target, message_count, avg_latency_ms, last_status, last_message_at}`
`totals = {agents, messages, tool_calls, model_calls, tokens, cost_estimate, avg_latency_ms,
p95_latency_ms, error_count, error_rate, duration_ms}`; `per_agent` rows feed charts;
`highlights = {slowest_agent, most_expensive_agent, most_active_agent, most_unreliable_agent}`.

### Status vocabularies

Run: `running | completed | failed`. Agent: `healthy | running | idle | failed | overloaded |
quarantined | unknown` (last three reserved for Phase 4 writers, renderable now).

---

## Task 1: Repo scaffold
**Files:** `.gitignore`, directory tree, this plan. Git init on `main`.
**Gate:** `git status` clean-ish tree, dirs exist. ✅ (done during planning)

## Task 2: Python SDK (`packages/sdk-python`)
**Files:** `pyproject.toml` (zero runtime deps, `[dev] pytest`), `agentlab/__init__.py`,
`_context.py` (ContextVars: run/agent/span), `_events.py` (registry + envelope builder),
`_transport.py` (Queue + daemon worker, urllib POST batches ≤50, 3 retries w/ backoff, re-buffer
on failure cap 10k, never raises into host app), `client.py` (`AgentLabClient`: `run()` ctx mgr,
`trace_agent` decorator, `trace_tool` ctx mgr, `send_message`, `log_model_call`,
`routing_decision`, `update_trust`, `flush`, `close`; `AGENTLAB_DISABLED=1` no-op), `decorators.py`
(module-level `trace_agent`/`trace_tool`/`trace_message`/`send_message` bound late to default client).
**Tests:** `tests/test_transport.py` (in-process HTTP server: batching, buffering across outage,
disabled mode), `tests/test_client.py` (decorator emits started/completed/failed, run ctx,
message/tool/model/routing envelope shapes, parent_event_id nesting).
**Gate:** `pytest packages/sdk-python -q` green.

## Task 3: API foundation (`apps/api`)
**Files:** `pyproject.toml` (fastapi, uvicorn[standard], sqlalchemy>=2, pydantic>=2,
pydantic-settings, psycopg[binary]; dev: pytest, httpx), `app/config.py` (Settings: database_url
default sqlite, api_keys, cors), `app/db.py` (engine factory, JSON/JSONB variant, session dep),
`app/models.py` (Project, Run, Agent (PK project_id+id), Event (`meta` attr → `metadata` column),
Message, ToolCall, RoutingDecision), `app/schemas.py` (Pydantic mirrors of contracts above).
**Gate:** `python -c "from app.main import create_app"` once Task 5 lands; models import clean now.

## Task 4: Collector + projections
**Files:** `app/events.py` (type registry), `app/collector.py`: `process_events(session, [EventIn])`
→ insert raw events (skip dup event_id), auto-create Project, project run/agent/message/tool/
routing/trust state transitions per type, return `(stored EventOut[], duplicates)`.
**Tests:** `tests/test_collector.py` — full demo-shaped event sequence drives: run lifecycle,
agent upserts + status transitions, message latency fill-in, tool call completion, routing row,
trust update clamps, duplicate event_id ignored, unknown type rejected.
**Gate:** `pytest apps/api -q` green.

## Task 5: REST + graph + metrics + WS
**Files:** `app/graph.py`, `app/metrics.py`, `app/ws.py` (ConnectionManager), `app/routers/{events,projects,runs,agents}.py`, `app/main.py` (`create_app()`, lifespan create_all + retry-wait for Postgres, CORS, `/api/health`).
**Tests:** `tests/test_api.py` (ingest→read endpoints, graph node/edge aggregates, metrics totals
+ p95 + highlights, auth 401 when keys configured, filters), `tests/test_ws.py` (TestClient
websocket receives broadcast on ingest).
**Gate:** `pytest apps/api -q` green.

## Task 6: Example app (`examples/basic_multi_agent`)
**Files:** `run_demo.py` (+README): Planner → (routing.decision) → Researcher (tools: web.search ×2,
model call) → Coder (model call, lint tool) → SecurityReviewer (scan tool, model call; can bounce
a fix request back to Coder) → ReportAgent. Scenarios: `success`, `retry` (tool fails then
succeeds), `failure` (security agent fails ⇒ run.failed). Flags: `--endpoint --api-key --project
--scenario --runs --fast --seed`. Simulated tokens/cost/latency; no LLM keys.
**Gate (end-to-end slice):** uvicorn (SQLite) + `python run_demo.py --runs 3` then
`curl /api/projects`, `/runs`, `/graph`, `/metrics` return populated, correctly-shaped JSON.

## Task 7: Web app foundation (`apps/web`)
**Files:** `package.json`, `vite.config.ts` (react + tailwindcss plugins; `/api` + `/ws` dev proxy
→ :8000), `tsconfig*.json`, `index.html`, `src/main.tsx`, `src/App.tsx` (routes), `src/index.css`
(Tailwind v4 + dark infra theme tokens), `src/lib/api.ts`, `src/lib/types.ts` (mirrors contracts),
`src/lib/format.ts`, `src/lib/status.ts` (color maps), `src/store/live.ts` (Zustand: WS status,
event buffers), `src/hooks/useProjectStream.ts` (reconnecting WS), shared UI primitives
`src/components/ui/` (Card, Badge, StatusDot, Stat, EmptyState, JsonView, Spinner, CopyButton).
**Gate:** `npm run build` green (tsc + vite).

## Task 8: Pages
**Files:** `src/components/layout/{Shell,Sidebar,TopBar}.tsx`; pages: `Dashboard` (fleet overview,
recent runs, empty-state with seed command), `Projects`, `ProjectDetail` (runs table + agents
grid), `RunDetail` (Task 9), `AgentDetail`, `Lab` (explicitly marked "arrives in v0.3 — pending
approval"), `Settings` (endpoint/WS status/version, read-only).
**Gate:** `npm run build` green; routes render with live API.

## Task 9: Run detail — the heart
**Files:** `src/components/topology/{TopologyView,AgentNode,MessageEdge,layout.ts}` (custom React
Flow nodes: status ring, role, trust bar, msg/err counts; edges labeled `N msgs · avg ms`,
animated while run live; deterministic layered DAG layout, no dagre dep),
`src/components/timeline/EventTimeline.tsx` (filterable by event family, click→inspect),
`src/components/inspector/{InspectorPanel,EventDetail,AgentInspector,EdgeInspector}.tsx`
(summary tab + raw JSON tab + parent/child related events via `metadata.parent_event_id`),
`src/components/metrics/{MetricCards,RunCharts}.tsx` (Recharts: latency by agent, tokens/cost by
agent, events-over-time area; highlights row), `src/pages/RunDetail.tsx` stitches: header strip,
tabs Topology/Timeline/Metrics, right inspector; WS events → append + 400 ms debounced
graph/metrics/run refetch.
**Gate:** `npm run build` green; with seeded API: nodes/edges visible, node click → inspector,
edge click → messages between pair, message click → payload + raw JSON, live run animates.

## Task 10: Live verification with browser preview
Run API (SQLite, seeded with all 3 scenarios) + `npm run dev`; use preview tooling to screenshot
Dashboard, RunDetail topology, inspector open; check console for errors.
**Gate:** Screenshots captured, zero console errors, WS shows "Live".

## Task 11: Docker + DX
**Files:** `apps/api/Dockerfile`, `apps/web/Dockerfile` (multi-stage → nginx), `apps/web/nginx.conf`
(SPA fallback + `/api` + `/ws` proxy → api:8000), `examples/basic_multi_agent/Dockerfile` (seed
image), `docker-compose.yml` (db: postgres:16-alpine + healthcheck; api; web :3000; `seed`
service under `--profile demo`), `.env.example`, `Makefile` (install/test/api/web/demo/up/seed),
`.github/workflows/ci.yml` (pytest + web build).
**Gate:** compose config validates (`docker compose config`); daemon is down on this machine so
container builds are documented-not-executed; CI file lints by inspection.

## Task 12: Documentation
**Files:** `README.md` (positioning, mermaid architecture, 3 quickstarts, SDK usage, screenshots
placeholders, roadmap), `PRODUCT_SPEC.md`, `ARCHITECTURE.md` (event flow, schema, WS protocol,
graph/metrics derivation, replay + lab design sketches for v0.2/v0.3), `ROADMAP.md` (v0.1 → v1.0),
`LICENSE` (MIT), per-package READMEs (sdk, example).
**Gate:** docs accurate against shipped code (commands copy-paste verified).

## Task 13: Final gates + handoff
Re-run: full pytest (api + sdk), `npm run build`, end-to-end seed + curl spot checks. Initial git
commit. Report Phase 1 + 2 acceptance criteria line-by-line, then **STOP and request approval**
for Phase 3 (replay), Phase 4 (lab/malicious/trust), per the product spec's explicit instruction.
