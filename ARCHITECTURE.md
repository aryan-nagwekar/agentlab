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
agent.joined · agent.suspicious         (Security Lab, v0.4)
message.flagged                         (Security Lab, v0.4)
routing.decision
trust.updated · risk.updated            (manual score overrides)
score.updated                           (formalized; v0.5 derives, never emits)
fault.injected                          (Lab Mode, v0.3)
attack.injected                         (Security Lab, v0.4)
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

## Lab mode (v0.3 — shipped)

Fault injection is *telemetry simulation through the normal pipeline*: a fault
emits a `fault.injected` event plus realistic follow-up events, so storage,
projections, WebSocket fan-out, the topology, metrics, and replay all react
without any special-casing.

**Endpoints**

```
GET  /api/lab/fault-templates      → 6 templates (label, target kind, params, emitted events)
POST /api/runs/{id}/faults         → validate + emit fault & follow-ups (auth-gated, WS broadcast)
GET  /api/runs/{id}/faults         → fault history for a run
```

**Fault → follow-up matrix** (`app/lab.py`)

| fault_type | target | follow-up events | visible effect |
| --- | --- | --- | --- |
| `kill_agent` | agent | `agent.failed` | node turns failed, error count up |
| `overload_agent` | agent | `agent.heartbeat{status: overloaded}` | node turns overloaded |
| `force_tool_failure` | agent | `tool.called` + `tool.failed` | tool failure in timeline/metrics |
| `simulate_model_timeout` | agent | `model.called` + `model.failed` | model failure, latency = timeout |
| `delay_messages` | channel | `message.sent` + delayed `message.received` | edge latency spikes; "sent" state visible mid-replay |
| `drop_messages` | channel | `message.sent` + `message.failed` | edge turns failed |

Validation: the fault type must be known, the victim (and channel source)
must be participants of the target run; injection is allowed into completed
runs (chaos-testing recorded workflows is the point — events append to the
tape). Every lab event carries `metadata.safe_simulation: true`,
`metadata.created_by: "lab"`, and follow-ups link back via
`metadata.fault_event_id`.

**The operator is not a participant.** Fault events use
`source_agent_id: "lab-controller"`, but graph/metrics/replay folds skip
lab events when collecting participants, so the controller never appears as a
workflow node. Replay marks fault indices in `markers.faults` (rose dots +
a dedicated jump button).

**Safety:** nothing in Lab Mode kills processes, drops real network traffic,
or touches secrets — a "fault" is the *telemetry* of a failure, generated
deterministically. Intercepting real agent traffic via an SDK control-plane
hook is explicitly future work.

## Security Lab — malicious-agent simulation (v0.4 — shipped)

Same pattern as fault injection: an attack emits `attack.injected` plus
mock-only follow-up events. The malicious agent is a real simulated
participant; the `lab-controller` operator is excluded from the topology.

**Endpoints**

```
GET  /api/lab/attack-templates    → 8 templates (label, severity, target kind, params, mock_payload)
POST /api/runs/{id}/attacks       → validate + emit attack & follow-ups (auth-gated, WS broadcast)
GET  /api/runs/{id}/attacks       → attack history for a run
```

**Attack → follow-up matrix** (`app/attacks.py`)

| attack_type | follow-up events | visible effect |
| --- | --- | --- |
| `malicious_agent_joined` | `agent.joined` + `risk.updated` | new suspicious node appears |
| `fake_capability_advertising` | `agent.suspicious` + `message.sent`/`flagged` + `risk.updated` | flagged edge, claimed (unverified) capabilities |
| `prompt_injection_message` | `agent.suspicious` + `message.sent`/`flagged` + `risk.updated` | flagged message with mock injection text |
| `mock_data_exfiltration_attempt` | `agent.suspicious` + `message.sent`/`flagged` + `risk.updated` + `agent.quarantined` | flagged edge to `attacker-endpoint`, then quarantine |
| `high_frequency_spam` | `agent.suspicious` + N×`message.sent` + `message.flagged` + `risk.updated` | edge message count spikes |
| `trust_poisoning` | `agent.suspicious` + `message.sent`/`flagged` + `risk.updated` | flagged fabricated-feedback message |
| `routing_manipulation` | `agent.suspicious` + `message.sent`/`flagged` + `risk.updated` (`manipulation_attempt: true`) | flagged routing-manipulation message |
| `unsafe_tool_request` | `agent.suspicious` + `tool.called` + `tool.failed` + `risk.updated` | blocked mock tool request |

