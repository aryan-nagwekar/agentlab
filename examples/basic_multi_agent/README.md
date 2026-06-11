# Basic multi-agent demo

A simulated five-agent software pipeline instrumented with the AgentLab SDK:

```
Planner ──▶ Researcher ──▶ Coder ──▶ Security Reviewer ──▶ Reporter
                              ▲              │
                              └── fix loop ──┘   (retry scenario)
```

No LLM API keys are needed — model calls, token counts, costs, and latencies
are simulated, but every event flowing to AgentLab is real.

Trust/risk scores are **not** set by this demo — they're derived by the
deterministic scoring engine from the events below. The malicious agent ends
quarantined at ~0.1 trust / 1.0 risk; a faulted agent degrades to `caution`
without being labelled malicious.

Each agent uses a **mock model provider** (no real API calls): Planner & Coder
on `mock:claude-sonnet`, Researcher on `mock:gpt-4.1`, Security on the free
`mock:local-ollama`, Reporter on `mock:gemini-pro`. Cost is derived from a
static pricing table, so in the **Cost & Tokens** tab the Coder is most
expensive, the Researcher is most token-heavy, and the Security reviewer is
free. The `failure` scenario includes one failed Security model call.

## Scenarios

| Scenario  | What happens                                                                  |
| --------- | ----------------------------------------------------------------------------- |
| `success` | Clean linear run                                                              |
| `retry`   | A `web.search` tool call times out and is retried; security review finds an issue and bounces a fix back to the coder (back-edge in the topology) |
| `failure` | The security reviewer crashes → `agent.failed` → `run.failed`, trust drops    |
| `fault`   | **Fault Injection Demo — Research Agent Timeout**: Lab Mode injects a simulated model timeout (`fault.injected` → `model.failed` → `agent.failed` → `run.failed`); jump to it with the Fault marker in Replay |
| `malicious` | **Malicious Agent Demo — Prompt Injection Attempt**: a simulated malicious agent joins, fakes capabilities, sends a prompt injection, attempts mock exfiltration, then is flagged and quarantined (`attack.injected` → `message.flagged` → `agent.quarantined`); jump to it with the Attack marker in Replay. All mock data. |

## Run it

```bash
# with the AgentLab API running on :8000
python run_demo.py                 # one run of each scenario
python run_demo.py --scenario retry --runs 2
python run_demo.py --fast          # minimal sleeps, used for seeding
python run_demo.py --use-gateway   # route model calls through the model gateway (mock)
```

By default model calls are logged directly. With `--use-gateway` each call is
routed through the AgentLab model gateway (mock provider) — useful for
exercising the full provider path. To use a real provider, set
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in `.env` and test it from
**Settings → Model Gateway**.

The script falls back to the in-repo SDK automatically, so it works without
installing anything (the SDK has zero dependencies).
