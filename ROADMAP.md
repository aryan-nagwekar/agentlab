# AgentLab — Roadmap

## v0.1 — Local observability ✅

The working vertical slice: **instrument → collect → visualize → inspect**.

- Zero-dependency Python SDK (agents, messages, tools, models, routing, trust)
- FastAPI collector: validated 22-type schema, idempotent batch ingest, optional API keys
- Append-only event log + relational projections (SQLite dev / PostgreSQL in Docker)
- Real-time dashboard: live topology (React Flow), Wireshark-style inspector,
  event timeline with filters, run metrics (tokens/cost/p95/error rate/highlights)
- 5-agent demo pipeline with success / retry / failure scenarios (no LLM keys)
- Docker Compose stack, Makefile DX, CI, 44 tests

## v0.2 — Replay debugger ✅

Open any run like a packet capture.

- `GET /runs/{id}/replay` (tape + jump markers) and
  `GET /runs/{id}/replay/graph?index=k` (server-side reconstruction)
- Client-side event-fold reducer with semantics identical to the server fold
  (pinned by both pytest and vitest suites); topology component reused
- Controls: play / pause / step / scrub (marker-dotted slider) / 0.5–8× speed,
  keyboard transport (space, arrows), clamped real-gap pacing
- Jump to next error / tool call / routing decision
- Inspector follows the playhead; pin any node/edge/event to detach
- Deferred to a later cut: snapshot memoization for very large tapes; live
  tape growth while a run is still streaming

## v0.3 — Fault Injection Lab ✅

Chaos engineering for agent systems — all simulated, telemetry only.

- 6 fault types via `POST /runs/{id}/faults`: kill_agent, overload_agent,
  force_tool_failure, simulate_model_timeout, delay_messages, drop_messages
- Each fault = `fault.injected` + realistic follow-up events through the
  normal pipeline (graph, metrics, WS, replay all react for free)
- Functional Lab UI: project/run pickers, live agent-status strip, template
  cards with targets + params, fault log with raw payloads
- Replay integration: `markers.faults`, rose scrubber dots, Fault jump button
- Seeded scenario: "Fault Injection Demo — Research Agent Timeout"
- Safety: simulation-only (`safe_simulation: true` end to end); no real
  process/network/secret interaction
- Deferred: `corrupt_message` / `increase_latency` variants; an SDK
  control-plane hook so faults can intercept *live* demo traffic

## v0.4 — Malicious-agent simulation ✅

A safe cyber range — all attacks are mock-only telemetry simulations.

- 8 attack types via `POST /runs/{id}/attacks`: malicious_agent_joined,
  fake_capability_advertising, prompt_injection_message,
  mock_data_exfiltration_attempt, high_frequency_spam, trust_poisoning,
  routing_manipulation, unsafe_tool_request
- Each attack = `attack.injected` + mock follow-ups (agent.joined/suspicious,
  flagged messages, risk.updated, quarantine) through the normal pipeline
- Security Lab UI (Lab → Security Lab): attack cards with mock-payload
  previews; suspicious/quarantine node states, flagged edges
- Replay integration: `markers.attacks`, fuchsia scrubber dots, Attack jump
- Metrics: attacks / flagged-messages / suspicious-agents counts
- Seeded scenario: "Malicious Agent Demo — Prompt Injection Attempt"
- Safety: mock secrets only; `safe_simulation: true`,
  `real_secrets_accessed: false`, `real_network_access: false` end to end
- The trust/risk *engine* itself shipped in v0.5 (below)

## v0.5 — Trust/risk engine ✅

Deterministic, event-derived, explainable scoring — no LLM, fully replayable.

- `app/scoring.py`: pure event-fold → per-agent trust/risk + explained history;
  one rule table shared by collector, graph, replay, metrics, and the JS mirror
- Endpoints: `/runs/{id}/scores`, `/runs/{id}/score-history`,
  `/runs/{id}/risk-summary`, `/agents/{id}/scores` (with trust/risk factors)
- Fixed the v0.4 bug: a quarantined malicious agent reads ~0.1 trust / 1.0 risk,
  never 1.0; a faulted agent degrades to `caution` without being labelled malicious
- UI: tier badges on nodes, score panel (reason + factors + history) in the
  inspector and agent page, run risk summary on the Metrics tab, and scores that
  evolve step-by-step in replay
