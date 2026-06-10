<div align="center">

# AgentLab

**Wireshark + Mininet + Kubernetes for AI agents.**

A production-style observability and control plane for multi-agent AI systems:
SDK-based instrumentation, real-time agent topology, message-level inspection,
run metrics, a replay debugger that steps through any run like a packet
capture, a fault-injection lab for chaos-testing, and a safe cyber range for
simulating malicious agents — with trust-aware routing analysis on the roadmap.

`Python 3.12` · `FastAPI` · `PostgreSQL/SQLite` · `React 18 + TypeScript` · `React Flow` · `WebSockets` · `Docker Compose`

<img src="docs/screenshots/topology-retry.png" alt="Live agent topology with the security reviewer selected: trust/risk meters, per-node stats, recent activity" width="100%" />

</div>

---

## Why

LLM observability tools answer *"what did the model say and what did it cost?"*
Multi-agent systems fail at a different layer:

- **Which agent** caused the bad output?
- **Which message or tool call** triggered the failure?
- **Why** was the task routed to Agent B instead of Agent C?
- Which agent is slow, expensive, unreliable — or behaving maliciously?
- What did the whole system do, **as a network**, from start to finish?

AgentLab treats an agent system the way network engineers treat a network:
agents are nodes, messages are packets, runs are captures you can open,
inspect, and (soon) replay.

## What works today (v0.4)

| Capability | Status |
| --- | --- |
| Python SDK — zero-dependency instrumentation (agents, messages, tools, models, routing, trust) | ✅ |
| Event collector — FastAPI, validated 22-type event schema, idempotent ingest | ✅ |
| Storage — append-only event log + relational projections (PostgreSQL / SQLite) | ✅ |
| Live dashboard — dark-mode infra UI with per-project WebSocket streaming | ✅ |
| Agent topology — React Flow graph: status rings, trust bars, per-node stats, labeled message edges | ✅ |
| Wireshark-style inspector — payload/metadata trees, parent↔child event links, raw JSON | ✅ |
| Run metrics — tokens, cost, avg/p95 latency, error rate, per-agent table, superlatives | ✅ |
| Demo workflow — 5-agent pipeline (success / retry / failure scenarios), no LLM keys needed | ✅ |
| Replay debugger — play/pause/step/scrub any run; jump to next error, tool call, routing decision, or fault; topology and inspector reconstruct at every cursor position | ✅ |
| Fault injection lab — kill / overload / tool failure / model timeout / message delay / message drop, injected from the UI; graph reacts live, every fault is replayable, all simulated | ✅ |
| Security Lab — 8 simulated malicious-agent attacks (prompt injection, mock exfiltration, fake capabilities, spam, trust poisoning, routing manipulation, unsafe tool request, rogue join); suspicious/quarantine markers, flagged edges, attack replay markers — all mock data, nothing real touched | ✅ |
| Trust/risk scoring engine + automatic quarantine + routing analysis | 🔜 v0.5 |

## Architecture

```mermaid
flowchart LR
    subgraph Your agent app
        A[Agents] -->|"@trace_agent · send_message · trace_tool"| SDK[AgentLab SDK\nbuffered bg thread]
    end
    SDK -->|"POST /api/events (batched, retried)"| API[FastAPI collector]
    API --> DB[(events log +\nprojections)]
    API -->|"WS /ws/projects/:id"| WEB[React dashboard]
    DB -->|"graph · metrics · timelines"| API
    WEB -->|"topology · inspector · metrics"| DEV((developer))
```

Raw events are the source of truth; runs, agents, messages, tool calls, and
routing decisions are **projections** maintained at ingest time. The full
design is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Quickstart

### Option A — Docker, one command (PostgreSQL + API + dashboard)

```bash
make up-demo     # builds + starts the stack, seeds 3 demo runs
open http://localhost:3000
```

(Equivalent to `docker compose up --build -d && docker compose --profile demo run --rm seed`.)

### Option B — bare metal, one command (SQLite, no services)

```bash
make install     # once: venv + editable installs + npm install
make dev         # collector :8000 + demo seed (first boot) + dashboard :5173
open http://localhost:5173
```

Prefer separate terminals? `make api`, `make web`, and `make demo` still exist.

### Option C — just the tests

```bash
make install && make test    # 44 tests: SDK transport/client + API/projections/graph/metrics/WS
```

## Instrument your own agents

