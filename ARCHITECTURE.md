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
(a blank agent defaults to the keyless `mock` provider; the v0.7 gateway
vocabulary is reused, not forked — and as of v3.2.1 the **templates** default to
local `ollama`/`qwen2.5-coder` so a template agent can do a real governed build),
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

## Sandboxed File Runtime (v1.2 — shipped, file operations only)

`app/runtime/sandbox.py` is the first real runtime layer, deliberately
narrow: create/read/update/list/delete files **inside
`{workspaces_root}/{workspace_id}` only** (Settings.workspaces_root, default
`.agentlab-workspaces/`, gitignored). No shell, no subprocess, no command
runner, no build/test execution, no dev server.

**Path safety is deterministic and runs before any disk access.**
`resolve_path` rejects, in order: empty paths (where a target is required),
null bytes, absolute paths (POSIX, Windows-drive, and `~` spellings), any
`..` segment, and any segment whose *name* matches the secret list (`.env`,
`.env.*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `.agentlab-secrets.json`,
`.netrc`, …). The surviving candidate is then `resolve()`d — which follows
symlinks — and rejected unless it is still relative to the resolved sandbox
root: that single check is also the symlink-escape guard. A rejected
operation raises `SandboxBlocked` **after** emitting a `sandbox.file.blocked`
audit event (operation, attempted logical path truncated to 200 chars,
human reason, matched rule). The router commits that event even though the
request fails — the rejection is part of workspace history — and returns a
clear `400 blocked (<rule>)` error. Tests prove blocked writes leave the
disk byte-for-byte untouched.

**Boundaries on success paths too.** Reads are UTF-8 only and capped at
256 KB; writes are capped at 1 MB by the schema; deletes accept files and
*empty* directories only. The only path representation that ever leaves the
server is the logical workspace-relative path (`_logical`); host filesystem
paths and file content never appear in events, error messages, or logs.
Event payloads carry logical path, byte size, and a sha256 prefix.

**Events, same pipeline.** Mutations emit `sandbox.initialized` /
`sandbox.file.created` / `sandbox.file.updated` / `sandbox.file.deleted` /
`sandbox.directory.created`, and content reads emit `sandbox.file.read`
(an access-audit signal), all through `collector.process_events` into the
workspace's activity run — so the activity feed, timeline, and Replay
reconstruct file history with zero special-casing. Pure queries (status,
list, tree) emit nothing, keeping the activity run signal-dense. The shared
event registry is extended in both the API and the SDK.

**Explicit non-goals for v1.2** (later Runtime versions): command execution,
shell, subprocess, build/test runners, dev servers, orchestration,
model-driven file writing, enforcement gateway, approvals, validators, real
quarantine, the bottle-selling demo.

## Safe Command Runner (v1.3 — shipped, allowlisted commands only)

`app/runtime/commands.py` adds narrow command execution to the sandbox — a
local safety layer for sandbox commands, deliberately **not** the Milestone-5
enforcement gateway (no policy engine, no approvals, no reroute/quarantine
decisions).

**Structured requests, never shell.** A request is `command` + `args` +
`timeout_seconds` + optional `working_subdir`. There is no shell string
anywhere: evaluation scans raw tokens, and execution is
`subprocess.run([resolved_executable, *args], shell=False)`. Shell
metacharacters (`;&|<>$`, backticks, newlines) are rejected in any token —
not because they would expand (they can't without a shell) but so a request
can never even encode chaining or redirection.

**Allowlist-first, block-by-default.** `evaluate()` rejects, in order:
metacharacters/null bytes → program paths (`/bin/ls`, `./x`) → named
dangerous programs (rm/mv/sudo/ssh/curl/nc/bash/perl/pip/yarn/git/docker/
kubectl/psql/env/… — an explicit `dangerous_command` rule for a clearer
audit trail) → unknown programs (anything not allowlisted) → per-command
argument validators. The validators are strict shapes: `pwd` takes nothing;
`ls` takes safe flags plus at most one path that must pass the v1.2
`check_path` (the pure resolver extracted in this version — `resolve_path`
now wraps it and keeps emitting `sandbox.file.blocked` for file APIs, while
the command runner converts the same `PathViolation` into
`sandbox.command.blocked`); `cat` takes exactly one checked path (secret
names included); interpreters accept `--version` only, with `-c`/`-e`
inline code explicitly rejected; `npm test`/`npm run build` additionally
require a real `package.json`, `python -m pytest` requires pytest config or
`tests/`; `npm install`-family subcommands map to a dedicated
`package_install` rule. If uncertain, block.

**Contained execution.** cwd is the path-checked sandbox directory; the
environment is rebuilt from scratch (PATH/HOME/LANG/NO_COLOR/CI only) so
host env vars — and any secrets in them — never reach the child; timeouts
are clamped to 1–120 s and produce `sandbox.command.timed_out`;
stdout/stderr are decoded with `errors="replace"`, secret-pattern redacted
(`sk-…`, `AIza…`, `ghp_…`, `AKIA…`, `xox…`), and capped (10 KB in the API
response, 2 KB summaries in events with an `output_truncated` flag). The
command display string and proposed argv are redacted too — a secret pasted
*as an argument* is scrubbed the same as one printed to stdout. Only logical
workspace paths appear anywhere.

**Events, same pipeline.** Every run emits `sandbox.command.proposed`, then
either `blocked` (committed even though the request fails — the rejection is
workspace history) or `allowed → started → completed/failed/timed_out`, all
through `collector.process_events` into the workspace activity run. The
history endpoint is an event query (`event_type LIKE 'sandbox.command.%'`);
timeline and Replay reconstruct every decision with zero special-casing.

**Explicit non-goals for v1.3** (later Runtime versions): interactive
shells, persistent sessions, long-running processes/process manager, dev
servers, file watchers, package installation, orchestration, the policy
engine/enforcement gateway, approvals, validators, real quarantine, the
bottle-selling demo.

## Orchestration Engine (v1.4 — shipped, status metadata only)

`app/runtime/orchestration.py` turns a workspace goal into a workflow →
plan → tasks pipeline whose every transition is an event. The hard v1.4
boundary: **orchestration is bookkeeping**. No model calls, no file writes,
no command execution, no tool calls stand behind any transition — a
dedicated test proves a full plan→start→complete cycle emits only
`runtime.workflow.*`/`runtime.task.*` events and never creates a sandbox
directory. The Files (v1.2) and Commands (v1.3) panels stay strictly
user-triggered; the orchestrator has no code path into them.

**Deterministic planner.** `PLAN_STEPS` is a fixed five-step pipeline
(plan → research → backend → UI → verify) with per-step role keywords,
risk levels, expected artifacts, and validation/approval flags that are
recorded on tasks but deliberately inert (inputs for the future
enforcement/approval versions). No model calls — plans are reproducible in
tests with zero keys. The DAG is acyclic by construction and dependencies
are not user-editable, so cycle detection is deferred until they are.

**Assignment rules (v1.1 statuses enforced).** For each step, candidates
are workspace agents whose role/name contains a step keyword, excluding
`disabled`/`quarantined` outright; among candidates the orchestrator
prefers `ready > running > caution > suspicious`, then creation order. A
step with no candidate becomes a `blocked` task with a `blocked_reason`
and a `runtime.task.assignment_failed` event. `PATCH` reassignment rejects
unassignable agents (409), revives blocked tasks to `pending`, and emits
`runtime.task.rerouted` when the task already had an agent.

**Lifecycle.** Workflow: planned → running (start requires a plan) with
pause/resume/cancel; `_advance` is the scheduler tick — it starts every
assigned pending task whose dependencies are all completed, then settles
the workflow: all-completed → `completed`; stuck with a failed task →
`failed`; stuck otherwise (unassigned/blocked tasks in the way) →
`blocked` (recoverable: reroute + resume). Task results are bounded text
(4 KB stored, 300-char event summary) recorded manually; recording
completes the task and re-runs the tick. `waiting_for_validation` /
`waiting_for_approval` statuses exist in the model but are unreachable —
reserved for the versions that own them.

**Explicit non-goals for v1.4** (later Runtime versions): enforcement
gateway, policy engine, approvals, validators, real quarantine, autonomous
or model-driven file/command execution, browser automation/web research,
dev servers, package installation, cost-budget enforcement, the
bottle-selling demo.

## Action Enforcement Gateway (v1.5 — shipped, decisions before execution)

`app/runtime/enforcement.py` is the control point the master plan's
Milestone 5 describes: **propose → evaluate → decide → (only then) execute**.
An `ActionProposal` row captures who/what/target (stored redacted and
bounded); a deterministic, priority-ordered registry of 22 `PolicyRule`s
evaluates it (first match decides, *every* match is recorded); an
`ActionDecision` row captures the verdict, matched rules, human-readable
reason, redacted evidence, and the actor's trust/risk snapshot. Each step
emits events — `action.proposed`, `policy.rule.matched` (per match),
`policy.evaluated`, then the decision event — so replay reconstructs not
just what agents did but what AgentLab allowed, blocked, or flagged.

**Evaluation semantics.** Rules are pure functions over an `ActionContext`
computed once per evaluation (actor agent row, task flags, path-safety
verdict via the v1.2 `check_path`, command-safety verdict via the v1.3
`evaluate`). Secrets are checked against the **raw** input while only the
redacted form persists. Nine decision values map onto five outcomes:
executable (`allow`, `allow_readonly`, `allow_sandbox_only`) versus halted
(`block`, `require_human_approval`, `reroute_to_verifier`,
`retry_with_constraints`, `downgrade_permissions`, `quarantine_agent`).
Halted means halted: the integrated surfaces never run the underlying
operation, and the generic proposal API never executes anything at all.
Unknown action types — and any action no rule matched — are blocked by
default.

**Integration without weakening.** File write/delete/mkdir, command run,
workflow start, and task-result recording route through
`guarded_execute`: enforcement decides, `action.started` marks execution,
the *existing* v1.2/v1.3 service runs (its own safety re-checks intact as
defense in depth), and `action.completed` closes the arc. When enforcement
refuses something the legacy layers would also have refused, it emits the
matching `sandbox.file.blocked` / `sandbox.command.proposed+blocked`
events too, so the v1.2/v1.3 audit streams remain complete and the HTTP
contract (`400 blocked (<rule>): …`) is unchanged; approval-required
refusals use `403 approval required (<rule>): …` instead. Manual user
task-result recording stays allowed (a human is the approver-of-record for
their own click); the same action proposed by an *agent* actor on a
flagged task resolves to approval-required/reroute — recorded, not
executed.

**Explicit non-goals for v1.5** (later Runtime versions): the approval
inbox and approve/deny/resume flow (v1.6 — `approval_required` proposals
just wait), validator execution/evidence (v1.8), real quarantine lifecycle
(v1.7 — `quarantine_agent` is a recorded decision), autonomous agent
execution, browser automation, deployment, package installation,
cost-budget enforcement beyond rule placeholders, the bottle-selling demo.

## Human Approval System (v1.6 — shipped, resolves enforcement halts)

`app/runtime/approvals.py` is Milestone 7: it turns the gateway's
`require_human_approval` verdict into a resolvable inbox item without
adding any autonomy. When `evaluate_action` returns that decision,
`ensure_approval` creates a pending `ApprovalRequest` (deduplicated per
unresolved action by action-type + target) and the proposal's metadata and
the 403 detail both carry the new approval ID. The request stores a
plain-English summary, a technical summary, the matched rules, a risk level
and recommended decision derived from the deciding rule, and — crucially —
the **exact stored execution payload** under `metadata.execution` (file
content, command argv, …). That payload is set only by the integrated
surfaces via `guarded_execute(approval_payload=…)`; it is never settable or
editable through the approval API and never appears in any event.

**Resolution semantics** (`approvals.resolve`): `approve`/`approve_once`
replay the stored action through the *existing* safe executors —
`sandbox.write_file/delete_path/make_dir` or `commands.run_command` — so
the v1.2 path checks and v1.3 command safety **re-run**; a command that no
longer passes is refused (`execution_failed`) even though a human approved
it. `deny` marks the proposal blocked and never executes. `approve_readonly`
executes only a genuinely read-only path (`file.read`) or records a
`skipped` execution with an explanation. `reroute` and `quarantine` set the
request status and emit `approval.override_used` + the specific
`approval.reroute_requested` / `approval.quarantine_requested` events;
quarantine additionally emits `enforcement.quarantine_triggered` — but the
agent definition is **not** modified, because real runtime quarantine is
v1.7. Each resolution emits `approval.approved/denied/cancelled`, the
`action.started/completed/failed` execution bracket where it resumes, and an
`approval.execution_resumed/failed/skipped` outcome event, so replay
reconstructs the entire request → decision → resume arc.

**Integration:** file write/delete/mkdir and command run already flow
through `guarded_execute`, so they pass an `approval_payload` and need no
further wiring — an approval-required halt automatically produces a
resumable approval. A new `approval-sensitive-command` policy rule (priority
34, above `approval-protected-action`) catches allowlisted commands whose
arguments touch sensitive paths. Workflow start / task-result recording
remain enforced metadata actions; they don't currently produce
approval-required halts for user actors, so no approval payload is attached
(future agent-actor flows can opt in).

**Explicit non-goals for v1.6** (later Runtime versions): deterministic
validators and their evidence (v1.8), autonomous agent/file/command
execution, browser automation, web research, deployment, package
installation, cost-budget enforcement, the visual project debugger, and the
bottle-selling demo. (v1.7 turns the recorded quarantine resolution into a
real restriction.)

## Real Runtime Quarantine (v1.7 — shipped, enforced restriction)

`app/runtime/quarantine.py` is Milestone 6: it makes a quarantined agent
*actually* unable to act, rather than just wearing a status badge. The key
realization is that the enforcement gateway already had the choke point —
the v1.5 `block-unassignable-actor` rule (priority 10) refuses any action
whose actor agent is `quarantined`/`disabled` before execution. v1.7 builds
the lifecycle around it and routes real actors through it.

**Bookkeeping without migration.** Quarantine details (reason, requested_by,
timestamps, source action/approval, prior status, lift fields) live in
`agent.meta["quarantine"]` — a JSON column that already exists — so v1.7
adds **no new columns** and works on databases created by earlier versions.
`service.update_agent` preserves that reserved key across a user metadata
PATCH, and `_agent_out` surfaces it as a dedicated `quarantine` field while
stripping it from the public `metadata`. `quarantine_agent` /
`unquarantine_agent` set the status, write the bookkeeping, and emit
`agent.quarantine.requested` → `agent.quarantined` → `agent.quarantine.
enforced` (and the inverse trio on lift, ending with
`agent.permissions.restored`).

**Real-actor enforcement.** The Files and Commands routes gained an optional
`agent_id`; when present, `guarded_execute` proposes the action with
`actor_type="agent"`, so a quarantined agent's write/delete/mkdir/command is
refused before execution (disk untouched) and the gateway emits the
quarantine-specific `agent.quarantine.blocked_action` alongside
`enforcement.blocked`. The v1.2/v1.3 safety layers are unchanged and still
run beneath. The v1.5 extreme-risk `quarantine_agent` decision now applies
real quarantine deterministically during evaluation, and the v1.6 approval
`quarantine` resolution quarantines the linked agent for real — and because
the quarantine rule outranks the approval rules, a quarantined agent's
sensitive action is blocked outright rather than creating a bypassable
approval.

**Workflow integration.** Assignment already excluded quarantined agents
(v1.4 `UNASSIGNABLE_AGENT_STATUSES`); quarantine now also blocks an agent's
existing pending/running tasks (`runtime.task.blocked`), and
`record_result` refuses a result attributed to a quarantined agent (raised
as `SandboxBlocked` so the audit event commits). User-actor recording for
non-quarantined agents is unaffected.

**Explicit non-goals for v1.7** (later Runtime versions): deterministic
validators (v1.8), the visual project debugger (v1.9), the bottle-selling
demo (v2.0), autonomous agent execution, browser automation, web research,
deployment, package installation, and a full agent-to-agent message system
(so the "quarantined agent may still message a Verifier/Human" allowance is
not built — quarantine restricts the existing action surfaces only).

## Deterministic Validators (v1.8 — shipped, evidence over trust)

`app/runtime/validators.py` is Milestone 8: deterministic, evidence-based
checks so the platform never has to take an agent's output on faith. Each
validator is a pure function returning an `Outcome` (passed, bounded/redacted
evidence, failures, suggested action, risk/trust deltas, plain-English
explanation, plus extra signal events); `run_validator` persists a
`ValidatorResult`, emits `validator.started` → signal events →
`validation.passed`/`failed` → `validator.completed`, and (when a `task_id`
is supplied) stamps the task's `validation_status` metadata. **No LLM
judgment, no web browsing, no live URL fetch, and no arbitrary project code
runs** — Python is checked with `ast.parse`, JSON with `json.loads`, and the
command-result validator *consumes* the most recent recorded v1.3 command
event rather than re-running anything.

**Evidence hygiene.** Secret detection uses a broader pattern set than the
command-output redactor (api keys, private-key headers, `.env` assignments)
but every captured snippet is run through the same `_redact` before it is
stored — a found secret is reported as `API_KEY = "[redacted]"`, never raw.
Evidence dicts and failure lists are length-capped, and only logical
workspace paths (never host paths) appear in results or events. A test plants
a live-looking key and greps the result, the activity stream, and the
decisions API to prove it never surfaces.

**Narrow integrations.** Enforcement gains exactly one rule —
`block-failed-validation` (priority 16) blocks an action whose proposal
metadata carries `validation_failed` (the caller references a failed
result), extending the existing v1.5 policy/evidence model without a new
engine. Trust/Risk integration is deliberately signal-only: results carry
`risk_delta`/`trust_delta` and the events expose them, but the deterministic
v0.5 event-fold is **not** modified — documented as a limitation so the
safety-critical scoring path stays a pure, reviewed function. Workflow
linkage is metadata-only (`task.meta["validation_status"]`) to avoid a
validator mutating the orchestration scheduler's state.

**Explicit non-goals for v1.8** (later Runtime versions): browser
automation, live external research/URL fetching, a production static
analyzer or full type-checker, autonomous execution, deployment, package
installation, the visual project debugger (v1.9), and the bottle-selling
demo (v2.0).

## Visual Project Debugging (v1.9 — shipped, read-only comprehension layer)

`app/runtime/debug.py` is Milestone 9: a beginner-friendly Workspace Home
built **entirely from existing data**. It is a pure, deterministic
aggregation — it mutates nothing, emits no events, and adds no runtime
behavior; a test proves the activity-event count is stable across repeated
debug calls. A single `_collect` pass reads agents, workflows/tasks,
enforcement decisions, pending approvals, validator results, sandbox status,
and the most recent ~200 activity events; `_signals` distills them, and the
public `summary` / `issues` / `project_map` builders shape three read-only
endpoints (all open in local mode — they expose nothing a panel couldn't
already fetch).

**Deterministic health.** `_health` checks signals in a fixed severity order
(agent_restricted > approval_needed > validation_failed > blocked >
build_test_failed > action_blocked > risky_change), takes the highest as the
primary state, and surfaces all active states as labels. "Meaningful"
activity deliberately excludes bare `workspace.*` lifecycle events, so a
freshly created workspace reads "No signals yet" rather than a false
"healthy". Recommended actions and issues are likewise rule-derived (no LLM)
and carry plain-English titles plus a target-panel hint and a row/event ref.

**Grounded, redacted by construction.** Every field is sourced from
already-redacted/bounded inputs — events exclude host paths, validator
evidence is pre-redacted — and the aggregator only re-surfaces logical paths
and short summaries; a test plants a live-looking secret and greps the
summary, issues, and project map for it and for the host root. The project
map is generic (goal → workflow → task → agent → artifact, plus data-flow/
claim validation nodes) with de-duplicated node ids — no demo-specific
hardcoding, future-proofed for v2.0.

**Explicit non-goals for v1.9** (later Runtime versions): the
bottle-selling demo (v2.0), autonomous execution, browser automation, web
research, deployment, a routed graph editor, live push updates, and any new
validator/enforcement/approval/quarantine engine.

## Bottle Shop End-to-End Demo (v2.0 — shipped, a seed, not an engine)

`app/runtime/demo_bottle_shop.py` is Milestone 10: a single isolated,
deterministic `seed()` that proves the whole runtime works together by
building a dependency-free storefront — and it deliberately adds **no new
behavior**. It only *orchestrates existing services*, in order: `service.
create_workspace` + `sandbox.init_sandbox`; `service.create_agent` ×6 (built
from `AgentDefinitionIn` defaults, with roles that match the deterministic
planner's step keywords so every task is assigned); `orchestration.
create_workflow` + `create_plan` + `transition_workflow("start")`; seven
website file writes through `enforcement.guarded_execute` →
`sandbox.write_file` (so each is a real propose→allow→execute arc);
`orchestration.record_result` walked over the DAG to completion; two
commands through `enforcement.guarded_execute` → `commands.run_command`;
five `validators.run_validator` calls; and one governance halt — a
payment-path write attributed to an agent actor that `guarded_execute`
refuses with `require_human_approval`, leaving a pending `ApprovalRequest`
the user resolves. The seed accumulates the normal events and the route
commits + broadcasts them, so Files/Commands/Workflows/Enforcement/Approvals/
Validators/Project-Debugging/Replay all light up with zero special-casing.

**Isolation & safety.** The bottle-shop content lives only in this module
(a `WEBSITE_FILES` dict and agent/result tables) — nothing bottle-specific
leaks into a generic runtime service. The route runs the seed in a
threadpool, commits once, broadcasts. The site is static and self-contained:
no secrets, no `https://`/CDN, no network, no package install, no server, no
real payment, no customer data; tests grep the API response, activity,
debug summary, and validator evidence for any host path or secret shape and
find none. The only "failures" are intentional and benign — the business-risk
validator flagging the checkout feature, and the payment write paused for
approval.

**Explicit non-goals for v2.0** (later versions): an autonomous coding
agent, browser automation, web research, package installation, cloud deploy,
payment integration, a real checkout, user accounts, a database-backed
store, and any new runtime engine. v2.0 is a demo that *uses* the platform,
not an extension of it.

## Website Preview + Landing Page (v2.1 — shipped, the Runtime v1 close-out)

`app/runtime/preview.py` is the final polish surface: a **safe, read-only
static serve** of files that already live inside a workspace sandbox, so a
user can see the generated site rendered inside AgentLab. It adds no engine
and no new behavior to the runtime — it is a read path layered on the v1.2
sandbox.

**Safety is reused, not reinvented.** `serve()` calls the v1.2 `check_path`
first, so traversal, absolute paths, secret-named files, and symlink/outside-
root escapes are rejected *before any disk access* (tests prove a planted
outside-root symlink and a `.env` are both refused and never echoed). Only a
fixed allowlist of static web extensions (`.html/.css/.js/.json/.svg/png/…`)
is served — anything else is a 415 — and a 2 MB cap bounds responses. The
route family is **GET-only** (POST/DELETE return 405); it returns file
*content* with a content-type, never a host path, and sets
`X-Frame-Options: SAMEORIGIN` + `Cache-Control: no-store`. The endpoints are
open in local mode (an `<iframe>` cannot attach `X-API-Key`), matching every
other read path. The frontend embeds the preview in a
`sandbox="allow-scripts"` iframe with no `allow-same-origin`: the previewed
markup/scripts run in an opaque origin and cannot reach the parent app, so
even arbitrary workspace HTML is contained; its cross-origin
`fetch('products.json')` falls back to in-file data, which is why the
storefront still renders without exposing the API to the isolated frame.

**Landing page.** `HomePage` at `/` is a static product page (hero, value
cards, how-it-works, positioning, CTAs); `/` no longer redirects to the
dashboard. The demo CTA calls the existing `POST /runtime/demo/bottle-shop`
seed and navigates to the new workspace — no new backend behavior.

**Explicit non-goals for v2.1** (would be a different product): a dev
server, build pipeline, package installation, cloud deployment, real
hosting, arbitrary web serving outside the target workspace, payment
integration, real checkout, user accounts, a large visual redesign, and any
new validator/enforcement/approval/quarantine/replay/model engine. The
preview is a *preview surface*, not a hosting platform. **This completes
Runtime v1.**

## Live Agent Execution — single governed step (v3.0 — shipped)

`app/runtime/agent_build.py` connects the model side (the v0.7 gateway / BYOK)
to the governed runtime — the first version where an agent's **own model
actually builds**. It is deliberately one bounded pass, not an autonomous
loop. Flow: take the workspace goal → build a strict-JSON-manifest prompt →
`await provider.complete(...)` through the gateway using the agent's own
`model_provider`/`model_name` → parse the manifest (tolerant of markdown
fences; a malformed or empty response yields **zero writes** and an
`agent.build.failed` event) → for **each** proposed file, call
`enforcement.guarded_execute(action_type="file.write", actor_type="agent",
agent_id=…, approval_payload={path,content}, execute=sandbox.write_file)`.

The single most important property: **the agent's writes go through the exact
same choke point as a manual write** — so v1.2 path safety, the v1.5 policy
registry, v1.6 approval halts, and v1.7 quarantine all apply with no new code.
Safe files are written; sensitive paths (auth/payment/deploy) raise
`EnforcementRefused` with a 403 and create an approval (recorded as
`halted_for_approval`); traversal/secret paths are blocked (recorded as
`blocked`, disk untouched); a blocked/held file never aborts the rest of the
manifest. The model's raw output is run through `_redact` *before* it enters
the `model.completed` telemetry preview — a real leak the test suite caught,
since generated code can contain a secret. The route validates + refuses a
quarantined agent (409), runs the async model call, then does all DB /
enforcement / event work in a threadpool and broadcasts.

Events: `agent.build.started/completed/failed` plus the reused `model.*`,
`action.*`, `enforcement.*`, and `sandbox.file.*` — Replay reconstructs the
full chain. Written files render through the v2.1 preview; held files appear
in the v1.6 Approvals panel.

**Explicit non-goals for v3.0** (later v3.x): no iteration/autonomous loop, no
agent-driven command execution, no multi-step planning, no validator-feedback
loop, no pause/resume across approval — those are v3.1 (bounded loop + governed
commands + validator feedback) and v3.2 (resume-on-approval). v3.0 reuses every
existing engine and adds none.

## Bounded Agent Loop (v3.1 — shipped, multi-step governed execution)

`app/runtime/agent_run.py` wraps the v3.0 single-pass body in a **bounded
iteration**. It is not a new engine — it is a controller that calls the model
gateway, enforcement, command runner, sandbox, and validators in a loop, all
exactly as the rest of the runtime calls them. v3.0's JSON tolerance is shared
verbatim: `agent_build.load_json_object` / `files_from` / `_salvage_html` were
factored out so both the single pass and the loop parse identically.

**The loop.** Up to `max_steps` passes (default 6, hard-capped at 8 by
`clamp_steps`). Each step: `build_step_prompt` assembles the goal + the current
sandbox file tree + the *previous* step's validator results, command results,
and approval/block notes → one real `provider.complete(...)` through the agent's
own provider/model → `parse_step` extracts `{summary, done, files[], commands[]}`
(commands accept `{command,args}` objects or bare strings; everything is bounded
and capped) → `apply_step` executes the actions. Because the async model call
must interleave with synchronous DB/enforcement work, the **loop body lives in
the route**: the model call is awaited, then `apply_step` runs in a threadpool
and commits per step, so a long loop streams its events as it goes.

**Same choke point for files *and* commands.** Every file write and every
`command.run` is attributed to the agent and routed through
`enforcement.guarded_execute` — so v1.2 path safety, the v1.5 policy registry,
v1.6 approval halts, and v1.7 quarantine apply with no new code. A safe file
lands in the sandbox; a safe command runs through the v1.3 runner (scrubbed env,
allowlist, timeout); a sensitive path/command raises `EnforcementRefused` (403)
and creates an approval; a traversal/secret path or unsafe command is blocked
(disk untouched). A blocked or held action never crashes the step — it is
recorded as an outcome.

**Validator feedback.** After a step's actions, `_run_step_validators` runs the
deterministic v1.8 validators over the outputs — `secret_exposure` on every
written file, `code_syntax` on `.py`/`.json`, `command_result` when a command
ran — and the pass/fail lines are folded into the next prompt. Validators are
reused unchanged; their evidence stays redacted and bounded, and the model
output is `_redact`ed before it ever reaches the `model.completed` preview.

**Stop conditions.** The loop stops on a model `done` signal, a step with no
actions, `max_steps`, an unrecoverable error (a failed or malformed model
response), or the **first approval-required action** — recorded as
`halted_for_approval`, after which the loop stops cleanly with a pending
approval. Pausing the loop and resuming it once that approval is granted is
v3.2 and deliberately not built here. `finalize_run` computes the overall
status (completed if any file was written or the model said done, else failed)
and emits `runtime.agent_run.completed`/`failed`.

**Events & replay.** `runtime.agent_run.started` → one `runtime.agent_run.step`
per pass (with per-step counts and the stop reason) → `completed`/`failed`,
plus all the reused `model.*`/`action.*`/`enforcement.*`/`sandbox.*`/
`validator.*` events — so Replay reconstructs the entire multi-step build.
Route: `POST /runtime/workspaces/{id}/agent-run` (gated; 409 if quarantined).
UI: the **Agent run** panel renders a per-step timeline (files, commands,
validator badges) with a plain-English stop reason.

**Explicit non-goals for v3.1** (later versions): pause/resume the loop across
an approval (v3.2), parallel agents, agent-to-agent handoff, arbitrary
long-running processes/dev servers, package installation, web research, and any
new validator/enforcement/approval/quarantine engine.

## Pause/Resume the Loop on Approval (v3.2 — shipped)

v3.1's loop ran entirely inside one request and *stopped* at the first
approval-required action. v3.2 makes that stop a **pause**: the loop is
persisted and can be **resumed** from the next step once the human resolves the
approval. It adds one state table and two endpoints — no change to the approval
engine, the enforcement gateway, or the step body.

**The state row.** `AgentRun` (`runtime_agent_runs`) persists everything the
loop needs to continue: the goal, `max_steps`, the `next_step` cursor, the
accumulated public step outcomes, the serialized `StepContext` for the next
prompt, the `pending_approval_ids` blocking a resume, and a `status`
(`running` → `awaiting_approval` → `running` → … → `completed`/`failed`). The
async loop body is shared by both entry points via `_drive_agent_loop`, which
runs steps `[start_step, max_steps)`; `_finalize_loop` then calls `pause_run`
(if the stop reason was `halted_for_approval`) or `complete_run`.

**Pause.** When a step holds an action, `pause_run` records the run as
`awaiting_approval`, sets `next_step` past the halting step, links the pending
approvals (matched by the held targets), and emits `runtime.agent_run.paused`.
The `POST …/agent-run` response now carries `run_id`, `status`, and
`pending_approval_ids` — the v3.1 single-shot completion became a resumable
checkpoint.

**Resume.** `POST …/agent-run/{run_id}/resume` refuses unless the run is
`awaiting_approval` and *every* linked approval is resolved (409 otherwise).
`resume_context` rebuilds the next prompt from the **current** sandbox tree
(an approved write now exists on disk) plus a plain-English note per
resolution, and `_reconcile_steps` rewrites the stored held outcome to
`approved` (granted + executed) or `denied` so the run's history reads true.
It emits `runtime.agent_run.resumed` and drives the loop onward from
`next_step`; a later approval pauses it again, fully re-resumable. The approval
is granted/denied entirely through the **existing v1.6 flow** — `approvals.
resolve` is not touched, and approving is what actually writes the held file
(the loop just observes the result). `GET …/agent-run/{run_id}` returns the
live state for the UI.

**Why an explicit resume (not auto-resume).** Driving the loop is async
(model calls) and belongs in the request/route layer; `approvals.resolve` is a
synchronous, widely-shared service. Keeping resume a separate, gated endpoint
keeps the approval system decoupled and composable, and lets a human resolve
several approvals before continuing.

**Explicit non-goals for v3.2** (later versions): auto-resume on approval,
parallel/branching runs, agent-to-agent handoff, long-running processes/dev
servers, package installation, web research, and any new enforcement/approval/
validator/quarantine engine. v3.2 completes the Live Agent Execution arc
(v3.0 single step → v3.1 bounded loop → v3.2 resumable loop).

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
