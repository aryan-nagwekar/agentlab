# AgentLab Runtime v1 — Acceptance Matrix

This matrix audits the Runtime v1 acceptance criteria against what is actually
implemented, **honestly**. Where a criterion is only partially satisfied, it
is marked **Partial** with the exact boundary, rather than claimed complete.

Legend — **Status**: ✅ Complete · 🟡 Partial · ⚠️ Limitation.
Evidence cites the version, module(s), and test file(s).

| # | Criterion | Status | Version | Evidence | Notes / boundary |
|---|---|---|---|---|---|
| 1 | Create a project workspace inside AgentLab | ✅ Complete | v1.0 | `app/runtime/service.py`, `routers/runtime.py`; `test_runtime_workspaces.py`; UI `RuntimeWorkspaces.tsx` | Workspaces are first-class with a lifecycle (draft/active/paused/completed/archived/failed) and a per-workspace activity run. |
| 2 | Create / select agents inside the workspace | ✅ Complete | v1.1 | `service.py` (agents), `agent_templates.py` (7 templates); `test_workspace_agents.py`; UI `WorkspaceAgentsPanel.tsx` | Agent definitions + a 13-flag permission profile; create from template or from scratch. |
| 3 | Agents use the model gateway / BYOK system | ✅ Complete | v0.7 + v1.1 + **v3.0** | `app/model_gateway/`, `agent_build.py`; `test_agent_build.py` | The v3.0 Agent-build path makes a **real live model call** through the gateway using the agent's own `model_provider`/`model_name` (live-verified with local `ollama/llama3.2`). **Note:** the v1.4 orchestrator (workflow tasks) still makes no model calls — agent-build is the surface that genuinely uses the gateway. |
| 4 | Orchestrate a multi-agent workflow | ✅ Complete | v1.4 | `orchestration.py`; `test_orchestration.py`; UI `WorkflowsPanel.tsx` | Goal → deterministic plan → role-assigned tasks with dependencies + a lifecycle. **Boundary:** the planner is a fixed deterministic pipeline (not goal-aware), by design. |
| 5 | Agents can generate files / artifacts inside a sandbox | ✅ Complete | v1.2 + **v3.0** | `sandbox.py`, `agent_build.py`; `test_agent_build.py`, `test_sandbox_files.py` | In v3.0 the agent's model **autonomously authors file contents**, each written through the enforcement-gated sandbox service (live-verified: `ollama/llama3.2` generated `index.html`+`styles.css`). **Boundary:** a single governed pass, not a multi-step autonomous loop (v3.1); the v2.0 demo still uses a deterministic seed. |
| 6 | Sandbox streams file, command, build, test, and runtime events | 🟡 Partial | v1.2 + v1.3 + v1.8 | `sandbox.*` events, `sandbox.command.*` events, `runtime.error.detected` | File and command events are real and replayable. **Boundary:** "build/test" are represented by **command-result events** (running e.g. `npm test`/`pytest` through the allowlisted runner) and validator `runtime.error.detected`, not a dedicated production build/test pipeline. |
| 7 | Every risky action goes through enforcement before execution | ✅ Complete | v1.5 | `enforcement.py` (`guarded_execute`); `test_enforcement.py` | File write/delete/mkdir, command run, workflow start, and task-result recording all propose → evaluate → (only if allowed) execute. **Boundary:** covers the integrated runtime surfaces; the generic proposal API evaluates without executing. |
| 8 | Unsafe commands are blocked before execution | ✅ Complete | v1.3 + v1.5 | `commands.py` (`evaluate`), enforcement `block-unsafe-command`; `test_sandbox_commands.py` | Marker-file tests prove blocked commands never spawn a process. |
| 9 | Human approval can pause and resume actions | ✅ Complete | v1.6 | `approvals.py`; `test_approvals.py`; UI `ApprovalsPanel.tsx` | Approval-required actions halt and store the *exact* payload; approve resumes that exact action through the safe executors (their safety re-runs); deny blocks. **Boundary:** resume is **action-level**; workflow pause/resume is a separate v1.4 lifecycle. |
| 10 | Unverified supplier/product research cannot reach DB / UI / marketing | 🟡 Partial | v1.5 + v1.8 | `reroute-unverified-research` policy rule; `research_claim` + `business_risk` + `data_flow` validators | Deterministic validators reject claims lacking cited evidence, and enforcement can reroute unverified-research actions. **Boundary:** there is **no live supplier database or marketing pipeline** — this is policy + evidence-based validation of *provided* data, not propagation control over a real datastore. |
| 11 | Low-trust / hallucinating agents can be rerouted to a Verifier | 🟡 Partial | v1.5 + v1.6 | enforcement `reroute-high-risk-actor`/`reroute-unverified-research`/`reroute-flagged-task-result`; approval `reroute` resolution | Reroute decisions and approval reroute are recorded as **events/metadata** with a clear reason. **Boundary:** there is **no autonomous reassignment loop** — reroute records intent for a human to act on; AgentLab does not automatically re-run the work on a verifier agent. |
| 12 | Quarantine actually restricts runtime permissions | ✅ Complete | v1.7 | `quarantine.py`; enforcement `block-unassignable-actor` choke point; `test_quarantine.py` | A quarantined agent's file/command/task actions are refused before execution (disk untouched), it is excluded from task assignment, and existing tasks are blocked. **Boundary:** restricts the **existing action surfaces**, application-level (not OS isolation); no agent-to-agent message channel exists, so the "may still message a Verifier/Human" allowance is not built. |
| 13 | Deterministic validators catch fake supplier claims | ✅ Complete | v1.8 | `validators.py` `research_claim`; `test_validators.py` | Fails on missing `source_url`, missing required evidence fields, or a claim unsupported by the provided evidence. **Boundary:** evidence-based on **provided** data — no live URL fetch or web browsing. |
| 14 | Deterministic validators catch frontend/backend/data mismatches | ✅ Complete | v1.8 | `validators.py` `data_flow`; `test_validators.py` | Detects missing/type-mismatched fields between a consumer and producer and explains it in plain English. |
| 15 | UI shows project health simply by default | ✅ Complete | v1.9 | `debug.py`; UI `ProjectDebugPanel.tsx`; `ProjectDebug.test.tsx` | Beginner-first health state, recommended next action, recent changes, and issues. |
| 16 | UI provides deeper diagnostics on demand | ✅ Complete | v1.9 | `ProjectDebugPanel.tsx` (advanced disclosure) + every detail panel + Replay | Progressive disclosure: summary first, raw events/inspectors/replay behind clicks. |
| 17 | Replay reconstructs workflow, validation, approval, enforcement, quarantine | ✅ Complete | v0.2 + v1.4–v1.8 | `app/replay.py`; events flow into the workspace activity run | Every control-plane action emits events into the activity run, so the existing replay fold reconstructs the full decision history. |
| 18 | Trust/risk scoring works and evolves during replay | ✅ Complete | v0.5 | `app/scoring.py` + JS mirror `scoring.ts` | Deterministic pure event-fold, shared by collector/graph/replay/metrics. **Boundary:** v1.8 validator `risk_delta`/`trust_delta` are recorded **signals**; the v0.5 fold is intentionally not modified to consume them (documented). |
| 19 | Cost/token profiling across workspace/workflow/task/agent/model | 🟡 Partial | v0.6 | `app/pricing.py`, `app/costing.py` | Per-agent / per-model / per-run cost + token attribution works from `model.*` events. **Boundary:** the v1.4 orchestrator makes **no model calls**, so there is no per-workflow/per-task cost in runtime workflows or the demo — attribution exists at the agent/model/run level (e.g. Studio runs), not yet wired through orchestration tasks. |
| 20 | Existing AgentLab observability features still work | ✅ Complete | all | full suite green (398 pytest + 165 vitest) | No regressions across v0.1–v2.1. |
| 21 | Bottle Shop demo runs end-to-end with MockProvider / no paid calls | ✅ Complete | v2.0 | `demo_bottle_shop.py`; `test_demo_bottle_shop.py` | One-click, deterministic, keyless. |
| 22 | All tests pass | ✅ Complete | — | `make test` → 398 · `npm test` → 165 · `npm run build` → clean | See [Testing](#testing-evidence). |
| 23 | No real API keys are required for demos/tests | ✅ Complete | — | mock provider is keyless; tests use no external services | |
| 24 | No unsafe/destructive actions occur outside the sandbox | ✅ Complete | v1.2 + v1.3 | path safety (`check_path`) + command safety; marker-file/disk-untouched tests | Traversal, absolute paths, outside-root/symlink escapes, and secret-named files are rejected before any disk access. |

## Summary

- **Complete (✅): 20** — 1, 2, 3, 4, 5, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24 (3 & 5 closed by v3.0)
- **Partial (🟡): 4** — 6, 10, 11, 19 (3 and 5 upgraded to ✅ by v3.0 Live Agent Execution: a real agent model call that autonomously authors enforcement-gated sandbox files)

The Partials are all the same kind of honest boundary: AgentLab is a **governed
runtime and control plane**, not an autonomous software engineer or a live
production datastore. The control-plane mechanisms (enforcement, approval,
quarantine, validators, replay) are real and enforced; the "agents autonomously
write code / make live model calls / propagate through real databases / auto-
reroute work" behaviors are intentionally **not** built — they are recorded as
intent/metadata or driven deterministically by the demo seed.

## Testing evidence

```
make test                    → 398 passed
cd apps/web && npm test      → 165 passed
cd apps/web && npm run build → clean
```

See [RUNTIME_DESIGN.md](RUNTIME_DESIGN.md), [SANDBOX_SAFETY.md](SANDBOX_SAFETY.md),
[ENFORCEMENT_POLICY.md](ENFORCEMENT_POLICY.md), [VALIDATOR_DESIGN.md](VALIDATOR_DESIGN.md),
and [HUMAN_APPROVAL.md](HUMAN_APPROVAL.md) for the per-system design.
