# AgentLab — Product Specification

## Problem

Teams shipping multi-agent AI systems are debugging distributed systems with
print statements. Existing LLM observability products (LangSmith, Langfuse,
Helicone, Datadog LLM Obs) are **model-call centric**: prompts, completions,
tokens, cost, latency. They answer "what did the model do?"

Multi-agent systems fail at the **coordination layer**:

- A planner routes work to the wrong specialist and nobody can say why.
- One agent's malformed message poisons three downstream agents.
- A tool failure cascades into a retry storm that looks like "the model is slow."
- A compromised or misbehaving agent quietly degrades the whole workflow.
- A run fails and the only artifact is a 40,000-line interleaved log.

There is no Wireshark for this layer — no way to see the system as a network
of agents, inspect the traffic between them, and replay what happened.

## Target users

1. **AI startups** building agent products who need to debug failures fast.
2. **Developers** on LangGraph / CrewAI / AutoGen / OpenAI Agents SDK / MCP or
   custom frameworks (the SDK is framework-agnostic first).
3. **Enterprise platform teams** operating internal agent fleets.
4. **Researchers** studying emergent multi-agent behavior.
5. **Security teams** analyzing agent behavior, tool usage, and trust.

This is developer infrastructure, not a consumer app.

## Product vision

> AgentLab is a production-grade observability and control plane for
> multi-agent AI systems: SDK-based instrumentation, real-time topology
> visualization, message-level inspection, replay debugging, fault injection,
> trust-aware routing analysis, and agent lifecycle monitoring.

The mental model is networking tooling, applied one layer up:

| Networking | AgentLab |
| --- | --- |
| Wireshark packet capture | event log + message inspector |
| Packet Tracer / Mininet topology | live agent graph, fault injection lab |
| Kubernetes control plane | agent lifecycle, quarantine, routing analysis |
| Datadog / Grafana | run metrics, trust/risk scores, health |

AgentLab deliberately does **not** invent an agent protocol. It is the
observability/testing layer that sits on top of whatever protocol or framework
a team already uses.

## Core features

### Shipped in v0.1
1. **Python SDK** — decorators + context managers (`run`, `trace_agent`,
   `trace_tool`, `send_message`, `log_model_call`, `routing_decision`,
   `update_trust/risk`). Zero dependencies, buffered background delivery,
   outage-tolerant, `AGENTLAB_DISABLED` kill switch.
2. **Event collector** — FastAPI; 22-type validated event schema; idempotent
   batch ingest; optional API-key auth; SQLite or PostgreSQL.
3. **Projections** — append-only event log plus derived runs / agents /
   messages / tool calls / routing decisions for fast queries.
4. **Real-time dashboard** — projects, runs, agents; per-project WebSocket
   stream; dark infra-native UI.
5. **Live topology** — agents as nodes (status, trust, risk, stats), message
   flows as edges (count, latency, last status); run-scoped historical accuracy.
6. **Message inspector** — Wireshark-style: summary + raw JSON, payload &
   metadata trees, parent/child event navigation, channel (edge) drill-down.
7. **Metrics** — tokens, cost, avg/p95 operation latency, error rate,
   per-agent breakdown, superlatives (slowest / most expensive / most active /
   most unreliable).
8. **Demo workflow** — 5-agent simulated pipeline with success / retry /
   failure scenarios; generates realistic telemetry with no LLM keys.

### Shipped in v0.2
9. **Replay debugger** — play/pause/step/scrub over the ordered event tape;
   topology and inspector reconstruct as of any cursor;
   jump-to-error/tool/routing with marker navigation.

### Shipped in v0.3
10. **Fault Injection Lab** — six simulated fault types (`kill_agent`,
    `overload_agent`, `force_tool_failure`, `simulate_model_timeout`,
    `delay_messages`, `drop_messages`) injected from the UI as
    `fault.injected` + realistic follow-up telemetry; the graph reacts live,
    every fault is replayable, all simulation-only.

