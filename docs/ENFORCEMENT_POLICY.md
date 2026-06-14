# AgentLab Enforcement Policy

The Action Enforcement Gateway (v1.5, `app/runtime/enforcement.py`) is the
control point that stops risky actions **before execution**. Every important
runtime action becomes a proposal, is evaluated by a deterministic policy
registry, and resolves into an explainable decision.

## Action proposal → policy decision

1. An action becomes an **`ActionProposal`** (who/what/target — stored redacted
   and bounded) and emits `action.proposed`.
2. The **policy registry** (24 ordered rules) is evaluated against an
   `ActionContext` computed once: the actor agent, task flags, the v1.2
   path-safety verdict, and the v1.3 command-safety verdict. Rules are
   priority-sorted, the **first match decides**, and **every** match is recorded
   (`policy.rule.matched` per match, then `policy.evaluated`).
3. An **`ActionDecision`** records the verdict, all matched rules, a
   human-readable reason, redacted evidence, and a trust/risk snapshot, then
   emits the decision event.

Secrets are evaluated against the *raw* input (so the secret rule can fire) while
only the redacted form is persisted.

## Decisions

| Decision | Executes? | Event |
|---|---|---|
| `allow` / `allow_readonly` / `allow_sandbox_only` | ✅ yes | `enforcement.allowed` |
| `block` | ❌ no | `enforcement.blocked` |
| `require_human_approval` | ❌ halts | `enforcement.approval_required` |
| `reroute_to_verifier` | ❌ no | `enforcement.rerouted` |
| `retry_with_constraints` | ❌ no | `enforcement.retry_required` |
| `downgrade_permissions` | ❌ no | `enforcement.permissions_downgraded` |
| `quarantine_agent` | ❌ no | `enforcement.quarantine_triggered` |

Allowed actions execute between `action.started` and `action.completed`; the
underlying v1.2/v1.3 safety **re-runs** during execution (defense in depth).
Anything not allowed never runs the underlying operation. Unknown action types,
and any action no rule matched, are **blocked by default**.

## Default policies (priority order)

`block-unassignable-actor` (disabled/quarantined actor) → `block-secret-in-input`
→ `block-failed-validation` (a v1.8 validator already failed) → `block-path-escape`
→ `block-secret-file` → `block-unsafe-command` → `retry-missing-manifest` →
`approval-sensitive-command` → `approval-protected-action`
(auth/payment/deployment/db-migration/package-install) → `approval-sensitive-file`
→ `approval-high-risk-publish` → `quarantine-extreme-risk-actor` (risk ≥ 0.9) →
`reroute-high-risk-actor` (risk ≥ 0.7) → `reroute-unverified-research` →
`approval-flagged-task-result` → `reroute-flagged-task-result` →
`downgrade-suspicious-actor` → `allow-sandbox-command` → `allow-readonly-caution`
→ `allow-file-read` → `allow-file-write` → `allow-metadata-action` →
`block-unknown-action` → `default-block` (catch-all).

## How risky actions are stopped before execution

File write/delete/mkdir, command run, workflow start, and task-result recording
all route through `guarded_execute`: **propose → evaluate → (only if allowed)
execute**. A refusal raises before the underlying service is called, so the disk
is never touched and no process spawns. When a refusal matches what the v1.2/v1.3
layers would also have refused, the gateway emits the legacy
`sandbox.file.blocked` / `sandbox.command.blocked` audit events too, keeping the
audit streams complete. Refusals are presented as `400 blocked (<rule>): …` or,
for approval, `403 approval required (<rule>): … — approval <id> is waiting`.

## Reroute / downgrade / quarantine-triggered behavior

In v1.5 these were recorded events only. From later versions:
- **quarantine_agent** (and the approval quarantine resolution) applies **real
  quarantine** to a linked agent (v1.7) — see [HUMAN_APPROVAL.md](HUMAN_APPROVAL.md)
  and `app/runtime/quarantine.py`.
- **reroute_to_verifier** and **downgrade_permissions** remain **recorded
  decisions / intent**, not an autonomous reassignment or permission rewrite.
  This is the honest boundary in
  [RUNTIME_V1_ACCEPTANCE_MATRIX.md](RUNTIME_V1_ACCEPTANCE_MATRIX.md) (#11).

## Generic API

`POST /api/runtime/workspaces/{id}/actions/propose` evaluates any action and
records the decision but **never executes anything**. `GET /api/runtime/policies`
lists the registry; `GET …/enforcement/decisions` lists decisions.

## Limitations

Policy rules are **code-defined**, not user-editable. Sensitive-path detection is
token-based and deliberately conservative (a path segment containing "auth" or
"deploy" triggers approval — false positives accepted). The enforcement
validator tie-in (`block-failed-validation`) blocks actions a caller explicitly
tags `validation_failed`; validators do not auto-block unrelated future actions.
