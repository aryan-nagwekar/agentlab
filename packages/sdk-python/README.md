# agentlab-sdk

Zero-dependency Python instrumentation SDK for [AgentLab](../../README.md) —
observability for multi-agent AI systems.

```python
from agentlab import AgentLabClient, trace_agent

client = AgentLabClient(
    project_id="demo-project",
    api_key="dev-key",
    endpoint="http://localhost:8000",
)

@trace_agent(name="PlannerAgent", role="planner")
def plan(goal: str):
    client.send_message("researcher", {"task": "dig into", "goal": goal})
    return {"next_agent": "researcher"}

with client.run(name="nightly-pipeline"):
    plan("ship the feature")
```

## What it captures

| API                        | Events emitted                                  |
| -------------------------- | ----------------------------------------------- |
| `client.run(...)`          | `run.started` / `run.completed` / `run.failed`  |
| `@trace_agent(...)`        | `agent.started` / `agent.completed` / `agent.failed` (+ latency, traceback) |
| `client.send_message(...)` | `message.sent` / `message.received` / `message.failed` |
| `client.trace_tool(...)`   | `tool.called` / `tool.completed` / `tool.failed` |
| `client.log_model_call(...)` | `model.called` / `model.completed` / `model.failed` (tokens, cost) |
| `client.routing_decision(...)` | `routing.decision` (candidates, reason, confidence) |
| `client.update_trust(...)` / `update_risk(...)` | `trust.updated` / `risk.updated` |
| `client.model_call(...)` | runs a provider via the model gateway → `model.called` + `model.completed`/`failed` |

## Model gateway (v0.7)

Route a model call through AgentLab's gateway. The server runs the provider and
emits telemetry, so the call appears in the dashboard, replay, and Cost &
Tokens. The `mock` provider needs no key; real providers use local-first BYOK
(keys live in the server's environment, never in your code).

```python
result = client.model_call(
    run_id="run-123",
    agent_id="research-agent",
    provider="mock",                 # or "openai" / "anthropic" / "ollama"
    model_name="mock:gpt-4.1",
    prompt="Research the security risks of multi-agent systems.",
)
print(result["status"], result["total_tokens"])
```

If the gateway is unreachable the failure is captured cleanly as a
`model.failed` event — `model_call` never raises into your agent code.

Nested calls are linked automatically through context variables: a tool call
made inside a traced agent function is attributed to that agent, and every
child event carries `metadata.parent_event_id` for the inspector.

## Design guarantees

- **Zero runtime dependencies** — pure standard library.
- **Never breaks the host app** — delivery runs on a background thread with
  batching, retries, and bounded buffering; a dead collector costs you
  telemetry, never an exception.
- **Kill switch** — `AGENTLAB_DISABLED=1` (or `disabled=True`) turns the whole
  SDK into a no-op while your code keeps running.
- **Framework-agnostic** — decorators and context managers work with plain
  functions; LangGraph/CrewAI adapters are on the roadmap.

## Install

```bash
pip install -e packages/sdk-python        # from the monorepo
```