**New projections.** `agent.joined` registers a node with a payload status
(`suspicious` for malicious joins); `agent.suspicious` sets status `suspicious`
(but never downgrades `quarantined`); `message.flagged` sets the message — and
therefore the topology edge — to `flagged` (rendered amber). Graph, replay
fold, and the client reducer all share these semantics (pinned by pytest +
vitest). Metrics gain `attacks`, `flagged_messages`, and `suspicious_agents`
counts. Replay marks attack indices in `markers.attacks` (fuchsia dots + an
Attack jump button).

**Safety (enforced by construction).** Builders only assemble Python dicts of
`MOCK_*` literals — they never read files/env, open sockets, or run commands.
Every payload carries `safe_simulation: true`; event metadata carries
`real_secrets_accessed: false` and `real_network_access: false`.

## Trust/risk engine (v0.5 — shipped)

`app/scoring.py` is a pure fold over a run's ordered events → per-agent
`{trust, risk, history}`. Deterministic (no LLM, no randomness), so a score is
reproducible and the score at replay cursor *k* is exactly
`score_events(events[:k+1])`.

**One rule table, five call sites.** The `EFFECTS` table (deltas + floors/
ceilings per event type) is the single source of truth used by the collector
(stored `Agent` row), `graph.py`, `replay.py`, `metrics.py`, and the dashboard
mirror `apps/web/src/lib/scoring.ts`. A change in one place is a change
everywhere; pytest (`test_scoring.py`) and vitest (`scoring.test.ts`) pin both
sides to the same 18-event-style fixtures.

| Signal | Effect |
| --- | --- |
| `agent.completed` | trust +0.05, risk −0.02 |
| `tool/model.completed`, `message.received` | trust +0.01 |
| `agent.failed` | trust −0.15, risk +0.10 |
| `tool/model.failed` | trust −0.10, risk +0.08 |
| `message.failed` | trust −0.07, risk +0.05 |
| `fault.injected` | trust −0.05, risk +0.10 (scores the **target**/victim) |
| `message.flagged` | trust −0.20, risk +0.25 |
| `attack.injected` | trust −0.25, risk +0.30 (scores the **target**/attacker) |
| `agent.suspicious` | trust ≤ 0.5, risk ≥ 0.6 (ceiling/floor) |
| `agent.quarantined` | trust ∈ [0.10, 0.20], risk ≥ 0.90 |
| `trust.updated` / `risk.updated` | manual override (set) |

**Attribution.** `attack.injected` and `fault.injected` carry
`source=lab-controller`, so they score `target_agent_id`; everything else
scores `source_agent_id`. The `lab-controller` operator never gets a score.

**Why no `score.updated` events.** v0.5 derives score changes on read and
returns them as `ScoreChange` history records. Nothing is written back into the
event log, so a score change can never trigger another — the
"no infinite score events" requirement holds by construction. `score.updated`
is formalized in the registry but reserved.

**Explainability.** Every change records `caused_by_event_id` +
`caused_by_event_type`, previous/new trust+risk, the deltas, and a human
reason. `factors()` aggregates a history into the biggest trust/risk movers.
`tier()` bands a score into `trusted | caution | suspicious | high-risk` for
node colouring.

**Endpoints:** `GET /runs/{id}/scores`, `/runs/{id}/score-history`,
`/runs/{id}/risk-summary`, `/agents/{id}/scores`. The dashboard shows a score
panel (reason + factors + history) in the inspector and on the agent page, a
run risk summary on the Metrics tab, tier badges on every node, and — because
the reducer folds with the same rules — trust/risk that visibly evolve as the
replay cursor advances.

This fixed the v0.4 inconsistency where a quarantined malicious agent could
read trust 1.0 / risk 0.95: it now reads ~0.10 / 1.0, derived from its own
attack/quarantine events. The engine **scores and explains; it does not
enforce** — no routing impact, no decay, quarantine stays a marker (future work).

## Cost/token engine (v0.6 — shipped)