- Scores derived on read = no `score.updated` events emitted (no feedback loops)
- 21 pytest + 11 vitest scoring tests
- Deferred: enforcement (routing impact, quarantine thresholds), score decay —
  the engine scores and explains, it is not a policy engine

## v0.6 — Cost/token profiler ✅

Deterministic per-agent / per-model / per-run cost and token attribution.

- `pricing.py` static table (mock providers, USD per 1M tokens) + `costing.py`
  pure fold over `model.*` events; cost always recomputed from tokens = single
  source of truth shared by endpoints, metrics, graph, and the JS mirror
- Endpoints: `/runs/{id}/costs`, `/runs/{id}/token-summary`,
  `/agents/{id}/costs`, `/projects/{id}/cost-summary`
- UI: Cost & Tokens tab (summary cards, cost/token/latency ranking bars,
  model-by-provider breakdown, agent table), model-call inspector with
  token/cost details, "Cost so far" strip that accumulates in replay
- SDK `log_model_call` gains provider/model_name/input_tokens/output_tokens
- Demo: per-agent mock providers — Coder most expensive, Researcher most
  token-heavy, Security on free local-ollama, a failed model call in the
  failure scenario
- 21 pytest + 10 vitest cost tests
- Deferred: real provider calls / BYOK (v0.7); pricing is a static local table

## v0.7 — Model gateway / BYOK ✅

Local-first model gateway: call providers through one interface, safely.

- `app/model_gateway/`: provider abstraction + mock (keyless default),
  OpenAI-compatible, Anthropic, and Ollama providers; registry from Settings;
  telemetry bridge to model.called/completed/failed
- Endpoints: `/model-gateway/providers`, `/providers/{p}/health`,
  `/model-gateway/test-call`, `/runs/{id}/model-call`
- SDK `client.model_call(...)` (clean model.failed if the gateway is unreachable)
- UI: Settings → Model Gateway — provider cards (status, models, redacted key)
  + safe test-call panel; gateway calls flow into telemetry, replay & Cost & Tokens
- Safe BYOK: keys env-only, never stored/returned/logged, redacted in UI; a test
  greps responses to prove no leak; `.env.example` placeholders only
- Demo `--use-gateway` routes model calls through the gateway (mock)
- 13 pytest + 2 SDK + 4 vitest gateway tests
- Deferred: hosted/cloud secret storage, per-user keys, real Gemini provider
  (→ v0.7.1)

## v0.7.1 — Model gateway patch: Gemini + Ollama troubleshooting ✅

- `GeminiProvider` (generateContent API): `GEMINI_API_KEY` / `GOOGLE_API_KEY`
  (GEMINI preferred), key server-side only and redacted in the UI like every
  other provider; `GEMINI_BASE_URL` overridable for tests
- Provider list now carries a `message` troubleshooting hint (mirrors health
  detail); rendered amber on unavailable/not-configured cards
- Ollama health check explains how to fix "unavailable": the configured
  `OLLAMA_BASE_URL`, `ollama serve` / `ollama pull llama3.2`, and the Docker
  `host.docker.internal:11434` hint
- 17 pytest + 6 vitest gateway tests (planted-key leak grep extended to Gemini)
- Still deferred: hosted/cloud secret storage, per-user keys

## v0.8 — Agent Builder Studio ✅

Build and run multi-agent workflows inside AgentLab.

- `app/studio/`: workflow/agent/edge definitions (own tables; the append-only
  `events` log stays the runtime source of truth), validation (DAG-only —
  cycles rejected with a clear error; provider/model checked against the
  gateway registry), and a deterministic topological executor
- Every model call goes through the v0.7 Model Gateway; a Studio run emits the
  standard run/agent/message/model events through the collector, so the graph,
  replay, inspector, metrics, trust/risk, and Cost & Tokens all work unchanged
- Endpoints: `/studio/workflows` CRUD, agent/edge CRUD, `/validate`, `/run`
  (+ `/runs` history); failed providers fail cleanly with `model.failed`,
  downstream agents are skipped, and the run ends in `run.failed`
