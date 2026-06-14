# AgentLab — Developer Integration Guide

How to instrument agents, talk to the collector, use the Model Gateway, and
extend the Runtime **without bypassing the safety systems**.

## Emit events with the SDK

The zero-dependency Python SDK (`packages/sdk-python/agentlab/`) is the supported
way to send telemetry. It uses contextvars for run → agent → span scoping and a
buffered background-thread transport with retry/outage buffering.

```python
import agentlab

# init() creates a client and registers it as the default.
client = agentlab.init("my-project", endpoint="http://localhost:8000")

# A run is a context manager.
with client.run("nightly-batch"):
    # trace_agent is a decorator that scopes events to an agent.
    @agentlab.trace_agent("planner", role="planner")
    def plan():
        agentlab.send_message("coder", "plan ready")            # message event
        agentlab.log_model_call(                                # model.* events
            "mock:claude-sonnet", provider="mock",
            input_tokens=120, output_tokens=80,
        )
        agentlab.routing_decision(to_agent_id="coder", reason="codegen")

    plan()
```

Other public helpers: `agentlab.trace_tool(...)`, `agentlab.model_call(...)`
(routes a real call through the gateway), `agentlab.update_trust(...)`,
`agentlab.update_risk(...)`. The full public surface is `agentlab.__all__`.

Event **types are a fixed registry** kept in lock-step between the API
(`apps/api/app/events.py`) and the SDK (`packages/sdk-python/agentlab/_events.py`).
Adding a new event type means adding it to **both** — a parity test enforces it.

## Talk to the collector directly

If you can't use the SDK, `POST /api/events` accepts the validated event schema
(`apps/api/app/schemas.py`, `EventIn`). The append-only `events` table is the
source of truth; runs/agents/messages/scores/costs/workspace-history are all
read-side projections. Writes are gated by `X-API-Key` when `AGENTLAB_API_KEYS`
is set (empty = open local mode).

## Model Gateway providers (BYOK)

The gateway (`apps/api/app/model_gateway/`) abstracts providers behind
`ModelProvider.complete()` / `health_check()` / `redact_key()`. Built-ins:
`mock` (keyless, deterministic), `openai_compatible`, `anthropic`, `gemini`,
`ollama`. Keys come from **environment only** (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OLLAMA_BASE_URL`,
`OPENROUTER_API_KEY`) or the gitignored, chmod-0600 `.agentlab-secrets.json`
(configured via the UI). **Keys are never stored in the DB, returned to clients,
logged, or put in events** — only a redacted hint is exposed.

To add a provider: implement the `ModelProvider` interface, register it in the
gateway registry, and make sure `redact_key` never returns the full key. A test
plants a fake key and greps responses — keep it passing.

## Create workspaces, agents, workflows

Use the runtime API (all under `/api/runtime`):

- Workspaces: `POST /workspaces`, lifecycle routes.
- Agents: `POST /workspaces/{id}/agents` or `…/agents/from-template/{tid}`.
- Workflows: `POST /workspaces/{id}/workflows`, `…/plan`, `…/start`, tasks,
  `…/tasks/{id}/result`.

Or, for a worked end-to-end example, read `app/runtime/demo_bottle_shop.py` — it
orchestrates the existing services and emits their normal events, with **no
demo-only logic leaked into the generic runtime**.

## Use sandbox services safely

Always go through the existing services — never write files or run commands
directly:

- Files: `app/runtime/sandbox.py` (`write_file`, `read_file`, `make_dir`,
  `delete_path`) — they call `check_path` first.
- Commands: `app/runtime/commands.py` (`run_command`) — allowlist-first,
  `shell=False`, scrubbed env.
- Better still, route mutating actions through
  `enforcement.guarded_execute(...)` so they are proposed, evaluated, and
  governed before execution (see [ENFORCEMENT_POLICY.md](ENFORCEMENT_POLICY.md)).

## Add validators or policies without bypassing existing systems

- **A validator** is a pure function returning an `Outcome` (bounded, redacted
  evidence + risk/trust signals). Add it to `app/runtime/validators.py` and the
  registry; do not browse the web, run arbitrary code, or emit raw secrets. See
  [VALIDATOR_DESIGN.md](VALIDATOR_DESIGN.md).
- **A policy rule** is a deterministic condition over `ActionContext` returning a
  decision. Add it to the `POLICY_RULES` list with a priority; it must be
  explainable (id + name + reason) and must **not** weaken the v1.2/v1.3 safety
  checks, which still run as defense in depth. See
  [ENFORCEMENT_POLICY.md](ENFORCEMENT_POLICY.md).

Keep safety-critical logic **deterministic** (trust/risk and costing are pure
folds with Python ↔ JS mirrors pinned by tests). Prefer deterministic validation
over LLM judgment for blocking decisions.

## Avoid leaking secrets

Non-negotiable: secret values must never appear in raw events, frontend state,
logs, traces, replay payloads, screenshots, or test snapshots. Reuse the existing
redaction helpers (`commands._redact`, validator redaction), keep keys env-only,
and never echo a host filesystem path to the client. There are tests that grep
for planted secrets and host paths — they must stay green.

## Tests

```
make test                    # backend (pytest)
cd apps/web && npm test      # frontend (vitest)
cd apps/web && npm run build # type-check + build
```