`app/costing.py` folds a run's `model.*` events into per-agent, per-model, and
run cost/token aggregates; `app/pricing.py` is a static USD-per-1M-token table
for mock providers only. Cost is **always recomputed from tokens via the
pricing table** (never trusted from the payload), making it the single source
of truth shared by the cost endpoints, `metrics.py`, `graph.py`, the run
finalizer, and the dashboard mirror `apps/web/src/lib/costing.ts`.

- **Normalization** reads tokens leniently: new `input_tokens`/`output_tokens`/
  `model_name`/`provider`, or legacy `prompt_tokens`/`completion_tokens`/
  `model`. Missing fields → 0. Unknown model → cost `null`,
  `pricing_status: "unknown"` (an explicit payload cost is honoured as
  `"provided"`). A `model.failed` still costs its consumed input tokens.
- **Per-agent:** in/out/total tokens, cost, avg + p95 latency, model-call
  count, failed calls, retries (`model.called` minus finished), most-used model.
- **Per-run highlights:** most-expensive / most-token-heavy / slowest /
  highest-failure agent + model breakdown.
- **Replay:** `aggregateCost(events[:cursor])` gives the cost at any cursor, so
  the "Cost so far" strip and node token counts grow as replay advances.

**Endpoints:** `/runs/{id}/costs`, `/runs/{id}/token-summary`,
`/agents/{id}/costs`, `/projects/{id}/cost-summary`.

**Scope:** v0.6 pricing covers the mock models; real models priced via the
gateway (v0.7) show `pricing_status: "unknown"` unless the provider returns a
cost.

## Model gateway / BYOK (v0.7 — shipped)

`app/model_gateway/` is a provider abstraction: a `ModelProvider` exposes
`async complete(ModelRequest) -> ModelResponse` and `async health_check()`. A
`ProviderRegistry` is built once from `Settings` and lives on `app.state`.

**Providers.** `mock` (keyless default — deterministic output + token usage,
configurable latency/failure, never networks), `openai` (OpenAI-compatible
chat completions, reused for OpenRouter), `anthropic` (messages API), `gemini`
(generateContent API, added in v0.7.1 — `GEMINI_API_KEY`/`GOOGLE_API_KEY`,
GEMINI preferred; key stays server-side and is redacted like every other
provider), `ollama` (local `/api/generate`). Real providers call out with
stdlib `urllib` on a worker thread (`asyncio.to_thread`) — no new dependency,
event loop never blocked.

**Troubleshooting hints (v0.7.1).** Each entry in the provider list carries a
`message` (the health detail): an unconfigured provider says which env var to
set, and an unreachable Ollama explains the configured `OLLAMA_BASE_URL`,
`ollama serve`, and the Docker `host.docker.internal:11434` workaround. The
dashboard renders the hint amber on unavailable/not-configured cards.

**Telemetry bridge.** `telemetry.build_model_events` turns a gateway call into
`model.called` + `model.completed`/`model.failed` `EventIn`s, run through the
normal `process_events` pipeline. So gateway calls land in storage, the WS
stream, graph, replay, inspector, metrics, and Cost & Tokens with zero
special-casing. Payloads carry a short prompt/output preview, never the key.

**Endpoints.** `GET /model-gateway/providers`, `/providers/{p}/health`,
`POST /model-gateway/test-call`, `POST /runs/{id}/model-call`. The SDK's
`client.model_call(...)` posts to the last one and returns the response,
capturing a clean `model.failed` if the gateway is unreachable.

**Key safety (enforced by construction):**

- Keys are read from the environment via `Settings` (validation aliases map the
  conventional `OPENAI_API_KEY` etc. names) and kept only in provider instances.
- They are never persisted, never serialized into any response schema
  (`ProviderOut`/health expose only `key_redacted`), and never logged — the HTTP
  helper deliberately omits headers from exceptions.
- `redact_key` emits at most a 3-char prefix + 4-char suffix; short keys become
  `***`; no key means "not configured".

A backend test greps every gateway response for a planted secret to prove it
never leaks.

## Agent Builder Studio (v0.8 — shipped)

`app/studio/` lets users author and run multi-agent workflows in-app. The
design principle: **definitions and telemetry stay separate**. Studio tables
(`studio_workflows`, `studio_agents`, `studio_edges`, `studio_workflow_runs`)
describe what was authored; the append-only `events` table remains the only
record of what happened when a workflow ran.

