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
