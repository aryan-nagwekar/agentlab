# Basic multi-agent demo

A simulated five-agent software pipeline instrumented with the AgentLab SDK:

```
Planner ──▶ Researcher ──▶ Coder ──▶ Security Reviewer ──▶ Reporter
                              ▲              │
                              └── fix loop ──┘   (retry scenario)
```

No LLM API keys are needed — model calls, token counts, costs, and latencies
are simulated, but every event flowing to AgentLab is real.

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
```

The script falls back to the in-repo SDK automatically, so it works without
installing anything (the SDK has zero dependencies).