```python
from agentlab import AgentLabClient, trace_agent

client = AgentLabClient(
    project_id="my-app",
    api_key="dev-key",
    endpoint="http://localhost:8000",
)

@trace_agent(name="PlannerAgent", role="planner")
def plan(goal: str):
    client.routing_decision(
        task="research",
        candidates=[
            {"agent_id": "researcher", "trust_score": 0.92, "latency_ms": 800},
            {"agent_id": "cache-agent", "trust_score": 0.55, "latency_ms": 90},
        ],
        selected_agent_id="researcher",
        reason="fresh data required; cache confidence below threshold",
        confidence=0.87,
    )
    client.send_message("researcher", {"task": "research", "goal": goal})

@trace_agent(name="ResearchAgent", role="researcher")
def research(query: str):
    with client.trace_tool("web.search", input={"q": query}) as tool:
        tool.output = {"hits": 3}
    client.log_model_call("fable-5", prompt_tokens=900, completion_tokens=260,
                          latency_ms=420, cost_estimate=0.006)

with client.run(name="my-first-traced-run"):
    plan("build the feature")
    research("API best practices")
```

Open the dashboard → your project appears automatically, with the run, the
topology, and every message inspectable. The SDK never raises into your app,
buffers through collector outages, and becomes a no-op with
`AGENTLAB_DISABLED=1`. Full SDK docs: [packages/sdk-python](packages/sdk-python/README.md).

## The demo, in 60 seconds

`make demo` seeds three runs of a simulated software pipeline
(`Planner → Researcher → Coder → Security Reviewer → Reporter`):

1. **success** — clean linear run. Open it → five healthy nodes, labeled message edges.
2. **retry** — a tool times out and is retried; security review bounces a fix
   back to the coder (a back-edge in the topology). Click the
   `coder → security` edge → both messages; click one → full payload + linked
   parent events.
3. **failure** — the security reviewer crashes: run fails, the node turns red,
   its trust score drops to 0.42 — visible in the graph and the agent page.
4. **replay it** — open the failed run → **Replay** tab → press ▶ (or scrub /
   arrow keys). The topology rebuilds event by event; hit **Error** to jump
   straight to the crash with the inspector following the playhead.
5. **break it yourself** — the seeded **Fault Injection Demo — Research Agent
   Timeout** run shows a Lab-injected model timeout killing the researcher
   mid-run (`fault.injected → model.failed → agent.failed → run.failed`).
   Then open **Lab**, pick any run, and inject your own: kill an agent, force
   a tool failure, drop messages on a channel — the status strip and topology
   react live, and the **Fault** marker in Replay takes you straight to the
   moment of injection.
6. **attack it (safely)** — the seeded **Malicious Agent Demo — Prompt
   Injection Attempt** run shows a fake agent joining, lying about its
   capabilities, sending a prompt-injection message, attempting mock secret
   exfiltration, and getting flagged and quarantined. Open its **Replay** tab
   and hit the **Attack** marker to inspect the raw (mock) attack payload. Or
   open **Lab → Security Lab** and launch your own attacks — every payload is a
   `MOCK_*` placeholder; nothing real is read, sent, or executed.

![Replay debugger: scrubber with markers, reconstructed topology at the failure, inspector following the playhead](docs/screenshots/replay-debugger.png)

![Fault Injection Lab: six simulated fault types with live agent status strip](docs/screenshots/lab-mode.png)

![Security Lab: eight simulated malicious-agent attacks with mock payloads](docs/screenshots/security-lab.png)

![Replay paused on a simulated attack with the malicious agent suspicious and the raw payload inspected](docs/screenshots/malicious-replay.png)

| Fleet dashboard | Message inspector |
| --- | --- |
| ![Dashboard](docs/screenshots/dashboard.png) | ![Message inspector with payload tree and parent event link](docs/screenshots/inspector-message.png) |

| Run metrics | |
| --- | --- |
| ![Metrics: stat cards, highlights, per-agent charts](docs/screenshots/metrics.png) | |

Screenshots are generated, not hand-made: `cd apps/web && npm run screenshots`
(Playwright, against the running stack — it also asserts the WebSocket stream
connects).

## Repository layout

```
agentlab/
├── apps/
│   ├── api/                  # FastAPI collector + read API + WS  (22 tests)
│   └── web/                  # React dashboard (Vite, TS, Tailwind, React Flow)
├── packages/
│   └── sdk-python/           # zero-dependency instrumentation SDK (22 tests)
├── examples/
│   └── basic_multi_agent/    # 5-agent simulated pipeline (3 scenarios)
├── docs/plans/               # implementation plans
├── docker-compose.yml        # postgres + api + web + seed profile
├── PRODUCT_SPEC.md · ARCHITECTURE.md · ROADMAP.md
└── Makefile                  # install / test / api / web / demo / up
```

