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

## v0.8 — Agent Builder Studio (pending approval)

- Define agents in-app and assign a provider/model to each (built on the gateway)
- Persisted agent definitions; invoke through the gateway
- No visual workflow builder / templates yet

## v0.9 — Framework integrations

- Adapters: LangGraph, CrewAI, OpenAI Agents SDK, MCP servers
- Auto-instrumentation where the framework exposes callbacks/middleware
- OpenTelemetry span export (interop with existing tracing stacks)
- Alembic migrations (lands with the first relational schema change)

## v0.10 — Teams & projects

- Real API-key management per project, scoped tokens
- Multi-user access, basic roles
- Retention policies + event archival
- Saved views, run comparison (A/B of two runs)

## v1.0 — Hosted platform

- Managed multi-tenant deployment
- Usage-based ingest quotas
- Alerting (failed runs, trust drops, cost spikes → Slack/webhook)
- SOC2-friendly audit logging

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
