# AgentLab — Architecture

## System overview

```mermaid
flowchart TB
    subgraph host["Host agent application"]
        code[Agent code] --> sdk["agentlab SDK\ncontextvars: run → agent → span"]
        sdk --> q[in-memory queue]
        q --> worker["transport worker thread\nbatch ≤50 · retry+backoff · bounded buffer"]
    end
    worker -->|"POST /api/events\n(single or {events:[…]})"| ingest

    subgraph api["apps/api (FastAPI)"]
        ingest[/"events router\n(validate · auth)"/] --> collector["collector.process_events\nidempotent · projections"]
        collector --> events[("events\n(append-only)")]
        collector --> proj[("runs · agents · messages\ntool_calls · routing_decisions")]
        ingest --> ws["ConnectionManager\nper-project channels"]
        read[/"read routers"/] --> graph["graph.py\nrun topology"]
        read --> metrics["metrics.py\ntotals · p95 · highlights"]
        graph & metrics --> events & proj
    end

    ws -->|"{type:'event', data}"| web
    subgraph web["apps/web (React SPA)"]
        store["zustand + hooks"] --> topo["TopologyView\n(React Flow)"]
        store --> tl["EventTimeline"]
        store --> insp["InspectorPanel\nagent · channel · event"]
        store --> mx["RunMetricsView"]
    end
    read --> store
```

**One principle drives the design:** the append-only `events` table is the
source of truth; everything else (run status, agent state, message latencies,
graphs, metrics) is *derived*. This is what makes replay (v0.2) a pure
frontend/read-path feature — the data is already event-sourced.

## Event schema (wire contract)

Every event, SDK → collector:

```json
{
  "event_id": "uuid4 — idempotency key, retries are safe",
  "event_type": "message.sent",
  "timestamp": "2026-06-09T12:00:00.123Z",
  "project_id": "demo-project",
  "run_id": "run-…",
  "source_agent_id": "planner",
  "target_agent_id": "researcher",
  "payload": { "content": { "task": "research X" } },
  "metadata": {
    "message_id": "msg-…",
    "parent_event_id": "uuid of the enclosing agent.started span",
    "_seq": 17,
    "sdk": "agentlab-python/0.1.0"
  }
}
```

22 validated types across 8 families:

```
run.{started,completed,failed}
agent.{started,completed,failed,heartbeat,quarantined}
message.{sent,received,failed}
tool.{called,completed,failed}
model.{called,completed,failed}
routing.decision
trust.updated · risk.updated
fault.injected · attack.injected        (accepted now, emitted by Lab Mode in v0.3)
```

Unknown types are rejected (422). The registry lives in
`packages/sdk-python/agentlab/_events.py` and `apps/api/app/events.py` (kept in sync).

## SDK design (`packages/sdk-python`)

- **Context propagation.** Three `ContextVar`s — `current_run_id`,
  `current_agent_id`, `current_span_id`. `@trace_agent` sets agent+span; any
  nested `trace_tool` / `send_message` / `log_model_call` attributes itself
  automatically and stamps `metadata.parent_event_id`, which powers the
  inspector's parent/child navigation.
- **Transport.** `enqueue()` is non-blocking; a daemon thread drains the queue,
  posts batches (≤50) with `urllib`, retries transient failures
  (408/429/5xx/connection) with exponential backoff, re-buffers on outage
  (bounded at 10k, oldest dropped with a warning), and **drops** batches the
  collector rejects as invalid (4xx) so one bad event can't wedge the pipeline.
  Failure modes cost telemetry, never exceptions in the host app.
- **Lifecycle.** `client.run()` is a context manager emitting
  `run.started/completed/failed` (+ flush on exit). Events emitted with no
  active run lazily open a shared implicit "ad-hoc" run, closed on
  `client.close()` (registered via `atexit`).
- **Module-level API.** Constructing `AgentLabClient` registers it as the
  process default; `from agentlab import trace_agent` resolves the default
  *at call time*, so decoration order doesn't matter.