**Model.** A workflow is a DAG of agent definitions (name, role, system
prompt, provider, model, temperature, max tokens, canvas position) connected
by labeled edges. `validation.py` rejects cycles ("Cycles are not supported in
v0.8."), dangling edges, duplicate ids, and unknown providers/mock models
(checked against the gateway registry); an unconfigured real provider is a
*warning* — the run is allowed and fails cleanly.

**Executor** (`executor.py`). Topological sort (Kahn, stable), then per agent:
hand upstream outputs over as `message.sent`/`message.received`, emit
`agent.started`, build a plain-text prompt (role + system prompt + workflow
input + upstream outputs), call the provider through the **Model Gateway**,
reuse `telemetry.build_model_events` for `model.called` +
`model.completed`/`model.failed`, then `agent.completed`/`agent.failed`. A
failed agent skips its downstream subtree; the run ends `run.completed` or
`run.failed` with failed/skipped agent lists. Timestamps advance on a
simulated clock by each call's reported latency, so the replay timeline reads
realistically. No user code, shell, tools, loops, or recursion — model calls
are the only side effect.

**Integration for free.** The executor returns plain `EventIn`s persisted
through `collector.process_events` and broadcast per-project over WS — so a
Studio run is indistinguishable from an SDK run to the graph, replay,
inspector, metrics, trust/risk, costing, and even the fault/attack labs. Every
event carries `metadata.source: "studio"` plus workflow id/name, agent
definition id, role, provider/model, and upstream/downstream agents for the
inspector.

**Seed.** At startup, if no workflows exist, the "Code Review Agent Team"
(Planner → Coder → Security Reviewer → Report, all on keyless mock models) is
created so Studio demos with zero configuration.

Deferred: loops, tools, hosted collaboration, cloud secrets.

## Project templates (v0.9 — shipped)

`app/studio/templates.py` is a static registry of six agent-team blueprints
(Code Review, Research, Resume Tailoring, SOC Investigation, Customer
Support, Data Analysis — five agents each, linear DAGs with labeled hops).
A template carries category/tags/difficulty/use case, per-agent role +
system prompt + mock-model defaults, a default input, expected outputs, and
demo notes.

**Templates are data, not a new run format.** `POST
/studio/templates/{id}/create-workflow` materializes the template into a
plain `WorkflowIn` and hands it to the same `service.create_workflow` used by
the editor — the result is an ordinary v0.8 workflow (editable, validatable,
runnable through the gateway; agents carry `template_id` in their metadata
for provenance). `GET /studio/templates[/{id}]` feeds the gallery and the
preview page, which reuses the Studio canvas read-only. Workflows created
from a template open in the editor with the template's default input
pre-filled in the run panel (via the `?template=` query param).

Deferred to Runtime v1 (not started): workspaces, sandboxed file runtime,
command execution, enforcement gateway, human approvals, deterministic
validators, real quarantine enforcement.

## Chat Mode / Agent Mode + secure provider setup (v0.9.1 — shipped)

**Modes.** A global Studio mode (zustand, default Agent) splits interaction:
Chat Mode is conversational and read-only — Studio action buttons disable and
the assistant refuses actions with "Switch to Agent Mode to perform this
action."; Agent Mode performs project actions (run, edit, `/connect`,
`/run`). The assistant is deliberately **deterministic and local**: rule-based
answers built from existing read APIs (workflow structure, latest run,
`run.failed` payloads, costs, risk summary) — there is no LLM behind the chat.

## Runtime Workspaces (v1.0 — shipped, metadata only)

`app/runtime/` is the foundation of the Runtime phase (master plan:
`docs/AGENTLAB_RUNTIME_V1_PLAN.md`). A **workspace** is the future home of an
AI-built project: id, name, goal, status (draft → active → paused/completed/
failed; archived), linked AgentLab project, free-form metadata for later
Runtime versions. **Artifacts** are registry entries (name/type/logical
path/metadata) for future project outputs — v1.0 never reads or writes real
files.