### Shipped in v0.4
11. **Security Lab — malicious-agent simulation** — eight sandboxed,
    mock-data-only attack types (rogue join, fake capability advertising,
    prompt injection, mock exfiltration, spam, trust poisoning, routing
    manipulation, unsafe tool request) injected from the UI as
    `attack.injected` + mock follow-ups; suspicious/quarantine node states,
    flagged edges, and attack replay markers. No real secrets, files, systems,
    or networks are touched.

### Shipped in v0.5
12. **Trust/risk engine** — deterministic, event-derived, explainable scoring:
    per-agent trust + risk from a shared rule table, tier badges, "why it
    changed" factors, score history, run risk summary, and scores that evolve
    step-by-step in replay. Fixes the prior trust-1.0-while-quarantined bug.

### Shipped in v0.6
13. **Cost/token profiler** — deterministic local pricing; per-agent, per-model,
    and per-run token + USD attribution; most-expensive / most-token-heavy /
    slowest / failed-call rankings; model-call inspector; cost that accumulates
    in replay. Mock providers only.

### Shipped in v0.7
14. **Model gateway / BYOK** — one provider interface (mock + OpenAI-compatible +
    Anthropic + Ollama); local-first keys read from the environment, never
    stored/returned/logged, redacted in the UI; provider health + safe test-call;
    gateway calls flow into telemetry, replay, and Cost & Tokens.

### Shipped in v0.7.1
15. **Gateway patch: Gemini + troubleshooting** — Gemini provider
    (`GEMINI_API_KEY`/`GOOGLE_API_KEY`, key server-side and redacted like every
    other provider, never stored in the DB); provider cards surface a
    troubleshooting hint (which env var to set; for an unreachable Ollama: the
    configured `OLLAMA_BASE_URL`, `ollama serve`, and the Docker
    `host.docker.internal` workaround).

### Shipped in v0.8
16. **Agent Builder Studio** — build multi-agent workflows in-app: visual DAG
    canvas, per-agent role/system prompt/provider/model (via the Model
    Gateway), validation (cycles rejected), one-click run. Studio runs are
    normal AgentLab runs — graph, replay, inspector, metrics, trust/risk, and
    Cost & Tokens work unchanged. Seeded "Code Review Agent Team" runs on the
    keyless mock provider.

### Next (gated, in order)
17. **Project templates (v0.9)** — not started; requires explicit approval.

## Non-goals (v1)

- Real billing / payments
- Complex auth or multi-tenant SaaS infrastructure
- Real Kubernetes deployment
- Decentralized identity
- Real exploits, real secret exfiltration, real attack tooling — all security
  scenarios are simulations over mock data
- 1000-agent swarms
- Custom LLM provider integrations beyond optional metadata

Core loop stays: **instrument → collect → visualize → inspect → replay → test**.

## Competitive positioning

| | Model-call tracing | Agent topology | Message inspection | Replay | Fault injection | Trust/quarantine |
| --- | --- | --- | --- | --- | --- | --- |
| LangSmith / Langfuse | ✅ deep | ⚠️ trace tree, not network | ⚠️ per-trace | ❌ | ❌ | ❌ |
| Datadog LLM Obs | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| AgentOps | ✅ | ⚠️ | ⚠️ | ⚠️ session video | ❌ | ❌ |
| **AgentLab** | ⚠️ metadata-level | ✅ first-class | ✅ first-class | ✅ shipped (v0.2) | ✅ shipped (v0.3) | ✅ trust/risk engine + quarantine (v0.4–v0.5) |

AgentLab competes on the **system view**, not on prompt analytics. It can sit
beside a prompt-tracing tool rather than replacing it.

## Success criteria

- A developer can go from `git clone` to seeing their own agents in the
  topology in under 10 minutes.
- "Why did this run fail?" is answerable by clicking: failed run → red node →
  failing event → payload.
- The demo communicates the value without any API keys or configuration.

## Future roadmap

See [ROADMAP.md](ROADMAP.md).