## Security Lab safety

The Security Lab is a **safe cyber range**. Every "attack" is a telemetry
simulation that emits an `attack.injected` event plus mock follow-up events
through the normal pipeline. There is **no real attack behavior anywhere**:

- ✅ Mock secrets only — hardcoded `MOCK_SECRET_TOKEN`, `MOCK_API_KEY_12345`, etc.
- ✅ Every attack payload is tagged `safe_simulation: true`, and event metadata
  asserts `real_secrets_accessed: false` and `real_network_access: false`.
- ❌ No real files or environment variables are read.
- ❌ No network requests are made to external hosts.
- ❌ No shell commands, no file deletion, no real system modification.
- ❌ No malware, exploit, or credential-theft code exists in this repo.

The malicious agent is a *simulated participant* (it shows up as a node); the
`lab-controller` that triggers an attack is excluded from the topology.

### Demo script

```text
make dev
open the dashboard → Malicious Agent Demo — Prompt Injection Attempt
go to the Replay tab → click the Attack marker
inspect the prompt-injection payload (all MOCK_ values)
open Lab → Security Lab
inject a Mock secret exfiltration attempt
watch the graph: malicious-agent turns suspicious → quarantined
```

## Known limitations (v0.1–v0.4)

Stated plainly so nobody discovers them the hard way:

- **Observability, not orchestration.** AgentLab records and explains agent
  behavior; it does not run, modify, or control your agents.
- **Single-node collector.** WebSocket fan-out is in-process; run one API
  replica. A Redis pub/sub layer is the planned path to horizontal scale.
- **Auth covers the write path only.** `AGENTLAB_API_KEYS` gates `POST
  /api/events`; the read API and dashboard are open, intended for local/
  trusted-network use until team auth lands (v0.7).
- **Trust/risk fallback semantics.** A run's topology shows trust/risk as of
  that run when the run contains `trust.updated`/`risk.updated` events;
  otherwise it falls back to the agent's *current* project-wide score.
- **Timestamps trust the SDK clock.** Events from multiple hosts with skewed
  clocks can interleave imperfectly; per-client `metadata._seq` is a
  tiebreaker, but there is no global logical clock.
- **Schema management is `create_all`.** Fine pre-1.0 with no migrations to
  preserve; Alembic arrives with the first schema change (v0.4). No retention
  policies yet — the event log grows until you prune it.
- **Demo telemetry is simulated.** The example pipeline's model calls, token
  counts, and costs are illustrative metadata, not real LLM usage.
- **Faults and attacks are telemetry simulations.** The Lab emits events *as if*
  the failure or attack happened — it does not intercept or control live agent
  traffic. A "killed" agent's real process keeps running; delay/drop faults and
  attack messages synthesize demonstration events rather than touching in-flight
  traffic. An SDK control-plane hook (real chaos against the demo workflow) is
  future work.
- **Quarantine is a visualization marker, not enforcement.** `agent.quarantined`
  paints the node and is recorded in the timeline/replay; it does not actually
  stop or isolate a running agent (real lifecycle control is out of scope until
  a later milestone).
- **Risk scores are simple and event-derived.** v0.4 sets risk from attack
  severity; there is no trust/risk *engine* yet (automatic thresholds,
  decay, routing impact) — that is v0.5.
- **Replay tape is a snapshot.** Opening the Replay tab loads the run's events
  once (up to 5,000); a still-running run keeps streaming, but the tape does
  not grow until the tab is reopened.
- **Replay folds from scratch per cursor move.** Fine into the low thousands
  of events; snapshot memoization is the planned fix for very large runs.
- **Bundle size.** The dashboard ships ~800 KB minified (React Flow +
  Recharts); route-level code-splitting is deferred.

## Roadmap (abridged — see [ROADMAP.md](ROADMAP.md))

- **v0.1 — local observability** ✅ instrument → collect → visualize → inspect
- **v0.2 — replay debugger** ✅ step through any run like a packet capture; jump to error/tool/routing
- **v0.3 — fault injection lab** ✅ six simulated fault types, injectable from the UI, replayable
- **v0.4 — malicious-agent simulation** ✅ eight sandboxed attack scenarios, suspicious/quarantine markers, attack replay
- **v0.5 — trust/risk engine**: event-driven scoring, automatic quarantine thresholds, routing analysis
- **v0.6 — framework adapters**: LangGraph, CrewAI, OpenAI Agents SDK, MCP
- **v0.7 — teams**: project auth, retention, multi-user
- **v1.0 — hosted platform**

## License

[MIT](LICENSE)