- UI: Studio section — workflow list, React Flow canvas (drag, connect,
  select), agent editor (role/system prompt/provider/model/temperature/max
  tokens with unconfigured-provider warnings), edge editor, validate banner,
  run panel with Open Run / Replay / Cost & Tokens links, run history
- Seeded "Code Review Agent Team" (Planner → Coder → Security Reviewer →
  Report, all on keyless mock models) created at startup when no workflows exist
- 16 pytest + 11 vitest studio tests
- Deferred: templates (v0.9), loops/recursion, tools, hosted collaboration,
  cloud key storage, workflow governance

## v0.9 — Project Templates ✅

Start from real agent-team blueprints instead of a blank canvas.

- `app/studio/templates.py`: template registry — six 5-agent teams (Code
  Review, Research, Resume Tailoring, SOC Investigation, Customer Support,
  Data Analysis), each with category/tags/difficulty/use case, per-agent
  role + system prompt + mock model defaults, labeled edges, default input,
  expected outputs, and demo notes
- Templates are data, not a new run format: `create-workflow` materializes a
  normal v0.8 workflow (editable, validatable, runnable; agents carry
  `template_id` provenance in metadata)
- Endpoints: `GET /studio/templates`, `GET /studio/templates/{id}`,
  `POST /studio/templates/{id}/create-workflow`
- UI: template gallery ("Start from template"), preview page (canvas preview,
  agent team, default input, expected outputs, demo notes; system prompts
  behind an advanced toggle), create-with-optional-rename → opens the v0.8
  editor with the template's default input pre-filled in the run panel
- 11 pytest + 4 vitest template tests
- Deferred: Runtime v1 (workspaces, sandbox runtime, enforcement gateway,
  approvals, validators, real quarantine) — starts after v0.9 approval

## v0.9.1 — Chat Mode / Agent Mode + secure provider setup ✅

The Studio usability/safety patch before the Runtime v1 roadmap.

- Mode switcher on Studio pages: **Chat Mode** (conversational, read-only —
  action buttons disable, the assistant answers questions about the workflow,
  runs, failures, cost/tokens, trust/risk) and **Agent Mode** (runs workflows,
  edits, `/connect <provider>`, `/run`). Action requests in Chat Mode get
  exactly "Switch to Agent Mode to perform this action."
- `/connect gemini|openai|anthropic|ollama` opens a **secure setup modal**
  (password field, optional base URL, Save locally / Test call / Remove saved
  key) — raw keys never travel through chat; key-like text pasted into chat is
  blocked with a warning and never sent or stored
- Backend: `POST /model-gateway/providers/{p}/configure` + `/clear` store
  secrets in a local **gitignored** `.agentlab-secrets.json` (chmod 0600,
  overlays env, registry rebuilt immediately) — never the DB, never logged,
  never in responses/events/replay; only the redacted hint is returned
- Settings → Model Gateway cards gain a Configure button using the same modal
- 8 pytest + 9 vitest; the assistant is deterministic/local (rule-based over
  existing APIs — no LLM behind the chat)

## Runtime v1.0 — Runtime Workspaces (next, pending approval)

The Runtime v1 roadmap begins after v0.9: workspaces, sandboxed runtime,
enforcement gateway, human approvals, deterministic validators, and real
quarantine enforcement. Not started — requires explicit owner approval.

## Later (unscheduled)

- Framework integrations: LangGraph / CrewAI / OpenAI Agents SDK / MCP
  adapters, auto-instrumentation, OpenTelemetry span export, Alembic
  migrations (lands with the first relational schema change)
- Teams & projects: per-project key management, scoped tokens, multi-user
  roles, retention/archival, saved views, run comparison
- Hosted platform: managed multi-tenant deployment, ingest quotas, alerting,
  audit logging

---

### Engineering debt ledger (tracked honestly)

- Alembic migrations deferred until the first relational schema change
  (v0.3 added no tables — faults are events)
- Read API is unauthenticated in local mode (auth lands v0.10)
- Trust/risk engine scores and explains but does not enforce (no routing
  impact, no score decay, quarantine is a marker) — enforcement is future work
- Replay folds from scratch per cursor move (snapshot memoization when tapes
  get large); replay tape doesn't grow live for still-running runs
- Dashboard bundle could code-split React Flow / Recharts routes
- `examples/langgraph_integration/` arrives with v0.4 adapters