- **Kill switch.** `AGENTLAB_DISABLED=1` or `disabled=True` → no transport,
  no-ops, traced functions still run.

## Backend (`apps/api`)

### Ingest path

`POST /api/events` (auth-gated when `AGENTLAB_API_KEYS` is set) → Pydantic
validation → `collector.process_events` in a threadpool:

1. Skip events whose `event_id` already exists (idempotent).
2. Auto-create the `Project`; auto-create shell rows for any referenced `Run`
   or `Agent` — events may legally arrive before/without announcements.
3. Insert the raw `Event` row (arrival order preserved by autoincrement id).
4. Apply the per-type projection (table below).
5. Commit, then broadcast each stored event on the project's WS channel.

| Event type | Projection effect |
| --- | --- |
| `run.started` | Run → running, name, started_at |
| `run.completed/failed` | status, completed_at, finalize: recount errors, sum tokens/cost from `model.completed` payloads |
| `agent.started` | Agent → running; name/role upsert |
| `agent.completed` / `failed` / `quarantined` | Agent status idle / failed / quarantined |
| `agent.heartbeat` | last_seen_at, optional status |
| `message.sent/received/failed` | Message row keyed by `metadata.message_id`: sent → delivered(+latency) / failed |
| `tool.called/completed/failed` | ToolCall row keyed by `metadata.tool_call_id`: running → completed(+output,latency) / failed |
| `routing.decision` | RoutingDecision row (candidates, reason, confidence) |
| `trust.updated` / `risk.updated` | Agent.trust_score / risk_score (clamped 0–1) |
| `model.*`, `fault.*`, `attack.*` | raw event only (metrics aggregate model payloads; lab consumes fault events in v0.3) |

### Database

`events` (append-only, indexed on run/project/type/timestamp/agents) plus
projections: `projects`, `runs`, `agents` (PK = project_id+id; agent ids are
human-readable slugs), `messages`, `tool_calls`, `routing_decisions`. JSON
columns use JSONB on PostgreSQL, JSON on SQLite (`with_variant`). Timestamps
are stored as naive UTC and serialized with a `Z` suffix.

**Deliberate v0.1 tradeoffs:** schema is created with `create_all` on startup
(Alembic lands with the first post-v0.1 schema change); agent ids are stored
as plain strings on events (no FK) so out-of-order arrival never fails.

### Read path

```
GET /api/projects · /api/projects/{id} · /api/projects/{id}/runs
GET /api/runs/{id} · /events?event_type=&agent_id=&limit=&offset= · /graph · /metrics
GET /api/agents/{id}?project_id= · /api/agents/{id}/events
GET /api/health
```

- **Graph** (`graph.py`): nodes = every agent referenced by the run's events,
  with **run-scoped** status/trust/risk (last lifecycle/trust event *within
  the run* wins, falling back to current project state) — so a past success
  run isn't repainted by a later failure. Edges aggregate the `messages`
  projection per (source, target): count, avg latency, last status.
- **Metrics** (`metrics.py`): latency aggregates are computed over *operation*
  latencies (agent task spans, tool calls, model calls); run wall-clock is
  reported separately. Highlights pick slowest / most expensive / most active
  / most unreliable agents.
- **Ordering contract:** `/events` returns `(timestamp, id)` ascending — the
  exact order replay will consume.

### WebSocket

`WS /ws/projects/{project_id}` — server-push only. Frame:
`{"type": "event", "data": <EventOut>}`. The manager holds a set of sockets
per project; dead sockets are evicted on send failure and can never break
ingest.

## Frontend (`apps/web`)

Vite + React 18 + TypeScript (strict) + Tailwind v4. No SSR — the dashboard
is same-origin behind the vite proxy (dev) or nginx (Docker), so `/api` and
`/ws` need no CORS in either mode.

- `lib/types.ts` mirrors the API schemas; `lib/api.ts` is a thin fetch client.
- `hooks/useProjectStream` — reconnecting WS subscription (exponential
  backoff), connection state in a zustand store (sidebar "Live stream" pill).
