# AgentLab Runtime — Design

How the Runtime control plane is built. This is the conceptual companion to
[../ARCHITECTURE.md](../ARCHITECTURE.md) (which has the per-version detail) and
the [AGENTLAB_RUNTIME_V1_PLAN.md](AGENTLAB_RUNTIME_V1_PLAN.md) master plan.

## One idea: raw events are the source of truth

Everything in AgentLab is a fold over an append-only event log. Runs, agents,
messages, trust/risk scores, costs, workspace history, enforcement decisions,
approvals, quarantine state, and validator results are **read-side projections**
of events — never a parallel source of truth. Every important action emits
events through one ingest path (`collector.process_events`), so the activity
feed, timeline, and **Replay** reconstruct control-plane history for free.

There are ~115 event types, kept in lock-step between the API
(`app/events.py`) and the SDK (`packages/sdk-python/agentlab/_events.py`).

## Workspace lifecycle

A **workspace** (`app/runtime/service.py`, v1.0) is a software project being
built inside AgentLab. Statuses: `draft → active → paused → completed →
archived → failed`. Each workspace owns an **activity run** (`{id}-activity`)
in its project; every workspace/agent/file/command/workflow/enforcement/
approval/quarantine/validator action emits its events into that run, which is
why one Replay reconstructs the whole build.

## Agents

**Workspace agents** (v1.1) are definitions: role, description, system prompt,
`model_provider`/`model_name` (reusing the Model Gateway vocabulary), a 13-flag
permission profile, budget ceilings, trust/risk, and a status
(`ready/running/caution/suspicious/quarantined/disabled`). Seven role templates
ship (Planner, UI, Backend Coder, Researcher, Marketing, Verifier, Safety
Reviewer). They are metadata + governance inputs; they do not autonomously
execute.

## Workflows and tasks

The **orchestrator** (v1.4) turns a workspace goal into a deterministic plan: a
fixed five-step pipeline (plan → research → backend → UI → verify) materialized
as **tasks** with dependencies, risk levels, and expected artifacts. Tasks are
assigned to agents by role keywords (disabled/quarantined agents are never
assigned). A scheduler tick starts tasks whose dependencies are complete and
settles the workflow to completed/failed/blocked. Results are recorded as
bounded text. The planner makes **no model calls** — it is deterministic and
keyless by design.

## Sandbox

The **sandbox** (v1.2) gives each workspace a real, workspace-bounded file area
under `{AGENTLAB_WORKSPACES_ROOT}/{workspace_id}/`. Path safety is deterministic
and checked before any disk access. See [SANDBOX_SAFETY.md](SANDBOX_SAFETY.md).

## Commands

The **safe command runner** (v1.3) runs a small allowlist of dev commands
(`pwd`, `ls`, `cat`, version checks, `npm test`/`run build`, `python -m pytest`)
with `shell=False`, a scrubbed environment, cwd locked to the sandbox, a hard
timeout, and capped/redacted output. Everything else is blocked before
execution. See [SANDBOX_SAFETY.md](SANDBOX_SAFETY.md).

## Enforcement, approvals, quarantine, validators

These are the **control plane**. Every important action is proposed, evaluated
by a deterministic policy registry, and resolved into an explainable decision
*before* execution (v1.5). Approval-required actions halt and can be resolved by
a human (v1.6). Quarantine actually restricts an agent's runtime actions (v1.7).
Deterministic validators produce evidence-based pass/fail results (v1.8). Each
has its own design doc:

- [ENFORCEMENT_POLICY.md](ENFORCEMENT_POLICY.md)
- [HUMAN_APPROVAL.md](HUMAN_APPROVAL.md)
- [VALIDATOR_DESIGN.md](VALIDATOR_DESIGN.md)

## Replay

Because every control-plane action emits events into the workspace activity run,
the existing **Replay** debugger (v0.2) reconstructs not only what agents did but
what AgentLab *allowed, blocked, rerouted, held for approval, or quarantined* —
step by step.

## Debug summary

The **Project Debugging UI** (v1.9, `app/runtime/debug.py`) is a **read-only**
deterministic aggregation over the existing models/events: project health,
recommended next action, recent changes, issues, and a project map. It mutates
nothing and emits no events.

## Demo flow

The **Bottle Shop demo** (v2.0, `app/runtime/demo_bottle_shop.py`) is a single
deterministic seed that orchestrates the existing services end-to-end — workspace
→ agents → workflow → sandbox files → safe commands → validators → a governance
halt (one payment write held for approval). It adds no engine. See
[BOTTLE_SHOP_DEMO.md](BOTTLE_SHOP_DEMO.md) and [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

## Website preview

The **website preview** (v2.1, `app/runtime/preview.py`) is a safe, read-only
static serve of files already inside the sandbox, rendered in a sandboxed iframe.
See [SANDBOX_SAFETY.md](SANDBOX_SAFETY.md#website-preview-safety-v21).

## What the Runtime is not

It is not an autonomous coding agent, a deployment platform, a build system, a
package manager, a browser/web-research tool, or a live database-backed store.
See [RUNTIME_V1_ACCEPTANCE_MATRIX.md](RUNTIME_V1_ACCEPTANCE_MATRIX.md) for the
honest Partial/Complete breakdown.
