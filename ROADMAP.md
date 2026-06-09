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

## v0.2 — Replay debugger 🔜 (next, pending approval)

Open any run like a packet capture.

- Client-side event-fold reducer reusing the topology component
- Controls: play / pause / step forward / step back / speed / scrub
- Jump to: next error, next tool call, next routing decision
- Inspector works at any replay cursor position
- Snapshot memoization for long runs

## v0.3 — Lab mode (fault injection + security simulation)

Chaos engineering for agent systems — all simulated, mock data only.

- Fault API emitting `fault.injected` events: kill_agent, delay_messages,
  drop_messages, corrupt_message, increase_latency, force_tool_failure,
  simulate_model_timeout, overload_agent
- Malicious-agent scenarios: prompt-injection message, fake capability
  advertising, mock data-exfiltration attempt, trust poisoning, spam flood
- Trust scoring engine: event-driven score updates with reasons
- Quarantine flow: trust threshold → `agent.quarantined` → topology + routing react
- Lab UI activates (controls are stubbed in v0.1)

## v0.4 — Framework integrations

- Adapters: LangGraph, CrewAI, OpenAI Agents SDK, MCP servers
- Auto-instrumentation where the framework exposes callbacks/middleware
- OpenTelemetry span export (interop with existing tracing stacks)
- Alembic migrations (first post-v0.1 schema change lands with this)

## v0.5 — Teams & projects

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

- Alembic migrations deferred until the first schema change (v0.4)
- Read API is unauthenticated in local mode (auth lands v0.5)
- Dashboard bundle could code-split React Flow / Recharts routes
- `examples/langgraph_integration/` arrives with v0.4 adapters
