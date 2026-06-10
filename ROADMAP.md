# AgentLab — Roadmap

## v0.1 — Local observability ✅ (current)

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
- Deferred to v0.5: an actual trust/risk *engine* (automatic thresholds,
  decay, routing impact); quarantine remains a visualization marker

## v0.5 — Trust/risk engine (pending approval)

- Event-driven trust/risk scoring with accumulation, decay, and reasons
- Automatic quarantine above a configurable threshold
- Explainable routing analysis that avoids low-trust agents

## v0.6 — Framework integrations

- Adapters: LangGraph, CrewAI, OpenAI Agents SDK, MCP servers
- Auto-instrumentation where the framework exposes callbacks/middleware
- OpenTelemetry span export (interop with existing tracing stacks)
- Alembic migrations (lands with the first relational schema change)

## v0.7 — Teams & projects

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
- Read API is unauthenticated in local mode (auth lands v0.7)
- Replay folds from scratch per cursor move (snapshot memoization when tapes
  get large); replay tape doesn't grow live for still-running runs
- Dashboard bundle could code-split React Flow / Recharts routes
- `examples/langgraph_integration/` arrives with v0.4 adapters