- **Live strategy:** stream events append instantly to the timeline; a 450 ms
  debounce then silently refetches run/graph/metrics/events to reconcile —
  instant feel, server-authoritative numbers.
- **Topology** — React Flow v12 custom nodes/edges. Layout is a deterministic
  BFS layered DAG (`topology/layout.ts`): first-visit depth ignores back-edges
  (a security reviewer bouncing work back to a coder still renders as a
  pipeline), isolated nodes get a trailing column. No layout library needed.
- **Inspector** — one panel, three lenses: agent (trust/risk meters, stats,
  recent activity), channel (messages between a pair), event (summary + raw
  JSON + parent/child links via `metadata.parent_event_id`).
- Pages: Dashboard, Projects, Project detail, Run detail
  (topology/timeline/metrics tabs + inspector), Agent detail, Lab (v0.3
  preview), Settings.

## Replay system (v0.2 — shipped)

Replay is a pure read-path feature on top of the event-sourced model.

**Endpoints**

```
GET /api/runs/{id}/replay                 → the tape: ordered events + markers + meta
GET /api/runs/{id}/replay/graph?index=k   → server-side topology at cursor k (clamped)
```

`markers` are tape indices for jump navigation: `errors` (every `*.failed`,
including `run.failed`), `tool_calls` (`tool.called`), `routing`
(`routing.decision`), and `messages` (`message.sent`).

**Two folds, one semantics.** `app/replay.py::fold_events` (server) and
`apps/web/src/components/replay/replayReducer.ts::foldReplayGraph` (client)
implement identical event-fold semantics; the backend suite pins them with an
18-event reference tape and the vitest suite pins the mirror. Replay state is
event-derived only — no projection-table fallback — so the result is the world
*as of that cursor*: an agent referenced before its `agent.started` renders as
`unknown`, trust starts at 1.0 until a `trust.updated` lands, and a message
shows `sent` until its `message.received` is applied.

**The hot path is client-side.** The dashboard folds `events[0..cursor]` in a
`useMemo` per cursor move — scrubbing never hits the network. The server-side
reconstruction endpoint exists for tests, scripts, and non-JS clients. Folding
is from-scratch per move (fine into the low thousands of events); snapshot
memoization is the planned upgrade for very large tapes.

**Transport UX.** Play/pause (space), step (arrow keys), scrub with
marker-dotted slider, 0.5–8× speed. Pacing uses real inter-event gaps divided
by speed, clamped to 80–1200 ms per step so both `--fast`-seeded and slow live
runs stay watchable. Jump buttons move the cursor to the next marker. The
inspector **follows the playhead** (shows the event at the cursor) until the
user pins a node/edge/event; a "follow playhead" affordance returns to
tracking. The topology component is reused unchanged — nodes appear and change
state as the cursor advances, and the timeline shows exactly the applied
prefix of the tape.

## Lab mode (v0.3 design sketch)

- API gains `POST /api/lab/faults` which *emits events* (`fault.injected`,
  `agent.quarantined`, `trust.updated`) into a run rather than mutating state
  directly — the same pipeline renders them.
- Faults against the demo workflow run in-process (the seeder polls a control
  endpoint); real instrumented apps opt in via an SDK hook.
- Malicious-agent scenarios are pre-scripted event sequences over mock data —
  no real attacks, no real secrets (see Safety in [PRODUCT_SPEC.md](PRODUCT_SPEC.md)).

## Testing

- **SDK (22 tests):** transport against a real in-process HTTP server —
  batching, ordering, API-key header, 5xx retry, collector outage + recovery,
  4xx drop, buffer cap; client envelope/context/nesting/disabled-mode.
- **API (22 tests):** ingest contract (validation, idempotency, auth),
  projection state machine via a realistic seeded run, graph aggregates,
  metrics totals/p95/highlights, WS broadcast + project scoping.
- CI (GitHub Actions): backend tests + dashboard typecheck/build.