**Events, not a parallel history.** Each workspace owns an *activity run*
(`{workspace_id}-activity`) in its project. Every lifecycle action emits a
`workspace.*` event (`created`/`updated`/`status_changed`/`archived`/
`artifact_registered` — added to the shared event registry in both the API
and the SDK) through `collector.process_events`, so the workspace's history
is ordinary telemetry: the `/activity` endpoint is an event query, and the
run timeline + replay reconstruct workspace history unchanged. Terminal
workspace statuses map onto the activity-run projection
(completed/failed/archived); otherwise the stream stays "running".
DELETE archives rather than destroys — append-only history discipline.

**Explicit non-goals for v1.0** (later Runtime versions): command execution,
shell, file writes/edits, sandboxing, orchestration, enforcement gateway,
policy blocking, human approvals, validators, real quarantine.

## Workspace Agent Definitions + Permissions (v1.1 — shipped, metadata only)

A **WorkspaceAgent** (`runtime_workspace_agents`, composite PK
`(workspace_id, id)`, CASCADE) is an agent *definition* inside a workspace:
role, description, system prompt, Model Gateway `model_provider`/`model_name`
(keyless mock defaults — the v0.7 gateway vocabulary is reused, not forked),
`allowed_tools`/`denied_tools`, a **permission profile**, budget ceilings
(`max_tokens_per_call`/`max_calls_per_run`/`max_tool_calls_per_run`),
`requires_verification`, `trust_score`/`risk_score`, and a `status`
(`ready / running / caution / suspicious / quarantined / disabled`). The row
is metadata: nothing executes, writes files, calls tools, meters budgets, or
enforces a permission. `quarantined`/`disabled` gate *assignment* in the UI
only — there is no real runtime quarantine.

**Permission profile.** Thirteen canonical boolean flags
(`AGENT_PERMISSION_KEYS`) stored as one JSON dict; a partial update is overlaid
onto the conservative default (read + agent/user messaging) so every stored
profile carries the full key set. `RISKY_PERMISSION_KEYS` (write/delete files,
run commands, database, auth, payment, deployment) drives the ⚠ warning badges
and "a future enforcement gateway will gate these" copy — these are
future-enforcement inputs, not live gates.

**Templates are data.** `app/runtime/agent_templates.py` holds seven
blueprints (Planner, UI, Backend Coder, Researcher, Marketing, Verifier,
Safety Reviewer). Instantiating one materializes a normal WorkspaceAgent (no
special run format); per-role `risk_notes` and `future_approval_required`
ride along as agent metadata.

**Events, same pipeline.** Create / update / permission_changed /
status_changed / deleted / template_instantiated each emit a
`workspace_agent.*` event (added to the shared registry in API **and** SDK)
through `collector.process_events` into the workspace's activity run — so the
activity feed, timeline, and Replay reconstruct the agent lifecycle with zero
special-casing. A field-only edit rolls up to `workspace_agent.updated`;
permission and status changes get their own event types. Deleting an agent
removes the definition row but the event log keeps the history.

**Explicit non-goals for v1.1** (later Runtime versions): agent execution,
command runner, shell, real file writes, orchestration, enforcement gateway,
approvals, validators, real runtime quarantine, the bottle-selling demo.

**Key hygiene.** Raw API keys must never enter the chat/event/replay stream.
The composer blocks key-like strings (`sk-…`, `AIza…`) in both modes with a
warning and refuses to send them. `/connect <provider>` (Agent Mode) opens a
secure modal — password-style input, optional base URL — which POSTs to
`/model-gateway/providers/{p}/configure`. Secrets land in a local gitignored
`.agentlab-secrets.json` (chmod 0600) that overlays the environment when the
provider registry is rebuilt (most recent explicit user action wins;
`/clear` falls back to the env). The key never touches the database, logs,
events, or any response — only `redact_key`'s hint comes back.

## Testing

- **SDK (22 tests):** transport against a real in-process HTTP server —
  batching, ordering, API-key header, 5xx retry, collector outage + recovery,
  4xx drop, buffer cap; client envelope/context/nesting/disabled-mode.
- **API (22 tests):** ingest contract (validation, idempotency, auth),
  projection state machine via a realistic seeded run, graph aggregates,
  metrics totals/p95/highlights, WS broadcast + project scoping.
- CI (GitHub Actions): backend tests + dashboard typecheck/build.
